from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.contexts.agent_execution.application.dto import RuntimeEventCommand
from app.contexts.agent_execution.application.ports import DurableGuardState
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    InvalidRuntimeProvenanceError,
    OutputPublishState,
    RunConflictError,
    RunEventConflictError,
    RunEventPayload,
    RunEventType,
    RunGuardBlockedError,
    RunStatus,
    RuntimeBindingStatus,
    RuntimeEventConflictError,
    RuntimeEventProvenance,
    RuntimeIngestFrame,
    RuntimeSequenceGapError,
    RuntimeStreamLeaseConflictError,
    SnapshotClassification,
    TerminalResult,
    TerminalResultConflictError,
    UnsupportedRunCapabilitiesError,
    inline_event_content,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    RunEventModel,
    RuntimeSessionBindingModel,
)
from tests.conftest import TEST_DB_URL
from tests.contexts.agent_execution.e1_helpers import (
    READONLY_NATIVE_CAPABILITIES,
    TENANT_A,
    AllowStartBarrier,
    StaticGuardState,
    bootstrap_compatibility,
    bootstrap_native_binding,
    make_event,
    make_run_command,
)


async def _create_native_running(db_session):
    identity = await bootstrap_compatibility(db_session)
    conversation_id = uuid.uuid4()
    profile_id, binding, stream_id = await bootstrap_native_binding(
        db_session,
        identity,
        conversation_id=conversation_id,
    )
    command = make_run_command(
        identity,
        conversation_id=conversation_id,
        runtime_profile_id=profile_id,
        runtime_capabilities=READONLY_NATIVE_CAPABILITIES,
        runtime_binding_id=binding.id,
    )
    coordinator = RunCoordinator(db_session, start_barrier=AllowStartBarrier())
    created = await coordinator.create_run(command)
    run, _ = await coordinator.start_run(
        tenant_id=TENANT_A,
        run_id=created.run.id,
        expected_revision=created.run.status_revision,
    )
    run, _ = await coordinator.transition_run(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.STARTING,
        expected_revision=run.status_revision,
        target_status=RunStatus.RUNNING,
        summary="Pi read-only Runtime is running",
    )
    return coordinator, command, binding, stream_id, run


def _runtime_command(
    *,
    command,
    binding,
    stream_id: uuid.UUID,
    seq: int,
    digest: str,
    event_id: uuid.UUID | None = None,
    event_type: RunEventType = RunEventType.PLAN_SUMMARY,
) -> RuntimeEventCommand:
    return RuntimeEventCommand(
        frame=RuntimeIngestFrame(
            tenant_id=command.tenant_id,
            conversation_id=command.conversation_id,
            run_id=command.run_id,
            runtime_profile_id=command.runtime_profile_id,
            provenance=RuntimeEventProvenance(
                binding_id=binding.id,
                runtime_epoch=binding.current_epoch,
                runtime_seq=seq,
                runtime_event_id=event_id or uuid.uuid4(),
            ),
            event_digest=digest,
        ),
        stream_id=stream_id,
        event=make_event(
            event_type=event_type,
            summary=f"Runtime event {seq}",
            correlation_id=command.correlation_id,
        ),
    )


