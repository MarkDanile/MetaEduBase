"""R1-S5 SCH-C Rebuild & Seeding 真实 PG 验收（stacked child）。

契约：Plan §R1-S5-B S5-B-1/2/3/5/6——G1/G2 drift → Option D quiesce →
rebuild/seeding + predecessor lineage。

反例映射（S5-B-9 实义 29 行，逐行具名 mutation）：
- 行 2/7/9/11/12/16/17/22/26/27/28/31/32：反例矩阵完整性收口批次补真实 PG 判别
  （行 21 = I2 已冻结 core family-B 门禁，映射 test_s5i2_six_owner_shared_write_removal
  两测试，不重复建）。REQ-047 不承接 SCH-C 当前验收缺口。
- 行 23/29/33：行 23 补 removed-completed 判别；行 29/33 为 mutation 判别行
  （阶段 1/2 边界 + seeded 副本信任 + expected-kind 公式），由对应测试 + 具名
  mutation 承载。

边界：严守 Option D（erasing 只返回 QUIESCE）；不实现 SCH-D settlement；不新增
migration 043、不改 registry；不启用生产 wiring。不转 Ready、不评分、不合并。
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


async def _seed_erased_fence(
    session, tid, cid, owner_key, *, purge_revision: int = 1
) -> None:
    ic = {"schema_version": 1, "sources": {}}
    ingress = canonical_digest(ic)
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
            "tid": tid, "cid": cid, "o": owner_key,
            "pr": purge_revision, "ic": json.dumps(ic, sort_keys=True),
            "ing": ingress, "ack": _ACK,
        },
    )


async def _seed_erased_fences(session, tid, cid, *, purge_revision: int = 1):
    for o in registry_snapshot():
        await _seed_erased_fence(
            session, tid, cid, str(o["owner_key"]), purge_revision=purge_revision
        )


class _NoopSettlement:
    """行 31 SCH-B retry 白名单判别用的零动作 settlement port（无 erasing 时不被调）。"""

    async def closeout_erasing(self, **kwargs) -> None:
        return None

    async def converge_failed_fence(self, **kwargs) -> None:
        return None


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


async def test_rebuild_blocked_null_reason_rolls_back(db_session, session_factory):
    """族 A 返修：blocked + NULL reason 不得落入 pending 重开（dirty-data fail
    closed 整事务回滚）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="blocked", reason=None)
    await db_session.commit()

    with pytest.raises(ValueError, match="lineage stage-1"):
        await _rebuild(db_session, tid, cid)
    await db_session.rollback()
    async with session_factory() as verify:
        assert len(await _ops(verify, cid)) == 1, "NULL reason 零新行"


async def test_rebuild_re_added_missing_cp_reopens(db_session, session_factory):
    """族 D 返修：re-added（有历史 fence + predecessor 缺 checkpoint + fence 非
    erased）→ 义务重开 pending（缺行不视为已完成）。"""
    import json as _json

    from app.composition.agent_erasure_registry import snapshot_digest

    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    # predecessor snapshot 缺 workspace.core.v1（模拟该 owner 曾移除、现 re-added）
    old_snapshot = [o for o in registry_snapshot() if o["owner_key"] != _OWNER_KEYS[0]]
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET "
            "registry_snapshot = :snap, registry_digest = :digest WHERE id = :op"
        ),
        {"snap": _json.dumps(old_snapshot), "digest": snapshot_digest(old_snapshot), "op": op1},
    )
    # 其余 owner 重开域 + re-added owner（_OWNER_KEYS[0]）有历史 fence（非 erased）
    # 但 predecessor 无其 checkpoint（claim 建行后删除该 owner 行）→ 命中
    # _re_added_lineage「cp 缺 + 非 erased → pending」分支。
    for k in _OWNER_KEYS[1:]:
        await _set_cp(
            db_session, op1, k, state="blocked",
            reason="purge_blocked_by_external_erase_timeout",
        )
    await db_session.execute(
        text(
            "DELETE FROM metaedu.agent_conversation_purge_owners "
            "WHERE purge_operation_id = :op AND owner_key = :k"
        ),
        {"op": op1, "k": _OWNER_KEYS[0]},
    )
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "revision, created_at, updated_at) VALUES (:tid, :cid, :k, 1, "
            "'active', 1, 0, :ic, :ing, 1, now(), now())"
        ),
        {
            "tid": tid, "cid": cid, "k": _OWNER_KEYS[0],
            "ic": json.dumps({"schema_version": 1, "sources": {}}, sort_keys=True),
            "ing": canonical_digest({"schema_version": 1, "sources": {}}),
        },
    )
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT
    async with session_factory() as verify:
        new_op = (await _ops(verify, cid))[1]
        cps = {c["owner_key"]: c for c in await _cp_rows(verify, new_op["id"])}
        assert cps[_OWNER_KEYS[0]]["state"] == "pending", "re-added 缺 cp 重开 pending"


