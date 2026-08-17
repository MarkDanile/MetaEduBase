"""R1-S5 SCH-C Rebuild & Seeding 真实 PG 验收（stacked child）。

契约：Plan §R1-S5-B S5-B-1/2/3/5/6——G1/G2 drift → Option D quiesce →
rebuild/seeding + predecessor lineage。

反例映射（S5-B-9 实义行，每项具名 mutation）：
- 行 1/17 hold create→quiesce→release→rebuild 全序列 / active hold 不 eager rebuild
- 行 3 继承证据（unchanged erased → inherited acked seed + fence 零修改）
- 行 2/15 partial ACK 重开 / outcome_unknown 不重开
- 行 5 新增 owner pending
- 行 6 removed unresolved 不得丢失
- 行 7 case-E version 迁移（active fence）
- 行 8 并发 rebuild 单一 revision
- 行 9/25 seeding 回滚零残留
- 行 10 rebuild 后 coordinator 正向 completed（inherited ACK 计入全 acked）
- 行 13 quiesce 门禁（erasing 挡 rebuild）
- 行 18 restore interleave 零新行
- 行 23 removed completed owner 无行
- 行 30 seeded 缺行 → G4 conflict

边界：严守 Option D（erasing 只返回 QUIESCE）；不实现 SCH-D settlement；不新增
migration 043、不改 registry；不启用生产 wiring。
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from sqlalchemy import text

from app.composition.agent_erasure_registry import registry_snapshot
from app.composition.conversation_purge_scheduler import (
    ConversationPurgeScheduler,
)
from app.composition.purge_rebuild import (
    PurgeRebuildService,
    RebuildKind,
)
from app.composition.transactional_projection_coordinator import (
    TransactionalProjectionCoordinator,
    build_scan_providers,
)
from app.shared.schemas.canonical_json import canonical_digest

_OWNER_KEYS = [str(o["owner_key"]) for o in registry_snapshot()]
assert sorted(_OWNER_KEYS) == _OWNER_KEYS
_ACK = "e" * 64


# ---------------------------------------------------------------------------
# 种子 helpers
# ---------------------------------------------------------------------------


async def _seed_conversation(
    session, *, tenant_id: uuid.UUID | None = None, actor_state: str = "redacted"
) -> tuple[uuid.UUID, uuid.UUID]:
    tid = tenant_id or uuid.uuid4()
    cid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, "
            "creator_identity_digest, title, title_source, state, purge_after, "
            "purge_state, purge_revision, hold_revision, revision, created_at, "
            "updated_at) "
            "VALUES (:id, :tid, NULL, 'redacted', :digest, :identity, 't', "
            "'none', 'deleted', now() - interval '1 day', 'scheduled', 1, 0, "
            "1, now(), now())"
        ),
        {"id": cid, "tid": tid, "digest": "c" * 64, "identity": "d" * 64},
    )
    return tid, cid


async def _claim(session, tid, cid):
    return await ConversationPurgeScheduler(session).claim(
        tenant_id=tid,
        conversation_id=cid,
        retention_policy_snapshot={"conversation_recovery_days": 30},
    )


async def _rebuild(session, tid, cid):
    return await PurgeRebuildService(session).rebuild(
        tenant_id=tid,
        conversation_id=cid,
        retention_policy_snapshot={"conversation_recovery_days": 30},
    )


async def _g2_block(session, op_id) -> None:
    """模拟 coordinator G2 投影：operation blocked + blocked_hold_revision_changed。"""
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET "
            "state='blocked', failure_code='blocked_hold_revision_changed' "
            "WHERE id = :op"
        ),
        {"op": op_id},
    )


async def _set_cp(session, op_id, owner_key, *, state, reason=None, attempt=None):
    sets = ["state = :state"]
    params = {"op": op_id, "k": owner_key, "state": state}
    if state == "acked":
        sets.append("ack_digest = :ack, checkpoint_digest = :ack")
        params["ack"] = _ACK
        sets.append("reason_code = NULL")
    elif reason is not None:
        sets.append("reason_code = :reason")
        params["reason"] = reason
    else:
        sets.append("reason_code = NULL")
    if attempt is not None:
        sets.append("attempt = :attempt")
        params["attempt"] = attempt
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners SET "
            + ", ".join(sets)
            + " WHERE purge_operation_id = :op AND owner_key = :k"
        ),
        params,
    )


async def _seed_erased_fences(session, tid, cid, *, purge_revision: int = 1):
    ic = {"schema_version": 1, "sources": {}}
    ingress = canonical_digest(ic)
    for o in registry_snapshot():
        await session.execute(
            text(
                "INSERT INTO metaedu.agent_erasure_fences "
                "(tenant_id, conversation_id, owner_key, owner_version, state, "
                "purge_revision, hold_revision, ingress_checkpoint, "
                "ingress_digest, ack_digest, acked_at, revision, created_at, "
                "updated_at) VALUES (:tid, :cid, :o, 1, 'erased', :pr, 0, :ic, "
                ":ing, :ack, now(), 1, now(), now())"
            ),
            {
                "tid": tid, "cid": cid, "o": str(o["owner_key"]),
                "pr": purge_revision, "ic": json.dumps(ic, sort_keys=True),
                "ing": ingress, "ack": _ACK,
            },
        )


async def _ops(session, cid) -> list[dict]:
    rows = await session.execute(
        text(
            "SELECT id, purge_revision, state, failure_code, lease_epoch, "
            "lease_expires_at FROM metaedu.agent_conversation_purges "
            "WHERE conversation_id = :cid ORDER BY purge_revision"
        ),
        {"cid": cid},
    )
    return [dict(r._mapping) for r in rows]


async def _cp_rows(session, op_id) -> list[dict]:
    rows = await session.execute(
        text(
            "SELECT owner_key, state, reason_code, ack_digest, owner_version "
            "FROM metaedu.agent_conversation_purge_owners "
            "WHERE purge_operation_id = :op ORDER BY owner_key"
        ),
        {"op": op_id},
    )
    return [dict(r._mapping) for r in rows]


async def _fence_version(session, cid, owner_key) -> int:
    return (
        await session.execute(
            text(
                "SELECT owner_version FROM metaedu.agent_erasure_fences "
                "WHERE conversation_id = :cid AND owner_key = :k"
            ),
            {"cid": cid, "k": owner_key},
        )
    ).scalar_one()


# ---------------------------------------------------------------------------
# 核心测试
# ---------------------------------------------------------------------------


async def test_rebuild_g2_creates_new_revision_and_acquires_lease(
    db_session, session_factory
):
    """S5-B-9 行 1 部分：G2 blocked → rebuild → 新 revision + 新 operation +
    lease acquire 并入同事务（无新 op 无租约窗口）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    # 全 owner 重开域：blocked + erase_timeout（可证明未发送 → 义务重开）。
    for k in _OWNER_KEYS:
        await _set_cp(
            db_session, op1, k, state="blocked",
            reason="purge_blocked_by_external_erase_timeout",
        )
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT
    assert outcome.purge_revision == 2
    assert outcome.lease_epoch == 1, "rebuild 后 acquire lease 并入同事务"
    assert outcome.lease_expires_at is not None

    async with session_factory() as verify:
        ops = await _ops(verify, cid)
        assert [o["purge_revision"] for o in ops] == [1, 2]
        new_op = ops[1]
        assert new_op["lease_epoch"] == 1
        assert new_op["lease_expires_at"] is not None
        cps = await _cp_rows(verify, new_op["id"])
        assert len(cps) == len(_OWNER_KEYS)
        assert all(c["state"] == "pending" for c in cps), "重开义务 → pending"
        conv_pr = (
            await verify.execute(
                text(
                    "SELECT purge_revision FROM metaedu.agent_conversations "
                    "WHERE id = :cid"
                ),
                {"cid": cid},
            )
        ).scalar_one()
        assert conv_pr == 2, "rebuild 写回 conversation.purge_revision"


