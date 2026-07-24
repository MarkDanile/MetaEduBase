from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contexts.agent_execution.domain.errors import InvalidRunTransitionError
from app.contexts.agent_execution.domain.snapshots import (
    RunBudgetSnapshot,
    RunConfigSnapshot,
    RuntimeCapabilitySnapshot,
    SnapshotClassification,
)


class RunStatus(StrEnum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    WAITING_APPROVAL = "waiting_approval"
    RESUME_REQUIRED = "resume_required"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


TERMINAL_RUN_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.EXPIRED,
    }
)
ACTIVE_RUN_STATUSES = frozenset(
    {
        RunStatus.STARTING,
        RunStatus.RUNNING,
        RunStatus.WAITING_INPUT,
        RunStatus.WAITING_APPROVAL,
        RunStatus.RESUME_REQUIRED,
        RunStatus.CANCELLING,
    }
)

ALLOWED_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset(
        {RunStatus.STARTING, RunStatus.CANCELLED, RunStatus.EXPIRED}
    ),
    RunStatus.STARTING: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.RESUME_REQUIRED,
            RunStatus.CANCELLING,
            RunStatus.FAILED,
            RunStatus.EXPIRED,
        }
    ),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.WAITING_INPUT,
            RunStatus.WAITING_APPROVAL,
            RunStatus.RESUME_REQUIRED,
            RunStatus.CANCELLING,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.EXPIRED,
        }
    ),
    RunStatus.WAITING_INPUT: frozenset(
        {RunStatus.RUNNING, RunStatus.CANCELLING, RunStatus.EXPIRED}
    ),
    RunStatus.WAITING_APPROVAL: frozenset(
        {RunStatus.RUNNING, RunStatus.CANCELLING, RunStatus.EXPIRED}
    ),
    RunStatus.RESUME_REQUIRED: frozenset(
        {RunStatus.STARTING, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.CANCELLING: frozenset(
        {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.EXPIRED,
            RunStatus.RESUME_REQUIRED,
        }
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
    RunStatus.EXPIRED: frozenset(),
}


class OutputPublishState(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    PUBLISHED = "published"
    DEAD_LETTER = "dead_letter"
    SUPPRESSED = "suppressed"


class TurnInputKind(StrEnum):
    ROOT = "root"
    STEER = "steer"
    HUMAN_RESPONSE = "human_response"


class RunUsageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    input_tokens: int = Field(default=0, ge=0, le=2**53 - 1)
    output_tokens: int = Field(default=0, ge=0, le=2**53 - 1)
    cached_tokens: int = Field(default=0, ge=0, le=2**53 - 1)
    tool_calls: int = Field(default=0, ge=0, le=100_000)
    model_calls: int = Field(default=0, ge=0, le=100_000)
    cost_micros: int = Field(default=0, ge=0, le=2**53 - 1)


class TerminalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    outcome: Literal["completed", "failed", "cancelled", "expired"]
    code: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    output_ref: str | None = Field(default=None, min_length=1, max_length=500)
    output_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    output_size: int | None = Field(default=None, ge=0, le=2**53 - 1)
    output_media_type: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$",
    )
    output_classification: SnapshotClassification | None = None
    terminal_message_id: uuid.UUID | None = None
    usage: RunUsageSummary = Field(default_factory=RunUsageSummary)

    @model_validator(mode="after")
    def validate_output_contract(self) -> TerminalResult:
        output_values = (
            self.output_ref,
            self.output_digest,
            self.output_size,
            self.output_media_type,
            self.output_classification,
            self.terminal_message_id,
        )
        if self.outcome == "completed":
            if any(value is None for value in output_values):
                raise ValueError("completed terminal results require complete output metadata")
            if self.output_ref is not None and (
                "://" in self.output_ref
                or any(character.isspace() for character in self.output_ref)
            ):
                raise ValueError("terminal output refs must be opaque identifiers")
        elif any(value is not None for value in output_values):
            raise ValueError("non-completed terminal results cannot carry output metadata")
        return self


@dataclass(frozen=True, slots=True)
class AgentRun:
    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    queue_seq: int
    root_input_message_id: uuid.UUID
    parent_run_id: uuid.UUID | None
    agent_definition_version_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    runtime_binding_id: uuid.UUID | None
    creation_digest: str
    status: RunStatus
    status_revision: int
    next_event_seq: int
    first_available_event_seq: int
    last_event_seq: int
    event_log_complete: bool
    queued_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    terminal_code: str | None
    terminal_reason: str | None
    terminal_result_digest: str | None
    terminal_output_ref: str | None
    terminal_output_digest: str | None
    terminal_output_size: int | None
    terminal_output_media_type: str | None
    terminal_output_classification: SnapshotClassification | None
    terminal_message_id: uuid.UUID | None
    output_publish_state: OutputPublishState
    created_by: uuid.UUID
    correlation_id: uuid.UUID
    runtime_capability_snapshot: RuntimeCapabilitySnapshot
    run_config_snapshot: RunConfigSnapshot
    context_snapshot_ref: str | None
    context_snapshot_digest: str | None
    context_snapshot_classification: SnapshotClassification | None
    budget_snapshot: RunBudgetSnapshot
    usage_summary: RunUsageSummary
    created_at: datetime
    updated_at: datetime

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_RUN_STATUSES


@dataclass(frozen=True, slots=True)
class TurnInput:
    id: uuid.UUID
    tenant_id: uuid.UUID
    run_id: uuid.UUID
    ordinal: int
    input_kind: TurnInputKind
    message_id: uuid.UUID
    request_id: uuid.UUID
    expected_runtime_epoch: int | None
    context_digest: str
    created_by: uuid.UUID
    created_at: datetime


def require_run_transition(current: RunStatus, target: RunStatus) -> None:
    if target not in ALLOWED_RUN_TRANSITIONS[current]:
        raise InvalidRunTransitionError(
            f"Agent Run transition {current.value} -> {target.value} is not allowed"
        )
