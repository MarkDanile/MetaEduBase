"""R1-S2 S2-A 正文 writer fence 接线：惰性建 fence / 非 active 拒绝 / AC3 race。

Spec §6.2 正文 writer 协议：每个 Conversation-owned 正文 writer 在同一事务
Guard -> Conversation row -> owner lock -> fence FOR UPDATE -> 仅 active 写正文。
本 Slice 接两个正文写注入点（title/create 留 S2-C）：

- 用户正文 ``reserve_user_turn``（repository.py）：行锁 + state 校验后取
  workspace.core.v1 owner lock + fence FOR UPDATE。
- assistant 正文 ``project_assistant_message``（bridge_repository.py）：
  ``_lock_projection_conversation`` 之后同 helper。

fence 惰性首写建立（Spec §4.2「新正文 writer 在首次写事务中创建缺失 fence」）：
无 fence 的历史/新会话首次写正文自动建 active fence 并放行；fence 一旦进入
erasing/blocked/erased（purge 进行中/已完成）一律 ``LateBodyWriteRejectedError``
（stable code ``late_body_write_rejected``），不得复活正在清除路径上的正文。
owner_version 漂移（registry 已升级）fail closed。
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from app.composition.agent_control_plane import (
    AgentBridgeDispatcher,
    ConversationExecutionCoordinator,
)
from app.composition.agent_erasure_locks import acquire_owner_lock
from app.composition.agent_erasure_registry import owner_registry
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    RunStatus,
    SnapshotClassification,
    TerminalResult,
)
from app.contexts.agent_execution.infrastructure.models import (
    ExecutionOutboxModel,
)
from app.contexts.agent_workspace.application.bridge import (
    AgentWorkspaceBridgeService,
)
from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.application.dto import (
    MessagePartInput,
    TurnCommand,
)
from app.contexts.agent_workspace.domain import (
    ErasureFenceState,
    LateBodyWriteRejectedError,
    MessagePartType,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    MessageModel,
    MessagePartModel,
)
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
    StaticOutputReader,
    bootstrap_workspace,
    create_baseline_fences,
    turn_command,
)

pytestmark = pytest.mark.asyncio

_OWNER_KEY = "workspace.core.v1"


def _text_command(text: str) -> TurnCommand:
    return TurnCommand(
        client_message_id=uuid.uuid4(),
        parts=(MessagePartInput(type=MessagePartType.TEXT, text=text),),
        agent_definition_version_id=uuid.UUID("10000000-0000-0000-0000-000000000004"),
    )


async def _fence_to_state(
    session,
    conversation_id,
    target: ErasureFenceState,
    *,
    ack_digest: str | None = None,
):
    """按锁序（owner lock -> fence FOR UPDATE CAS）推进 workspace.core fence。"""
    tenant_id = await _tenant_id(session, conversation_id)
    await acquire_owner_lock(
        session,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=_OWNER_KEY,
    )
    repo = AgentErasureRepository(session)
    fence = await repo.get_fence_for_update(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=_OWNER_KEY,
    )
    assert fence is not None
    assert fence.state is ErasureFenceState.ACTIVE
    erasing = await repo.transition_fence_state(
        tenant_id=tenant_id,
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
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=_OWNER_KEY,
        expected_state=ErasureFenceState.ERASING,
        expected_revision=erasing.revision,
        new_state=target,
        purge_revision=1,
        hold_revision=0,
        ack_digest=ack_digest,
    )


async def _count_body_parts(
    session, conversation_id, *, message_kind: str | None = None
) -> int:
    """该会话 Message 的 MessagePart 正文行数（经 Message.conversation_id 关联）。

    ``message_kind`` 限定时只计该 kind（如 assistant_output），用于区分用户正文
    与 assistant 正文——构造 completed Run 的 submit_turn 会写一条用户正文。
    """
    stmt = (
        select(func.count())
        .select_from(MessagePartModel)
        .join(MessageModel, MessagePartModel.message_id == MessageModel.id)
        .where(MessageModel.conversation_id == conversation_id)
    )
    if message_kind is not None:
        stmt = stmt.where(MessageModel.message_kind == message_kind)
    return await session.scalar(stmt)


async def _tenant_id(db_session, conversation_id) -> uuid.UUID:
    row = await db_session.get(ConversationModel, conversation_id)
    assert row is not None
    return row.tenant_id


async def _actor_id(db_session, conversation_id) -> uuid.UUID:
    row = await db_session.get(ConversationModel, conversation_id)
    assert row is not None
    return row.created_by


async def test_reserve_user_turn_creates_fence_on_first_body_write(db_session):
    """惰性建 fence（Spec §4.2）+ fencing token 同步 + checkpoint 原子推进
    （Spec §6.2 第 3/4 步）：无 fence 的新会话首次写用户正文，同事务建立
    active fence、同步到 Conversation 当前 token、推进 last_body_write_at 与
    fence revision，并放行正文写。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    tenant_id = await _tenant_id(db_session, conversation_id)
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")

    result = await service.reserve_user_turn(
        tenant_id=tenant_id,
        actor_id=await _actor_id(db_session, conversation_id),
        conversation_id=conversation_id,
        command=_text_command("hello fence"),
    )
    assert result.idempotent_replay is False

    fence = await AgentErasureRepository(db_session).get_fence_for_update(
        tenant_id=tenant_id, conversation_id=conversation_id, owner_key=_OWNER_KEY
    )
    assert fence is not None
    assert fence.state is ErasureFenceState.ACTIVE
    conversation = await db_session.get(ConversationModel, conversation_id)
    assert conversation is not None
    # 新 fence 同步到 Conversation 当前 fencing token（新会话均为 0）。
    assert fence.purge_revision == conversation.purge_revision
    assert fence.hold_revision == conversation.hold_revision
    # 正文写 checkpoint 原子推进：last_body_write_at 已落、fence revision 推进。
    # S2-C 复审后：create（rev1）-> 初始 title ingress 推进（rev2，bootstrap 带
    # title）-> 首次 body 写推进（rev3）。verdict 不再推进 revision（P2-6）。
    assert fence.last_body_write_at is not None
    assert fence.revision == 3  # create(1) -> title ingress(2) -> body write(3)