async def test_rebuild_blocked_erased_fence_conflict(db_session, session_factory):
    """P2 返修：blocked × erased fence（S5-C-1 ACK-lost 输入态）→ dirty-data
    fail closed（不可按 reopen 处理）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    for k in _OWNER_KEYS:
        await _set_cp(
            db_session, op1, k, state="blocked",
            reason="purge_blocked_by_external_erase_timeout",
        )
    await _seed_erased_fences(db_session, tid, cid, purge_revision=1)
    await db_session.commit()

    with pytest.raises(ValueError, match="lineage stage-1"):
        await _rebuild(db_session, tid, cid)
    await db_session.rollback()
    async with session_factory() as verify:
        assert len(await _ops(verify, cid)) == 1, "ACK-lost 零新行"


async def test_rebuild_case_e_blocked_fence_carry(db_session, session_factory):
    """族 B 返修：case-E version-changed + blocked fence（carry reason）→
    carried_blocked（非 active fence 不迁移、不整事务回滚）。"""
    import json as _json

    from app.composition.agent_erasure_registry import snapshot_digest

    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    # predecessor snapshot 把 workspace.core.v1 的 version 改为 2（模拟 registry 升级）
    # → current registry version=1 → version_changed。
    old_snapshot = [
        dict(o, owner_version=2) if o["owner_key"] == _OWNER_KEYS[0] else o
        for o in registry_snapshot()
    ]
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET "
            "registry_snapshot = :snap, registry_digest = :digest WHERE id = :op"
        ),
        {"snap": _json.dumps(old_snapshot), "digest": snapshot_digest(old_snapshot), "op": op1},
    )
    # workspace.core.v1 checkpoint blocked + carry reason（outcome_unknown）。
    await _set_cp(
        db_session, op1, _OWNER_KEYS[0], state="blocked",
        reason="purge_blocked_by_external_outcome_unknown",
    )
    for k in _OWNER_KEYS[1:]:
        await _set_cp(
            db_session, op1, k, state="blocked",
            reason="purge_blocked_by_external_erase_timeout",
        )
    # workspace.core.v1 历史 fence blocked（非 active）+ owner_version=2。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "revision, created_at, updated_at) VALUES (:tid, :cid, :k, 2, "
            "'blocked', 1, 0, :ic, :ing, 1, now(), now())"
        ),
        {
            "tid": tid, "cid": cid, "k": _OWNER_KEYS[0],
            "ic": json.dumps({"schema_version": 1, "sources": {}}, sort_keys=True),
            "ing": canonical_digest({"schema_version": 1, "sources": {}}),
        },
    )
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT, "case-E blocked fence 不应回滚"
    async with session_factory() as verify:
        new_op = (await _ops(verify, cid))[1]
        cps = {c["owner_key"]: c for c in await _cp_rows(verify, new_op["id"])}
        assert cps[_OWNER_KEYS[0]]["state"] == "blocked", "version-changed carry"
        assert (
            cps[_OWNER_KEYS[0]]["reason_code"]
            == "purge_blocked_by_external_outcome_unknown"
        )


async def test_rebuild_re_added_erased_fence_conflict(db_session, session_factory):
    """族 D 返修：re-added + 历史 fence erased + predecessor 缺 checkpoint →
    锚点缺失（无法验证「历史 acked」item 2）→ conflict 整事务回滚。"""
    import json as _json

    from app.composition.agent_erasure_registry import snapshot_digest

    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
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
    await db_session.execute(
        text(
            "DELETE FROM metaedu.agent_conversation_purge_owners "
            "WHERE purge_operation_id = :op AND owner_key = :k"
        ),
        {"op": op1, "k": _OWNER_KEYS[0]},
    )
    # _OWNER_KEYS[0] 历史 fence erased（锚点存在但 predecessor 缺 cp）。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "ack_digest, acked_at, revision, created_at, updated_at) VALUES "
            "(:tid, :cid, :k, 1, 'erased', 1, 0, :ic, :ing, :ack, now(), 1, "
            "now(), now())"
        ),
        {
            "tid": tid, "cid": cid, "k": _OWNER_KEYS[0],
            "ic": json.dumps({"schema_version": 1, "sources": {}}, sort_keys=True),
            "ing": canonical_digest({"schema_version": 1, "sources": {}}),
            "ack": _ACK,
        },
    )
    await db_session.commit()

    with pytest.raises(ValueError, match="lineage stage-1"):
        await _rebuild(db_session, tid, cid)
    await db_session.rollback()
    async with session_factory() as verify:
        assert len(await _ops(verify, cid)) == 1, "re-added 锚点缺失零新行"


# ---------------------------------------------------------------------------
# 反例矩阵完整性收口批次（S5-B-9 实义 29 行补齐；REQ-047 不承接 SCH-C 当前验收缺口）
# ---------------------------------------------------------------------------


async def test_rebuild_partial_ack_mixed_obligations(db_session, session_factory):
    """S5-B-9 行 2：partial ACK 混合 obligation——acked+erased 继承 acked；
    reopenable blocked 重开 pending；outcome_unknown blocked carry blocked；
    partial 不 completed。变异「未完成 owner 被 seed 为 acked」→红。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    # owner[1] reopenable blocked → 重开 pending；owner[2] outcome_unknown → carry。
    # 先设 blocked（避免 acked 残留 ack_digest 触发 ck_agent_purge_owner_ack）。
    await _set_cp(
        db_session, op1, _OWNER_KEYS[1], state="blocked",
        reason="purge_blocked_by_external_erase_timeout",
    )
    await _set_cp(
        db_session, op1, _OWNER_KEYS[2], state="blocked",
        reason="purge_blocked_by_external_outcome_unknown",
    )
    for k in _OWNER_KEYS:
        if k not in (_OWNER_KEYS[1], _OWNER_KEYS[2]):
            await _set_cp(db_session, op1, k, state="acked")
    await _seed_erased_fences(db_session, tid, cid, purge_revision=1)
    # owner[1]/[2] 的 fence 改 active（非 erased）——reopen/carry 判别前提。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET state='active', "
            "ack_digest=NULL, acked_at=NULL WHERE conversation_id = :cid "
            "AND owner_key IN (:a, :b)"
        ),
        {"cid": cid, "a": _OWNER_KEYS[1], "b": _OWNER_KEYS[2]},
    )
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT
    async with session_factory() as verify:
        new_op = (await _ops(verify, cid))[1]
        cps = {c["owner_key"]: c for c in await _cp_rows(verify, new_op["id"])}
        assert cps[_OWNER_KEYS[0]]["state"] == "acked", "acked+erased 继承 acked"
        assert cps[_OWNER_KEYS[1]]["state"] == "pending", "reopenable 重开 pending"
        assert cps[_OWNER_KEYS[2]]["state"] == "blocked", "unknown carry blocked"
        assert (
            cps[_OWNER_KEYS[2]]["reason_code"]
            == "purge_blocked_by_external_outcome_unknown"
        ), "unknown 不被重开 pending（reason 保留）"
        assert all(
            c["state"] == "acked"
            for k, c in cps.items()
            if k not in (_OWNER_KEYS[1], _OWNER_KEYS[2])
        ), "其余 owner 继承 acked"