@pytest.mark.asyncio
async def test_runtime_event_and_contiguous_ack_commit_or_rollback_together(db_session):
    coordinator, command, binding, stream_id, _ = await _create_native_running(
        db_session
    )
    runtime_event_id = uuid.uuid4()
    frame = _runtime_command(
        command=command,
        binding=binding,
        stream_id=stream_id,
        seq=1,
        digest="c" * 64,
        event_id=runtime_event_id,
    )
    await db_session.commit()

    transient = await coordinator.ingest_runtime_event(frame)
    assert transient.acked_through_runtime_seq == 1
    await db_session.rollback()

    persisted_binding = await db_session.get(RuntimeSessionBindingModel, binding.id)
    assert persisted_binding is not None
    assert persisted_binding.acked_through_runtime_seq == 0
    assert persisted_binding.next_expected_runtime_seq == 1
    assert await db_session.scalar(
        select(RunEventModel.id).where(
            RunEventModel.runtime_event_id == runtime_event_id
        )
    ) is None

    accepted = await coordinator.ingest_runtime_event(frame)
    assert accepted.event is not None
    assert accepted.acked_through_runtime_seq == 1
    assert accepted.idempotent_replay is False
    await db_session.commit()

    replay = await coordinator.ingest_runtime_event(frame)
    assert replay.event is None
    assert replay.acked_through_runtime_seq == 1
    assert replay.idempotent_replay is True

    with pytest.raises(RuntimeEventConflictError, match="conflicting"):
        await coordinator.ingest_runtime_event(
            _runtime_command(
                command=command,
                binding=binding,
                stream_id=stream_id,
                seq=1,
                digest="d" * 64,
                event_id=runtime_event_id,
            )
        )
    with pytest.raises(RuntimeEventConflictError, match="event id"):
        await coordinator.ingest_runtime_event(
            _runtime_command(
                command=command,
                binding=binding,
                stream_id=stream_id,
                seq=2,
                digest="e" * 64,
                event_id=runtime_event_id,
            )
        )


@pytest.mark.asyncio
async def test_runtime_gap_and_boundary_fail_without_advancing_ack(db_session):
    coordinator, command, binding, stream_id, _ = await _create_native_running(
        db_session
    )
    await db_session.commit()

    with pytest.raises(RuntimeSequenceGapError) as gap:
        await coordinator.ingest_runtime_event(
            _runtime_command(
                command=command,
                binding=binding,
                stream_id=stream_id,
                seq=2,
                digest="e" * 64,
            )
        )
    assert gap.value.expected == 1
    persisted_binding = await db_session.get(RuntimeSessionBindingModel, binding.id)
    assert persisted_binding is not None
    assert persisted_binding.acked_through_runtime_seq == 0

    with pytest.raises(RuntimeStreamLeaseConflictError):
        await coordinator.ingest_runtime_event(
            _runtime_command(
                command=command,
                binding=binding,
                stream_id=uuid.uuid4(),
                seq=1,
                digest="f" * 64,
            )
        )

    wrong_profile = _runtime_command(
        command=command,
        binding=binding,
        stream_id=stream_id,
        seq=1,
        digest="f" * 64,
    )
    wrong_profile = RuntimeEventCommand(
        frame=RuntimeIngestFrame(
            tenant_id=wrong_profile.frame.tenant_id,
            conversation_id=wrong_profile.frame.conversation_id,
            run_id=wrong_profile.frame.run_id,
            runtime_profile_id=uuid.uuid4(),
            provenance=wrong_profile.frame.provenance,
            event_digest=wrong_profile.frame.event_digest,
        ),
        stream_id=wrong_profile.stream_id,
        event=wrong_profile.event,
    )
    with pytest.raises(InvalidRuntimeProvenanceError, match="target Run binding"):
        await coordinator.ingest_runtime_event(wrong_profile)

    with pytest.raises(UnsupportedRunCapabilitiesError, match="durable entity"):
        await coordinator.ingest_runtime_event(
            _runtime_command(
                command=command,
                binding=binding,
                stream_id=stream_id,
                seq=1,
                digest="9" * 64,
                event_type=RunEventType.TOOL_STARTED,
            )
        )

    phase = _runtime_command(
        command=command,
        binding=binding,
        stream_id=stream_id,
        seq=1,
        digest="7" * 64,
        event_type=RunEventType.PHASE_CHANGED,
    )
    phase = replace(
        phase,
        event=replace(
            phase.event,
            content=inline_event_content(
                RunEventPayload(
                    summary="Forged Runtime status",
                    status_from=RunStatus.RUNNING,
                    status_to=RunStatus.COMPLETED,
                ),
                classification=SnapshotClassification.INTERNAL,
            ),
        ),
    )
    with pytest.raises(RunEventConflictError, match="cannot claim"):
        await coordinator.ingest_runtime_event(phase)