async def test_reserve_user_turn_with_contradictory_token_rejected(db_session):
    """fencing token 矛盾 fail closed（Spec §5.1/§6.2 第 3 步）：active fence 的
    purge_revision 高于 Conversation 当前值（fence 携带 purge token 但 state
    仍 active 且 Conversation 无对应 purge——矛盾状态）-> 拒绝正文写。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    tenant_id = await _tenant_id(db_session, conversation_id)
    actor_id = await _actor_id(db_session, conversation_id)
    await create_baseline_fences(
        db_session, tenant_id=tenant_id, conversation_id=conversation_id
    )
    # 直接抬 fence purge_revision 超过 Conversation（构造矛盾 token）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET purge_revision = 99 "
            "WHERE tenant_id = :tenant_id AND conversation_id = :conversation_id "
            "AND owner_key = :owner_key"
        ),
        {
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "owner_key": _OWNER_KEY,
        },
    )
    await db_session.commit()

    with pytest.raises(LateBodyWriteRejectedError):
        await AgentWorkspaceService(
            db_session, cursor_secret="test-secret"
        ).reserve_user_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            command=_text_command("should be rejected"),
        )
    await db_session.rollback()
    assert await _count_body_parts(db_session, conversation_id) == 0


async def test_reserve_user_turn_with_erasing_fence_rejected(db_session):
    """fence erasing（purge fencing 已开始）-> 拒绝用户正文写。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    tenant_id = await _tenant_id(db_session, conversation_id)
    actor_id = await _actor_id(db_session, conversation_id)
    await create_baseline_fences(
        db_session, tenant_id=tenant_id, conversation_id=conversation_id
    )
    await _fence_to_state(db_session, conversation_id, ErasureFenceState.ERASING)
    await db_session.commit()

    with pytest.raises(LateBodyWriteRejectedError):
        await AgentWorkspaceService(
            db_session, cursor_secret="test-secret"
        ).reserve_user_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            command=_text_command("should be rejected"),
        )
    await db_session.rollback()
    # 未写入正文。
    assert await _count_body_parts(db_session, conversation_id) == 0


