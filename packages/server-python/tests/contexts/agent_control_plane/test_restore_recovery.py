"""R1-S2 restore 恢复截止：deadline / owner fence 完整性 / purge CAS fail-closed 契约。

恢复规则（Spec §3/§4.2 + R1-S2 复审收口）：

1. 仅 owner 可恢复，且必须满足 ``now < purge_after``、``purged_at IS NULL``；
   ``state=deleted`` 且 ``purge_after IS NULL`` 无法证明在恢复窗口内 -> fail closed。
2. 预期 owner fence 集合（registry 全部固定 owner）必须完整且全部 ``active``：
   - 任一 fence ``erased`` -> conversation_purged（终态优先）；
   - 任一 fence ``blocked/erasing`` -> conversation_purge_in_progress；
   - 任一预期 fence 缺失、出现未知 owner 或 owner_version 漂移 -> fail closed
     （conversation_restore_not_allowed；没有查到 fence 不是隐式安全，Spec §4.2）。
3. ``purge_state=running|completed`` 拒绝普通恢复。
4. 恢复成功通过 CAS 取消尚未开始的 purge operation 并推进 ``purge_revision``
   （旧 purge lease/revision 随后失效，Spec §3-3）；``hold_revision`` 由
   Conversation 行锁 + CAS 谓词兜底。scheduled operation 若已有 owner
   checkpoint 进入 erasing/blocked/acked，说明清除实际已开始 -> fail closed。
5. 生产裁决时间在 Guard -> Conversation row -> owner lock -> fence FOR UPDATE
   之后读数据库 ``clock_timestamp()``；测试经 ``now`` 注入时钟。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.composition.agent_control_plane import (
    ConversationExecutionCoordinator,
)
from app.composition.agent_erasure_locks import acquire_owner_lock
from app.composition.agent_erasure_registry import owner_registry
from app.contexts.agent_workspace.application.bridge import (
    AgentWorkspaceBridgeService,
)
from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.domain import (
    ConversationPurgedError,
    ConversationPurgeInProgressError,
    ConversationRecoveryExpiredError,
    ConversationRestoreNotAllowedError,
    ConversationState,
    ErasureFenceState,
    PurgeOperationState,
    PurgeState,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import ConversationModel
from app.shared.infrastructure.seed import DEFAULT_TENANT_ID
from tests.conftest import TEST_DB_URL
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
    bootstrap_workspace,
    create_baseline_fences,
    create_baseline_fences_via_engine,
)

pytestmark = pytest.mark.asyncio

_OWNER_KEY = "workspace.core.v1"
_DELETED_AT = datetime(2026, 1, 1, tzinfo=UTC)


async def _delete(
    session: AsyncSession, conversation_id, *, now: datetime | None = None
):
    return await ConversationExecutionCoordinator(session).delete_conversation(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        expected_revision=1,
        now=now,
    )


async def _restore(
    session: AsyncSession, conversation_id, *, now: datetime | None = None
):
    return await ConversationExecutionCoordinator(session).restore_conversation(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        expected_revision=2,
        now=now,
    )


async def _create_baseline_fences(
    session: AsyncSession, conversation_id, *, skip_owner: str | None = None
):
    """本模块 TENANT_ID 的 baseline fence（等价 backfill 已覆盖的基线）。"""
    await create_baseline_fences(
        session,
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        skip_owner=skip_owner,
    )


async def _fence_to_state(
    session: AsyncSession,
    conversation_id,
    target: ErasureFenceState,
    *,
    ack_digest: str | None = None,
):
    """按锁序（owner lock -> fence FOR UPDATE CAS）推进 workspace.core fence。"""
    await acquire_owner_lock(
        session,
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        owner_key=_OWNER_KEY,
    )
    repo = AgentErasureRepository(session)
    fence = await repo.get_fence_for_update(
        tenant_id=TENANT_ID, conversation_id=conversation_id, owner_key=_OWNER_KEY
    )
    assert fence is not None
    assert fence.state is ErasureFenceState.ACTIVE
    erasing = await repo.transition_fence_state(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        owner_key=_OWNER_KEY,
        expected_state=ErasureFenceState.ACTIVE,
        expected_revision=fence.revision,
        new_state=ErasureFenceState.ERASING,
        purge_revision=1,
        hold_revision=0,
    )
    if target is ErasureFenceState.ERASING:
        return erasing
    return await repo.transition_fence_state(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        owner_key=_OWNER_KEY,
        expected_state=ErasureFenceState.ERASING,
        expected_revision=erasing.revision,
        new_state=target,
        purge_revision=1,
        hold_revision=0,
        ack_digest=ack_digest,
    )


async def _assert_still_deleted(session: AsyncSession, conversation_id) -> None:
    row = await session.get(ConversationModel, conversation_id)
    assert row is not None
    assert row.state == ConversationState.DELETED.value


async def test_restore_deleted_before_deadline_succeeds(db_session):
    """基线：fence 集合完整且全部 active + purge_after 在未来 -> restore 清
    purge 调度并恢复。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    deleted = await _delete(db_session, conversation_id, now=_DELETED_AT)
    assert deleted.purge_after == _DELETED_AT + timedelta(days=30)
    await _create_baseline_fences(db_session, conversation_id)

    restored = await _restore(
        db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
    )
    assert restored.state is ConversationState.ACTIVE
    assert restored.purge_after is None
    assert restored.purge_state is PurgeState.NOT_SCHEDULED


async def test_restore_after_deadline_fails_closed_without_side_effects(db_session):
    """now >= purge_after -> 拒绝恢复，且 purge_after/purge_state 不被清除。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    deleted = await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    await db_session.commit()

    with pytest.raises(ConversationRecoveryExpiredError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=31)
        )
    await db_session.rollback()

    row = await db_session.get(ConversationModel, conversation_id)
    assert row is not None
    assert row.state == ConversationState.DELETED.value
    assert row.purge_after == deleted.purge_after
    assert row.purge_state == PurgeState.SCHEDULED.value


async def test_restore_with_erasing_fence_fails_closed(db_session):
    """任一 owner fence 进入 erasing（purge 已开始 ACK）-> 拒绝普通恢复。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    await _fence_to_state(db_session, conversation_id, ErasureFenceState.ERASING)
    await db_session.commit()

    with pytest.raises(ConversationPurgeInProgressError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )


async def test_restore_with_erased_fence_fails_closed(db_session):
    """任一 owner fence 已 erased（owner ACK 完成）-> 视为已 purge，拒绝恢复。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    await _fence_to_state(
        db_session,
        conversation_id,
        ErasureFenceState.ERASED,
        ack_digest="a" * 64,
    )
    await db_session.commit()

    with pytest.raises(ConversationPurgedError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )


async def test_restore_with_blocked_fence_fails_closed(db_session):
    """blocked fence（owner 暂停 purge）同样拒绝恢复：purge 未终结，恢复会复活
    正在清除路径上的正文。只有全部 fence active 才允许普通恢复。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    await _fence_to_state(db_session, conversation_id, ErasureFenceState.BLOCKED)
    await db_session.commit()

    with pytest.raises(ConversationPurgeInProgressError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )
    await db_session.rollback()
    await _assert_still_deleted(db_session, conversation_id)


async def test_restore_with_missing_owner_fence_fails_closed(db_session):
    """预期 owner fence 缺失（集合不完整）-> fail closed：没有查到 fence 不是
    隐式安全（Spec §4.2），不得恢复，且 Conversation 保持 deleted。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(
        db_session, conversation_id, skip_owner="workspace.transport.v1"
    )
    await db_session.commit()

    with pytest.raises(ConversationRestoreNotAllowedError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )
    await db_session.rollback()
    await _assert_still_deleted(db_session, conversation_id)


async def test_restore_without_any_fence_fails_closed(db_session):
    """全新/历史会话没有任何 fence（create 不建 fence、backfill 未覆盖）->
    缺失按 fail closed 处理，不得当作「无 purge 记录 = 安全」放行。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await db_session.commit()

    with pytest.raises(ConversationRestoreNotAllowedError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )
    await db_session.rollback()
    await _assert_still_deleted(db_session, conversation_id)