async def test_rebuild_case_e_active_fence_migrates(db_session, session_factory):
    """S5-B-9 行 7（active 分支）：version-changed + active fence → 义务重开
    pending + fence.owner_version 迁移对齐当前 registry 版本（1）。变异
    「purge-path/erased fence 也被 version bump 或 lineage seed」→红。

    （registry 为 code-defined 不可变，用「predecessor snapshot 版本漂移」模拟
    case-E——旧 snapshot version=2、当前 registry version=1；迁移把 fence 对齐
    当前 registry 版本。）"""
    import json as _json

    from app.composition.agent_erasure_registry import snapshot_digest

    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    old_snapshot = [
        dict(o, owner_version=2) if o["owner_key"] == _OWNER_KEYS[0] else o
        for o in registry_snapshot()
    ]
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET "
            "registry_snapshot = :snap, registry_digest = :digest WHERE id = :op"
        ),
        {"snap": _json.dumps(old_snapshot), "digest": snapshot_digest(old_snapshot), "op": op1},
    )
    await _set_cp(
        db_session, op1, _OWNER_KEYS[0], state="blocked",
        reason="purge_blocked_by_external_erase_timeout",
    )
    # 历史 fence active（owner_version=2，与旧 snapshot 一致）。
    ic = {"schema_version": 1, "sources": {}}
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "revision, created_at, updated_at) VALUES (:tid, :cid, :k, 2, "
            "'active', 1, 0, :ic, :ing, 1, now(), now())"
        ),
        {
            "tid": tid, "cid": cid, "k": _OWNER_KEYS[0],
            "ic": json.dumps(ic, sort_keys=True), "ing": canonical_digest(ic),
        },
    )
    for k in _OWNER_KEYS[1:]:
        await _set_cp(
            db_session, op1, k, state="blocked",
            reason="purge_blocked_by_external_erase_timeout",
        )
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT, "case-E active fence 不回滚"
    async with session_factory() as verify:
        new_op = (await _ops(verify, cid))[1]
        cps = {c["owner_key"]: c for c in await _cp_rows(verify, new_op["id"])}
        assert cps[_OWNER_KEYS[0]]["state"] == "pending", "case-E active → 义务重开"
        assert (
            await _fence_version(verify, cid, _OWNER_KEYS[0]) == 1
        ), "active fence owner_version 迁移对齐当前 registry"


async def test_rebuild_case_e_erased_fence_fail_closed(db_session, session_factory):
    """S5-B-9 行 7（erased 分支）：version-changed + erased fence → rebuild fail
    closed（整事务回滚，零新行）。变异「purge-path/erased fence 也被 version bump
    或 lineage seed」→红。"""
    import json as _json

    from app.composition.agent_erasure_registry import snapshot_digest

    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    old_snapshot = [
        dict(o, owner_version=2) if o["owner_key"] == _OWNER_KEYS[0] else o
        for o in registry_snapshot()
    ]
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET "
            "registry_snapshot = :snap, registry_digest = :digest WHERE id = :op"
        ),
        {"snap": _json.dumps(old_snapshot), "digest": snapshot_digest(old_snapshot), "op": op1},
    )
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="acked")
    await _seed_erased_fences(db_session, tid, cid, purge_revision=1)
    await db_session.commit()

    with pytest.raises(ValueError, match="lineage stage-1"):
        await _rebuild(db_session, tid, cid)
    await db_session.rollback()
    async with session_factory() as verify:
        assert len(await _ops(verify, cid)) == 1, "case-E erased fence 零新行"