async def test_rebuild_inherited_acked_seed(db_session, session_factory):
    """S5-B-9 行 3：unchanged erased owner → inherited acked seed + fence 零修改
    （purge_revision 仍为旧值）+ lineage 六项全过。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="acked")
    await _seed_erased_fences(db_session, tid, cid, purge_revision=1)
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT

    async with session_factory() as verify:
        ops = await _ops(verify, cid)
        new_op = ops[1]
        cps = await _cp_rows(verify, new_op["id"])
        assert all(c["state"] == "acked" for c in cps), "inherited acked seed"
        assert all(c["ack_digest"] == _ACK for c in cps), "信任锚点复制"
        # fence 零修改：purge_revision 仍 1（继承不推进 fence token）。
        fence_pr = (
            await verify.execute(
                text(
                    "SELECT purge_revision FROM metaedu.agent_erasure_fences "
                    "WHERE conversation_id = :cid AND owner_key = :k"
                ),
                {"cid": cid, "k": _OWNER_KEYS[0]},
            )
        ).scalar_one()
        assert fence_pr == 1, "inherited ACK 不推进 fence purge_revision"


async def test_rebuild_outcome_unknown_carry(db_session, session_factory):
    """S5-B-9 行 15：outcome_unknown blocked → carried_blocked（不重开 pending，
    不二次 adapter 调用）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    for k in _OWNER_KEYS:
        await _set_cp(
            db_session, op1, k, state="blocked",
            reason="purge_blocked_by_external_outcome_unknown",
        )
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT
    async with session_factory() as verify:
        new_op = (await _ops(verify, cid))[1]
        cps = await _cp_rows(verify, new_op["id"])
        assert all(c["state"] == "blocked" for c in cps), "outcome_unknown carry"
        assert all(
            c["reason_code"] == "purge_blocked_by_external_outcome_unknown"
            for c in cps
        ), "reason 保留"