async def test_restore_with_unknown_owner_fence_fails_closed(db_session):
    """出现 registry 之外的 owner fence（未知 owner）-> fail closed（Spec §4.2）。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            " purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            " revision, created_at, updated_at) "
            "VALUES (:tenant_id, :conversation_id, 'unknown.owner.v9', 1, "
            " 'active', 0, 0, '{}'::jsonb, :digest, 1, now(), now())"
        ),
        {
            "tenant_id": TENANT_ID,
            "conversation_id": conversation_id,
            "digest": "b" * 64,
        },
    )
    await db_session.commit()

    with pytest.raises(ConversationRestoreNotAllowedError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )
    await db_session.rollback()
    await _assert_still_deleted(db_session, conversation_id)


async def test_restore_with_owner_version_drift_fails_closed(db_session):
    """fence 记录的 owner_version 与已安装 registry 不一致（registry 已升级）
    -> fail closed，不基于过期能力视图恢复（Spec §4.2）。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET owner_version = 99 "
            "WHERE tenant_id = :tenant_id AND conversation_id = :conversation_id "
            "AND owner_key = :owner_key"
        ),
        {
            "tenant_id": TENANT_ID,
            "conversation_id": conversation_id,
            "owner_key": _OWNER_KEY,
        },
    )
    await db_session.commit()

    with pytest.raises(ConversationRestoreNotAllowedError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )
    await db_session.rollback()
    await _assert_still_deleted(db_session, conversation_id)


async def test_restore_deleted_without_purge_after_fails_closed(db_session):
    """state=deleted 且 purge_after IS NULL：无法证明 now < purge_after ->
    fail closed，不得当作「无截止 = 可恢复」放行。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    await db_session.execute(
        update(ConversationModel)
        .where(ConversationModel.id == conversation_id)
        .values(purge_after=None)
    )
    await db_session.commit()

    with pytest.raises(ConversationRecoveryExpiredError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )
    await db_session.rollback()
    await _assert_still_deleted(db_session, conversation_id)


async def test_restore_with_running_purge_state_fails_closed(db_session):
    """Conversation 行 purge_state=running -> 拒绝普通恢复。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    await db_session.execute(
        update(ConversationModel)
        .where(ConversationModel.id == conversation_id)
        .values(purge_state=PurgeState.RUNNING.value)
    )
    await db_session.commit()

    with pytest.raises(ConversationPurgeInProgressError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )


async def test_restore_with_completed_purge_state_fails_closed(db_session):
    """Conversation 行 purge_state=completed -> 拒绝普通恢复。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    await db_session.execute(
        update(ConversationModel)
        .where(ConversationModel.id == conversation_id)
        .values(purge_state=PurgeState.COMPLETED.value)
    )
    await db_session.commit()

    with pytest.raises(ConversationPurgeInProgressError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )


async def test_restore_with_purged_row_fails_closed(db_session):
    """基线：purged_at 非空 -> 拒绝恢复（现有行为保持）。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    await db_session.execute(
        update(ConversationModel)
        .where(ConversationModel.id == conversation_id)
        .values(purged_at=_DELETED_AT + timedelta(days=30))
    )
    await db_session.commit()

    with pytest.raises(ConversationPurgedError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )


async def test_restore_win_cancels_scheduled_operation_and_stale_revision_cannot_revive(
    db_session, session_factory
):
    """restore-win / Spec §3-3：restore 先持锁完成，CAS 取消尚未开始的 purge
    operation（置 cancelled 终态、保留审计行）并推进 purge_revision；后到的
    purge worker 重读 operation 必须看到 cancelled 并放弃（fence 保持
    active），以旧 purge_revision 重启 purge 不得复活。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    deleted = await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    operation = await AgentErasureRepository(db_session).create_purge_operation(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=deleted.purge_revision,
        retention_policy_snapshot={"conversation_recovery_days": 30},
        hold_revision_snapshot=0,
    )
    await db_session.commit()

    restored = await _restore(
        db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
    )
    assert restored.state is ConversationState.ACTIVE
    # 旧 purge lease/revision 失效：purge_revision 单调推进。
    assert restored.purge_revision == deleted.purge_revision + 1
    await db_session.commit()

    # purge worker 后到：FOR UPDATE 重读 operation -> cancelled 终态，不得推进。
    async with session_factory() as session, session.begin():
        repo = AgentErasureRepository(session)
        stale = await repo.get_purge_operation_for_update(
            tenant_id=TENANT_ID, purge_operation_id=operation.id
        )
        assert stale is not None
        assert stale.state is PurgeOperationState.CANCELLED
        assert stale.next_retry_at is None
        fences = await repo.list_fences_for_update(
            tenant_id=TENANT_ID, conversation_id=conversation_id
        )
        assert len(fences) == len(owner_registry())
        assert all(fence.state is ErasureFenceState.ACTIVE for fence in fences)
        row = await session.get(ConversationModel, conversation_id)
        assert row is not None
        assert row.state == ConversationState.ACTIVE.value

    # 以旧 purge_revision 重启 purge：revision 唯一约束 fail closed，不得复活。
    async with session_factory() as session, session.begin():
        with pytest.raises(IntegrityError):
            await AgentErasureRepository(session).create_purge_operation(
                tenant_id=TENANT_ID,
                conversation_id=conversation_id,
                purge_revision=deleted.purge_revision,
                retention_policy_snapshot={},
                hold_revision_snapshot=0,
            )


async def test_restore_with_started_owner_checkpoint_fails_closed(db_session):
    """scheduled operation 的 owner checkpoint 已进入 erasing：operation 尚未
    标记开始但清除实际已开始，状态自相矛盾 -> fail closed，不得恢复，
    operation 保持 scheduled（由 saga 恢复路径处理，不在 restore 内改写）。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    deleted = await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    repo = AgentErasureRepository(db_session)
    operation = await repo.create_purge_operation(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=deleted.purge_revision,
        retention_policy_snapshot={},
        hold_revision_snapshot=0,
    )
    checkpoint = await repo.create_owner_checkpoint(
        tenant_id=TENANT_ID,
        purge_operation_id=operation.id,
        owner_key=_OWNER_KEY,
    )
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners "
            "SET state = 'erasing' WHERE id = :id"
        ),
        {"id": checkpoint.id},
    )
    await db_session.commit()

    with pytest.raises(ConversationPurgeInProgressError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )
    await db_session.rollback()
    await _assert_still_deleted(db_session, conversation_id)
    persisted = await AgentErasureRepository(
        db_session
    ).get_purge_operation_for_update(
        tenant_id=TENANT_ID, purge_operation_id=operation.id
    )
    assert persisted is not None
    assert persisted.state is PurgeOperationState.SCHEDULED


async def test_restore_with_failed_owner_checkpoint_fails_closed(db_session):
    """scheduled operation 的 owner checkpoint 为 failed：failed 蕴含已发生过
    一次擦除尝试（pending->erasing->failed），并非「尚未开始」。与
    erasing/blocked/acked 一样属清除路径上的状态 -> fail closed，不得恢复，
    operation 保持 scheduled 不被误改（留 saga 恢复路径处理）。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    deleted = await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    repo = AgentErasureRepository(db_session)
    operation = await repo.create_purge_operation(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=deleted.purge_revision,
        retention_policy_snapshot={},
        hold_revision_snapshot=0,
    )
    checkpoint = await repo.create_owner_checkpoint(
        tenant_id=TENANT_ID,
        purge_operation_id=operation.id,
        owner_key=_OWNER_KEY,
    )
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners "
            "SET state = 'failed' WHERE id = :id"
        ),
        {"id": checkpoint.id},
    )
    await db_session.commit()

    with pytest.raises(ConversationPurgeInProgressError):
        await _restore(
            db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
        )
    await db_session.rollback()
    await _assert_still_deleted(db_session, conversation_id)
    persisted = await AgentErasureRepository(
        db_session
    ).get_purge_operation_for_update(
        tenant_id=TENANT_ID, purge_operation_id=operation.id
    )
    assert persisted is not None
    assert persisted.state is PurgeOperationState.SCHEDULED


async def test_delete_deleted_at_and_purge_after_share_one_clock_sample(db_session):
    """delete：deleted_at 与 purge_after 必须来自同一时钟采样
    （purge_after = deleted_at + 30 天），不得分别取应用/数据库时钟。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    deleted = await _delete(db_session, conversation_id, now=_DELETED_AT)
    assert deleted.deleted_at == _DELETED_AT
    assert deleted.purge_after == deleted.deleted_at + timedelta(days=30)


