from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import func, select, update

from app.composition.agent_control_plane import (
    AgentBridgeDispatcher,
    ConversationExecutionCoordinator,
    DispatchPolicy,
    PoisonedIntegrationEventError,
)
from app.contexts.agent_execution.application.bridge import AgentExecutionBridgeService
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    OutputPublishState,
    RunStatus,
    SnapshotClassification,
    TerminalResult,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    ExecutionOutboxModel,
)
from app.contexts.agent_workspace.domain import (
    MessageContentState,
    WorkspaceIntegrationConflictError,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    MessageModel,
    MessagePartModel,
)
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
    FailingOutputReader,
    StaticOutputReader,
    bootstrap_workspace,
    turn_command,
)

pytestmark = pytest.mark.asyncio


async def _completed_run(db_session, session_factory, *, content: bytes):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "complete output"),
        launch=launch,
    )
    await db_session.commit()
    run = await AgentBridgeDispatcher(
        session_factory, worker_id="output-setup"
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
        )
    return conversation_id, completed, terminal_message_id


async def test_terminal_and_publish_outbox_are_atomic_then_project_once(
    db_session, session_factory
):
    content = b"# Durable answer"
    _, run, message_id = await _completed_run(
        db_session, session_factory, content=content
    )
    outbox = await db_session.scalar(
        select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.aggregate_id == run.id
        )
    )
    assert outbox is not None
    assert outbox.status == "pending"
    assert run.output_publish_state is OutputPublishState.PENDING

    dispatcher = AgentBridgeDispatcher(
        session_factory,
        worker_id="output-worker",
        output_reader=StaticOutputReader(content),
    )
    assert await dispatcher.dispatch_output(event_id=outbox.id) is True

    persisted_run = await db_session.get(AgentRunModel, run.id)
    assert persisted_run is not None
    await db_session.refresh(persisted_run)
    assert persisted_run.output_publish_state == OutputPublishState.PUBLISHED.value
    message = await db_session.get(MessageModel, message_id)
    assert message is not None
    assert message.origin_run_id == run.id
    assert message.content_state == MessageContentState.VISIBLE.value


async def test_output_dead_letter_can_retry_with_same_event_and_message_ids(
    db_session, session_factory
):
    content = b"recoverable output"
    _, run, message_id = await _completed_run(
        db_session, session_factory, content=content
    )
    outbox = await db_session.scalar(
        select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.aggregate_id == run.id
        )
    )
    assert outbox is not None
    assert outbox.status == "pending"
    failing = AgentBridgeDispatcher(
        session_factory,
        worker_id="failing-output",
        output_reader=FailingOutputReader(),
        policy=DispatchPolicy(max_attempts=1),
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        await failing.dispatch_output(event_id=outbox.id)

    await db_session.refresh(outbox)
    failed_run = await db_session.get(AgentRunModel, run.id)
    assert failed_run is not None
    await db_session.refresh(failed_run)
    assert outbox.status == "dead_letter"
    assert failed_run.output_publish_state == OutputPublishState.DEAD_LETTER.value

    await ConversationExecutionCoordinator(db_session).retry_output_projection(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        run_id=run.id,
    )
    await db_session.commit()
    recovered = AgentBridgeDispatcher(
        session_factory,
        worker_id="recovered-output",
        output_reader=StaticOutputReader(content),
    )
    assert await recovered.dispatch_output(event_id=outbox.id) is True
    message = await db_session.get(MessageModel, message_id)
    assert message is not None
    assert message.origin_run_id == run.id


async def test_suppressed_tombstone_stores_controlled_reason_code_not_free_text(
    db_session, session_factory
):
    """P2-5（Codex）：suppressed tombstone 的 redacted_reason 只存受控 reason
    code，自由文本（可能含正文/提示词/secret）不落库。白名单 code 原样保留；
    非白名单输入归一到通用 code，不反射原始内容。"""
    content = b"sensitive body"
    _, run, message_id = await _completed_run(
        db_session, session_factory, content=content
    )
    secret_reason = "user prompt: 我的身份证号 110101199001011234, delete this"
    await ConversationExecutionCoordinator(db_session).suppress_output_projection(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        run_id=run.id,
        reason=secret_reason,
    )
    await db_session.commit()

    message = await db_session.get(MessageModel, message_id)
    assert message is not None
    assert message.content_state == MessageContentState.REDACTED.value
    # 自由文本（含敏感内容）不落 tombstone；只存受控归一 code。
    assert message.redacted_reason == "operator_suppressed"
    assert "身份证" not in (message.redacted_reason or "")
    assert "110101199001011234" not in (message.redacted_reason or "")


async def test_authorized_suppress_writes_redacted_tombstone_and_audit(
    db_session, session_factory
):
    content = b"permanently unavailable"
    _, run, message_id = await _completed_run(
        db_session, session_factory, content=content
    )

    await ConversationExecutionCoordinator(db_session).suppress_output_projection(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        run_id=run.id,
        reason="external object was permanently deleted",
    )
    await db_session.commit()

    persisted_run = await db_session.get(AgentRunModel, run.id)
    outbox = await db_session.scalar(
        select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.aggregate_id == run.id
        )
    )
    message = await db_session.get(MessageModel, message_id)
    assert persisted_run is not None
    assert outbox is not None
    assert message is not None
    assert persisted_run.output_publish_state == OutputPublishState.SUPPRESSED.value
    assert outbox.status == "cancelled"
    assert outbox.decision_actor_id == ACTOR_ID
    assert outbox.decision_digest is not None
    assert message.content_state == MessageContentState.REDACTED.value
    assert await db_session.scalar(
        select(func.count())
        .select_from(MessagePartModel)
        .where(MessagePartModel.message_id == message_id)
    ) == 0