async def test_rebuild_added_owner_pending(db_session, session_factory):
    """S5-B-9 行 5：新增 owner → pending（新义务不丢失）。

    （registry 为 code-defined 不可变，本测试用「predecessor snapshot 缺 owner」
    模拟——通过直接改写 predecessor 的 registry_snapshot 制造 added 形态。）"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    # 把 predecessor 的 registry_snapshot 删掉第一个 owner（模拟「旧 snapshot 缺
    # 该 owner，当前 registry 有」→ added）。
    import json as _json

    from app.composition.agent_erasure_registry import snapshot_digest

    old_snapshot = [o for o in registry_snapshot() if o["owner_key"] != _OWNER_KEYS[0]]
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET "
            "registry_snapshot = :snap, registry_digest = :digest WHERE id = :op"
        ),
        {"snap": _json.dumps(old_snapshot), "digest": snapshot_digest(old_snapshot), "op": op1},
    )
    for k in _OWNER_KEYS[1:]:
        await _set_cp(
            db_session, op1, k, state="blocked",
            reason="purge_blocked_by_external_erase_timeout",
        )
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT
    async with session_factory() as verify:
        new_op = (await _ops(verify, cid))[1]
        cps = {c["owner_key"]: c for c in await _cp_rows(verify, new_op["id"])}
        assert cps[_OWNER_KEYS[0]]["state"] == "pending", "added owner → pending"
        assert len(cps) == len(_OWNER_KEYS)


async def test_rebuild_removed_unfinished_fail_closed(db_session, session_factory):
    """S5-B-9 行 6：removed owner 旧义务未完成 → rebuild fail closed（零新行，
    旧 operation 不变）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    # 把 predecessor snapshot 多塞一个「已移除 owner」（旧 snapshot 有、当前无）
    # 且其 checkpoint 未完成（pending）→ removed unfinished。
    import json as _json

    from app.composition.agent_erasure_registry import snapshot_digest

    removed_entry = {
        "owner_key": "removed.owner.v9",
        "owner_version": 1,
        "capability_digest": "f" * 64,
    }
    old_snapshot = registry_snapshot() + [removed_entry]
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET "
            "registry_snapshot = :snap, registry_digest = :digest WHERE id = :op"
        ),
        {"snap": _json.dumps(old_snapshot), "digest": snapshot_digest(old_snapshot), "op": op1},
    )
    # removed owner 的 checkpoint：pending（未完成）。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversation_purge_owners "
            "(id, tenant_id, purge_operation_id, owner_key, owner_version, "
            "capability_digest, state, attempt, created_at, updated_at) "
            "VALUES (:id, :tid, :op, 'removed.owner.v9', 1, :cap, 'pending', 0, "
            "now(), now())"
        ),
        {"id": uuid.uuid4(), "tid": tid, "op": op1, "cap": "f" * 64},
    )
    await db_session.commit()

    with pytest.raises(ValueError, match="removed owner with unfinished"):
        await _rebuild(db_session, tid, cid)
    await db_session.rollback()
    async with session_factory() as verify:
        ops = await _ops(verify, cid)
        assert len(ops) == 1, "removed unfinished → 零新行"
        assert ops[0]["state"] == "blocked", "旧 operation 不变"