async def test_rebuild_seeding_crash_atomic_rollback(db_session, session_factory):
    """S5-B-9 行 9：seeding 事务中途崩溃/回滚 → 零半套 checkpoint（旧 op 完整
    保留，零孤儿 seed 行），重放得同一结果。变异「分批提交 seed」→红（部分
    seed 已提交残留）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="acked")
    await _seed_erased_fences(db_session, tid, cid, purge_revision=1)
    await db_session.commit()

    # 崩溃模拟：rebuild 单事务内已写全 seed 但未提交 → 进程崩溃（服务端回滚）。
    async with session_factory() as crash:
        await _rebuild(crash, tid, cid)
        await crash.rollback()

    async with session_factory() as verify:
        ops = await _ops(verify, cid)
        assert len(ops) == 1, "崩溃后零新 operation"
        assert ops[0]["state"] == "blocked", "旧 operation 完整保留"
        total_cp = (
            await verify.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_conversation_purge_owners "
                    "WHERE tenant_id = :t"
                ),
                {"t": tid},
            )
        ).scalar_one()
        assert total_cp == len(_OWNER_KEYS), "零半套 checkpoint（无孤儿 seed 行）"

    # 重放得同一结果：revision 2 + 全 owner seeded。
    async with session_factory() as replay:
        outcome = await _rebuild(replay, tid, cid)
        await replay.commit()
    assert outcome.kind is RebuildKind.REBUILT
    assert outcome.purge_revision == 2
    async with session_factory() as verify:
        ops = await _ops(verify, cid)
        assert len(ops) == 2, "重放产生同一 revision 链"
        cps = await _cp_rows(verify, ops[1]["id"])
        assert len(cps) == len(_OWNER_KEYS)


async def test_rebuild_double_drift_chain(db_session, session_factory):
    """S5-B-9 行 11：二次 drift/rebuild——op2 再次 G2-block → 又一次 rebuild
    （新 revision 3），op1/op2 immutable blocked。变异「对已 superseded op 继续
    写（revision 不复用）」→红。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    for k in _OWNER_KEYS:
        await _set_cp(
            db_session, op1, k, state="blocked",
            reason="purge_blocked_by_external_erase_timeout",
        )
    await db_session.commit()

    first = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert first.kind is RebuildKind.REBUILT
    op2 = first.purge_operation_id
    # 二次 drift：op2 再 G2-block → 又一次 rebuild。
    await _g2_block(db_session, op2)
    await db_session.commit()

    second = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert second.kind is RebuildKind.REBUILT
    assert second.purge_revision == 3

    async with session_factory() as verify:
        ops = await _ops(verify, cid)
        assert [o["purge_revision"] for o in ops] == [1, 2, 3], "二次 rebuild 链"
        assert ops[0]["state"] == "blocked" and ops[1]["state"] == "blocked"
        assert ops[2]["lease_epoch"] == 1
        conv_pr = (
            await verify.execute(
                text(
                    "SELECT purge_revision FROM metaedu.agent_conversations "
                    "WHERE id = :cid"
                ),
                {"cid": cid},
            )
        ).scalar_one()
        assert conv_pr == 3, "写回推进到 3"


async def test_rebuild_cross_tenant_predecessor_forgery(db_session, session_factory):
    """S5-B-9 行 12：cross-tenant predecessor 伪造——op1 的 checkpoint 行 tenant_id
    被篡改为 tenant B（DB 篡改注入，replica 模式绕 FK）→ lineage 定位按同
    (tenant, conversation) 强制，跨域伪造 fail closed（零写）。变异「lineage 定位
    去掉 tenant 维度」→红。"""
    tid_a, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid_a, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="acked")
    await _seed_erased_fences(db_session, tid_a, cid, purge_revision=1)
    await db_session.commit()
    # 跨域伪造：把 op1 的 checkpoint 行 tenant_id 改为 tenant B（模拟 tenant B 的
    # predecessor 证据）——lineage 定位按 (tenant, conversation) 强制。
    tid_b = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(text("SET LOCAL session_replication_role = replica"))
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners SET tenant_id = :tb "
                "WHERE purge_operation_id = :op"
            ),
            {"tb": tid_b, "op": op1},
        )
        await s.commit()

    with pytest.raises(ValueError, match="lineage stage-1"):
        await _rebuild(db_session, tid_a, cid)
    await db_session.rollback()
    async with session_factory() as verify:
        assert len(await _ops(verify, cid)) == 1, "跨域伪造零新行"


async def test_rebuild_re_added_erased_native_anchor(db_session, session_factory):
    """S5-B-9 行 16（正向）：re-added（predecessor snapshot 缺 owner）+ 历史
    fence erased + 锚点（fence.ack_digest）与 predecessor checkpoint acked 一致
    → lineage seed acked（不建 pending 撞 terminal fence）。变异「按新增建
    pending」→红。"""
    import json as _json

    from app.composition.agent_erasure_registry import snapshot_digest

    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    old_snapshot = [o for o in registry_snapshot() if o["owner_key"] != _OWNER_KEYS[0]]
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET "
            "registry_snapshot = :snap, registry_digest = :digest WHERE id = :op"
        ),
        {"snap": _json.dumps(old_snapshot), "digest": snapshot_digest(old_snapshot), "op": op1},
    )
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="acked")
    await _seed_erased_fences(db_session, tid, cid, purge_revision=1)
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT
    async with session_factory() as verify:
        new_op = (await _ops(verify, cid))[1]
        cps = {c["owner_key"]: c for c in await _cp_rows(verify, new_op["id"])}
        assert cps[_OWNER_KEYS[0]]["state"] == "acked", "re-added + erased 锚点 → seed acked"
        assert cps[_OWNER_KEYS[0]]["ack_digest"] == _ACK, "锚点定位复制"
        assert len(cps) == len(_OWNER_KEYS)


async def test_rebuild_removed_completed_skips(db_session, session_factory):
    """S5-B-9 行 23：removed owner 旧义务已 acked/erased → rebuild 继续、无该
    owner 行（义务已清偿，不 seed 残留行）。变异「removed completed owner 也
    seed 一行」→红。"""
    import json as _json

    from app.composition.agent_erasure_registry import snapshot_digest

    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    # predecessor snapshot 多一个已移除 owner（旧有、当前无），其义务已完成。
    removed_entry = {
        "owner_key": "removed.owner.v9", "owner_version": 1,
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
    # removed owner 的 checkpoint acked + fence erased（义务清偿）。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversation_purge_owners "
            "(id, tenant_id, purge_operation_id, owner_key, owner_version, "
            "capability_digest, state, attempt, ack_digest, checkpoint_digest, "
            "created_at, updated_at) VALUES (:id, :tid, :op, 'removed.owner.v9', "
            "1, :cap, 'acked', 0, :ack, :ack, now(), now())"
        ),
        {"id": uuid.uuid4(), "tid": tid, "op": op1, "cap": "f" * 64, "ack": _ACK},
    )
    ic = {"schema_version": 1, "sources": {}}
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "ack_digest, acked_at, revision, created_at, updated_at) VALUES "
            "(:tid, :cid, 'removed.owner.v9', 1, 'erased', 1, 0, :ic, :ing, "
            ":ack, now(), 1, now(), now())"
        ),
        {
            "tid": tid, "cid": cid,
            "ic": json.dumps(ic, sort_keys=True), "ing": canonical_digest(ic),
            "ack": _ACK,
        },
    )
    for k in _OWNER_KEYS:
        await _set_cp(
            db_session, op1, k, state="blocked",
            reason="purge_blocked_by_external_erase_timeout",
        )
    await db_session.commit()

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT, "removed completed 不拦 rebuild"
    async with session_factory() as verify:
        new_op = (await _ops(verify, cid))[1]
        cps = await _cp_rows(verify, new_op["id"])
        keys = {c["owner_key"] for c in cps}
        assert "removed.owner.v9" not in keys, "removed completed 不 seed 一行"
        assert len(cps) == len(_OWNER_KEYS)


async def test_rebuild_active_hold_defers(db_session, session_factory):
    """S5-B-9 行 17：active hold 期间不 eager rebuild——G2 命中 + hold 仍 active
    → HOLD_GATED 零新行（不产生全 pending 中间 op）；release 后一次 rebuild。
    变异「active hold 期间 eager rebuild」→红。"""
    from app.contexts.agent_workspace.infrastructure.erasure_repository import (
        AgentErasureRepository,
    )

    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    repo = AgentErasureRepository(db_session)
    hold = await repo.create_legal_hold(
        tenant_id=tid, conversation_id=cid, reason_code="litigation",
        purpose="hold", actor_id=uuid.uuid4(),
    )
    await db_session.commit()
    await _g2_block(db_session, op1)
    for k in _OWNER_KEYS:
        await _set_cp(
            db_session, op1, k, state="blocked",
            reason="purge_blocked_by_external_erase_timeout",
        )
    await db_session.commit()

    # active hold → HOLD_GATED 零新行。
    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.HOLD_GATED, "active hold 期间 rebuild 延迟"
    async with session_factory() as verify:
        assert len(await _ops(verify, cid)) == 1, "active hold 不产生中间 op"

    # release → 一次 rebuild。
    await repo.release_legal_hold(
        tenant_id=tid, conversation_id=cid, hold_id=hold.id,
        expected_revision=1, released_by=uuid.uuid4(),
    )
    await db_session.commit()
    outcome2 = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome2.kind is RebuildKind.REBUILT
    async with session_factory() as verify:
        assert len(await _ops(verify, cid)) == 2, "release 后一次 rebuild"


async def test_coordinator_double_chain_tamper_g4(db_session, session_factory):
    """S5-B-9 行 22：双深链伪造（lineage item 5）——篡改中间 seeded checkpoint
    N+1（非 fence）后 N+2 聚合 → N+2 lineage 重验失败（N+1.ack_digest !=
    fence.ack_digest）→ G4（blocked + purge_owner_ack_conflict；checkpoint 零
    修改；不回滚已提交 N+2）。变异「信任 seeded 副本不逐跳重验」→红。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    # op1 全 acked + erased fence → op2 seeded acked（可被篡改的锚点行）。
    for k in _OWNER_KEYS:
        await _set_cp(db_session, op1, k, state="acked")
    await _seed_erased_fences(db_session, tid, cid, purge_revision=1)
    await db_session.commit()
    first = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert first.kind is RebuildKind.REBUILT
    op2 = first.purge_operation_id
    # 第二次 rebuild（N+1 → N+2）。
    await _g2_block(db_session, op2)
    await db_session.commit()
    second = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert second.kind is RebuildKind.REBUILT
    op3 = second.purge_operation_id
    # 篡改中间 seeded checkpoint（op2 的 owner[0] ack_digest）——非 fence。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners SET "
                "ack_digest = :bad, checkpoint_digest = :bad "
                "WHERE purge_operation_id = :op AND owner_key = :k"
            ),
            {"bad": "d" * 64, "op": op2, "k": _OWNER_KEYS[0]},
        )
        await s.commit()

    async with session_factory() as s:
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op3
        )
        await s.commit()

    async with session_factory() as verify:
        row = (
            await verify.execute(
                text(
                    "SELECT state, failure_code FROM "
                    "metaedu.agent_conversation_purges WHERE id = :op"
                ),
                {"op": op3},
            )
        ).one()
        assert row.state == "blocked"
        assert row.failure_code == "purge_owner_ack_conflict", "G4 derived conflict"
        cps = await _cp_rows(verify, op3)
        assert all(c["state"] == "acked" for c in cps), "checkpoint 零修改"
        assert len(await _ops(verify, cid)) == 3, "已提交 N+2 不回滚"


async def test_coordinator_stage2_fence_tamper_g4(db_session, session_factory):
    """S5-B-9 行 26：seeding 合法提交后篡改 predecessor checkpoint 行（阶段 2
    lineage 重验信任锚点）→ 聚合重验失败 → G4（blocked + purge_owner_ack_conflict；
    checkpoint 零修改；已提交新 op 不回滚）。变异「信任 seeded 副本不逐跳重验」
    →红。"""
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
    # 篡改 predecessor（op1）的 checkpoint ack_digest（阶段 2 重验输入）。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners SET "
                "ack_digest = :bad, checkpoint_digest = :bad "
                "WHERE purge_operation_id = :op AND owner_key = :k"
            ),
            {"bad": "d" * 64, "op": op1, "k": _OWNER_KEYS[0]},
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
        row = (
            await verify.execute(
                text(
                    "SELECT state, failure_code FROM "
                    "metaedu.agent_conversation_purges WHERE id = :op"
                ),
                {"op": new_op},
            )
        ).one()
        assert row.state == "blocked"
        assert row.failure_code == "purge_owner_ack_conflict", "G4 derived conflict"
        cps = await _cp_rows(verify, new_op)
        assert all(c["state"] == "acked" for c in cps), "checkpoint 零修改"
        assert len(await _ops(verify, cid)) == 2, "已提交新 op 不回滚"


@pytest.mark.parametrize(
    "reason_kind",
    [
        pytest.param(
            {"state": "blocked", "reason": "purge_blocked_by_external_erase_timeout",
             "expect_state": "pending", "expect_rollback": False},
            id="reopenable",
        ),
        pytest.param(
            {"state": "blocked", "reason": "purge_blocked_by_external_outcome_unknown",
             "expect_state": "blocked", "expect_rollback": False},
            id="3-5-6-outcome-unknown",
        ),
        pytest.param(
            {"state": "failed", "reason": "purge_blocked_by_external_erase_timeout",
             "expect_state": "failed", "expect_rollback": False},
            id="failed-non-erased",
        ),
        pytest.param(
            {"state": "blocked", "reason": None,
             "expect_state": None, "expect_rollback": True},
            id="null-dirty-data",
        ),
    ],
)
async def test_rebuild_re_added_reason_family_parametrized(
    db_session, session_factory, reason_kind
):
    """S5-B-9 行 27：re-added owner reason 全参数分派（族 F）——reopenable →
    pending；3/5/6 → carried_blocked（禁重开）；failed+非 erased → carried_failed；
    NULL → dirty-data 整事务回滚。变异「3/5/6 重开 pending / unknown 落入通用
    pending」→红。"""
    import json as _json

    from app.composition.agent_erasure_registry import snapshot_digest

    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    old_snapshot = [o for o in registry_snapshot() if o["owner_key"] != _OWNER_KEYS[0]]
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET "
            "registry_snapshot = :snap, registry_digest = :digest WHERE id = :op"
        ),
        {"snap": _json.dumps(old_snapshot), "digest": snapshot_digest(old_snapshot), "op": op1},
    )
    if reason_kind["expect_rollback"]:
        await _set_cp(db_session, op1, _OWNER_KEYS[0], state="blocked", reason=None)
    elif reason_kind["state"] == "failed":
        await _set_cp(
            db_session, op1, _OWNER_KEYS[0], state="failed",
            reason=reason_kind["reason"],
        )
    else:
        await _set_cp(
            db_session, op1, _OWNER_KEYS[0], state="blocked",
            reason=reason_kind["reason"],
        )
    for k in _OWNER_KEYS[1:]:
        await _set_cp(
            db_session, op1, k, state="blocked",
            reason="purge_blocked_by_external_erase_timeout",
        )
    # 历史 fence active（非 erased）——re-added 分派前提。
    ic = {"schema_version": 1, "sources": {}}
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "revision, created_at, updated_at) VALUES (:tid, :cid, :k, 1, "
            "'active', 1, 0, :ic, :ing, 1, now(), now())"
        ),
        {
            "tid": tid, "cid": cid, "k": _OWNER_KEYS[0],
            "ic": json.dumps(ic, sort_keys=True), "ing": canonical_digest(ic),
        },
    )
    await db_session.commit()

    if reason_kind["expect_rollback"]:
        with pytest.raises(ValueError, match="lineage stage-1"):
            await _rebuild(db_session, tid, cid)
        await db_session.rollback()
        async with session_factory() as verify:
            assert len(await _ops(verify, cid)) == 1, "NULL reason 整事务回滚"
        return

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT
    async with session_factory() as verify:
        new_op = (await _ops(verify, cid))[1]
        cps = {c["owner_key"]: c for c in await _cp_rows(verify, new_op["id"])}
        assert cps[_OWNER_KEYS[0]]["state"] == reason_kind["expect_state"]
        if reason_kind["expect_state"] == "blocked":
            assert (
                cps[_OWNER_KEYS[0]]["reason_code"] == reason_kind["reason"]
            ), "3/5/6 carry 保留具名 reason"


@pytest.mark.parametrize(
    "reason_kind",
    [
        pytest.param(
            {"reason": "purge_blocked_by_external_outcome_unknown",
             "expect_rollback": False},
            id="3-outcome-unknown",
        ),
        pytest.param(
            {"reason": "purge_blocked_by_external_settlement_deadline_expired",
             "expect_rollback": False},
            id="5-deadline-expired",
        ),
        pytest.param(
            {"reason": "purge_blocked_by_external_adapter_unresolvable",
             "expect_rollback": False},
            id="6-adapter-unresolvable",
        ),
        pytest.param(
            {"reason": None, "expect_rollback": True},
            id="output-4-erased-fence",
        ),
    ],
)
async def test_rebuild_version_changed_reason_family_parametrized(
    db_session, session_factory, reason_kind
):
    """S5-B-9 行 28：version-changed 3/5/6 禁重开（族 F 收口）——旧 fence
    erasing/blocked + 输出态 3/5/6 → carried_blocked（具名 reason 保留）；输出态
    4（erased fence）→ fail closed。变异「settlement_deadline_expired/
    adapter_unresolvable 被重开 pending」→红。"""
    import json as _json

    from app.composition.agent_erasure_registry import snapshot_digest

    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op1 = out.token.purge_operation_id
    await _g2_block(db_session, op1)
    old_snapshot = [
        dict(o, owner_version=2) if o["owner_key"] == _OWNER_KEYS[0] else o
        for o in registry_snapshot()
    ]
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges SET "
            "registry_snapshot = :snap, registry_digest = :digest WHERE id = :op"
        ),
        {"snap": _json.dumps(old_snapshot), "digest": snapshot_digest(old_snapshot), "op": op1},
    )
    if reason_kind["expect_rollback"]:
        await _set_cp(db_session, op1, _OWNER_KEYS[0], state="acked")
    else:
        await _set_cp(
            db_session, op1, _OWNER_KEYS[0], state="blocked",
            reason=reason_kind["reason"],
        )
    for k in _OWNER_KEYS[1:]:
        await _set_cp(
            db_session, op1, k, state="blocked",
            reason="purge_blocked_by_external_erase_timeout",
        )
    ic = {"schema_version": 1, "sources": {}}
    fence_state = "erased" if reason_kind["expect_rollback"] else "blocked"
    # ck_agent_erasure_fence_ack：非 erased 必须 ack_digest NULL 且 acked_at NULL。
    acked_at_sql = "now()" if fence_state == "erased" else "NULL"
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "ack_digest, acked_at, revision, created_at, updated_at) VALUES "
            "(:tid, :cid, :k, 2, :fs, 1, 0, :ic, :ing, :ack, "
            + acked_at_sql
            + ", 1, now(), now())"
        ),
        {
            "tid": tid, "cid": cid, "k": _OWNER_KEYS[0], "fs": fence_state,
            "ic": json.dumps(ic, sort_keys=True), "ing": canonical_digest(ic),
            "ack": _ACK if fence_state == "erased" else None,
        },
    )
    await db_session.commit()

    if reason_kind["expect_rollback"]:
        with pytest.raises(ValueError, match="lineage stage-1"):
            await _rebuild(db_session, tid, cid)
        await db_session.rollback()
        async with session_factory() as verify:
            assert len(await _ops(verify, cid)) == 1, "输出态 4 fail closed"
        return

    outcome = await _rebuild(db_session, tid, cid)
    await db_session.commit()
    assert outcome.kind is RebuildKind.REBUILT
    async with session_factory() as verify:
        new_op = (await _ops(verify, cid))[1]
        cps = {c["owner_key"]: c for c in await _cp_rows(verify, new_op["id"])}
        assert cps[_OWNER_KEYS[0]]["state"] == "blocked", "3/5/6 不重开 pending"
        assert (
            cps[_OWNER_KEYS[0]]["reason_code"] == reason_kind["reason"]
        ), "3/5/6 carry 保留具名 reason"


async def test_schb_retry_whitelist_3_5_6_zero_side_effects(
    db_session, session_factory
):
    """S5-B-9 行 31：3/5/6 blocked owner 经 SCH-B retry 编排（run_cycle）→ 拒绝：
    零 adapter 调用、零状态推进（checkpoint state/reason/attempt 与 fence/op
    语义不变）。变异「白名单含 3/5/6 / 重试重开 blocked→running」→红。"""
    from app.composition.owner_execution_orchestrator import (
        OwnerEntryOutcome,
        OwnerEntryRequest,
        OwnerExecutionOrchestrator,
    )

    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    await _set_cp(
        db_session, op_id, _OWNER_KEYS[0], state="blocked",
        reason="purge_blocked_by_external_outcome_unknown",
    )
    for k in _OWNER_KEYS[1:]:
        await _set_cp(db_session, op_id, k, state="acked")
    await db_session.commit()

    async def _raiser_entry(request: OwnerEntryRequest) -> OwnerEntryOutcome:
        raise AssertionError(f"3/5/6 owner 不得被重开 entry: {request.owner_key}")

    orch = OwnerExecutionOrchestrator(
        session_factory,
        owner_entries={k: _raiser_entry for k in _OWNER_KEYS},
        settlement_port=_NoopSettlement(),
        scan_providers=build_scan_providers,
    )
    await orch.run_cycle(tenant_id=tid, conversation_id=cid, purge_operation_id=op_id)

    async with session_factory() as verify:
        cp = (
            await verify.execute(
                text(
                    "SELECT state, reason_code, attempt FROM "
                    "metaedu.agent_conversation_purge_owners "
                    "WHERE purge_operation_id = :op AND owner_key = :k"
                ),
                {"op": op_id, "k": _OWNER_KEYS[0]},
            )
        ).one()
        assert cp.state == "blocked", "3/5/6 不重开 running"
        assert cp.reason_code == "purge_blocked_by_external_outcome_unknown"
        assert cp.attempt == 0, "零状态推进（attempt 不变）"
        fence_rows = (
            await verify.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t AND conversation_id = :c"
                ),
                {"t": tid, "c": cid},
            )
        ).scalar_one()
        assert fence_rows == 0, "fence 零写"
        op_state = (
            await verify.execute(
                text(
                    "SELECT state, failure_code, purge_revision FROM "
                    "metaedu.agent_conversation_purges WHERE id = :op"
                ),
                {"op": op_id},
            )
        ).one()
        assert op_state.failure_code is None, "op 无新失败语义"
        assert op_state.purge_revision == 1


async def test_rebuild_stage2_read_consistency_first_lock(session_factory):
    """S5-B-9 行 32：阶段 2 撕裂读——rebuild 的 predecessor/fence 只读依赖
    Conversation 首锁串行。判别：连接 A 持首锁时，连接 B 的 rebuild 必须在首锁
    后串行（lock_timeout 阻塞）；变异「rebuild 取 Conversation 行锁省略 FOR
    UPDATE」→ B 不再阻塞 → 红。"""
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

    async with session_factory() as lock_holder:
        # 连接 A 持 Conversation 首锁（模拟合法写者在锁窗口内）。
        await lock_holder.execute(
            text(
                "SELECT id FROM metaedu.agent_conversations "
                "WHERE tenant_id = :t AND id = :c FOR UPDATE"
            ),
            {"t": tid, "c": cid},
        )
        blocked_on_first_lock = False
        async with session_factory() as writer:
            await writer.execute(text("SET LOCAL lock_timeout = '1s'"))
            try:
                await _rebuild(writer, tid, cid)
            except Exception as exc:  # noqa: BLE001 - lock timeout → 首锁后串行
                blocked_on_first_lock = (
                    "lock timeout" in str(exc).lower()
                    or "55p03" in str(exc).lower()
                )
        assert blocked_on_first_lock, (
            "rebuild 必须阻塞在 Conversation 首锁后（绕过即撕裂读）"
        )
        await lock_holder.commit()
