"""R1-S5-I1：Legal Hold Revision Fencing Producer 真实 PostgreSQL 验收。

契约：Plan §R1-S5-A-4 hold_revision 生产者前置 + S5-A-6 I1——
create/release 均先取 Conversation 行锁 + 同事务推进 `Conversation.hold_revision`
（均 bump）；仅 repository/domain producer primitive，无 HTTP/CLI；
不 commit()（原子性归调用方事务）；不定义 create 重放（无 idempotency key）。

pre-I2 可测项（S5-A-6 I1 验收 re-scope）：
- bump 串行化（Conversation 行锁，真实 PG 双连接并发）；
- drift 拒绝 in-flight participant entry（现有 `_load_verified_operation`
  hold 校验可观测：operation.hold_revision_snapshot < conversation.hold_revision
  -> 拒绝，正文/fence/checkpoint/operation/投影零变化）。

本文件为 I1 专项独立测试文件（不并入既有 fault/schema 大文件）；
全部使用真实 PostgreSQL + 独立 AsyncSession/连接。
并发等待：正向等待一律 `asyncio.wait_for(..., timeout=15)`；负向判别窗口
（锁序探测/插队判定的短超时）属刻意偏离，取值已在各用例注释标注阶段与预算。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.contexts.agent_workspace.domain.erasure import (
    ErasureFenceState,
    LegalHoldState,
)
from app.contexts.agent_workspace.domain.errors import LateBodyWriteRejectedError
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationLegalHoldModel,
    ConversationModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)
from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (
    WorkspaceErasureParticipant,
)

WORKSPACE_CORE_OWNER = "workspace.core.v1"
_AUDIT_SECRET = "test-audit-secret"
_AUDIT_SECRET_VERSION = 1

_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# 种子 helpers（与 db_session 同事务；teardown 由 composition autouse clean 兜底）
# ---------------------------------------------------------------------------


async def _seed_conversation(
    session,
    *,
    tenant_id: uuid.UUID | None = None,
    state: str = "active",
    hold_revision: int = 0,
    purge_revision: int = 0,
    purge_state: str = "not_scheduled",
    purge_after_delta: timedelta | None = None,
    title: str = "sensitive title",
) -> tuple[uuid.UUID, uuid.UUID]:
    """插入 conversation 行，返回 (tenant_id, conversation_id)。

    participant drift 测试需要 deleted + 已过 purge_after；纯 repository 测试
    用默认 active 即可。purge_after 为空时用过去 1 天（participant 语义）。
    """
    tid = tenant_id or uuid.uuid4()
    cid = uuid.uuid4()
    digest = "a" * 64
    purge_after = datetime.now(UTC) - (purge_after_delta or timedelta(days=1))
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, title, "
            "title_source, state, purge_after, purge_state, purge_revision, "
            "hold_revision, revision, created_at, updated_at) "
            "VALUES (:id, :tid, :creator, 'present', :digest, :title, 'none', "
            ":state, :purge_after, :purge_state, :purge_revision, "
            ":hold_revision, 1, now(), now())"
        ),
        {
            "id": cid,
            "tid": tid,
            "creator": tid,
            "digest": digest,
            "title": title,
            "state": state,
            "purge_after": purge_after,
            "purge_state": purge_state,
            "purge_revision": purge_revision,
            "hold_revision": hold_revision,
        },
    )
    return tid, cid


async def _seed_workspace_fence(session, tid, cid) -> None:
    digest = "b" * 64
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            "purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            "revision, created_at, updated_at) "
            "VALUES (:tid, :cid, :owner, 1, 'active', 0, 0, "
            "'{\"schema_version\": 1, \"sources\": {}}', :digest, 1, now(), now())"
        ),
        {"tid": tid, "cid": cid, "owner": WORKSPACE_CORE_OWNER, "digest": digest},
    )


async def _seed_operation_and_checkpoint(
    session, tid, cid, purge_revision: int, hold_revision_snapshot: int
) -> tuple[uuid.UUID, int]:
    """建 scheduled purge operation + pending workspace checkpoint。

    返回 (operation_id, operation_revision)。与 create_purge_operation 默认
    对齐（lease_epoch=0、revision=1）。
    """
    repo = AgentErasureRepository(session)
    operation = await repo.create_purge_operation(
        tenant_id=tid,
        conversation_id=cid,
        purge_revision=purge_revision,
        retention_policy_snapshot={"conversation_recovery_days": 30},
        hold_revision_snapshot=hold_revision_snapshot,
    )
    await repo.create_owner_checkpoint(
        tenant_id=tid,
        purge_operation_id=operation.id,
        owner_key=WORKSPACE_CORE_OWNER,
    )
    await session.flush()
    return operation.id, operation.revision


async def _conversation(session, cid) -> ConversationModel:
    return (
        (await session.execute(select(ConversationModel).where(ConversationModel.id == cid)))
        .scalars()
        .one()
    )


async def _holds(session, cid) -> list[ConversationLegalHoldModel]:
    rows = (
        await session.execute(
            select(ConversationLegalHoldModel).where(
                ConversationLegalHoldModel.conversation_id == cid
            )
        )
    ).scalars()
    return list(rows)


async def _hold_by_id(session, hold_id) -> ConversationLegalHoldModel:
    return (
        (
            await session.execute(
                select(ConversationLegalHoldModel).where(
                    ConversationLegalHoldModel.id == hold_id
                )
            )
        )
        .scalars()
        .one()
    )


async def _participant(session) -> WorkspaceErasureParticipant:
    return WorkspaceErasureParticipant(
        session,
        audit_secret=_AUDIT_SECRET,
        audit_secret_version=_AUDIT_SECRET_VERSION,
    )


async def _checkpoint_state(session, operation_id) -> str:
    row = (
        (
            await session.execute(
                select(PurgeOwnerCheckpointModel).where(
                    PurgeOwnerCheckpointModel.purge_operation_id == operation_id
                )
            )
        )
        .scalars()
        .one()
    )
    return row.state


async def _operation_state(session, operation_id) -> str:
    row = (
        (
            await session.execute(
                select(PurgeOperationModel).where(PurgeOperationModel.id == operation_id)
            )
        )
        .scalars()
        .one()
    )
    return row.state


async def _fence_state(session, cid) -> str:
    row = (
        await session.execute(
            text(
                "SELECT state FROM metaedu.agent_erasure_fences "
                "WHERE conversation_id = :cid AND owner_key = :owner"
            ),
            {"cid": cid, "owner": WORKSPACE_CORE_OWNER},
        )
    ).scalar_one()
    return row


async def _hold_revision(session, cid) -> int:
    conv = await _conversation(session, cid)
    return conv.hold_revision


# ---------------------------------------------------------------------------
# create / release 基本语义
# ---------------------------------------------------------------------------


async def test_create_bumps_hold_revision_in_caller_transaction(db_session):
    """用例 1：create 后 hold_revision 0→1，hold 行与 bump 同事务提交。"""
    tid, cid = await _seed_conversation(db_session)
    assert await _hold_revision(db_session, cid) == 0

    hold = await AgentErasureRepository(db_session).create_legal_hold(
        tenant_id=tid,
        conversation_id=cid,
        reason_code="litigation",
        purpose="ongoing case",
        actor_id=uuid.uuid4(),
    )
    # 同事务内已可见（未 commit 前 bump 与 hold 行均已 flush）。
    assert hold.state is LegalHoldState.ACTIVE
    assert hold.revision == 1
    assert await _hold_revision(db_session, cid) == 1

    await db_session.commit()
    assert await _hold_revision(db_session, cid) == 1
    assert len(await _holds(db_session, cid)) == 1


async def test_release_transitions_and_bumps(db_session):
    """用例 2：release 后 hold_revision 1→2，hold 精确 RELEASED + 字段正确。"""
    tid, cid = await _seed_conversation(db_session)
    repo = AgentErasureRepository(db_session)
    released_by = uuid.uuid4()
    hold = await repo.create_legal_hold(
        tenant_id=tid,
        conversation_id=cid,
        reason_code="litigation",
        purpose="ongoing case",
        actor_id=uuid.uuid4(),
    )
    assert hold.revision == 1

    released = await repo.release_legal_hold(
        tenant_id=tid,
        conversation_id=cid,
        hold_id=hold.id,
        expected_revision=1,
        released_by=released_by,
    )
    assert released.state is LegalHoldState.RELEASED
    assert released.revision == 2
    assert released.released_at is not None
    assert released.released_by == released_by
    assert await _hold_revision(db_session, cid) == 2

    await db_session.commit()
    row = await _hold_by_id(db_session, hold.id)
    assert row.state == LegalHoldState.RELEASED.value
    assert row.revision == 2
    assert row.released_at is not None
    assert row.released_by == released_by
    assert await _hold_revision(db_session, cid) == 2


# ---------------------------------------------------------------------------
# 并发（真实 PG 双连接；wait_for 阶段标注）
# ---------------------------------------------------------------------------


async def test_concurrent_creates_no_lost_update(session_factory):
    """用例 3：两个并发 create 各自 +1，最终 revision +2、两行均存在。"""
    async with session_factory() as seed:
        tid, cid = await _seed_conversation(seed)
        await seed.commit()

    async def _create_one():
        async with session_factory() as s:
            hold = await AgentErasureRepository(s).create_legal_hold(
                tenant_id=tid,
                conversation_id=cid,
                reason_code="litigation",
                purpose=f"case {uuid.uuid4()}",
                actor_id=uuid.uuid4(),
            )
            await s.commit()
            return hold.id

    ids = await asyncio.wait_for(
        asyncio.gather(_create_one(), _create_one()), timeout=_TIMEOUT
    )

    async with session_factory() as verify:
        assert await _hold_revision(verify, cid) == 2
        rows = await _holds(verify, cid)
        assert {r.id for r in rows} == set(ids)


async def test_concurrent_create_and_release_order_independent(session_factory):
    """用例 4：create 与另一 active hold 的 release 并发，最终 +2 且与提交顺序无关。"""
    async with session_factory() as seed:
        tid, cid = await _seed_conversation(seed)
        repo = AgentErasureRepository(seed)
        hold_a = await repo.create_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            reason_code="litigation",
            purpose="case A",
            actor_id=uuid.uuid4(),
        )
        hold_b = await repo.create_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            reason_code="litigation",
            purpose="case B",
            actor_id=uuid.uuid4(),
        )
        await seed.commit()
    assert hold_a.revision == 1 and hold_b.revision == 1

    async def _release():
        async with session_factory() as s:
            await AgentErasureRepository(s).release_legal_hold(
                tenant_id=tid,
                conversation_id=cid,
                hold_id=hold_a.id,
                expected_revision=1,
                released_by=uuid.uuid4(),
            )
            await s.commit()

    async def _create():
        async with session_factory() as s:
            await AgentErasureRepository(s).create_legal_hold(
                tenant_id=tid,
                conversation_id=cid,
                reason_code="litigation",
                purpose="case C",
                actor_id=uuid.uuid4(),
            )
            await s.commit()

    await asyncio.wait_for(asyncio.gather(_release(), _create()), timeout=_TIMEOUT)

    async with session_factory() as verify:
        assert await _hold_revision(verify, cid) == 4
        rows = await _holds(verify, cid)
        released = [r for r in rows if r.id == hold_a.id]
        assert len(released) == 1 and released[0].state == LegalHoldState.RELEASED.value
        assert sum(1 for r in rows if r.state == LegalHoldState.ACTIVE.value) == 2


async def test_release_holds_conversation_lock_blocks_late_create(session_factory):
    """用例 5：锁序判别——release 已持 Conversation 锁 + hold 行锁期间，
    后到 create 必须阻塞排队，不得插队提交。"""
    async with session_factory() as seed:
        tid, cid = await _seed_conversation(seed)
        hold = await AgentErasureRepository(seed).create_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            reason_code="litigation",
            purpose="case A",
            actor_id=uuid.uuid4(),
        )
        await seed.commit()
    async with session_factory() as verify:
        assert await _hold_revision(verify, cid) == 1

    # 负向判别窗口：create 必须在窗口内完成才判「插队」——窗口取 1.0s（实测
    # create+commit 约 0.25-0.3s，留 3 倍余量；慢环境冷启动可再放宽）。

    async with session_factory() as blocker:
        # T1：模拟 release 先持 Conversation 行锁 + hold 行锁（与 release
        # primitive 同锁序：Conversation FOR UPDATE → hold FOR UPDATE）。
        await blocker.execute(
            text(
                "SELECT id FROM metaedu.agent_conversations "
                "WHERE tenant_id = :tid AND id = :cid FOR UPDATE"
            ),
            {"tid": tid, "cid": cid},
        )
        await blocker.execute(
            text(
                "SELECT id FROM metaedu.agent_conversation_legal_holds "
                "WHERE id = :hid FOR UPDATE"
            ),
            {"hid": hold.id},
        )

        async def _late_create():
            async with session_factory() as s:
                await AgentErasureRepository(s).create_legal_hold(
                    tenant_id=tid,
                    conversation_id=cid,
                    reason_code="litigation",
                    purpose="late case",
                    actor_id=uuid.uuid4(),
                )
                await s.commit()

        late_task = asyncio.create_task(_late_create())
        # T2 必须被 T1 的 Conversation 锁挡住（release 持锁期间不得插队）。
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                asyncio.shield(late_task), timeout=1.0
            )
        assert not late_task.done() or late_task.cancelled()

        # T1 在已持锁前提下完成 release（同事务 re-lock 无副作用）并提交。
        await AgentErasureRepository(blocker).release_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            hold_id=hold.id,
            expected_revision=1,
            released_by=uuid.uuid4(),
        )
        await blocker.commit()

        # T2 排队完成：create 在 release 提交后落库，最终 +2。
        await asyncio.wait_for(late_task, timeout=_TIMEOUT)

    async with session_factory() as verify:
        assert await _hold_revision(verify, cid) == 3
        rows = await _holds(verify, cid)
        assert len(rows) == 2


async def test_release_takes_conversation_lock_before_hold_lock(session_factory):
    """用例 5b：锁序判别——release primitive 必须先取 Conversation 行锁。

    观测构造（无 AB-BA、确定性）：T1 只持 hold 行锁（不取 Conversation）；
    T2 调 release primitive；T3 循环探测 Conversation FOR UPDATE——
    - 正确实现：T2 持有 Conversation、阻塞于 hold 行 → T3 探测必然超时；
    - 变异（release 不取 Conversation 锁）：T2 阻塞于 hold 行但未持有
      Conversation → T3 探测全部成功 → 判失败。
    """
    async with session_factory() as seed:
        tid, cid = await _seed_conversation(seed)
        hold = await AgentErasureRepository(seed).create_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            reason_code="litigation",
            purpose="lock order case",
            actor_id=uuid.uuid4(),
        )
        await seed.commit()

    async def _do_release():
        async with session_factory() as s:
            await AgentErasureRepository(s).release_legal_hold(
                tenant_id=tid,
                conversation_id=cid,
                hold_id=hold.id,
                expected_revision=1,
                released_by=uuid.uuid4(),
            )
            await s.commit()

    async with session_factory() as t1:
        await t1.execute(
            text(
                "SELECT id FROM metaedu.agent_conversation_legal_holds "
                "WHERE id = :hid FOR UPDATE"
            ),
            {"hid": hold.id},
        )
        release_task = asyncio.create_task(_do_release())
        blocked = False
        for _ in range(24):
            try:
                async with session_factory() as t3:
                    await asyncio.wait_for(
                        t3.execute(
                            text(
                                "SELECT id FROM metaedu.agent_conversations "
                                "WHERE tenant_id = :tid AND id = :cid FOR UPDATE"
                            ),
                            {"tid": tid, "cid": cid},
                        ),
                        timeout=0.25,
                    )
                await asyncio.sleep(0.05)  # 未阻塞：release 可能尚未进入，继续探测
            except TimeoutError:
                blocked = True
                break
        if not blocked and not release_task.done():
            release_task.cancel()
            pytest.fail("release 未持有 Conversation 锁（探测从未阻塞，锁序变异）")
        # 释放 hold 行锁 → release 完成。
        await t1.commit()
        await asyncio.wait_for(release_task, timeout=_TIMEOUT)

    async with session_factory() as verify:
        assert await _hold_revision(verify, cid) == 2
        row = await _hold_by_id(verify, hold.id)
        assert row.state == LegalHoldState.RELEASED.value


# ---------------------------------------------------------------------------
# drift 拒绝 in-flight participant entry（pre-I2 可测项）
# ---------------------------------------------------------------------------


async def _seed_drift_entry_scenario(session, *, final_hold_revision: int):
    """建 deleted+expired 会话（带正文）+ fence + operation(snapshot=0) +
    checkpoint，再经 I1 producer 把 hold_revision 推进到 final_hold_revision。

    返回 (tid, cid, operation_id, op_revision)。
    """
    tid, cid = await _seed_conversation(
        session,
        state="deleted",
        purge_revision=1,
        purge_state="scheduled",
    )
    await _seed_workspace_fence(session, tid, cid)
    operation_id, op_revision = await _seed_operation_and_checkpoint(
        session, tid, cid, purge_revision=1, hold_revision_snapshot=0
    )
    repo = AgentErasureRepository(session)
    hold = await repo.create_legal_hold(
        tenant_id=tid,
        conversation_id=cid,
        reason_code="litigation",
        purpose="drift case",
        actor_id=uuid.uuid4(),
    )
    if final_hold_revision == 2:
        await repo.release_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            hold_id=hold.id,
            expected_revision=1,
            released_by=uuid.uuid4(),
        )
    assert await _hold_revision(session, cid) == final_hold_revision
    await session.commit()
    return tid, cid, operation_id, op_revision


async def _assert_entry_rejected_zero_writes(
    db_session, session_factory, *, final_hold_revision: int
):
    """旧 snapshot（0）的 participant entry 必须被 hold drift 拒绝，零变化。"""
    tid, cid, operation_id, op_revision = await _seed_drift_entry_scenario(
        db_session, final_hold_revision=final_hold_revision
    )
    title_before = (await _conversation(db_session, cid)).title

    with pytest.raises(ValueError, match="hold_revision"):
        participant = await _participant(db_session)
        await participant.erase_conversation_body(
            tenant_id=tid,
            conversation_id=cid,
            purge_revision=1,
            purge_operation_id=operation_id,
            expected_operation_revision=op_revision,
        )
    await db_session.rollback()

    async with session_factory() as verify:
        conv = await _conversation(verify, cid)
        assert conv.title == title_before
        assert conv.purge_state == "scheduled"
        assert conv.hold_revision == final_hold_revision
        assert await _fence_state(verify, cid) == ErasureFenceState.ACTIVE.value
        assert await _checkpoint_state(verify, operation_id) == "pending"
        assert await _operation_state(verify, operation_id) == "scheduled"


async def test_create_drift_rejects_participant_entry(db_session, session_factory):
    """用例 6：create 后 drift——旧 operation snapshot 调真实 participant entry
    必须被拒绝，正文/fence/checkpoint/operation/投影零变化。"""
    await _assert_entry_rejected_zero_writes(db_session, session_factory, final_hold_revision=1)


async def test_release_drift_rejects_participant_entry(db_session, session_factory):
    """用例 7：release 后 drift——同样拒绝旧 snapshot 的 participant entry。"""
    await _assert_entry_rejected_zero_writes(db_session, session_factory, final_hold_revision=2)


# ---------------------------------------------------------------------------
# fail closed 矩阵（零写、零 bump）
# ---------------------------------------------------------------------------


async def test_missing_conversation_fails_closed_zero_write(db_session):
    """用例 8a：Conversation 缺失 -> fail closed，零写零 bump。"""
    tid = uuid.uuid4()
    repo = AgentErasureRepository(db_session)
    with pytest.raises(LateBodyWriteRejectedError):
        await repo.create_legal_hold(
            tenant_id=tid,
            conversation_id=uuid.uuid4(),
            reason_code="litigation",
            purpose="ghost",
            actor_id=uuid.uuid4(),
        )
    rows = (
        await db_session.execute(
            select(ConversationLegalHoldModel).where(
                ConversationLegalHoldModel.tenant_id == tid
            )
        )
    ).scalars()
    assert list(rows) == []


async def test_cross_tenant_and_cross_conversation_release_fail_closed(db_session):
    """用例 8b：跨 tenant / 跨 conversation 的 hold release -> fail closed，零 bump。

    跨 tenant：用 tenant A 的 conversation 寻址 tenant B 的 hold——
    Conversation-first 锁序下先按 (A, conversation) 查 conversation（存在），
    再查 hold（属于 B）→ tenant 不符 fail closed。
    """
    tid, cid = await _seed_conversation(db_session)
    other_tid, other_cid = await _seed_conversation(db_session)
    _, third_cid = await _seed_conversation(db_session, tenant_id=other_tid)
    repo = AgentErasureRepository(db_session)
    hold = await repo.create_legal_hold(
        tenant_id=other_tid,
        conversation_id=other_cid,
        reason_code="litigation",
        purpose="foreign case",
        actor_id=uuid.uuid4(),
    )
    await db_session.commit()
    assert await _hold_revision(db_session, other_cid) == 1

    with pytest.raises(ValueError, match="tenant"):
        await repo.release_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            hold_id=hold.id,
            expected_revision=1,
            released_by=uuid.uuid4(),
        )
    with pytest.raises(ValueError, match="conversation"):
        await repo.release_legal_hold(
            tenant_id=other_tid,
            conversation_id=third_cid,
            hold_id=hold.id,
            expected_revision=1,
            released_by=uuid.uuid4(),
        )
    await db_session.rollback()

    row = await _hold_by_id(db_session, hold.id)
    assert row.state == LegalHoldState.ACTIVE.value
    assert row.revision == 1
    assert await _hold_revision(db_session, other_cid) == 1
    assert await _hold_revision(db_session, third_cid) == 0


async def test_stale_and_duplicate_release_fail_closed(db_session):
    """用例 9：stale revision 与重复 release 均 fail closed，第二次不得 bump。"""
    tid, cid = await _seed_conversation(db_session)
    repo = AgentErasureRepository(db_session)
    hold = await repo.create_legal_hold(
        tenant_id=tid,
        conversation_id=cid,
        reason_code="litigation",
        purpose="case",
        actor_id=uuid.uuid4(),
    )
    await db_session.commit()

    with pytest.raises(ValueError, match="revision"):
        await repo.release_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            hold_id=hold.id,
            expected_revision=99,
            released_by=uuid.uuid4(),
        )
    await db_session.rollback()
    assert await _hold_revision(db_session, cid) == 1

    await repo.release_legal_hold(
        tenant_id=tid,
        conversation_id=cid,
        hold_id=hold.id,
        expected_revision=1,
        released_by=uuid.uuid4(),
    )
    await db_session.commit()
    assert await _hold_revision(db_session, cid) == 2

    with pytest.raises(ValueError, match="active"):
        await repo.release_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            hold_id=hold.id,
            expected_revision=2,
            released_by=uuid.uuid4(),
        )
    await db_session.rollback()
    assert await _hold_revision(db_session, cid) == 2
    row = await _hold_by_id(db_session, hold.id)
    assert row.revision == 2


async def test_release_missing_conversation_and_missing_hold_fail_closed(db_session):
    """用例 8c：release 侧 missing Conversation / missing hold -> fail closed 零写零 bump。"""
    tid, cid = await _seed_conversation(db_session)
    await db_session.commit()
    repo = AgentErasureRepository(db_session)
    with pytest.raises(LateBodyWriteRejectedError):
        await repo.release_legal_hold(
            tenant_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            hold_id=uuid.uuid4(),
            expected_revision=1,
            released_by=uuid.uuid4(),
        )
    with pytest.raises(ValueError, match="missing"):
        await repo.release_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            hold_id=uuid.uuid4(),
            expected_revision=1,
            released_by=uuid.uuid4(),
        )
    assert await _hold_revision(db_session, cid) == 0


async def test_outer_transaction_rollback_rolls_back_hold_and_bump(session_factory):
    """用例 10：外层事务 rollback——create/release 的 hold 变更与 bump 一起回滚。"""
    async with session_factory() as seed:
        tid, cid = await _seed_conversation(seed)
        await seed.commit()

    async with session_factory() as tx:
        await AgentErasureRepository(tx).create_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            reason_code="litigation",
            purpose="rolled back case",
            actor_id=uuid.uuid4(),
        )
        await tx.rollback()

    async with session_factory() as verify:
        assert await _hold_revision(verify, cid) == 0
        assert await _holds(verify, cid) == []

    async with session_factory() as setup:
        hold = await AgentErasureRepository(setup).create_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            reason_code="litigation",
            purpose="release rollback case",
            actor_id=uuid.uuid4(),
        )
        await setup.commit()

    async with session_factory() as tx:
        await AgentErasureRepository(tx).release_legal_hold(
            tenant_id=tid,
            conversation_id=cid,
            hold_id=hold.id,
            expected_revision=1,
            released_by=uuid.uuid4(),
        )
        await tx.rollback()

    async with session_factory() as verify:
        assert await _hold_revision(verify, cid) == 1
        row = await _hold_by_id(verify, hold.id)
        assert row.state == LegalHoldState.ACTIVE.value
        assert row.revision == 1
        assert row.released_at is None