async def test_rebuild_quiesce_erasing(db_session, session_factory):
    """S5-B-9 行 13：quiesce 门禁——任一 checkpoint erasing → QUIESCE 零推进。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    await _set_cp(db_session, op1, _OWNER_KEYS[0], state="erasing")
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.QUIESCE
    async with session_factory() as verify:
        ops = await _ops(verify, cid)
        assert len(ops) == 1, "erasing quiesce 零新 operation"
        assert ops[0]["purge_revision"] == 1, "未推进 revision"


async def test_rebuild_restore_active_zero_rows(db_session, session_factory):
    """S5-B-9 行 18：restore interleave → Conversation 锁内 DELETED 门禁 → 零新行。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    # restore 落库：state=active。
    await db_session.execute(
        text("UPDATE metaedu.agent_conversations SET state='active' WHERE id=:cid"),
        {"cid": cid},
    )
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.NOT_DUE
    async with session_factory() as verify:
        assert len(await _ops(verify, cid)) == 1, "restore → 零新行"


async def test_rebuild_seeding_lineage_fail_rolls_back(db_session, session_factory):
    """S5-B-9 行 4/25：seeding 期 lineage 失败（acked 但 fence 非 erased）→ 整
    事务回滚（零新 operation、零新 checkpoint、旧 operation 不变）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    # 全 owner acked，但 fence 是 active（非 erased）→ lineage 矛盾。
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="acked")
    await db_session.commit()

    with pytest.raises(ValueError, match="lineage stage-1"):
        await _rebuild(db_session, tid, cid)
    await db_session.rollback()
    async with session_factory() as verify:
        ops = await _ops(verify, cid)
        assert len(ops) == 1, "lineage 失败零新 operation"


async def test_rebuild_concurrent_single_revision(session_factory):
    """S5-B-9 行 8：双 scheduler 并发 rebuild → Conversation 锁串行，只一个
    新 revision，后到者幂等返回。"""
    async with session_factory() as seed:
        tid, cid = await _seed_conversation(seed)
        out = await _claim(seed, tid, cid)
        op1 = out.token.purge_operation_id
        await _g2_block(seed, op1)
        for k in _OWNER_KEYS:
            await _set_cp(
                seed, op1, k, state="blocked",
                reason="purge_blocked_by_external_erase_timeout",
            )
        await seed.commit()

    async def _one():
        async with session_factory() as s:
            r = await _rebuild(s, tid, cid)
            await s.commit()
            return r

    r1, r2 = await asyncio.wait_for(
        asyncio.gather(_one(), _one()), timeout=15.0
    )
    kinds = sorted((r1.kind.value, r2.kind.value))
    assert kinds == ["idempotent", "rebuilt"], f"单一 revision，实际 {kinds}"

    async with session_factory() as verify:
        ops = await _ops(verify, cid)
        assert len(ops) == 2, "只产生一个新 revision"


async def test_rebuild_idempotent_no_drift(db_session, session_factory):
    """S5-B-6：无 drift（top 非 G1/G2-blocked）→ IDEMPOTENT 返回既有 rebuild。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.IDEMPOTENT
    assert outcome.purge_operation_id == op1


