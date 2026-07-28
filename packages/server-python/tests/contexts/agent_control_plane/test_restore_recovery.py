"""R1-S2 restore 恢复截止：deadline / owner ACK / purge 状态 fail-closed 契约。

恢复规则（Spec §3 冻结）：仅 owner 可恢复，且必须满足 ``now < purge_after``、
``purged_at IS NULL``、无 owner fence 进入 ``erasing/erased``；
``purge_state=running|completed`` 拒绝普通恢复；``blocked/failed`` 不阻止，
但也不能绕过 30 天截止。fence 与时间检查必须在 Guard -> Conversation row ->
owner advisory lock -> fence FOR UPDATE 锁序下与同事务完成，与 purge 竞争时
不得复活正文。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.composition.agent_control_plane import (
    ConversationExecutionCoordinator,
    ConversationExecutionGuard,
)
from app.composition.agent_erasure_locks import acquire_owner_lock
from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.domain import (
    ConversationPurgedError,
    ConversationPurgeInProgressError,
    ConversationRecoveryExpiredError,
    ConversationState,
    ErasureFenceState,
    PurgeState,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import ConversationModel
from tests.conftest import TEST_DB_URL
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
    bootstrap_workspace,
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
    fence = await repo.create_fence(
        tenant_id=TENANT_ID, conversation_id=conversation_id, owner_key=_OWNER_KEY
    )
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


async def test_restore_deleted_before_deadline_succeeds(db_session):
    """基线：deleted + purge_after 在未来 -> restore 清 purge 调度并恢复。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    deleted = await _delete(db_session, conversation_id, now=_DELETED_AT)
    assert deleted.purge_after == _DELETED_AT + timedelta(days=30)

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


async def test_restore_with_blocked_fence_still_restores(db_session):
    """blocked fence（owner 暂停）不阻止恢复；30 天截止时间依旧生效兜底。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await _fence_to_state(db_session, conversation_id, ErasureFenceState.BLOCKED)
    await db_session.commit()

    restored = await _restore(
        db_session, conversation_id, now=_DELETED_AT + timedelta(days=1)
    )
    assert restored.state is ConversationState.ACTIVE


async def test_restore_with_running_purge_state_fails_closed(db_session):
    """Conversation 行 purge_state=running -> 拒绝普通恢复。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
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


async def test_restore_and_purge_fence_race_serialized_by_owner_lock(
    db_session, session_factory
):
    """restore/purge race：purge 持锁推进 fence 时 restore 阻塞；purge 提交
    erasing 后 restore 必须 fail closed，不得复活正文。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, conversation_id, now=_DELETED_AT)
    await db_session.commit()

    fence_transitioned = asyncio.Event()
    release_purge = asyncio.Event()

    async def purge_fences_conversation():
        async with session_factory() as session, session.begin():
            # 模拟 purge saga 的锁序：Guard -> owner lock -> fence CAS。
            await ConversationExecutionGuard().acquire(
                session, tenant_id=TENANT_ID, conversation_id=conversation_id
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
        # purge 事务持有 Guard/owner lock：restore 不得插队完成。
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


async def test_restore_deadline_boundary_with_frozen_clock(db_session):
    """冻结时钟 30 天边界：第 29 天可恢复；第 30 天（含）起拒绝。"""
    day29_id, _, _ = await bootstrap_workspace(db_session)
    await _delete(db_session, day29_id, now=_DELETED_AT)
    restored = await _restore(
        db_session, day29_id, now=_DELETED_AT + timedelta(days=29)
    )
    assert restored.state is ConversationState.ACTIVE

    service = AgentWorkspaceService(db_session)
    day30, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title="day 30 boundary"
    )
    await _delete(db_session, day30.conversation.id, now=_DELETED_AT)
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
    await db_session.commit()
    with pytest.raises(ConversationRecoveryExpiredError):
        await _restore(
            db_session,
            day31.conversation.id,
            now=_DELETED_AT + timedelta(days=31),
        )
    await db_session.rollback()


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