@pytest.mark.asyncio
async def test_runtime_terminal_observation_does_not_make_run_terminal(db_session):
    coordinator, command, binding, stream_id, _ = await _create_native_running(
        db_session
    )
    frame = _runtime_command(
        command=command,
        binding=binding,
        stream_id=stream_id,
        seq=1,
        digest="1" * 64,
        event_type=RunEventType.RUNTIME_TERMINAL_OBSERVED,
    )
    observed = await coordinator.ingest_runtime_event(frame)
    run = await coordinator.require_run(tenant_id=TENANT_A, run_id=command.run_id)
    assert observed.event is not None
    assert observed.event.event_type is RunEventType.RUNTIME_TERMINAL_OBSERVED
    assert run.status is RunStatus.RUNNING
    assert run.ended_at is None

    terminal, _, _ = await coordinator.commit_terminal(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.RUNNING,
        expected_revision=run.status_revision,
        result=TerminalResult(
            outcome="failed",
            code="runtime_failed",
            reason="Runtime terminal observation was evaluated",
        ),
    )
    assert terminal.status is RunStatus.FAILED
    replay = await coordinator.ingest_runtime_event(frame)
    assert replay.event is None
    assert replay.acked_through_runtime_seq == 1
    assert replay.idempotent_replay is True
    with pytest.raises(RunEventConflictError, match="active Run"):
        await coordinator.ingest_runtime_event(
            _runtime_command(
                command=command,
                binding=binding,
                stream_id=stream_id,
                seq=2,
                digest="6" * 64,
            )
        )
    persisted_binding = await db_session.get(RuntimeSessionBindingModel, binding.id)
    assert persisted_binding is not None
    assert persisted_binding.acked_through_runtime_seq == 1
    assert persisted_binding.next_expected_runtime_seq == 2


@pytest.mark.asyncio
async def test_runtime_binding_cannot_ingest_into_another_native_run(db_session):
    coordinator, first_command, first_binding, first_stream_id, _ = (
        await _create_native_running(db_session)
    )
    identity = await bootstrap_compatibility(db_session)
    second_conversation_id = uuid.uuid4()
    second_profile_id, second_binding, _ = await bootstrap_native_binding(
        db_session,
        identity,
        conversation_id=second_conversation_id,
    )
    second_command = make_run_command(
        identity,
        conversation_id=second_conversation_id,
        runtime_profile_id=second_profile_id,
        runtime_capabilities=READONLY_NATIVE_CAPABILITIES,
        runtime_binding_id=second_binding.id,
    )
    second_created = await coordinator.create_run(second_command)
    second_run, _ = await coordinator.start_run(
        tenant_id=TENANT_A,
        run_id=second_command.run_id,
        expected_revision=second_created.run.status_revision,
    )
    second_run, _ = await coordinator.transition_run(
        tenant_id=TENANT_A,
        run_id=second_run.id,
        expected_status=RunStatus.STARTING,
        expected_revision=second_run.status_revision,
        target_status=RunStatus.RUNNING,
        summary="Second Runtime is running",
    )
    assert second_run.status is RunStatus.RUNNING
    assert first_command.runtime_profile_id == second_command.runtime_profile_id

    forged = _runtime_command(
        command=second_command,
        binding=first_binding,
        stream_id=first_stream_id,
        seq=1,
        digest="3" * 64,
    )
    with pytest.raises(InvalidRuntimeProvenanceError, match="target Run binding"):
        await coordinator.ingest_runtime_event(forged)
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                update(AgentRunModel)
                .where(AgentRunModel.id == second_run.id)
                .values(runtime_binding_id=first_binding.id)
            )