async def test_coordinator_inherited_ack_counts_completed(
    db_session, session_factory
):
    """S5-B-9 行 10：rebuild 后 coordinator 聚合——inherited acked 计入全 acked
    → completed（lineage 接入 coordinator，替换 no-predecessor 路径）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="acked")
    await _seed_erased_fences(db_session, tid, cid, purge_revision=1)
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT
    new_op = outcome.purge_operation_id

    async with session_factory() as s:
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid, purge_operation_id=new_op
        )
        await s.commit()

    async with session_factory() as verify:
        state = (
            await verify.execute(
                text(
                    "SELECT state FROM metaedu.agent_conversation_purges "
                    "WHERE id = :op"
                ),
                {"op": new_op},
            )
        ).scalar_one()
        assert state == "completed", "inherited acked 计入全 acked → completed"


async def test_sch3_hold_create_quiesce_release_rebuild_full_sequence(
    db_session, session_factory
):
    """SCH-3 / S5-B-9 行 1：purge 中 create hold → G2 blocked → quiesce →
    release → rebuild（新 revision + 新 snapshot 载当前 hold_revision）。"""
    from app.contexts.agent_workspace.infrastructure.erasure_repository import (
        AgentErasureRepository,
    )

    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    # create hold → hold_revision 0→1（I1 producer）。
    repo = AgentErasureRepository(db_session)
    hold = await repo.create_legal_hold(
        tenant_id=tid, conversation_id=cid, reason_code="litigation",
        purpose="hold", actor_id=uuid.uuid4(),
    )
    await db_session.commit()
    # coordinator 聚合 → G2 blocked。
    async with session_factory() as s:
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op1
        )
        await s.commit()
    # release hold → hold_revision 1→2。
    await repo.release_legal_hold(
        tenant_id=tid, conversation_id=cid, hold_id=hold.id,
        expected_revision=1, released_by=uuid.uuid4(),
    )
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT
    assert outcome.purge_revision == 2

    async with session_factory() as verify:
        ops = await _ops(verify, cid)
        assert [o["purge_revision"] for o in ops] == [1, 2]
        # 新 snapshot 载当前 hold_revision=2。
        hold_snap = (
            await verify.execute(
                text(
                    "SELECT hold_revision_snapshot FROM "
                    "metaedu.agent_conversation_purges WHERE id = :op"
                ),
                {"op": outcome.purge_operation_id},
            )
        ).scalar_one()
        assert hold_snap == 2, "新 snapshot 载当前 hold_revision"


async def test_seeded_missing_row_g4_conflict(db_session, session_factory):
    """S5-B-9 行 30：seeded（inherited_acked）缺行 → lineage conflict → G4
    blocked + purge_owner_ack_conflict（不落 running、不重建 pending）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="acked")
    await _seed_erased_fences(db_session, tid, cid, purge_revision=1)
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    new_op = outcome.purge_operation_id
    # 删除一个 seeded（inherited_acked）checkpoint → 聚合应 G4。
    async with session_factory() as s:
        await s.execute(
            text(
                "DELETE FROM metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id = :op AND owner_key = :k"
            ),
            {"op": new_op, "k": _OWNER_KEYS[0]},
        )
        await s.commit()

    async with session_factory() as s:
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid, purge_operation_id=new_op
        )
        await s.commit()

    async with session_factory() as verify:
        state = (
            await verify.execute(
                text(
                    "SELECT state, failure_code FROM "
                    "metaedu.agent_conversation_purges WHERE id = :op"
                ),
                {"op": new_op},
            )
        ).one()
        assert state.state == "blocked"
        assert state.failure_code == "purge_owner_ack_conflict", "G4 conflict"


async def test_rebuild_forged_ack_digest_rolls_back(db_session, session_factory):
    """S5-B-9 行 4：inherited ACK 但 checkpoint.ack_digest != fence.ack_digest
    （信任锚点不一致）→ lineage 六项 5 失败 → 整事务回滚。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="acked")
    # erased fence 但 ack_digest 用不同值（"d"*64）→ 信任锚点不一致。
    await _seed_erased_fences(db_session, tid, cid, purge_revision=1)
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET ack_digest = :bad "
            "WHERE conversation_id = :cid"
        ),
        {"bad": "d" * 64, "cid": cid},
    )
    await db_session.commit()

    with pytest.raises(ValueError, match="lineage stage-1"):
        await _rebuild(db_session, tid, cid)
    await db_session.rollback()
    async with session_factory() as verify:
        assert len(await _ops(verify, cid)) == 1, "伪造 ack_digest 零新行"