async def test_reserve_user_turn_with_erased_fence_rejected(db_session):
    """fence erased（owner ACK 完成）-> 拒绝用户正文写（终态）。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    tenant_id = await _tenant_id(db_session, conversation_id)
    actor_id = await _actor_id(db_session, conversation_id)
    await create_baseline_fences(
        db_session, tenant_id=tenant_id, conversation_id=conversation_id
    )
    await _fence_to_state(
        db_session, conversation_id, ErasureFenceState.ERASED, ack_digest="a" * 64
    )
    await db_session.commit()

    with pytest.raises(LateBodyWriteRejectedError):
        await AgentWorkspaceService(
            db_session, cursor_secret="test-secret"
        ).reserve_user_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            command=_text_command("should be rejected"),
        )


async def test_reserve_user_turn_with_blocked_fence_rejected(db_session):
    """fence blocked（owner 暂停 purge）-> 拒绝用户正文写（清除路径上的状态）。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    tenant_id = await _tenant_id(db_session, conversation_id)
    actor_id = await _actor_id(db_session, conversation_id)
    await create_baseline_fences(
        db_session, tenant_id=tenant_id, conversation_id=conversation_id
    )
    await _fence_to_state(db_session, conversation_id, ErasureFenceState.BLOCKED)
    await db_session.commit()

    with pytest.raises(LateBodyWriteRejectedError):
        await AgentWorkspaceService(
            db_session, cursor_secret="test-secret"
        ).reserve_user_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            command=_text_command("should be rejected"),
        )


async def test_reserve_user_turn_with_owner_version_drift_rejected(db_session):
    """fence owner_version 与已安装 registry 不一致 -> fail closed，不基于过期
    能力视图写正文。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    tenant_id = await _tenant_id(db_session, conversation_id)
    actor_id = await _actor_id(db_session, conversation_id)
    await create_baseline_fences(
        db_session, tenant_id=tenant_id, conversation_id=conversation_id
    )
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET owner_version = 99 "
            "WHERE tenant_id = :tenant_id AND conversation_id = :conversation_id "
            "AND owner_key = :owner_key"
        ),
        {
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "owner_key": _OWNER_KEY,
        },
    )
    await db_session.commit()

    with pytest.raises(LateBodyWriteRejectedError):
        await AgentWorkspaceService(
            db_session, cursor_secret="test-secret"
        ).reserve_user_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            command=_text_command("should be rejected"),
        )


async def test_writer_fence_purge_win_race_body_not_resurrected(
    db_session, session_factory
):
    """R1-AC3：writer 与 purge 共用 owner lock/fence transaction。purge 先把
    fence 推进 erasing 并提交；writer（reserve_user_turn）在 owner lock 上等待，
    purge 提交后 writer 必须 fail closed，正文不得复活。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    tenant_id = await _tenant_id(db_session, conversation_id)
    actor_id = await _actor_id(db_session, conversation_id)
    await create_baseline_fences(
        db_session, tenant_id=tenant_id, conversation_id=conversation_id
    )
    await db_session.commit()

    fence_transitioned = asyncio.Event()
    release_purge = asyncio.Event()

    async def purge_fences_conversation():
        async with session_factory() as session, session.begin():
            # purge 模拟锁序：Conversation row -> owner lock -> fence CAS，
            # 与 writer 仅靠 row/owner/fence 锁串行。
            await AgentWorkspaceBridgeService(session).lock_owned_conversation(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
                include_deleted=True,
            )
            await _fence_to_state(session, conversation_id, ErasureFenceState.ERASING)
            fence_transitioned.set()
            await release_purge.wait()

    async def writer():
        async with session_factory() as session, session.begin():
            return await AgentWorkspaceService(
                session, cursor_secret="test-secret"
            ).reserve_user_turn(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
                command=_text_command("racing body write"),
            )

    purge_task = asyncio.create_task(purge_fences_conversation())
    writer_task: asyncio.Task | None = None
    try:
        await asyncio.wait_for(fence_transitioned.wait(), timeout=5)
        writer_task = asyncio.create_task(writer())
        # purge 持有 Conversation row/owner/fence 锁：writer 不得插队完成。
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(writer_task), timeout=0.5)
        release_purge.set()
        await asyncio.wait_for(purge_task, timeout=5)
        # purge 已提交 erasing fence：writer 继续后必须 fail closed。
        with pytest.raises(LateBodyWriteRejectedError):
            await asyncio.wait_for(writer_task, timeout=5)
    finally:
        release_purge.set()
        for task in (purge_task, writer_task):
            if task is not None and not task.done():
                task.cancel()

    # 正文未复活：无任何 MessagePart 写入该会话。
    async with session_factory() as session:
        assert await _count_body_parts(session, conversation_id) == 0


async def test_baseline_backfill_idempotent_over_lazy_writer_fence(db_session):
    """backfill 幂等（Spec §4.2/§10.3）：正文写已惰性建 workspace.core fence 后，
    create_baseline_fences 补齐其余 owner 不得与该惰性 fence PK 冲突；最终
    workspace.core fence 仍唯一且 active。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    tenant_id = await _tenant_id(db_session, conversation_id)
    actor_id = await _actor_id(db_session, conversation_id)
    # 首次正文写惰性建 workspace.core fence。
    await AgentWorkspaceService(
        db_session, cursor_secret="test-secret"
    ).reserve_user_turn(
        tenant_id=tenant_id,
        actor_id=actor_id,
        conversation_id=conversation_id,
        command=_text_command("lazy fence"),
    )
    await db_session.commit()

    # backfill 补齐全部 owner：对惰性 fence 幂等，不 PK 冲突。
    await create_baseline_fences(
        db_session, tenant_id=tenant_id, conversation_id=conversation_id
    )
    await db_session.commit()

    repo = AgentErasureRepository(db_session)
    fences = await repo.list_fences(
        tenant_id=tenant_id, conversation_id=conversation_id
    )
    core = [f for f in fences if f.owner_key == _OWNER_KEY]
    assert len(core) == 1
    assert core[0].state is ErasureFenceState.ACTIVE
    assert len(fences) == len(owner_registry())


async def test_create_fence_on_non_active_fence_fails_closed(db_session):
    """create_fence 不得覆盖非 active fence（清除路径上的状态）：fence 已
    erasing 时重建请求 fail closed，不把既有行当作可安全重建。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    tenant_id = await _tenant_id(db_session, conversation_id)
    await create_baseline_fences(
        db_session, tenant_id=tenant_id, conversation_id=conversation_id
    )
    await _fence_to_state(db_session, conversation_id, ErasureFenceState.ERASING)
    await db_session.commit()

    from app.composition.agent_erasure_registry import OwnerRegistryChangedError

    with pytest.raises(OwnerRegistryChangedError):
        await AgentErasureRepository(db_session).create_fence_under_owner_lock(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=_OWNER_KEY,
        )


async def _completed_run_with_pending_output(
    db_session, session_factory, *, content: bytes
):
    """构造 completed Run + pending execution outbox（assistant 正文待投影）。

    复用 test_output_bridge 的 _completed_run 模式：submit_turn -> dispatch_turn
    -> start_run -> RUNNING -> commit_terminal（产生 pending output outbox）。
    返回 (conversation_id, run, terminal_message_id, outbox)。
    """
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "bridge fence"),
        launch=launch,
    )
    await db_session.commit()
    run = await AgentBridgeDispatcher(
        session_factory, worker_id="writer-fence-setup"
    ).dispatch_turn(event_id=receipt.event_id)
    assert run is not None
    terminal_message_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        started, _ = await ConversationExecutionCoordinator(session).start_run(
            tenant_id=TENANT_ID,
            run_id=run.id,
            expected_revision=1,
        )
        running, _ = await RunCoordinator(session).transition_run(
            tenant_id=TENANT_ID,
            run_id=run.id,
            expected_status=RunStatus.STARTING,
            expected_revision=started.status_revision,
            target_status=RunStatus.RUNNING,
            summary="Runtime started",
        )
        completed, _, _ = await RunCoordinator(session).commit_terminal(
            tenant_id=TENANT_ID,
            run_id=run.id,
            expected_status=RunStatus.RUNNING,
            expected_revision=running.status_revision,
            result=TerminalResult(
                outcome="completed",
                code="ok",
                reason="answer ready",
                output_ref=f"terminal-output-{run.id}",
                output_digest=hashlib.sha256(content).hexdigest(),
                output_size=len(content),
                output_media_type="text/markdown",
                output_classification=SnapshotClassification.INTERNAL,
                terminal_message_id=terminal_message_id,
            ),
            # R1-S4-C（S4-C C2）：COMPLETED 写 publish outbox 需带真实 epoch。
            producer_purge_revision=(
                await session.scalar(
                    select(ConversationModel.purge_revision).where(
                        ConversationModel.tenant_id == TENANT_ID,
                        ConversationModel.id == conversation_id,
                    )
                )
            ),
        )
    outbox = await db_session.scalar(
        select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.aggregate_id == run.id
        )
    )
    assert outbox is not None
    return conversation_id, completed, terminal_message_id, outbox


async def test_project_assistant_message_creates_fence_on_first_body_write(
    db_session, session_factory
):
    """assistant 正文注入点（bridge_repository.project_assistant_message）：
    惰性首写建 fence。无 fence 的会话首次投影 assistant 正文，同事务建立
    workspace.core.v1 active fence 并放行正文写。"""
    content = b"# assistant body"
    conversation_id, _, _, outbox = await _completed_run_with_pending_output(
        db_session, session_factory, content=content
    )

    dispatcher = AgentBridgeDispatcher(
        session_factory,
        worker_id="writer-fence-output",
        output_reader=StaticOutputReader(content),
    )
    assert await dispatcher.dispatch_output(event_id=outbox.id) is True

    tenant_id = await _tenant_id(db_session, conversation_id)
    fence = await AgentErasureRepository(db_session).get_fence_for_update(
        tenant_id=tenant_id, conversation_id=conversation_id, owner_key=_OWNER_KEY
    )
    assert fence is not None
    assert fence.state is ErasureFenceState.ACTIVE
    # assistant 正文已写入。
    assert (
        await _count_body_parts(
            db_session, conversation_id, message_kind="assistant_output"
        )
        >= 1
    )


async def test_project_assistant_message_with_erasing_fence_rejected(
    db_session, session_factory
):
    """assistant 正文注入点：fence erasing（purge fencing 进行中），迟到的
    publish_requested 事件被消费时必须 fail closed
    （LateBodyWriteRejectedError），assistant 正文不得复活（MessagePart 零写入）。"""
    content = b"# late assistant body"
    conversation_id, _, _, outbox = await _completed_run_with_pending_output(
        db_session, session_factory, content=content
    )
    tenant_id = await _tenant_id(db_session, conversation_id)
    await create_baseline_fences(
        db_session, tenant_id=tenant_id, conversation_id=conversation_id
    )
    await _fence_to_state(db_session, conversation_id, ErasureFenceState.ERASING)
    await db_session.commit()

    dispatcher = AgentBridgeDispatcher(
        session_factory,
        worker_id="writer-fence-output-late",
        output_reader=StaticOutputReader(content),
    )
    with pytest.raises(LateBodyWriteRejectedError):
        await dispatcher.dispatch_output(event_id=outbox.id)

    # assistant 正文未复活：该会话无任何 assistant_output 正文
    # （构造 completed Run 的 submit_turn 用户正文不算）。
    async with session_factory() as session:
        assert (
            await _count_body_parts(
                session, conversation_id, message_kind="assistant_output"
            )
            == 0
        )


async def test_write_after_restore_aligns_stale_active_fence(db_session):
    """restore 推进 Conversation purge_revision（S2-B）后，恢复会话的 active
    fence token 仍是 delete 时的旧值（落后）。首次写正文必须把 stale active
    fence 单调对齐到 Conversation 当前 token 并放行——不得把「恢复后可写」
    误判为 stale 拒绝（Codex P1-1 核心产品路径）。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    deleted_at = datetime(2026, 1, 1, tzinfo=UTC)
    await ConversationExecutionCoordinator(db_session).delete_conversation(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        expected_revision=1,
        now=deleted_at,
    )
    await create_baseline_fences(
        db_session, tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    await ConversationExecutionCoordinator(db_session).restore_conversation(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        expected_revision=2,
        now=deleted_at + timedelta(days=1),
    )
    await db_session.commit()
    conversation = await db_session.get(ConversationModel, conversation_id)
    assert conversation is not None
    # restore 已推进 Conversation purge_revision（delete +1、restore +1）。
    assert conversation.purge_revision == 2

    # 恢复后写正文：stale active fence 单调对齐并放行。
    result = await AgentWorkspaceService(
        db_session, cursor_secret="test-secret"
    ).reserve_user_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=_text_command("after restore"),
    )
    assert result.idempotent_replay is False

    fence = await AgentErasureRepository(db_session).get_fence_for_update(
        tenant_id=TENANT_ID, conversation_id=conversation_id, owner_key=_OWNER_KEY
    )
    assert fence is not None
    assert fence.state is ErasureFenceState.ACTIVE
    # fence token 已对齐到 Conversation 当前值。
    assert fence.purge_revision == conversation.purge_revision
    assert fence.last_body_write_at is not None


async def test_writer_win_race_purge_waits_then_takes_over(
    db_session, session_factory
):
    """R1-AC3 writer-win（Codex P1-3）：writer 通过 active fence check 后在
    commit 前暂停（持有 Conversation 行锁 + owner lock + fence 行锁）；purge
    CAS 必须在 owner/fence 锁上等待，不得插队。writer 提交正文后 purge 才获锁
    推进 erasing——writer 在 fence check 后写入的正文被 purge 接管，此后任何
    新正文写都被 fence 拒绝（不复活）。

    与 purge-win race（test_writer_fence_purge_win_race_body_not_resurrected）
    互补：那条证明 purge 先赢时 writer 被拒；这条证明 writer 先持锁时 purge
    被串行、writer 提交后 purge 接管，两个方向都不丢正确性。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    tenant_id = await _tenant_id(db_session, conversation_id)
    actor_id = await _actor_id(db_session, conversation_id)
    await create_baseline_fences(
        db_session, tenant_id=tenant_id, conversation_id=conversation_id
    )
    await db_session.commit()

    writer_holds_locks = asyncio.Event()
    release_writer = asyncio.Event()

    async def writer():
        async with session_factory() as session, session.begin():
            # writer 锁序：Conversation 行锁 -> owner lock -> fence FOR UPDATE
            # （require_body_write_fence_for_update），通过 active check。
            await AgentWorkspaceBridgeService(session).lock_owned_conversation(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
                include_deleted=False,
            )
            await AgentErasureRepository(
                session
            ).require_body_write_fence_for_update(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=_OWNER_KEY,
            )
            # fence check 已通过、行锁在握；在 commit 前暂停，模拟「writer 过
            # check 后与 purge 竞争」的窗口。
            writer_holds_locks.set()
            await release_writer.wait()
            # 窗口后提交正文（fence 仍 active，writer 合法持有锁）。
            await AgentWorkspaceService(
                session, cursor_secret="test-secret"
            ).reserve_user_turn(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
                command=_text_command("writer-win body"),
            )

    async def purge():
        async with session_factory() as session, session.begin():
            await AgentWorkspaceBridgeService(session).lock_owned_conversation(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
                include_deleted=True,
            )
            await _fence_to_state(session, conversation_id, ErasureFenceState.ERASING)

    writer_task = asyncio.create_task(writer())
    purge_task: asyncio.Task | None = None
    try:
        # writer 已持 Conversation 行锁 + owner lock + fence 行锁。
        await asyncio.wait_for(writer_holds_locks.wait(), timeout=5)
        purge_task = asyncio.create_task(purge())
        # purge 在 Conversation 行锁/owner lock 上被 writer 阻塞，不得插队完成。
        await asyncio.sleep(0.5)
        assert not purge_task.done()
        # writer 提交正文后释放锁；purge 获锁推进 erasing。
        release_writer.set()
        await asyncio.wait_for(writer_task, timeout=5)
        await asyncio.wait_for(purge_task, timeout=5)
    finally:
        release_writer.set()
        for task in (writer_task, purge_task):
            if task is not None and not task.done():
                task.cancel()

    # writer 在 fence check 后提交的正文已落库（writer-win，合法）。
    async with session_factory() as session:
        assert await _count_body_parts(session, conversation_id) == 1
        # purge 已接管：fence 进入 erasing，此后新正文写被拒（不复活）。
        fence = await AgentErasureRepository(session).get_fence_for_update(
            tenant_id=tenant_id, conversation_id=conversation_id, owner_key=_OWNER_KEY
        )
        assert fence is not None
        assert fence.state is ErasureFenceState.ERASING