async def test_delete_production_default_uses_database_clock(db_session):
    """delete 生产默认（不注入时钟）：deleted_at 取自数据库 clock_timestamp，
    且与 purge_after 同源。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    before = await db_session.scalar(select(func.clock_timestamp()))
    deleted = await _delete(db_session, conversation_id)
    after = await db_session.scalar(select(func.clock_timestamp()))
    assert before is not None and after is not None
    assert deleted.deleted_at is not None
    assert before <= deleted.deleted_at <= after
    assert deleted.purge_after == deleted.deleted_at + timedelta(days=30)


async def test_purge_win_race_restore_fails_closed_after_fence_erasing(
    db_session, session_factory
):
    """purge-win race：purge participant（不取 Guard，仅 Conversation row ->
    owner lock -> fence CAS）先把 fence 推进到 erasing；restore 在锁上等待，
    purge 提交后 restore 必须 fail closed，不得复活正文。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, conversation_id)
    await db_session.commit()

    fence_transitioned = asyncio.Event()
    release_purge = asyncio.Event()

    async def purge_fences_conversation():
        async with session_factory() as session, session.begin():
            # purge 模拟锁序（不经 B1 Guard 提前串行）：Conversation row ->
            # owner lock -> fence CAS，与 restore 仅靠 row/owner/fence 锁串行。
            await AgentWorkspaceBridgeService(session).lock_owned_conversation(
                tenant_id=TENANT_ID,
                actor_id=ACTOR_ID,
                conversation_id=conversation_id,
                include_deleted=True,
            )
            await _fence_to_state(
                session, conversation_id, ErasureFenceState.ERASING
            )
            fence_transitioned.set()
            await release_purge.wait()

    async def restore():
        async with session_factory() as session, session.begin():
            return await ConversationExecutionCoordinator(
                session
            ).restore_conversation(
                tenant_id=TENANT_ID,
                actor_id=ACTOR_ID,
                conversation_id=conversation_id,
                expected_revision=2,
                now=_DELETED_AT + timedelta(days=1),
            )

    purge_task = asyncio.create_task(purge_fences_conversation())
    restore_task: asyncio.Task | None = None
    try:
        await asyncio.wait_for(fence_transitioned.wait(), timeout=5)
        restore_task = asyncio.create_task(restore())
        # purge 事务持有 Conversation row/owner/fence 锁：restore 不得插队完成。
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(restore_task), timeout=0.5)
        release_purge.set()
        await asyncio.wait_for(purge_task, timeout=5)
        # purge 已提交 erasing fence：restore 继续后必须 fail closed。
        with pytest.raises(ConversationPurgeInProgressError):
            await asyncio.wait_for(restore_task, timeout=5)
    finally:
        # 失败路径也必须释放锁并回收任务，避免 teardown TRUNCATE 死锁。
        release_purge.set()
        for task in (purge_task, restore_task):
            if task is not None and not task.done():
                task.cancel()


