from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AgentDefinitionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"


class RuntimeBindingStatus(StrEnum):
    CREATING = "creating"
    ACTIVE = "active"
    RESUME_REQUIRED = "resume_required"
    CLOSED = "closed"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class AgentDefinitionVersion:
    id: uuid.UUID
    tenant_id: uuid.UUID
    definition_key: str
    version: int
    status: AgentDefinitionStatus
    definition_digest: str
    created_by: uuid.UUID
    created_at: datetime

    @property
    def versioned_key(self) -> str:
        return f"{self.definition_key}.v{self.version}"


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    id: uuid.UUID
    tenant_id: uuid.UUID
    profile_key: str
    runtime_kind: str
    adapter_key: str
    config_digest: str
    capability_digest: str
    enabled: bool
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RuntimeSessionBinding:
    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    runtime_session_ref: str | None
    status: RuntimeBindingStatus
    current_epoch: int
    next_expected_runtime_seq: int
    acked_through_runtime_seq: int
    active_stream_id: uuid.UUID | None
    stream_lease_expires_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime
