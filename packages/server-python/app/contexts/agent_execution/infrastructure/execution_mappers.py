from __future__ import annotations

from app.contexts.agent_execution.domain import (
    AgentRun,
    EventPayloadState,
    EventVisibility,
    OutputPublishState,
    RunBudgetSnapshot,
    RunConfigSnapshot,
    RunEvent,
    RunEventContent,
    RunEventPayload,
    RunEventType,
    RunStatus,
    RuntimeBindingStatus,
    RuntimeCapabilitySnapshot,
    RuntimeSessionBinding,
    RunUsageSummary,
    SnapshotClassification,
    TerminalResult,
    inline_event_content,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    RunEventModel,
    RuntimeSessionBindingModel,
)


def run_values(run: AgentRun) -> dict[str, object]:
    return {
        "id": run.id,
        "tenant_id": run.tenant_id,
        "conversation_id": run.conversation_id,
        "queue_seq": run.queue_seq,
        "root_input_message_id": run.root_input_message_id,
        "parent_run_id": run.parent_run_id,
        "agent_definition_version_id": run.agent_definition_version_id,
        "runtime_profile_id": run.runtime_profile_id,
        "runtime_binding_id": run.runtime_binding_id,
        "creation_digest": run.creation_digest,
        "status": run.status.value,
        "status_revision": run.status_revision,
        "cancel_requested_revision": run.cancel_requested_revision,
        "next_event_seq": run.next_event_seq,
        "first_available_event_seq": run.first_available_event_seq,
        "last_event_seq": run.last_event_seq,
        "event_log_complete": run.event_log_complete,
        "queued_at": run.queued_at,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "terminal_code": run.terminal_code,
        "terminal_reason": run.terminal_reason,
        "terminal_result_digest": run.terminal_result_digest,
        "terminal_output_ref": run.terminal_output_ref,
        "terminal_output_digest": run.terminal_output_digest,
        "terminal_output_size": run.terminal_output_size,
        "terminal_output_media_type": run.terminal_output_media_type,
        "terminal_output_classification": (
            run.terminal_output_classification.value
            if run.terminal_output_classification is not None
            else None
        ),
        "terminal_message_id": run.terminal_message_id,
        "output_publish_state": run.output_publish_state.value,
        "created_by": run.created_by,
        "correlation_id": run.correlation_id,
        "runtime_capability_snapshot": run.runtime_capability_snapshot.model_dump(
            mode="json"
        ),
        "run_config_snapshot": run.run_config_snapshot.model_dump(mode="json"),
        "context_snapshot_ref": run.context_snapshot_ref,
        "context_snapshot_digest": run.context_snapshot_digest,
        "context_snapshot_classification": (
            run.context_snapshot_classification.value
            if run.context_snapshot_classification is not None
            else None
        ),
        "budget_snapshot": run.budget_snapshot.model_dump(mode="json"),
        "usage_summary": run.usage_summary.model_dump(mode="json"),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def to_run(row: AgentRunModel) -> AgentRun:
    return AgentRun(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_id=row.conversation_id,
        queue_seq=row.queue_seq,
        root_input_message_id=row.root_input_message_id,
        parent_run_id=row.parent_run_id,
        agent_definition_version_id=row.agent_definition_version_id,
        runtime_profile_id=row.runtime_profile_id,
        runtime_binding_id=row.runtime_binding_id,
        creation_digest=row.creation_digest,
        status=RunStatus(row.status),
        status_revision=row.status_revision,
        cancel_requested_revision=row.cancel_requested_revision,
        next_event_seq=row.next_event_seq,
        first_available_event_seq=row.first_available_event_seq,
        last_event_seq=row.last_event_seq,
        event_log_complete=row.event_log_complete,
        queued_at=row.queued_at,
        started_at=row.started_at,
        ended_at=row.ended_at,
        terminal_code=row.terminal_code,
        terminal_reason=row.terminal_reason,
        terminal_result_digest=row.terminal_result_digest,
        terminal_output_ref=row.terminal_output_ref,
        terminal_output_digest=row.terminal_output_digest,
        terminal_output_size=row.terminal_output_size,
        terminal_output_media_type=row.terminal_output_media_type,
        terminal_output_classification=(
            SnapshotClassification(row.terminal_output_classification)
            if row.terminal_output_classification is not None
            else None
        ),
        terminal_message_id=row.terminal_message_id,
        output_publish_state=OutputPublishState(row.output_publish_state),
        created_by=row.created_by,
        correlation_id=row.correlation_id,
        runtime_capability_snapshot=RuntimeCapabilitySnapshot.model_validate(
            row.runtime_capability_snapshot
        ),
        run_config_snapshot=RunConfigSnapshot.model_validate(row.run_config_snapshot),
        context_snapshot_ref=row.context_snapshot_ref,
        context_snapshot_digest=row.context_snapshot_digest,
        context_snapshot_classification=(
            SnapshotClassification(row.context_snapshot_classification)
            if row.context_snapshot_classification is not None
            else None
        ),
        budget_snapshot=RunBudgetSnapshot.model_validate(row.budget_snapshot),
        usage_summary=RunUsageSummary.model_validate(row.usage_summary),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def to_binding(row: RuntimeSessionBindingModel) -> RuntimeSessionBinding:
    return RuntimeSessionBinding(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_id=row.conversation_id,
        runtime_profile_id=row.runtime_profile_id,
        runtime_session_ref=row.runtime_session_ref,
        status=RuntimeBindingStatus(row.status),
        current_epoch=row.current_epoch,
        next_expected_runtime_seq=row.next_expected_runtime_seq,
        acked_through_runtime_seq=row.acked_through_runtime_seq,
        active_stream_id=row.active_stream_id,
        stream_lease_expires_at=row.stream_lease_expires_at,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def to_event(row: RunEventModel) -> RunEvent:
    content = RunEventContent(
        payload_inline=(
            RunEventPayload.model_validate(row.payload_inline)
            if row.payload_inline is not None
            else None
        ),
        payload_ref=row.payload_ref,
        payload_state=EventPayloadState(row.payload_state),
        payload_digest=row.payload_digest,
        payload_size=row.payload_size,
        media_type=row.media_type,
        classification=SnapshotClassification(row.classification),
        expires_at=row.expires_at,
    )
    return RunEvent(
        id=row.id,
        tenant_id=row.tenant_id,
        conversation_id=row.conversation_id,
        run_id=row.run_id,
        seq=row.seq,
        event_type=RunEventType(row.event_type),
        schema_version=row.schema_version,
        occurred_at=row.occurred_at,
        persisted_at=row.persisted_at,
        visibility=EventVisibility(row.visibility),
        content=content,
        runtime_profile_id=row.runtime_profile_id,
        runtime_binding_id=row.runtime_binding_id,
        runtime_epoch=row.runtime_epoch,
        runtime_seq=row.runtime_seq,
        runtime_event_id=row.runtime_event_id,
        runtime_event_digest=row.runtime_event_digest,
        correlation_id=row.correlation_id,
        causation_id=row.causation_id,
    )


def phase_content(
    *,
    status_from: RunStatus,
    status_to: RunStatus,
    summary: str,
) -> RunEventContent:
    return inline_event_content(
        RunEventPayload(
            summary=summary,
            status_from=status_from,
            status_to=status_to,
        ),
        classification=SnapshotClassification.INTERNAL,
    )


def terminal_content(result: TerminalResult) -> RunEventContent:
    return inline_event_content(
        RunEventPayload(
            summary=result.reason,
            code=result.code,
            status_to=RunStatus(result.outcome),
            usage=result.usage,
            output_digest=result.output_digest,
        ),
        classification=SnapshotClassification.INTERNAL,
    )
