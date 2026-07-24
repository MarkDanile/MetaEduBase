from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.contexts.agent_execution.domain import (
    EventVisibility,
    RunBudgetSnapshot,
    RunConfigSnapshot,
    RunEventContent,
    RunEventType,
    RuntimeCapabilitySnapshot,
    RuntimeIngestFrame,
    SnapshotClassification,
)


@dataclass(frozen=True, slots=True)
class CreateRunCommand:
    run_id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    queue_seq: int
    root_input_message_id: uuid.UUID
    root_request_id: uuid.UUID
    root_context_digest: str
    parent_run_id: uuid.UUID | None
    agent_definition_version_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    runtime_binding_id: uuid.UUID | None
    runtime_capability_snapshot: RuntimeCapabilitySnapshot
    run_config_snapshot: RunConfigSnapshot
    context_snapshot_ref: str | None
    context_snapshot_digest: str | None
    context_snapshot_classification: SnapshotClassification | None
    budget_snapshot: RunBudgetSnapshot
    created_by: uuid.UUID
    correlation_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class NewRunEvent:
    event_type: RunEventType
    content: RunEventContent
    visibility: EventVisibility
    occurred_at: datetime
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class RuntimeEventCommand:
    frame: RuntimeIngestFrame
    stream_id: uuid.UUID
    event: NewRunEvent
