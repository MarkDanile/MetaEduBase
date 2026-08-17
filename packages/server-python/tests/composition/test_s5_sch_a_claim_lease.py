"""R1-S5 SCH-A Claim & Lease：`ConversationPurgeScheduler` claim/lease 服务真实 PG 验收。

契约：Plan §R1-S5-D（S5-SCH-1.1/1.3b-i/2）+ §R1-S5-D-A（S5-SCH-7/8/9/10）——
migration 042 lease carrier + 租约三态 × 四转移 expected-epoch CAS。

反例映射（每项具名 mutation，驱动 = `scripts/sch_a_mutation_kill.py`，
运行方式见该脚本 docstring）：

- SCH-1 claim 过期行走 takeover 单写者（M-SCH-1：claim 对过期行跳过 takeover）
- SCH-2 首 claim 原子建行与全 owner checkpoint（M-SCH-2：checkpoint 建行不完整）
- SCH-5 崩溃恢复 takeover + 强制聚合 + 旧 token 零写（M-SCH-5：takeover 缺 epoch CAS）
- SCH-6 跨 tenant 零写（M-SCH-6：Conversation 锁裸 id 谓词）
- SCH-7 旧 token 重放零写（M-SCH-7：release 不校验 epoch）
- SCH-9 通用 updated_at 写不续租（M-SCH-9：renew 谓词改用 updated_at）
- SCH-10 过期 token 不得 renew（M-SCH-10：renew 缺到期检查）
- SCH-11 未到期租约不可接管（M-SCH-11：takeover 缺在租检查）
- SCH-12 release 使旧 token 失效（M-SCH-12：release 不推进 epoch）
- SCH-13 terminal/expired 不占 slot（M-SCH-13：计数含终态行）
- SCH-14 migration 042 往返（M-SCH-14：042 伪造 backfill，roundtrip 文件）
- SCH-15 epoch-0 NULL 行可 claim（M-SCH-15：claim 跳过 NULL 态 acquire）
- SCH-16 写 expiry 必推进 epoch（M-SCH-16：acquire 写 expiry 不推进 epoch）

边界：本测试只覆盖 claim/lease 服务（无后台循环）；六 participant 擦除
入口不参与（组合根静态守卫禁止本服务引用这些名字）。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.composition.agent_erasure_registry import registry_snapshot
from app.composition.conversation_purge_scheduler import (
    ClaimKind,
    ConversationPurgeScheduler,
    DeferReason,
    ReleaseOutcomeKind,
    RenewOutcomeKind,
    TakeoverOutcomeKind,
)
from app.composition.transactional_projection_coordinator import (
    TransactionalProjectionCoordinator,
    build_scan_providers,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)

_TIMEOUT = 15.0
_TTL_SECONDS = 600
_OWNER_COUNT = len(registry_snapshot())


# ---------------------------------------------------------------------------
# 种子 helpers（与 db_session 同事务；teardown 由 composition autouse clean 兜底）
# ---------------------------------------------------------------------------


async def _seed_conversation(
    session,
    *,
    tenant_id: uuid.UUID | None = None,
    state: str = "deleted",
    hold_revision: int = 0,
    purge_revision: int = 1,
    purge_state: str = "scheduled",
    purge_after_delta: timedelta | None = None,
    purged_at: bool = False,
    actor_state: str = "present",
) -> tuple[uuid.UUID, uuid.UUID]:
    """插入 conversation 行，返回 (tenant_id, conversation_id)。

    默认即 claim 谓词可过的形态：deleted + purge_after 已过 1 天 +
    purge_revision=1；purge_after_delta 为未来时刻的偏移（正值 = 未到期）。
    completed 事实集测试需 actor_state='redacted'（workspace scan 把
    present actor 计入未匿名 → scan 非零；ck_agent_conv_actor 要求 redacted
    时 created_by IS NULL + creator_identity_digest 64-hex）。
    """
    tid = tenant_id or uuid.uuid4()
    cid = uuid.uuid4()
    digest = "c" * 64
    purge_after = datetime.now(UTC) + (
        purge_after_delta
        if purge_after_delta is not None
        else timedelta(days=-1)
    )
    if actor_state == "redacted":
        created_by = None
        identity_digest: str | None = "d" * 64
    else:
        created_by = tid
        identity_digest = None
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, "
            "creator_identity_digest, title, title_source, state, purge_after, "
            "purge_state, purge_revision, purged_at, hold_revision, revision, "
            "created_at, updated_at) "
            "VALUES (:id, :tid, :creator, :actor_state, :digest, :identity, "
            "'t', 'none', :state, :purge_after, :purge_state, :purge_revision, "
            ":purged_at, :hold_revision, 1, now(), now())"
        ),
        {
            "id": cid,
            "tid": tid,
            "creator": created_by,
            "actor_state": actor_state,
            "digest": digest,
            "identity": identity_digest,
            "state": state,
            "purge_after": purge_after,
            "purge_state": purge_state,
            "purge_revision": purge_revision,
            "purged_at": datetime.now(UTC) if purged_at else None,
            "hold_revision": hold_revision,
        },
    )
    return tid, cid


async def _db_clock(session) -> datetime:
    return (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()


async def _claim(session, tid, cid) -> object:
    return await ConversationPurgeScheduler(session).claim(
        tenant_id=tid,
        conversation_id=cid,
        retention_policy_snapshot={"conversation_recovery_days": 30},
    )


async def _purge_rows(session, cid) -> list:
    rows = await session.execute(
        text(
            "SELECT id, purge_revision, state, lease_epoch, lease_expires_at, "
            "next_retry_at FROM metaedu.agent_conversation_purges "
            "WHERE conversation_id = :cid ORDER BY purge_revision"
        ),
        {"cid": cid},
    )
    return [
        {
            "id": r.id,
            "purge_revision": r.purge_revision,
            "state": r.state,
            "lease_epoch": r.lease_epoch,
            "lease_expires_at": r.lease_expires_at,
            "next_retry_at": r.next_retry_at,
        }
        for r in rows
    ]


async def _checkpoint_rows(session, op_id) -> list:
    rows = await session.execute(
        text(
            "SELECT owner_key, state, attempt FROM "
            "metaedu.agent_conversation_purge_owners "
            "WHERE purge_operation_id = :op ORDER BY owner_key"
        ),
        {"op": op_id},
    )
    return [
        {"owner_key": r.owner_key, "state": r.state, "attempt": r.attempt}
        for r in rows
    ]


async def _expire_lease(session, op_id) -> None:
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purges "
            "SET lease_expires_at = clock_timestamp() - interval '1 second' "
            "WHERE id = :op"
        ),
        {"op": op_id},
    )


async def _set_checkpoints(
    session, op_id, *, state: str | None = None, attempt: int | None = None
) -> None:
    sets, params = [], {"op": op_id}
    if state is not None:
        sets.append("state = :state")
        params["state"] = state
        if state == "acked":
            # ck_agent_purge_owner_ack：acked 必须携带 64 位 ack_digest；
            # checkpoint_digest 同步写入且必须与 fence ack_digest 一致
            # （calculator 五方验证：checkpoint.ack_digest == fence.ack_digest，
            # 镜像 I2 _ack_checkpoint facts 形态，统一 "e"*64）。
            sets.append("ack_digest = :ack, checkpoint_digest = :ack")
            params["ack"] = "e" * 64
    if attempt is not None:
        sets.append("attempt = :attempt")
        params["attempt"] = attempt
    assert sets, "no-op _set_checkpoints"
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners SET "
            + ", ".join(sets)
            + " WHERE purge_operation_id = :op"
        ),
        params,
    )


async def _seed_erased_fences(session, tid, cid) -> None:
    """全 owner erased fence（镜像 I2 `_seed_all_acked_facts`：completed 判定
    要求全部 owner 有 acked checkpoint + erased fence + 零扫描）。"""
    import json

    from app.shared.schemas.canonical_json import canonical_digest

    ic = {"schema_version": 1, "sources": {}}
    ingress_digest = canonical_digest(ic)
    ic_json = json.dumps(ic, sort_keys=True)
    for owner in registry_snapshot():
        await session.execute(
            text(
                "INSERT INTO metaedu.agent_erasure_fences "
                "(tenant_id, conversation_id, owner_key, owner_version, state, "
                "purge_revision, hold_revision, ingress_checkpoint, "
                "ingress_digest, ack_digest, acked_at, revision, created_at, "
                "updated_at) "
                "VALUES (:tid, :cid, :owner, 1, 'erased', 1, 0, :ic, :ingress, "
                ":ack, now(), 1, now(), now())"
            ),
            {
                "tid": tid,
                "cid": cid,
                "owner": str(owner["owner_key"]),
                "ic": ic_json,
                "ingress": ingress_digest,
                "ack": "e" * 64,
            },
        )


async def _seed_completed_facts(session, tid, cid, op_id) -> None:
    """全 owner acked checkpoint + erased fence：coordinator 聚合后 completed。"""
    await _set_checkpoints(session, op_id, state="acked")
    await _seed_erased_fences(session, tid, cid)
    session.expire_all()


async def _seed_fence(session, tid, cid, *, state: str) -> None:
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "revision, created_at, updated_at) "
            "VALUES (:tid, :cid, 'workspace.core.v1', 1, :state, 1, 0, "
            "'{\"schema_version\": 1, \"sources\": {}}', :digest, 1, "
            "now(), now())"
        ),
        {"tid": tid, "cid": cid, "state": state, "digest": "d" * 64},
    )


async def _seed_hold(session, tid, cid) -> uuid.UUID:
    return (
        await AgentErasureRepository(session).create_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            reason_code="litigation",
            purpose="hold for claim predicate test",
            actor_id=uuid.uuid4(),
        )
    ).id


def _assert_token(token, op_id, expected_epoch: int) -> None:
    assert token is not None
    assert token.purge_operation_id == op_id
    assert token.lease_epoch == expected_epoch
    assert token.lease_expires_at is not None


# ---------------------------------------------------------------------------
# SCH-2 / SCH-15 / SCH-16：首 claim 原子建行 + 全 owner checkpoint + 租约不变量
# ---------------------------------------------------------------------------


async def test_first_claim_creates_operation_full_checkpoints_and_lease(
    db_session, session_factory
):
    """SCH-2/SCH-16：首 claim 同事务建 operation + 全 owner checkpoint +
    acquire（epoch 0→1、expiry 非 NULL），无任何行时零伪造历史租约。

    mutation（SCH-16）：acquire 写 expiry 不推进 epoch -> 断言 epoch==1 转红。
    mutation（SCH-2）：全 owner checkpoint 建行不完整 -> 断言
    len(rows)==_OWNER_COUNT 转红。
    """
    tid, cid = await _seed_conversation(db_session)
    before = await _db_clock(db_session)
    outcome = await _claim(db_session, tid, cid)
    await db_session.commit()

    assert outcome.kind is ClaimKind.CLAIMED
    token = outcome.token
    assert token is not None
    assert token.lease_epoch == 1, "acquire 必须恰好 epoch 0 -> 1"
    assert token.lease_expires_at is not None, "claim 后必须有 active lease"

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert len(rows) == 1
        row = rows[0]
        assert row["purge_revision"] == 1
        assert row["state"] == "scheduled"
        assert row["lease_epoch"] == 1, "不变量：写 expiry 必推进 epoch"
        assert row["lease_expires_at"] is not None
        ttl = row["lease_expires_at"] - before
        assert timedelta(seconds=590) < ttl <= timedelta(seconds=610)
        checkpoints = await _checkpoint_rows(verify, row["id"])
        assert len(checkpoints) == _OWNER_COUNT, (
            "全 owner checkpoint 建行必须完整且同事务"
        )
        assert all(c["state"] == "pending" for c in checkpoints)
        assert all(c["attempt"] == 0 for c in checkpoints)


async def test_claim_rollback_leaves_zero_rows(db_session, session_factory):
    """原子性：claim 后不 commit 直接 rollback -> operation/checkpoint/lease
    零残留（建行与 acquire 同事务）。"""
    tid, cid = await _seed_conversation(db_session)
    await db_session.commit()
    async with session_factory() as s:
        await _claim(s, tid, cid)
        await s.rollback()
    async with session_factory() as verify:
        assert await _purge_rows(verify, cid) == []


# ---------------------------------------------------------------------------
# SCH-2 / SCH-1 / SCH-11：重复 claim 幂等与双 scheduler 单写者
# ---------------------------------------------------------------------------


async def test_repeated_claim_idempotent_single_row(
    db_session, session_factory
):
    """SCH-2：同 conversation 重复 claim（无 drift）-> 首 claim 建行一次，
    重复 claim 幂等返回既有 operation（HELD），零新增行零 lease 写。
    （建行唯一性判别点由 SCH-1 双 claim 单写者测试承载。）"""
    tid, cid = await _seed_conversation(db_session)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    assert first.kind is ClaimKind.CLAIMED
    first_op = first.token.purge_operation_id

    async with session_factory() as s:
        second = await _claim(s, tid, cid)
        await s.commit()
    assert second.kind is ClaimKind.HELD, "在租 claim 幂等返回既有 operation"
    assert second.purge_operation_id == first_op
    assert second.existing_lease_epoch == 1

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert len(rows) == 1, "重复 claim 零建行"
        assert rows[0]["lease_epoch"] == 1, "重复 claim 零 lease 写"
        checkpoints = await _checkpoint_rows(verify, first_op)
        assert len(checkpoints) == _OWNER_COUNT, "重复 claim 零 checkpoint 建行"


async def test_concurrent_dual_claim_single_writer(session_factory):
    """SCH-1/SCH-11：双 scheduler 并发 claim 同一 conversation ->
    Conversation 锁串行 + 幂等判别收敛为单一写者：恰一 CLAIMED（epoch 1），
    另一 HELD 零写；全库仅一行 operation、一套 checkpoint。
    （锁串行阻塞判别由 test_dual_claim_serialized_by_conversation_lock
    承载。）"""
    async with session_factory() as seed:
        tid, cid = await _seed_conversation(seed)
        await seed.commit()

    async def _one():
        async with session_factory() as s:
            outcome = await _claim(s, tid, cid)
            await s.commit()
            return outcome

    outcomes = await asyncio.wait_for(
        asyncio.gather(_one(), _one()), timeout=_TIMEOUT
    )
    kinds = sorted(o.kind.value for o in outcomes)
    assert kinds == ["claimed", "held"], f"单一写者，实际 {kinds}"
    claimed = next(o for o in outcomes if o.kind is ClaimKind.CLAIMED)

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert len(rows) == 1
        assert rows[0]["lease_epoch"] == 1
        checkpoints = await _checkpoint_rows(verify, claimed.token.purge_operation_id)
        assert len(checkpoints) == _OWNER_COUNT


async def test_claim_stale_revision_creates_new_operation(
    db_session, session_factory
):
    """建行判据 (i)：top operation 是旧 purge_revision（restore 已推进
    conversation.purge_revision）-> 旧 top 租约**过期/未认领**时按当前
    revision 建新行，旧行不动；旧 top 仍在租（≤TTL 窗口）时 HELD 延迟
    （「无在租 claim」谓词约束旧 revision 分支，防双活租约）。"""
    tid, cid = await _seed_conversation(db_session, purge_revision=1)
    outcome = await _claim(db_session, tid, cid)
    await db_session.commit()
    old_op = outcome.token.purge_operation_id
    # 模拟 restore + 再次 delete：conversation.purge_revision 推进到 2。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversations SET purge_revision = 2 "
            "WHERE id = :cid"
        ),
        {"cid": cid},
    )
    await db_session.commit()

    # 旧 top 仍在租 -> HELD 延迟（零建行），不得双活租约。
    async with session_factory() as s:
        held = await _claim(s, tid, cid)
        await s.rollback()
    assert held.kind is ClaimKind.HELD
    assert held.purge_operation_id == old_op

    # 旧租约过期后 -> 按当前 revision 建新行。
    async with session_factory() as s:
        await _expire_lease(s, old_op)
        await s.commit()
    async with session_factory() as s:
        second = await _claim(s, tid, cid)
        await s.commit()
    assert second.kind is ClaimKind.CLAIMED
    assert second.token.purge_operation_id != old_op
    assert second.token.lease_epoch == 1

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert [r["purge_revision"] for r in rows] == [1, 2]


# ---------------------------------------------------------------------------
# SCH-5：claim 后崩溃 -> 到期 takeover + 强制聚合 + 旧 token 零写
# ---------------------------------------------------------------------------


async def test_crash_recovery_takeover_and_forced_aggregation(
    db_session, session_factory
):
    """SCH-5：claim（epoch 1）后 scheduler 崩溃 -> 租约到期 -> 新实例
    takeover（epoch 2）成功且**强制 coordinator 聚合**（全 owner acked ->
    operation completed + conversation purged_at/purge_state 落库）-> 返回
    新 token；旧 token（epoch 1）重放 renew/takeover 零写。

    mutation（SCH-5）：takeover CAS 缺 epoch 谓词 -> 旧 token takeover
    仍写转红。
    """
    tid, cid = await _seed_conversation(db_session, actor_state="redacted")
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id

    # 模拟 owner 全部完成：checkpoint 全 acked + fence 全 erased；随后
    # scheduler 崩溃，租约到期。
    async with session_factory() as s:
        await _seed_completed_facts(s, tid, cid, op_id)
        await _expire_lease(s, op_id)
        await s.commit()

    async with session_factory() as s:
        takeover = await ConversationPurgeScheduler(s).takeover(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.commit()
    assert takeover.kind is TakeoverOutcomeKind.TAKEN
    _assert_token(takeover.token, op_id, 2)

    # 强制聚合已发生：completed + purged_at。
    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert rows[0]["state"] == "completed"
        conversation = await verify.execute(
            text(
                "SELECT purge_state, purged_at FROM metaedu.agent_conversations "
                "WHERE id = :cid"
            ),
            {"cid": cid},
        )
        purge_state, purged_at = conversation.one()
        assert purge_state == "completed"
        assert purged_at is not None

    # 旧 token 重放：epoch 1 已失效，零写。
    async with session_factory() as s:
        stale_renew = await ConversationPurgeScheduler(s).renew(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.rollback()
    assert stale_renew.kind is RenewOutcomeKind.STALE
    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert rows[0]["lease_epoch"] == 2, "旧 token 重放零写"


async def test_claim_path_takes_over_expired_lease(db_session, session_factory):
    """claim 谓词「无在租 claim」正式化：op 存在且租约已过期 -> claim 走
    takeover 路径（epoch+1），不是 HELD 也不是新建行。"""
    tid, cid = await _seed_conversation(db_session)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id
    async with session_factory() as s:
        await _expire_lease(s, op_id)
        await s.commit()

    async with session_factory() as s:
        outcome = await _claim(s, tid, cid)
        await s.commit()
    assert outcome.kind is ClaimKind.CLAIMED
    assert outcome.token.purge_operation_id == op_id
    assert outcome.token.lease_epoch == 2, "过期 claim = takeover，epoch+1"

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert len(rows) == 1, "takeover 不建新行"


# ---------------------------------------------------------------------------
# SCH-12 / SCH-10 / SCH-9：renew/release token 更新与旧 token 失效
# ---------------------------------------------------------------------------


async def test_renew_advances_epoch_and_resets_expiry(
    db_session, session_factory
):
    """SCH-12 前置：renew（current-epoch + 未到期）成功 -> epoch 恰好 +1、
    expiry 重置（DB clock + TTL）；renew 后旧 epoch token 失效。"""
    tid, cid = await _seed_conversation(db_session)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id

    async with session_factory() as s:
        before = await _db_clock(s)
        renewed = await ConversationPurgeScheduler(s).renew(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.commit()
    assert renewed.kind is RenewOutcomeKind.RENEWED
    _assert_token(renewed.token, op_id, 2)
    ttl = renewed.token.lease_expires_at - before
    assert timedelta(seconds=590) < ttl <= timedelta(seconds=610)

    # 旧 epoch token 已失效。
    async with session_factory() as s:
        stale = await ConversationPurgeScheduler(s).renew(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.rollback()
    assert stale.kind is RenewOutcomeKind.STALE


async def test_expired_token_cannot_renew(db_session, session_factory):
    """SCH-10：租约过期后旧持有者携 current-epoch renew -> CAS 拒零写
    （EXPIRED）；过期仅 takeover 可推进。

    mutation（SCH-10）：renew 谓词缺到期检查 -> EXPIRED 用例转红。
    """
    tid, cid = await _seed_conversation(db_session)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id
    async with session_factory() as s:
        await _expire_lease(s, op_id)
        await s.commit()

    async with session_factory() as s:
        expired = await ConversationPurgeScheduler(s).renew(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.rollback()
    assert expired.kind is RenewOutcomeKind.EXPIRED

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert rows[0]["lease_epoch"] == 1, "过期 renew 零写"


async def test_updated_at_change_does_not_renew(db_session, session_factory):
    """SCH-9：coordinator 聚合写 operation 行（updated_at 变化）不得续租——
    lease_expires_at 不变；过期后 renew 仍被拒（updated_at 非租约事实源）。

    mutation（SCH-9）：renew 谓词改用 updated_at 判定 -> coordinator 写后
    过期 renew 成功转红。
    """
    tid, cid = await _seed_conversation(db_session, actor_state="redacted")
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id
    async with session_factory() as s:
        await _seed_completed_facts(s, tid, cid, op_id)
        await _expire_lease(s, op_id)
        await s.commit()

    # 非租约写者：coordinator 聚合（全 acked + 全 erased -> completed，
    # 写 updated_at）。
    async with session_factory() as s:
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid,
            conversation_id=cid,
            purge_operation_id=op_id,
        )
        await s.commit()

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert rows[0]["lease_expires_at"] is not None
        # updated_at 已变（coordinator 写），但租约事实源 lease_expires_at
        # 仍是过期时刻 -> renew 必须仍被拒。
        stale_lease = rows[0]["lease_expires_at"]
        assert stale_lease < await _db_clock(verify)

    async with session_factory() as s:
        expired = await ConversationPurgeScheduler(s).renew(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.rollback()
    assert expired.kind is RenewOutcomeKind.EXPIRED, (
        "updated_at 变化不得构成续租"
    )


async def test_release_clears_expiry_and_invalidates_old_token(
    db_session, session_factory
):
    """SCH-12：release（current-epoch + 在租）-> epoch 恰好 +1、expiry 清
    NULL；release 后旧 token 重放 renew 零写（STALE）；NULL 态可再 claim
    （acquire，epoch 再 +1）。

    mutation（SCH-12）：release 不推进 epoch -> 旧 token renew 成功转红。
    """
    tid, cid = await _seed_conversation(db_session)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id

    async with session_factory() as s:
        released = await ConversationPurgeScheduler(s).release(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.commit()
    assert released.kind is ReleaseOutcomeKind.RELEASED
    assert released.lease_epoch == 2

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert rows[0]["lease_epoch"] == 2
        assert rows[0]["lease_expires_at"] is None, "release 清 expiry"

    # 旧 token 失效。
    async with session_factory() as s:
        stale = await ConversationPurgeScheduler(s).renew(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.rollback()
    assert stale.kind is RenewOutcomeKind.STALE

    # NULL 态再 claim = acquire（epoch 2 -> 3）。
    async with session_factory() as s:
        again = await _claim(s, tid, cid)
        await s.commit()
    assert again.kind is ClaimKind.CLAIMED
    assert again.token.lease_epoch == 3


async def test_release_idempotent_on_null_lease(db_session, session_factory):
    """SCH-12 补：已释放（NULL）行重复 release -> 零写成功返回
    （ALREADY_RELEASED），不冗余推进 epoch。"""
    tid, cid = await _seed_conversation(db_session)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id
    async with session_factory() as s:
        await ConversationPurgeScheduler(s).release(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.commit()

    async with session_factory() as s:
        again = await ConversationPurgeScheduler(s).release(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=2,
        )
        await s.commit()
    assert again.kind is ReleaseOutcomeKind.ALREADY_RELEASED

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert rows[0]["lease_epoch"] == 2, "重复 release 零写"


async def test_terminal_release_by_observation(
    db_session, session_factory
):
    """SCH-13 收尾：终态观察 release——operation 已 completed（expiry 未清）
    时 release CAS 合法收尾（epoch+1、expiry NULL）；终态行不可 takeover
    （TERMINAL 零写）。"""
    tid, cid = await _seed_conversation(db_session, actor_state="redacted")
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id
    async with session_factory() as s:
        await _seed_completed_facts(s, tid, cid, op_id)
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
        )
        await s.commit()

    async with session_factory() as s:
        takeover = await ConversationPurgeScheduler(s).takeover(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.rollback()
    assert takeover.kind is TakeoverOutcomeKind.TERMINAL, "终态行禁止 takeover"

    async with session_factory() as s:
        released = await ConversationPurgeScheduler(s).release(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.commit()
    assert released.kind is ReleaseOutcomeKind.RELEASED
    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert rows[0]["lease_expires_at"] is None
        assert rows[0]["lease_epoch"] == 2


# ---------------------------------------------------------------------------
# SCH-6 / SCH-7：跨 tenant 与旧 token 零写
# ---------------------------------------------------------------------------


async def test_cross_tenant_zero_write(db_session, session_factory):
    """SCH-6：claim/takeover/renew/release 携带错误 tenant -> 零写 fail
    closed（Conversation 谓词含 tenant，不锁外租户行、不泄露）。

    mutation（SCH-6）：Conversation 锁查询去掉 tenant_id（裸 id 谓词）->
    外租户 conversation 被锁且 claim 建行转红。
    """
    tid, cid = await _seed_conversation(db_session)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id
    other_tid = uuid.uuid4()

    async with session_factory() as s:
        with pytest.raises(ValueError):
            await _claim(s, other_tid, cid)
        await s.rollback()

    for call in (
        lambda s: ConversationPurgeScheduler(s).renew(
            tenant_id=other_tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        ),
        lambda s: ConversationPurgeScheduler(s).takeover(
            tenant_id=other_tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        ),
        lambda s: ConversationPurgeScheduler(s).release(
            tenant_id=other_tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        ),
    ):
        async with session_factory() as s:
            with pytest.raises(ValueError):
                await call(s)
            await s.rollback()

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert len(rows) == 1
        assert rows[0]["lease_epoch"] == 1, "跨 tenant 全部零写"


async def test_stale_epoch_zero_write_on_renew_takeover_release(
    db_session, session_factory
):
    """SCH-7：旧 lease_epoch token 重放 renew/takeover/release 全部零写。"""
    tid, cid = await _seed_conversation(db_session)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id

    async with session_factory() as s:
        await _expire_lease(s, op_id)
        await s.commit()

    async with session_factory() as s:
        stale_takeover = await ConversationPurgeScheduler(s).takeover(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=99,
        )
        stale_release = await ConversationPurgeScheduler(s).release(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=99,
        )
        await s.rollback()
    assert stale_takeover.kind is TakeoverOutcomeKind.STALE
    assert stale_release.kind is ReleaseOutcomeKind.STALE

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert rows[0]["lease_epoch"] == 1, "旧 token 零写"


async def test_takeover_live_lease_rejected_in_lease(
    db_session, session_factory
):
    """SCH-11：未到期租约不可接管——takeover 在租行零写（IN_LEASE），
    不产生第二持有者。

    mutation（SCH-11）：takeover 谓词缺在租检查（删
    `lease_expires_at IS NULL OR <= clock_timestamp()`）-> 在租行被
    takeover 成功、epoch 双推进转红。
    """
    tid, cid = await _seed_conversation(db_session)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id

    async with session_factory() as s:
        rejected = await ConversationPurgeScheduler(s).takeover(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.rollback()
    assert rejected.kind is TakeoverOutcomeKind.IN_LEASE

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert rows[0]["lease_epoch"] == 1, "在租 takeover 零写"


async def test_lease_cas_missing_operation_fails_closed(db_session):
    """三键限定 + fail closed：不存在或跨 conversation 的 operation id ->
    ValueError 零写（不锁目标行、无外租户信息）。"""
    tid, cid = await _seed_conversation(db_session)
    await _claim(db_session, tid, cid)
    await db_session.commit()
    bogus = uuid.uuid4()
    with pytest.raises(ValueError):
        await ConversationPurgeScheduler(db_session).renew(
            tenant_id=tid,
            purge_operation_id=bogus,
            conversation_id=cid,
            expected_lease_epoch=1,
        )


# ---------------------------------------------------------------------------
# SCH-13：tenant 上限 4、advisory 计数、terminal/expired 不占 slot
# ---------------------------------------------------------------------------


async def test_tenant_cap_four_and_slot_counting(db_session, session_factory):
    """SCH-13：per-tenant 并发上限 4——第 5 个 claim 拒（tenant_cap，零建行）；
    terminal（completed 但 expiry 未清）与 expired 不占 slot；计数与 acquire
    同事务（自身不超限）。

    mutation（SCH-13）：计数谓词含终态/过期行 -> 第 5/6 个 claim 本应成功
    被误拒转红。
    """
    tid = uuid.uuid4()
    claimed = []
    for i in range(4):
        _, cid = await _seed_conversation(
            db_session,
            tenant_id=tid,
            actor_state="redacted" if i == 0 else "present",
        )
        outcome = await _claim(db_session, tid, cid)
        assert outcome.kind is ClaimKind.CLAIMED
        claimed.append((cid, outcome.token.purge_operation_id))
    await db_session.commit()

    # 第 5 个：cap 命中 -> 零建行。
    _, cid5 = await _seed_conversation(db_session, tenant_id=tid)
    await db_session.commit()
    async with session_factory() as s:
        fifth = await _claim(s, tid, cid5)
        await s.rollback()
    assert fifth.kind is ClaimKind.DEFERRED
    assert fifth.defer_reason is DeferReason.TENANT_CAP

    # 1 个 terminal（completed + expiry 未清）+ 1 个 expired -> 释放 2 slot。
    async with session_factory() as s:
        cid1, op1 = claimed[0]
        await _seed_completed_facts(s, tid, cid1, op1)
        coordinator = TransactionalProjectionCoordinator(
            s, scan_providers=build_scan_providers(s)
        )
        await coordinator.aggregate_projection(
            tenant_id=tid, conversation_id=cid1, purge_operation_id=op1
        )
        cid2, op2 = claimed[1]
        await _expire_lease(s, op2)
        await s.commit()

    async with session_factory() as s:
        again5 = await _claim(s, tid, cid5)
        await s.commit()
    assert again5.kind is ClaimKind.CLAIMED, "terminal 不占 slot"
    _, cid6 = await _seed_conversation(db_session, tenant_id=tid)
    await db_session.commit()
    async with session_factory() as s:
        sixth = await _claim(s, tid, cid6)
        await s.commit()
    assert sixth.kind is ClaimKind.CLAIMED, "expired 不占 slot"

    # 第 7 个：再次 cap（active = 3,4,5,6）。
    _, cid7 = await _seed_conversation(db_session, tenant_id=tid)
    await db_session.commit()
    async with session_factory() as s:
        seventh = await _claim(s, tid, cid7)
        await s.rollback()
    assert seventh.kind is ClaimKind.DEFERRED
    assert seventh.defer_reason is DeferReason.TENANT_CAP


async def test_tenant_cap_independent_across_tenants(
    db_session, session_factory
):
    """SCH-6/SCH-13：跨 tenant 独立——A 租户打满 4，B 租户 claim 不受影响。"""
    tid_a = uuid.uuid4()
    for _ in range(4):
        _, cid = await _seed_conversation(db_session, tenant_id=tid_a)
        await _claim(db_session, tid_a, cid)
    await db_session.commit()

    tid_b = uuid.uuid4()
    _, cid_b = await _seed_conversation(db_session, tenant_id=tid_b)
    await db_session.commit()
    async with session_factory() as s:
        outcome = await _claim(s, tid_b, cid_b)
        await s.commit()
    assert outcome.kind is ClaimKind.CLAIMED, "tenant 隔离"


async def test_claim_takeover_exempt_from_cap(db_session, session_factory):
    """三面返修裁决固化：claim 引发的 takeover 豁免 cap 计数——expired 行
    不占 slot（S5-SCH-8 计数谓词），claim-takeover 是恢复语义而非新占
    slot；否则「4 active + 1 expired」的 tenant 无法恢复（liveness 洞）。"""
    tid = uuid.uuid4()
    claimed = []
    for _ in range(4):
        _, cid = await _seed_conversation(db_session, tenant_id=tid)
        outcome = await _claim(db_session, tid, cid)
        assert outcome.kind is ClaimKind.CLAIMED
        claimed.append((cid, outcome.token.purge_operation_id))
    await db_session.commit()
    expired_cid, expired_op = claimed[0]

    # 第 1 个租约过期（不占 slot）后，第 5 个 conversation 正常建行
    # （active = 2,3,4,5 回到 4）。
    async with session_factory() as s:
        await _expire_lease(s, expired_op)
        await s.commit()
    _, cid5 = await _seed_conversation(db_session, tenant_id=tid)
    await db_session.commit()
    async with session_factory() as s:
        fifth = await _claim(s, tid, cid5)
        await s.commit()
    assert fifth.kind is ClaimKind.CLAIMED

    # claim 对过期行走 takeover，豁免 cap -> CLAIMED（epoch 2），瞬时
    # active 越过 4（advisory 恢复语义）。
    async with session_factory() as s:
        again = await _claim(s, tid, expired_cid)
        await s.commit()
    assert again.kind is ClaimKind.CLAIMED
    assert again.token.purge_operation_id == expired_op
    assert again.token.lease_epoch == 2


async def test_dual_claim_serialized_by_conversation_lock(session_factory):
    """SCH-1 锁串行判别：会话 A 裸 SQL 持 Conversation 行锁，迟到 claim
    （会话 B）必须阻塞排队——A 提交后 B 才完成（HELD，零写）。

    负向短超时（1s）判定「被挡住」属刻意偏离，与 I1 锁序判别同规格。"""
    async with session_factory() as seed:
        tid, cid = await _seed_conversation(seed)
        await seed.commit()

    async with session_factory() as a:
        # A 手动持锁（模拟正在执行的 claim 事务）。
        await a.execute(
            text(
                "SELECT id FROM metaedu.agent_conversations "
                "WHERE tenant_id = :tid AND id = :cid FOR UPDATE"
            ),
            {"tid": tid, "cid": cid},
        )
        late_task = asyncio.create_task(
            _claim_in_fresh_session(tid, cid, session_factory)
        )
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                asyncio.shield(late_task), timeout=1.0
            ), "迟到 claim 必须被 Conversation 行锁阻塞"
        await a.commit()
        late_outcome = await asyncio.wait_for(late_task, timeout=_TIMEOUT)
    assert late_outcome.kind is ClaimKind.CLAIMED, (
        "A 未建行（裸锁），B 排队后首个建行"
    )


async def _claim_in_fresh_session(tid, cid, factory):
    async with factory() as s:
        outcome = await _claim(s, tid, cid)
        await s.commit()
        return outcome


async def test_takeover_aggregation_failure_rolls_back_zero_residue(
    db_session, session_factory
):
    """三面返修补测：takeover 成功后强制聚合异常（旧 revision op 触发
    coordinator I2 门禁）-> 异常传播 -> 调用方 rollback -> lease/backoff/
    聚合写全部零残留（模块不 commit 的原子性边界）。"""
    tid, cid = await _seed_conversation(db_session, purge_revision=1)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id
    # 推进 conversation.purge_revision 制造旧 revision op（聚合 I2 门禁会拒）。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversations SET purge_revision = 2 "
                "WHERE id = :cid"
            ),
            {"cid": cid},
        )
        await _expire_lease(s, op_id)
        await s.commit()

    async with session_factory() as s:
        with pytest.raises(ValueError):
            await ConversationPurgeScheduler(s).takeover(
                tenant_id=tid,
                purge_operation_id=op_id,
                conversation_id=cid,
                expected_lease_epoch=1,
            )
        await s.rollback()

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert rows[0]["lease_epoch"] == 1, "rollback 后 lease 零残留"


async def test_top_revision_exceeds_conversation_fail_closed(db_session):
    """防御性 fail-closed：top operation purge_revision > conversation
    purge_revision（数据异常形态）-> ValueError 零建行。"""
    tid, cid = await _seed_conversation(db_session, purge_revision=1)
    repo = AgentErasureRepository(db_session)
    await repo.create_purge_operation(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=2,  # 超过 conversation 当前 revision 1
        retention_policy_snapshot={"conversation_recovery_days": 30},
        hold_revision_snapshot=0,
    )
    await db_session.commit()
    with pytest.raises(ValueError):
        await _claim(db_session, tid, cid)
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 谓词延迟：not_deleted / purge_not_due / already_purged / active_hold / quiesce
# ---------------------------------------------------------------------------


async def test_claim_predicate_deferrals_zero_rows(db_session):
    """谓词拒绝全部零建行：未 deleted、purge_after 未到、purge_after NULL
    （永不到期推断）、已 purged。"""
    tid = uuid.uuid4()
    _, not_deleted = await _seed_conversation(
        db_session, tenant_id=tid, state="active"
    )
    _, not_due = await _seed_conversation(
        db_session, tenant_id=tid, purge_after_delta=timedelta(hours=1)
    )
    _, no_deadline = await _seed_conversation(
        db_session, tenant_id=tid, purge_after_delta=timedelta(0)
    )
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversations SET purge_after = NULL "
            "WHERE id = :cid"
        ),
        {"cid": no_deadline},
    )
    _, purged = await _seed_conversation(
        db_session, tenant_id=tid, purged_at=True
    )

    o1 = await _claim(db_session, tid, not_deleted)
    assert o1.kind is ClaimKind.DEFERRED and o1.defer_reason is DeferReason.NOT_DELETED
    o2 = await _claim(db_session, tid, not_due)
    assert o2.kind is ClaimKind.DEFERRED and o2.defer_reason is DeferReason.PURGE_NOT_DUE
    o3 = await _claim(db_session, tid, no_deadline)
    assert o3.kind is ClaimKind.DEFERRED and o3.defer_reason is DeferReason.PURGE_NOT_DUE
    o4 = await _claim(db_session, tid, purged)
    assert o4.kind is ClaimKind.DEFERRED and o4.defer_reason is DeferReason.ALREADY_PURGED
    await db_session.commit()

    for cid in (not_deleted, not_due, no_deadline, purged):
        assert await _purge_rows(db_session, cid) == []


async def test_claim_defers_active_hold_until_release(db_session, session_factory):
    """active hold 延迟 claim（零建行）；release 后同 conversation 可 claim。"""
    tid, cid = await _seed_conversation(db_session)
    hold_id = await _seed_hold(db_session, tid, cid)
    await db_session.commit()

    async with session_factory() as s:
        deferred = await _claim(s, tid, cid)
        await s.rollback()
    assert deferred.kind is ClaimKind.DEFERRED
    assert deferred.defer_reason is DeferReason.ACTIVE_HOLD

    async with session_factory() as s:
        await AgentErasureRepository(s).release_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            hold_id=hold_id,
            expected_revision=1,
            released_by=uuid.uuid4(),
        )
        await s.commit()

    async with session_factory() as s:
        outcome = await _claim(s, tid, cid)
        await s.commit()
    assert outcome.kind is ClaimKind.CLAIMED


async def test_claim_defers_quiesce_on_erasing_checkpoint_or_fence(
    db_session, session_factory
):
    """quiesce 门禁：任一 owner checkpoint erasing 或任一 fence erasing ->
    零建行延迟（DEFERRED quiesce）。"""
    # 变体 1：erasing checkpoint（既有 operation）。
    tid, cid = await _seed_conversation(db_session)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id
    async with session_factory() as s:
        await _set_checkpoints(s, op_id, state="erasing")
        await ConversationPurgeScheduler(s).release(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.commit()

    async with session_factory() as s:
        deferred = await _claim(s, tid, cid)
        await s.rollback()
    assert deferred.kind is ClaimKind.DEFERRED
    assert deferred.defer_reason is DeferReason.QUIESCE

    # 变体 2：erasing fence（无 operation）。
    tid2, cid2 = await _seed_conversation(db_session)
    await _seed_fence(db_session, tid2, cid2, state="erasing")
    await db_session.commit()
    async with session_factory() as s:
        deferred2 = await _claim(s, tid2, cid2)
        await s.rollback()
    assert deferred2.kind is ClaimKind.DEFERRED
    assert deferred2.defer_reason is DeferReason.QUIESCE
    async with session_factory() as verify:
        assert await _purge_rows(verify, cid2) == []


# ---------------------------------------------------------------------------
# SCH-15：epoch-0 NULL 行（rebuild 未并入 acquire 的模拟）可被 claim acquire
# ---------------------------------------------------------------------------


async def test_epoch_zero_null_lease_claimable(db_session, session_factory):
    """SCH-15：已有 operation（epoch 0 + NULL expiry，模拟 rebuild 未并入
    acquire 的遗留行）-> claim 走 acquire（epoch 0 -> 1），可判、不建新行。

    mutation（SCH-15）：claim 对 epoch-0 NULL 行跳过 acquire -> 断言
    epoch==1 转红。
    """
    tid, cid = await _seed_conversation(db_session)
    # 直接种子 rebuild 遗留形态：op 行 epoch 0 / expiry NULL + 全 owner
    # checkpoint 已建（重建事务未 acquire 即提交）。
    repo = AgentErasureRepository(db_session)
    op = await repo.create_purge_operation(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=1,
        retention_policy_snapshot={"conversation_recovery_days": 30},
        hold_revision_snapshot=0,
    )
    for owner in registry_snapshot():
        await repo.create_owner_checkpoint(
            tenant_id=tid,
            purge_operation_id=op.id,
            owner_key=str(owner["owner_key"]),
        )
    await db_session.commit()

    async with session_factory() as s:
        outcome = await _claim(s, tid, cid)
        await s.commit()
    assert outcome.kind is ClaimKind.CLAIMED
    assert outcome.token.purge_operation_id == op.id
    assert outcome.token.lease_epoch == 1, "NULL 态 claim = acquire epoch 0->1"

    async with session_factory() as verify:
        rows = await _purge_rows(verify, cid)
        assert len(rows) == 1, "不重复建行"


# ---------------------------------------------------------------------------
# 退避与 next_retry_at 最早值仲裁（claim/renew/takeover 短事务内锁内重算）
# ---------------------------------------------------------------------------


async def _backoff_seconds(session, op_id) -> float:
    row = (
        await session.execute(
            text(
                "SELECT next_retry_at FROM metaedu.agent_conversation_purges "
                "WHERE id = :op"
            ),
            {"op": op_id},
        )
    ).scalar_one()
    now = await _db_clock(session)
    return (row - now).total_seconds()


async def test_next_retry_at_min_arbitration(db_session, session_factory):
    """退避写：next_retry_at = now + min(5s × 2^min_attempt, 5m)，随
    claim/renew/takeover 短事务锁内重算（不依赖持久 jitter）。

    - 首 claim（attempt 全 0）-> ≈ 5s；
    - attempts [3, 7] -> renew 重算 ≈ 40s（最早者仲裁）；
    - attempts [10] -> renew 重算 ≈ 300s（封顶）。
    """
    tid, cid = await _seed_conversation(db_session)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id

    async with session_factory() as s:
        assert abs(await _backoff_seconds(s, op_id) - 5) < 1.5

    # attempts [3, 7] -> 5s × 2^3 = 40s（min 仲裁）。
    async with session_factory() as s:
        await _set_checkpoints(s, op_id, attempt=7)
        await _set_checkpoints_partial(s, op_id, "workspace.core.v1", attempt=3)
        await ConversationPurgeScheduler(s).renew(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.commit()
    async with session_factory() as s:
        assert abs(await _backoff_seconds(s, op_id) - 40) < 1.5

    # attempt 10 -> 5s × 2^10 = 5120s -> 封顶 300s。
    async with session_factory() as s:
        await _set_checkpoints(s, op_id, attempt=10)
        await ConversationPurgeScheduler(s).renew(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=2,
        )
        await s.commit()
    async with session_factory() as s:
        assert abs(await _backoff_seconds(s, op_id) - 300) < 1.5


async def _set_checkpoints_partial(
    session, op_id, owner_key: str, *, attempt: int
) -> None:
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners SET attempt = :a "
            "WHERE purge_operation_id = :op AND owner_key = :k"
        ),
        {"a": attempt, "op": op_id, "k": owner_key},
    )


async def test_takeover_recomputes_backoff_in_lock(
    db_session, session_factory
):
    """takeover 后按 attempt 锁内重算：持久 next_retry_at 不是可信来源。"""
    tid, cid = await _seed_conversation(db_session)
    first = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = first.token.purge_operation_id
    async with session_factory() as s:
        await _set_checkpoints(s, op_id, attempt=4)
        await _expire_lease(s, op_id)
        await s.commit()

    async with session_factory() as s:
        taken = await ConversationPurgeScheduler(s).takeover(
            tenant_id=tid,
            purge_operation_id=op_id,
            conversation_id=cid,
            expected_lease_epoch=1,
        )
        await s.commit()
    assert taken.kind is TakeoverOutcomeKind.TAKEN
    async with session_factory() as s:
        assert abs(await _backoff_seconds(s, op_id) - 80) < 1.5, (
            "5s × 2^4 = 80s，takeover 锁内重算"
        )
