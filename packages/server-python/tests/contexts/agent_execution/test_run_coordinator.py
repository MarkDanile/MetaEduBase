from __future__ import annotations

import uuid
from dataclasses import replace

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.contexts.agent_execution.application.execution_identity_service import (
    ExecutionIdentityService,
)
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    OutputPublishState,
    RunConflictError,
    RunEventConflictError,
    RunEventPayload,
    RunEventType,
    RunNotFoundError,
    RunStatus,
    RuntimeCapabilitySnapshot,
    SnapshotClassification,
    TerminalResult,
    UnsupportedRunCapabilitiesError,
    inline_event_content,
    snapshot_digest,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    RunEventModel,
    TurnInputModel,
)
from app.contexts.agent_workspace.infrastructure.models import ConversationModel
from tests.contexts.agent_execution.e1_helpers import (
    TENANT_A,
    TENANT_B,
    AllowStartBarrier,
    bootstrap_compatibility,
    make_event,
    make_run_command,
)


@pytest.mark.asyncio
async def test_create_run_and_root_input_are_idempotent_and_tenant_scoped(db_session):
    identity = await bootstrap_compatibility(db_session)
    command = make_run_command(identity)
    coordinator = RunCoordinator(db_session)

    first = await coordinator.create_run(command)
    replay = await coordinator.create_run(command)

    assert first.created is True
    assert replay.created is False
    assert replay.run.id == first.run.id
    assert replay.run.status is RunStatus.QUEUED
    root_count = await db_session.scalar(
        select(func.count())
        .select_from(TurnInputModel)
        .where(TurnInputModel.run_id == command.run_id)
    )
    assert root_count == 1

    with pytest.raises(RunConflictError, match="already used"):
        await coordinator.create_run(
            replace(command, root_request_id=uuid.uuid4())
        )
    conflicting_request = make_run_command(
        identity,
        conversation_id=command.conversation_id,
        queue_seq=2,
    )
    with pytest.raises(RunConflictError, match="request id"):
        await coordinator.create_run(
            replace(
                conflicting_request,
                root_request_id=command.root_request_id,
            )
        )
    with pytest.raises(RunNotFoundError):
        await coordinator.require_run(
            tenant_id=TENANT_A,
            run_id=conflicting_request.run_id,
        )
    with pytest.raises(RunNotFoundError):
        await coordinator.require_run(tenant_id=TENANT_B, run_id=command.run_id)
    with pytest.raises(RunConflictError, match="definition"):
        await coordinator.create_run(
            make_run_command(identity, tenant_id=TENANT_B)
        )


@pytest.mark.asyncio
async def test_run_creation_rejects_partial_or_mismatched_snapshots(db_session):
    identity = await bootstrap_compatibility(db_session)
    coordinator = RunCoordinator(db_session)
    command = make_run_command(identity)

    with pytest.raises(RunConflictError, match="partial"):
        await coordinator.create_run(
            replace(command, context_snapshot_ref="context:1")
        )
    with pytest.raises(RunConflictError, match="config snapshot"):
        await coordinator.create_run(
            replace(
                command,
                run_config_snapshot=command.run_config_snapshot.model_copy(
                    update={"runtime_profile_id": uuid.uuid4()}
                ),
            )
        )


@pytest.mark.asyncio
async def test_e1_rejects_profiles_that_require_extended_durable_stores(db_session):
    identity = await bootstrap_compatibility(db_session)
    capabilities = RuntimeCapabilitySnapshot(
        runtime_kind="pi",
        adapter_key="pi-sdk",
        resume=True,
        steer=True,
        native_tools=True,
        tool_calls=True,
        input_requests=False,
        approvals=False,
        event_ack=True,
    )
    profile = await ExecutionIdentityService(db_session).publish_runtime_profile(
        tenant_id=TENANT_A,
        profile_key="runtime.pi.tools-not-installed.v1",
        runtime_kind="pi",
        adapter_key="pi-sdk",
        config_digest=snapshot_digest(
            {"profile_key": "runtime.pi.tools-not-installed.v1", "schema_version": 1}
        ),
        capability_snapshot=capabilities,
        enabled=True,
    )

    with pytest.raises(UnsupportedRunCapabilitiesError, match="E1 only"):
        await RunCoordinator(db_session).create_run(
            make_run_command(
                identity,
                runtime_profile_id=profile.id,
                runtime_capabilities=capabilities,
            )
        )