async def test_restore_waiting_across_deadline_fails_closed(
    db_session, session_factory
):
    """跨截止等待：请求在截止前进入、行锁等待跨过截止后，restore 必须按锁后
    采样的数据库时钟 fail closed（不得用进入请求时的应用时钟放行）。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    db_now = await db_session.scalar(select(func.clock_timestamp()))
    assert db_now is not None
    # 截止点设在真实数据库时钟 3 秒后：请求进入时（约 db_now）仍在窗口内。
    deleted = await _delete(
        db_session,
        conversation_id,
        now=db_now - timedelta(days=30) + timedelta(seconds=3),
    )
    assert deleted.purge_after is not None
    assert db_now < deleted.purge_after
    await _create_baseline_fences(db_session, conversation_id)
    await db_session.commit()

    row_locked = asyncio.Event()
    release_lock = asyncio.Event()

    async def hold_row_lock():
        async with session_factory() as session, session.begin():
            await AgentWorkspaceBridgeService(session).lock_owned_conversation(
                tenant_id=TENANT_ID,
                actor_id=ACTOR_ID,
                conversation_id=conversation_id,
                include_deleted=True,
            )
            row_locked.set()
            await release_lock.wait()

    async def restore():
        async with session_factory() as session, session.begin():
            # 生产路径：不注入时钟，裁决时间必须在锁后读 DB clock_timestamp。
            return await ConversationExecutionCoordinator(
                session
            ).restore_conversation(
                tenant_id=TENANT_ID,
                actor_id=ACTOR_ID,
                conversation_id=conversation_id,
                expected_revision=2,
            )

    lock_task = asyncio.create_task(hold_row_lock())
    restore_task: asyncio.Task | None = None
    try:
        await asyncio.wait_for(row_locked.wait(), timeout=5)
        restore_task = asyncio.create_task(restore())
        # 行锁等待 6 秒，跨过 db_now + 3s 的截止点；restore 不得提前完成。
        await asyncio.sleep(6)
        assert not restore_task.done()
        release_lock.set()
        # 锁后采样已过截止 -> 必须 fail closed；若以进入时间裁决则会错误放行。
        with pytest.raises(ConversationRecoveryExpiredError):
            await asyncio.wait_for(restore_task, timeout=5)
    finally:
        release_lock.set()
        for task in (lock_task, restore_task):
            if task is not None and not task.done():
                task.cancel()


async def test_restore_deadline_boundary_with_frozen_clock(db_session):
    """冻结时钟 30 天边界：第 29 天可恢复；第 30 天（含）起拒绝。"""
    day29_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, day29_id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, day29_id)
    restored = await _restore(
        db_session, day29_id, now=_DELETED_AT + timedelta(days=29)
    )
    assert restored.state is ConversationState.ACTIVE

    service = AgentWorkspaceService(db_session)
    day30, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title="day 30 boundary"
    )
    await _delete(db_session, day30.conversation.id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, day30.conversation.id)
    await db_session.commit()
    with pytest.raises(ConversationRecoveryExpiredError):
        await _restore(
            db_session,
            day30.conversation.id,
            now=_DELETED_AT + timedelta(days=30),
        )
    await db_session.rollback()

    day31, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title="day 31 boundary"
    )
    await _delete(db_session, day31.conversation.id, now=_DELETED_AT)
    await _create_baseline_fences(db_session, day31.conversation.id)
    await db_session.commit()
    with pytest.raises(ConversationRecoveryExpiredError):
        await _restore(
            db_session,
            day31.conversation.id,
            now=_DELETED_AT + timedelta(days=31),
        )
    await db_session.rollback()


async def _create_baseline_fences_via_engine(conversation_id: str) -> None:
    """API 测试的 fence 基线：经独立 engine 以生产 create_fence 路径建立。"""
    await create_baseline_fences_via_engine(
        tenant_id=DEFAULT_TENANT_ID, conversation_id=uuid.UUID(conversation_id)
    )


async def test_restore_api_maps_recovery_expired_to_409(client, auth_headers):
    """router：恢复截止 -> 409 + conversation_recovery_expired 稳定错误码。"""
    created = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        json={"title": "expired restore"},
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    deleted = await client.delete(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers={**auth_headers, "If-Match": "1"},
    )
    assert deleted.status_code == 202, deleted.text
    await _create_baseline_fences_via_engine(conversation_id)

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE metaedu.agent_conversations "
                    "SET purge_after = now() - interval '1 day' "
                    "WHERE id = :id"
                ),
                {"id": conversation_id},
            )
    finally:
        await engine.dispose()

    restored = await client.post(
        f"/api/v1/agent-workspace/conversations/{conversation_id}/restore",
        headers={**auth_headers, "If-Match": "2"},
    )
    assert restored.status_code == 409, restored.text
    assert restored.json()["detail"]["code"] == "conversation_recovery_expired"


async def test_restore_api_maps_purge_in_progress_to_409(client, auth_headers):
    """router：purge 进行中 -> 409 + conversation_purge_in_progress 稳定错误码。"""
    created = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        json={"title": "purge in progress restore"},
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    deleted = await client.delete(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers={**auth_headers, "If-Match": "1"},
    )
    assert deleted.status_code == 202, deleted.text
    await _create_baseline_fences_via_engine(conversation_id)

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE metaedu.agent_conversations "
                    "SET purge_state = 'running' "
                    "WHERE id = :id"
                ),
                {"id": conversation_id},
            )
    finally:
        await engine.dispose()

    restored = await client.post(
        f"/api/v1/agent-workspace/conversations/{conversation_id}/restore",
        headers={**auth_headers, "If-Match": "2"},
    )
    assert restored.status_code == 409, restored.text
    assert restored.json()["detail"]["code"] == "conversation_purge_in_progress"


async def test_restore_api_maps_restore_not_allowed_to_409(client, auth_headers):
    """router：fence 账本不完整（无 fence）-> 409 + conversation_restore_not_allowed。"""
    created = await client.post(
        "/api/v1/agent-workspace/conversations",
        headers=auth_headers,
        json={"title": "restore without fences"},
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    deleted = await client.delete(
        f"/api/v1/agent-workspace/conversations/{conversation_id}",
        headers={**auth_headers, "If-Match": "1"},
    )
    assert deleted.status_code == 202, deleted.text

    restored = await client.post(
        f"/api/v1/agent-workspace/conversations/{conversation_id}/restore",
        headers={**auth_headers, "If-Match": "2"},
    )
    assert restored.status_code == 409, restored.text
    assert restored.json()["detail"]["code"] == "conversation_restore_not_allowed"