async def test_suppressed_tombstone_allowed_during_running_purge(
    db_session, session_factory
):
    """P1-2（Codex）：purge_state=running 时 suppressed tombstone 仍可落——
    联合契约要求 running/completed 时不得读 output ref、只能写 redacted
    tombstone 并 suppress Run。修复前 project_suppressed_output 经
    _lock_projection_conversation 的 purge_state 拒绝被挡，迟到 output 只能
    失败重试/死信；修复后 tombstone 正常落库且不写 MessagePart 正文。"""
    content = b"late output during purge"
    _, run, message_id = await _completed_run(
        db_session, session_factory, content=content
    )
    # 把 Conversation 置 purge_state=running（purge 进行中）。
    await db_session.execute(
        update(ConversationModel)
        .where(ConversationModel.id == run.conversation_id)
        .values(purge_state="running")
    )
    await db_session.commit()

    # suppressed tombstone 必须可落（不被 purge_state 拒绝）。
    await ConversationExecutionCoordinator(db_session).suppress_output_projection(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        run_id=run.id,
        reason="suppressed during purge",
    )
    await db_session.commit()

    message = await db_session.get(MessageModel, message_id)
    assert message is not None
    assert message.content_state == MessageContentState.REDACTED.value
    # 无正文 tombstone：不写 MessagePart。
    assert await db_session.scalar(
        select(func.count())
        .select_from(MessagePartModel)
        .where(MessagePartModel.message_id == message_id)
    ) == 0


async def test_workspace_projection_commit_before_execution_ack_reconciles_once(
    db_session, session_factory
):
    content = b"ACK was lost"
    _, run, message_id = await _completed_run(
        db_session, session_factory, content=content
    )
    outbox = await db_session.scalar(
        select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.aggregate_id == run.id
        )
    )
    assert outbox is not None

    async with session_factory() as session, session.begin():
        claimed = await AgentExecutionBridgeService(session).claim_output_event(
            worker_id="projection-before-ack",
            now=outbox.next_attempt_at,
            stale_before=outbox.next_attempt_at,
            event_id=outbox.id,
        )
    assert claimed is not None
    async with session_factory() as session, session.begin():
        await ConversationExecutionCoordinator(
            session, output_reader=StaticOutputReader(content)
        ).consume_output_event(claimed, consumed_at=outbox.next_attempt_at)

    async with session_factory() as session, session.begin():
        reconciled = await ConversationExecutionCoordinator(
            session
        ).reconcile_output_projection(
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            run_id=run.id,
            now=outbox.next_attempt_at,
        )
    assert reconciled is True
    persisted_run = await db_session.get(AgentRunModel, run.id)
    assert persisted_run is not None
    await db_session.refresh(persisted_run)
    assert persisted_run.output_publish_state == OutputPublishState.PUBLISHED.value
    messages = list(
        (
            await db_session.scalars(
                select(MessageModel).where(MessageModel.origin_run_id == run.id)
            )
        ).all()
    )
    assert [message.id for message in messages] == [message_id]


async def test_late_projection_into_deleted_conversation_stays_hidden_and_inactive(
    db_session, session_factory
):
    content = b"completed before deletion"
    conversation_id, run, message_id = await _completed_run(
        db_session, session_factory, content=content
    )
    conversation = await db_session.get(ConversationModel, conversation_id)
    assert conversation is not None
    last_activity_at = conversation.last_activity_at

    deleted = await ConversationExecutionCoordinator(db_session).delete_conversation(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        expected_revision=1,
    )
    await db_session.commit()
    assert deleted.state.value == "deleted"
    event = await db_session.scalar(
        select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.aggregate_id == run.id
        )
    )
    assert event is not None

    assert await AgentBridgeDispatcher(
        session_factory,
        worker_id="late-output",
        output_reader=StaticOutputReader(content),
    ).dispatch_output(event_id=event.id)
    message = await db_session.get(MessageModel, message_id)
    assert message is not None
    await db_session.refresh(conversation)
    assert conversation.state == "deleted"
    assert conversation.last_activity_at == last_activity_at


async def test_visible_projection_cannot_be_relabelled_as_suppressed(
    db_session, session_factory
):
    content = b"visible before ACK"
    _, run, _ = await _completed_run(db_session, session_factory, content=content)
    outbox = await db_session.scalar(
        select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.aggregate_id == run.id
        )
    )
    assert outbox is not None
    async with session_factory() as session, session.begin():
        claimed = await AgentExecutionBridgeService(session).claim_output_event(
            worker_id="visible-before-suppress",
            now=outbox.next_attempt_at,
            stale_before=outbox.next_attempt_at,
            event_id=outbox.id,
        )
    assert claimed is not None
    async with session_factory() as session, session.begin():
        await ConversationExecutionCoordinator(
            session, output_reader=StaticOutputReader(content)
        ).consume_output_event(claimed, consumed_at=outbox.next_attempt_at)

    async with session_factory() as session, session.begin():
        with pytest.raises(WorkspaceIntegrationConflictError, match="visible output"):
            await ConversationExecutionCoordinator(session).suppress_output_projection(
                tenant_id=TENANT_ID,
                actor_id=ACTOR_ID,
                run_id=run.id,
                reason="must not overwrite a visible projection",
            )
    async with session_factory() as session, session.begin():
        assert await ConversationExecutionCoordinator(
            session
        ).reconcile_output_projection(
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            run_id=run.id,
        )


async def test_reconcile_rejects_tampered_projected_content(
    db_session, session_factory
):
    content = b"original projection"
    _, run, message_id = await _completed_run(
        db_session, session_factory, content=content
    )
    outbox = await db_session.scalar(
        select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.aggregate_id == run.id
        )
    )
    assert outbox is not None
    async with session_factory() as session, session.begin():
        claimed = await AgentExecutionBridgeService(session).claim_output_event(
            worker_id="tamper-before-ack",
            now=outbox.next_attempt_at,
            stale_before=outbox.next_attempt_at,
            event_id=outbox.id,
        )
    assert claimed is not None
    async with session_factory() as session, session.begin():
        await ConversationExecutionCoordinator(
            session, output_reader=StaticOutputReader(content)
        ).consume_output_event(claimed, consumed_at=outbox.next_attempt_at)
    await db_session.execute(
        update(MessagePartModel)
        .where(MessagePartModel.message_id == message_id)
        .values(text_content="tampered projection")
    )
    await db_session.commit()

    async with session_factory() as session, session.begin():
        with pytest.raises(WorkspaceIntegrationConflictError, match="bytes conflict"):
            await ConversationExecutionCoordinator(session).reconcile_output_projection(
                tenant_id=TENANT_ID,
                actor_id=ACTOR_ID,
                run_id=run.id,
            )


async def test_corrupt_output_outbox_is_quarantined_without_hot_loop(
    db_session, session_factory
):
    _, run, _ = await _completed_run(
        db_session, session_factory, content=b"poison output"
    )
    outbox = await db_session.scalar(
        select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.aggregate_id == run.id
        )
    )
    assert outbox is not None
    await db_session.execute(
        update(ExecutionOutboxModel)
        .where(ExecutionOutboxModel.id == outbox.id)
        .values(
            payload_inline={
                "event_type": "assistant_message.publish_requested.v1"
            }
        )
    )
    await db_session.commit()

    dispatcher = AgentBridgeDispatcher(session_factory, worker_id="poison-output")
    with pytest.raises(PoisonedIntegrationEventError, match="quarantined"):
        await dispatcher.dispatch_output(event_id=outbox.id)
    persisted_run = await db_session.get(AgentRunModel, run.id)
    assert persisted_run is not None
    await db_session.refresh(outbox)
    await db_session.refresh(persisted_run)
    assert outbox.status == "dead_letter"
    assert persisted_run.output_publish_state == OutputPublishState.DEAD_LETTER.value
    assert await dispatcher.dispatch_output(event_id=outbox.id) is False


async def test_reconcile_rejects_tampered_projection_digest_metadata(
    db_session, session_factory
):
    content = b"digest metadata"
    _, run, message_id = await _completed_run(
        db_session, session_factory, content=content
    )
    outbox = await db_session.scalar(
        select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.aggregate_id == run.id
        )
    )
    assert outbox is not None
    async with session_factory() as session, session.begin():
        claimed = await AgentExecutionBridgeService(session).claim_output_event(
            worker_id="digest-before-ack",
            now=outbox.next_attempt_at,
            stale_before=outbox.next_attempt_at,
            event_id=outbox.id,
        )
    assert claimed is not None
    async with session_factory() as session, session.begin():
        await ConversationExecutionCoordinator(
            session, output_reader=StaticOutputReader(content)
        ).consume_output_event(claimed, consumed_at=outbox.next_attempt_at)
    await db_session.execute(
        update(MessagePartModel)
        .where(MessagePartModel.message_id == message_id)
        .values(digest="f" * 64)
    )
    await db_session.commit()

    async with session_factory() as session, session.begin():
        with pytest.raises(WorkspaceIntegrationConflictError, match="digest metadata"):
            await ConversationExecutionCoordinator(session).reconcile_output_projection(
                tenant_id=TENANT_ID,
                actor_id=ACTOR_ID,
                run_id=run.id,
            )