@pytest.mark.asyncio
async def test_start_is_fail_closed_by_default_and_uses_revision_cas(db_session):
    identity = await bootstrap_compatibility(db_session)
    command = make_run_command(identity)
    await RunCoordinator(db_session).create_run(command)

    with pytest.raises(RunConflictError, match="owned commands"):
        await RunCoordinator(db_session).transition_run(
            tenant_id=TENANT_A,
            run_id=command.run_id,
            expected_status=RunStatus.QUEUED,
            expected_revision=1,
            target_status=RunStatus.STARTING,
            summary="Must not bypass start_run",
        )

    with pytest.raises(RunConflictError, match="start barrier"):
        await RunCoordinator(db_session).start_run(
            tenant_id=TENANT_A,
            run_id=command.run_id,
            expected_revision=1,
        )

    coordinator = RunCoordinator(db_session, start_barrier=AllowStartBarrier())
    run, event = await coordinator.start_run(
        tenant_id=TENANT_A,
        run_id=command.run_id,
        expected_revision=1,
    )
    assert run.status is RunStatus.STARTING
    assert run.status_revision == 2
    assert event.seq == 1
    assert event.event_type is RunEventType.RUN_STARTED

    with pytest.raises(RunConflictError, match="revision"):
        await coordinator.transition_run(
            tenant_id=TENANT_A,
            run_id=command.run_id,
            expected_status=RunStatus.STARTING,
            expected_revision=1,
            target_status=RunStatus.RUNNING,
            summary="Runtime started",
        )

    with pytest.raises(RunConflictError, match="owned commands"):
        await coordinator.transition_run(
            tenant_id=TENANT_A,
            run_id=command.run_id,
            expected_status=RunStatus.STARTING,
            expected_revision=run.status_revision,
            target_status=RunStatus.RESUME_REQUIRED,
            summary="Compatibility path cannot resume",
        )
    with pytest.raises(UnsupportedRunCapabilitiesError, match="resume"):
        await coordinator.mark_run_resume_required(
            tenant_id=TENANT_A,
            run_id=command.run_id,
            expected_status=RunStatus.STARTING,
            expected_run_revision=run.status_revision,
            expected_runtime_epoch=1,
            expected_binding_revision=1,
            summary="Compatibility path cannot resume",
        )


@pytest.mark.asyncio
async def test_fifo_and_predecessor_projection_barrier(db_session):
    identity = await bootstrap_compatibility(db_session)
    conversation_id = uuid.uuid4()
    # R1-S4-C（S4-C C2）：execution outbox 新写带 conversation_id，触发
    # migration 040 条件 FK fk_agent_exec_outbox_scope_conv——fixture 必须建
    # 对应 agent_conversations 行。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, creation_digest, created_by) "
            "VALUES (:id, :tenant, :digest, :actor)"
        ),
        {"id": conversation_id, "tenant": TENANT_A, "digest": "d" * 64, "actor": uuid.uuid4()},
    )
    first_command = make_run_command(
        identity,
        conversation_id=conversation_id,
        queue_seq=1,
    )
    second_command = make_run_command(
        identity,
        conversation_id=conversation_id,
        queue_seq=2,
    )
    coordinator = RunCoordinator(db_session, start_barrier=AllowStartBarrier())
    await coordinator.create_run(first_command)
    await coordinator.create_run(second_command)

    with pytest.raises(RunConflictError, match="earlier Run"):
        await coordinator.start_run(
            tenant_id=TENANT_A,
            run_id=second_command.run_id,
            expected_revision=1,
        )

    first, _ = await coordinator.start_run(
        tenant_id=TENANT_A,
        run_id=first_command.run_id,
        expected_revision=1,
    )
    first, _ = await coordinator.transition_run(
        tenant_id=TENANT_A,
        run_id=first.id,
        expected_status=RunStatus.STARTING,
        expected_revision=first.status_revision,
        target_status=RunStatus.RUNNING,
        summary="Runtime running",
    )
    first, terminal_event, _ = await coordinator.commit_terminal(
        tenant_id=TENANT_A,
        run_id=first.id,
        expected_status=RunStatus.RUNNING,
        expected_revision=first.status_revision,
        result=TerminalResult(
            outcome="completed",
            code="ok",
            reason="Completed",
            output_ref="terminal-output:first",
            output_digest="b" * 64,
            output_size=42,
            output_media_type="text/markdown",
            output_classification=SnapshotClassification.INTERNAL,
            terminal_message_id=uuid.uuid4(),
        ),
        # R1-S4-C（S4-C C2）：COMPLETED 写 publish outbox 需带真实 epoch。
        producer_purge_revision=(
            await db_session.scalar(
                select(ConversationModel.purge_revision).where(
                    ConversationModel.tenant_id == TENANT_A,
                    ConversationModel.id == conversation_id,
                )
            )
        ),
    )
    assert terminal_event is not None
    assert first.output_publish_state is OutputPublishState.PENDING

    with pytest.raises(RunConflictError, match="projection"):
        await coordinator.start_run(
            tenant_id=TENANT_A,
            run_id=second_command.run_id,
            expected_revision=1,
        )

    await db_session.execute(
        update(AgentRunModel)
        .where(AgentRunModel.id == first.id)
        .values(output_publish_state=OutputPublishState.PUBLISHED.value)
    )
    await db_session.flush()
    second, _ = await coordinator.start_run(
        tenant_id=TENANT_A,
        run_id=second_command.run_id,
        expected_revision=1,
    )
    assert second.status is RunStatus.STARTING