async def test_concurrent_lazy_writer_and_backfill_no_pk_conflict(
    db_session, session_factory
):
    """P2-4（Codex）：惰性 writer 与受控 backfill 并发建同一 fence 时，双方经
    公开入口（require_body_write_fence_for_update /
    create_fence_under_owner_lock）自带 owner lock 串行，不得双 insert 撞唯一
    索引；最终 fence 唯一且 active。"""
    conversation_id, _, _ = await bootstrap_workspace(db_session)
    tenant_id = await _tenant_id(db_session, conversation_id)
    actor_id = await _actor_id(db_session, conversation_id)
    await db_session.commit()

    async def lazy_writer():
        async with session_factory() as session, session.begin():
            await AgentWorkspaceService(
                session, cursor_secret="test-secret"
            ).reserve_user_turn(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=conversation_id,
                command=_text_command("concurrent lazy"),
            )

    async def backfill():
        async with session_factory() as session, session.begin():
            await AgentErasureRepository(
                session
            ).create_fence_under_owner_lock(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=_OWNER_KEY,
            )

    # 并发执行：任一顺序都必须成功（owner lock 串行 + 幂等）。
    results = await asyncio.gather(
        lazy_writer(), backfill(), return_exceptions=True
    )
    errors = [r for r in results if isinstance(r, Exception)]
    assert not errors, f"concurrent fence creation raised: {errors!r}"

    async with session_factory() as session:
        fence = await AgentErasureRepository(session).get_fence_for_update(
            tenant_id=tenant_id, conversation_id=conversation_id, owner_key=_OWNER_KEY
        )
        assert fence is not None
        assert fence.state is ErasureFenceState.ACTIVE
