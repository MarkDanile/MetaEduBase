from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contexts.agent_execution.domain.errors import RunEventPayloadError
from app.contexts.agent_execution.domain.run import RunStatus, RunUsageSummary
from app.contexts.agent_execution.domain.snapshots import (
    SnapshotClassification,
    snapshot_digest,
)

MAX_INLINE_EVENT_BYTES = 32 * 1024


class RunEventType(StrEnum):
    RUN_STARTED = "run.started"
    PHASE_CHANGED = "phase.changed"
    PLAN_SUMMARY = "plan.summary"
    TOOL_STARTED = "tool.started"
    TOOL_PROGRESS = "tool.progress"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    EVIDENCE_ADDED = "evidence.added"
    EVIDENCE_CONFLICT = "evidence.conflict"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    APPROVAL_EXPIRED = "approval.expired"
    INPUT_REQUESTED = "input.requested"
    INPUT_RESOLVED = "input.resolved"
    ARTIFACT_CREATED = "artifact.created"
    ARTIFACT_UPDATED = "artifact.updated"
    USAGE_UPDATED = "usage.updated"
    RETRY_SCHEDULED = "retry.scheduled"
    ERROR_REPORTED = "error.reported"
    RUN_RESUME_REQUIRED = "run.resume_required"
    TOOL_OUTCOME_UNKNOWN = "tool.outcome_unknown"
    RUNTIME_TERMINAL_OBSERVED = "runtime.terminal_observed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    RUN_EXPIRED = "run.expired"
    MESSAGE_PUBLISH_REQUESTED = "message.publish_requested"
    MESSAGE_PUBLISHED = "message.published"


TERMINAL_EVENT_TYPES = frozenset(
    {
        RunEventType.RUN_COMPLETED,
        RunEventType.RUN_FAILED,
        RunEventType.RUN_CANCELLED,
        RunEventType.RUN_EXPIRED,
    }
)


class EventVisibility(StrEnum):
    USER = "user"
    TENANT_ADMIN = "tenant_admin"
    INTERNAL = "internal"


class EventPayloadState(StrEnum):
    INLINE = "inline"
    EXTERNAL = "external"
    REDACTED = "redacted"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class RunEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    summary: str | None = Field(default=None, max_length=4_000)
    phase: str | None = Field(default=None, max_length=100)
    code: str | None = Field(default=None, max_length=100)
    status_from: RunStatus | None = None
    status_to: RunStatus | None = None
    attempt: int | None = Field(default=None, ge=0, le=10_000)
    usage: RunUsageSummary | None = None
    output_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RunEventContent:
    payload_inline: RunEventPayload | None
    payload_ref: str | None
    payload_state: EventPayloadState
    payload_digest: str
    payload_size: int
    media_type: str
    classification: SnapshotClassification
    expires_at: datetime | None

    def __post_init__(self) -> None:
        if len(self.payload_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.payload_digest
        ):
            raise RunEventPayloadError(
                "event payload digest must be lowercase SHA-256"
            )
        if not 0 <= self.payload_size <= 2**53 - 1:
            raise RunEventPayloadError(
                "event payload size is outside the supported range"
            )
        media_type_parts = self.media_type.split("/")
        if (
            not self.media_type
            or len(self.media_type) > 100
            or len(media_type_parts) != 2
            or any(not part for part in media_type_parts)
            or any(character.isspace() for character in self.media_type)
        ):
            raise RunEventPayloadError(
                "event media type must be a compact type/subtype"
            )
        if self.payload_state is EventPayloadState.INLINE:
            self._validate_inline()
        elif self.payload_state is EventPayloadState.EXTERNAL:
            self._validate_external()
        elif self.payload_inline is not None:
            raise RunEventPayloadError(
                "redacted, expired, or archived payloads cannot be inline"
            )
        elif self.payload_ref is not None:
            _validate_opaque_ref(self.payload_ref)

    def _validate_inline(self) -> None:
        if self.payload_inline is None or self.payload_ref is not None:
            raise RunEventPayloadError(
                "inline RunEvent payload requires a body and no external ref"
            )
        if self.classification is SnapshotClassification.RESTRICTED:
            raise RunEventPayloadError("restricted RunEvent payloads must be external")
        serialized = _serialize_payload(self.payload_inline)
        if len(serialized) > MAX_INLINE_EVENT_BYTES:
            raise RunEventPayloadError("inline RunEvent payload exceeds 32 KiB")
        if self.payload_size != len(serialized):
            raise RunEventPayloadError("inline RunEvent payload size does not match body")
        expected_digest = snapshot_digest(
            self.payload_inline.model_dump(mode="json")
        )
        if self.payload_digest != expected_digest:
            raise RunEventPayloadError(
                "inline RunEvent payload digest does not match body"
            )

    def _validate_external(self) -> None:
        if self.payload_inline is not None or self.payload_ref is None:
            raise RunEventPayloadError(
                "external RunEvent payload requires a ref and no inline body"
            )
        _validate_opaque_ref(self.payload_ref)


@dataclass(frozen=True, slots=True)
class RunEvent:
    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    run_id: uuid.UUID
    seq: int
    event_type: RunEventType
    schema_version: int
    occurred_at: datetime
    persisted_at: datetime
    visibility: EventVisibility
    content: RunEventContent
    runtime_profile_id: uuid.UUID | None
    runtime_binding_id: uuid.UUID | None
    runtime_epoch: int | None
    runtime_seq: int | None
    runtime_event_id: uuid.UUID | None
    runtime_event_digest: str | None
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None


def inline_event_content(
    payload: RunEventPayload,
    *,
    classification: SnapshotClassification,
    expires_at: datetime | None = None,
) -> RunEventContent:
    if classification is SnapshotClassification.RESTRICTED:
        raise RunEventPayloadError("restricted RunEvent payloads must be external")
    serialized = _serialize_payload(payload)
    if len(serialized) > MAX_INLINE_EVENT_BYTES:
        raise RunEventPayloadError("inline RunEvent payload exceeds 32 KiB")
    return RunEventContent(
        payload_inline=payload,
        payload_ref=None,
        payload_state=EventPayloadState.INLINE,
        payload_digest=snapshot_digest(payload.model_dump(mode="json")),
        payload_size=len(serialized),
        media_type="application/json",
        classification=classification,
        expires_at=expires_at,
    )


def external_event_content(
    *,
    payload_ref: str,
    payload_digest: str,
    payload_size: int,
    media_type: str,
    classification: SnapshotClassification,
    expires_at: datetime | None = None,
) -> RunEventContent:
    return RunEventContent(
        payload_inline=None,
        payload_ref=payload_ref,
        payload_state=EventPayloadState.EXTERNAL,
        payload_digest=payload_digest,
        payload_size=payload_size,
        media_type=media_type,
        classification=classification,
        expires_at=expires_at,
    )


def _serialize_payload(payload: RunEventPayload) -> bytes:
    return json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_opaque_ref(payload_ref: str) -> None:
    if (
        not payload_ref
        or len(payload_ref) > 500
        or "://" in payload_ref
        or any(character.isspace() for character in payload_ref)
    ):
        raise RunEventPayloadError("event payload refs must be opaque identifiers")