@pytest.mark.asyncio
async def test_database_enforces_one_active_run_per_conversation(db_session):
    identity = await bootstrap_compatibility(db_session)
    conversation_id = uuid.uuid4()
    first = make_run_command(identity, conversation_id=conversation_id, queue_seq=1)
    second = make_run_command(identity, conversation_id=conversation_id, queue_seq=2)
    coordinator = RunCoordinator(db_session)
    await coordinator.create_run(first)
    await coordinator.create_run(second)

    await db_session.execute(
        update(AgentRunModel)
        .where(AgentRunModel.id == first.run_id)
        .values(status=RunStatus.STARTING.value)
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                update(AgentRunModel)
                .where(AgentRunModel.id == second.run_id)
                .values(status=RunStatus.STARTING.value)
            )


@pytest.mark.asyncio
async def test_run_events_are_append_only_and_terminal_events_are_coordinator_owned(
    db_session,
):
    identity = await bootstrap_compatibility(db_session)
    command = make_run_command(identity)
    coordinator = RunCoordinator(db_session)
    await coordinator.create_run(command)
    event = await coordinator.append_event(
        tenant_id=TENANT_A,
        run_id=command.run_id,
        event=make_event(correlation_id=command.correlation_id),
    )

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                RunEventModel(
                    id=uuid.uuid4(),
                    tenant_id=event.tenant_id,
                    conversation_id=event.conversation_id,
                    run_id=event.run_id,
                    seq=event.seq + 100,
                    event_type=event.event_type.value,
                    schema_version=event.schema_version,
                    occurred_at=event.occurred_at,
                    persisted_at=event.persisted_at,
                    visibility=event.visibility.value,
                    classification=event.content.classification.value,
                    payload_inline=(
                        event.content.payload_inline.model_dump(mode="json")
                        if event.content.payload_inline is not None
                        else None
                    ),
                    payload_ref=event.content.payload_ref,
                    payload_state=event.content.payload_state.value,
                    payload_digest=event.content.payload_digest,
                    payload_size=event.content.payload_size,
                    media_type=event.content.media_type,
                    expires_at=event.content.expires_at,
                    runtime_profile_id=event.runtime_profile_id,
                    runtime_binding_id=event.runtime_binding_id,
                    runtime_epoch=event.runtime_epoch,
                    runtime_seq=event.runtime_seq,
                    runtime_event_id=event.runtime_event_id,
                    runtime_event_digest=event.runtime_event_digest,
                    correlation_id=uuid.uuid4(),
                    causation_id=event.causation_id,
                )
            )
            await db_session.flush()

    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                update(RunEventModel)
                .where(RunEventModel.id == event.id)
                .values(event_type=RunEventType.ERROR_REPORTED.value)
            )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                delete(RunEventModel).where(RunEventModel.id == event.id)
            )
    with pytest.raises(RunEventConflictError, match="commit_terminal"):
        await coordinator.append_event(
            tenant_id=TENANT_A,
            run_id=command.run_id,
            event=make_event(
                event_type=RunEventType.RUN_FAILED,
                correlation_id=command.correlation_id,
            ),
        )
    with pytest.raises(RunEventConflictError, match="Runtime ingestion"):
        await coordinator.append_event(
            tenant_id=TENANT_A,
            run_id=command.run_id,
            event=make_event(
                event_type=RunEventType.RUNTIME_TERMINAL_OBSERVED,
                correlation_id=command.correlation_id,
            ),
        )
    with pytest.raises(RunEventConflictError, match="correlation"):
        await coordinator.append_event(
            tenant_id=TENANT_A,
            run_id=command.run_id,
            event=make_event(),
        )
    with pytest.raises(UnsupportedRunCapabilitiesError, match="durable entity"):
        await coordinator.append_event(
            tenant_id=TENANT_A,
            run_id=command.run_id,
            event=make_event(
                event_type=RunEventType.TOOL_STARTED,
                correlation_id=command.correlation_id,
            ),
        )
    forged_phase = replace(
        make_event(
            event_type=RunEventType.PHASE_CHANGED,
            correlation_id=command.correlation_id,
        ),
        content=inline_event_content(
            RunEventPayload(
                summary="Forged transition",
                status_from=RunStatus.QUEUED,
                status_to=RunStatus.STARTING,
            ),
            classification=SnapshotClassification.INTERNAL,
        ),
    )
    with pytest.raises(RunEventConflictError, match="cannot claim"):
        await coordinator.append_event(
            tenant_id=TENANT_A,
            run_id=command.run_id,
            event=forged_phase,
        )