@pytest.mark.asyncio
async def test_run_resume_state_is_fenced_by_binding_status_and_epoch(db_session):
    coordinator, command, binding, _, run = await _create_native_running(db_session)
    with pytest.raises(RuntimeStreamLeaseConflictError, match="live ingest stream"):
        await coordinator.mark_run_resume_required(
            tenant_id=TENANT_A,
            run_id=run.id,
            expected_status=RunStatus.RUNNING,
            expected_run_revision=run.status_revision,
            expected_runtime_epoch=binding.current_epoch,
            expected_binding_revision=binding.revision,
            summary="Runtime disconnected",
        )

    await db_session.execute(
        update(RuntimeSessionBindingModel)
        .where(RuntimeSessionBindingModel.id == binding.id)
        .values(stream_lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.flush()
    run, event, resume_binding = await coordinator.mark_run_resume_required(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.RUNNING,
        expected_run_revision=run.status_revision,
        expected_runtime_epoch=binding.current_epoch,
        expected_binding_revision=binding.revision,
        summary="Runtime requires resume",
    )
    assert run.status is RunStatus.RESUME_REQUIRED
    assert event.event_type is RunEventType.RUN_RESUME_REQUIRED
    assert resume_binding.status is RuntimeBindingStatus.RESUME_REQUIRED

    run, event, active_binding = await coordinator.resume_run(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_run_revision=run.status_revision,
        expected_runtime_epoch=resume_binding.current_epoch,
        expected_binding_revision=resume_binding.revision,
        runtime_session_ref=f"pi-resumed-{command.conversation_id}",
        summary="Runtime resumed in a new epoch",
    )
    assert run.status is RunStatus.STARTING
    assert event.event_type is RunEventType.PHASE_CHANGED
    assert active_binding.status is RuntimeBindingStatus.ACTIVE
    assert active_binding.current_epoch == binding.current_epoch + 1


@pytest.mark.asyncio
async def test_mark_and_resume_roll_back_run_and_binding_together(db_session):
    coordinator, command, binding, _, run = await _create_native_running(db_session)
    await db_session.execute(
        update(RuntimeSessionBindingModel)
        .where(RuntimeSessionBindingModel.id == binding.id)
        .values(stream_lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()

    resumed_run, _, _ = await coordinator.mark_run_resume_required(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.RUNNING,
        expected_run_revision=run.status_revision,
        expected_runtime_epoch=binding.current_epoch,
        expected_binding_revision=binding.revision,
        summary="Rollback mark",
    )
    assert resumed_run.status is RunStatus.RESUME_REQUIRED
    await db_session.rollback()
    persisted_run = await db_session.get(AgentRunModel, run.id)
    persisted_binding = await db_session.get(RuntimeSessionBindingModel, binding.id)
    assert persisted_run is not None
    assert persisted_run.status == RunStatus.RUNNING.value
    assert persisted_binding is not None
    assert persisted_binding.status == RuntimeBindingStatus.ACTIVE.value

    resumed_run, _, resume_binding = await coordinator.mark_run_resume_required(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.RUNNING,
        expected_run_revision=run.status_revision,
        expected_runtime_epoch=binding.current_epoch,
        expected_binding_revision=binding.revision,
        summary="Commit mark",
    )
    await db_session.commit()
    starting_run, _, active_binding = await coordinator.resume_run(
        tenant_id=TENANT_A,
        run_id=resumed_run.id,
        expected_run_revision=resumed_run.status_revision,
        expected_runtime_epoch=resume_binding.current_epoch,
        expected_binding_revision=resume_binding.revision,
        runtime_session_ref=f"pi-rollback-{command.conversation_id}",
        summary="Rollback resume",
    )
    assert starting_run.status is RunStatus.STARTING
    assert active_binding.current_epoch == binding.current_epoch + 1
    await db_session.rollback()
    persisted_run = await db_session.get(AgentRunModel, run.id)
    persisted_binding = await db_session.get(RuntimeSessionBindingModel, binding.id)
    assert persisted_run is not None
    assert persisted_run.status == RunStatus.RESUME_REQUIRED.value
    assert persisted_binding is not None
    assert persisted_binding.status == RuntimeBindingStatus.RESUME_REQUIRED.value
    assert persisted_binding.current_epoch == binding.current_epoch


@pytest.mark.asyncio
async def test_runtime_ingest_and_resume_coordination_share_run_then_binding_lock_order(
    db_session,
):
    _, command, binding, stream_id, run = await _create_native_running(db_session)
    frame = _runtime_command(
        command=command,
        binding=binding,
        stream_id=stream_id,
        seq=1,
        digest="8" * 64,
    )
    await db_session.execute(
        update(RuntimeSessionBindingModel)
        .where(RuntimeSessionBindingModel.id == binding.id)
        .values(stream_lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()

    engine = create_async_engine(TEST_DB_URL, pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def mark_resume():
        async with factory() as session:
            try:
                result = await RunCoordinator(session).mark_run_resume_required(
                    tenant_id=TENANT_A,
                    run_id=run.id,
                    expected_status=RunStatus.RUNNING,
                    expected_run_revision=run.status_revision,
                    expected_runtime_epoch=binding.current_epoch,
                    expected_binding_revision=binding.revision,
                    summary="Concurrent Runtime disconnect",
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    async def ingest():
        async with factory() as session:
            try:
                result = await RunCoordinator(session).ingest_runtime_event(frame)
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    try:
        results = await asyncio.gather(mark_resume(), ingest())
    finally:
        await engine.dispose()

    assert not any(isinstance(result, DBAPIError) for result in results)
    assert sum(isinstance(result, tuple) for result in results) == 1
    assert sum(
        isinstance(result, RuntimeStreamLeaseConflictError) for result in results
    ) == 1


@pytest.mark.asyncio
async def test_resume_required_terminal_closes_recovery_intent_atomically(db_session):
    coordinator, command, binding, _, run = await _create_native_running(db_session)
    identity = await bootstrap_compatibility(db_session)
    queued_command = make_run_command(
        identity,
        conversation_id=command.conversation_id,
        queue_seq=2,
        runtime_profile_id=command.runtime_profile_id,
        runtime_capabilities=READONLY_NATIVE_CAPABILITIES,
        runtime_binding_id=binding.id,
    )
    await coordinator.create_run(queued_command)
    await db_session.execute(
        update(RuntimeSessionBindingModel)
        .where(RuntimeSessionBindingModel.id == binding.id)
        .values(stream_lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.flush()
    run, _, resume_binding = await coordinator.mark_run_resume_required(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.RUNNING,
        expected_run_revision=run.status_revision,
        expected_runtime_epoch=binding.current_epoch,
        expected_binding_revision=binding.revision,
        summary="Runtime cannot be resumed",
    )
    await db_session.commit()

    terminal, event, replay = await coordinator.commit_terminal(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.RESUME_REQUIRED,
        expected_revision=run.status_revision,
        result=TerminalResult(
            outcome="failed",
            code="resume_failed",
            reason="Recovery intent closed",
        ),
    )
    assert terminal.status is RunStatus.FAILED
    assert event is not None
    assert replay is False
    await db_session.rollback()

    persisted_run = await db_session.get(AgentRunModel, run.id)
    persisted_binding = await db_session.get(
        RuntimeSessionBindingModel,
        resume_binding.id,
    )
    assert persisted_run is not None
    assert persisted_run.status == RunStatus.RESUME_REQUIRED.value
    assert persisted_binding is not None
    assert persisted_binding.status == RuntimeBindingStatus.RESUME_REQUIRED.value

    terminal, event, replay = await coordinator.commit_terminal(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.RESUME_REQUIRED,
        expected_revision=run.status_revision,
        result=TerminalResult(
            outcome="failed",
            code="resume_failed",
            reason="Recovery intent closed",
        ),
    )
    assert terminal.status is RunStatus.FAILED
    assert event is not None
    assert replay is False
    persisted_binding = await db_session.get(
        RuntimeSessionBindingModel,
        resume_binding.id,
    )
    assert persisted_binding is not None
    assert persisted_binding.status == RuntimeBindingStatus.CLOSED.value
    with pytest.raises(RunConflictError, match="not active"):
        await coordinator.start_run(
            tenant_id=TENANT_A,
            run_id=queued_command.run_id,
            expected_revision=1,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "guard",
    [
        DurableGuardState(active_tool_calls=1),
        DurableGuardState(active_input_requests=1),
        DurableGuardState(active_approvals=1),
        DurableGuardState(outcome_unknown_tool_calls=1),
    ],
)
async def test_pending_or_unknown_durable_state_blocks_terminal(db_session, guard):
    identity = await bootstrap_compatibility(db_session)
    command = make_run_command(identity)
    coordinator = RunCoordinator(
        db_session,
        start_barrier=AllowStartBarrier(),
        guard_state=StaticGuardState(guard),
    )
    created = await coordinator.create_run(command)
    run, _ = await coordinator.start_run(
        tenant_id=TENANT_A,
        run_id=command.run_id,
        expected_revision=created.run.status_revision,
    )
    run, _ = await coordinator.transition_run(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.STARTING,
        expected_revision=run.status_revision,
        target_status=RunStatus.RUNNING,
        summary="Running",
    )
    with pytest.raises(RunGuardBlockedError, match="durable state"):
        await coordinator.commit_terminal(
            tenant_id=TENANT_A,
            run_id=run.id,
            expected_status=RunStatus.RUNNING,
            expected_revision=run.status_revision,
            result=TerminalResult(
                outcome="failed",
                code="runtime_failed",
                reason="Runtime failed",
            ),
        )


@pytest.mark.asyncio
async def test_canonical_terminal_is_atomic_idempotent_and_conflict_closed(db_session):
    identity = await bootstrap_compatibility(db_session)
    command = make_run_command(identity)
    # R1-S4-C（S4-C C2）：execution outbox 新写带 conversation_id，触发
    # migration 040 条件 FK——fixture 必须建对应 agent_conversations 行。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, creation_digest, created_by) "
            "VALUES (:id, :tenant, :digest, :actor)"
        ),
        {
            "id": command.conversation_id,
            "tenant": TENANT_A,
            "digest": "d" * 64,
            "actor": uuid.uuid4(),
        },
    )
    coordinator = RunCoordinator(db_session, start_barrier=AllowStartBarrier())
    created = await coordinator.create_run(command)
    run, _ = await coordinator.start_run(
        tenant_id=TENANT_A,
        run_id=command.run_id,
        expected_revision=created.run.status_revision,
    )
    run, _ = await coordinator.transition_run(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.STARTING,
        expected_revision=run.status_revision,
        target_status=RunStatus.RUNNING,
        summary="Running",
    )
    await db_session.commit()
    result = TerminalResult(
        outcome="completed",
        code="ok",
        reason="Completed",
        output_ref="terminal-output:atomic",
        output_digest="2" * 64,
        output_size=100,
        output_media_type="text/markdown",
        output_classification=SnapshotClassification.INTERNAL,
        terminal_message_id=uuid.uuid4(),
    )

    transient, event, replay = await coordinator.commit_terminal(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.RUNNING,
        expected_revision=run.status_revision,
        result=result,
    )
    assert transient.status is RunStatus.COMPLETED
    assert transient.output_publish_state is OutputPublishState.PENDING
    assert event is not None
    assert event.event_type is RunEventType.RUN_COMPLETED
    assert replay is False
    await db_session.rollback()

    persisted = await db_session.get(AgentRunModel, run.id)
    assert persisted is not None
    assert persisted.status == RunStatus.RUNNING.value
    terminal_count = len(
        (
            await db_session.scalars(
                select(RunEventModel).where(
                    RunEventModel.run_id == run.id,
                    RunEventModel.event_type == RunEventType.RUN_COMPLETED.value,
                )
            )
        ).all()
    )
    assert terminal_count == 0

    terminal, event, replay = await coordinator.commit_terminal(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.RUNNING,
        expected_revision=run.status_revision,
        result=result,
    )
    assert terminal.status is RunStatus.COMPLETED
    assert event is not None
    assert replay is False
    await db_session.commit()

    replayed, event, replay = await coordinator.commit_terminal(
        tenant_id=TENANT_A,
        run_id=run.id,
        expected_status=RunStatus.RUNNING,
        expected_revision=run.status_revision,
        result=result,
    )
    assert replayed.status is RunStatus.COMPLETED
    assert event is None
    assert replay is True

    with pytest.raises(TerminalResultConflictError, match="conflicts"):
        await coordinator.commit_terminal(
            tenant_id=TENANT_A,
            run_id=run.id,
            expected_status=RunStatus.RUNNING,
            expected_revision=run.status_revision,
            result=TerminalResult(
                outcome="failed",
                code="conflicting",
                reason="Conflicting terminal result",
            ),
        )
