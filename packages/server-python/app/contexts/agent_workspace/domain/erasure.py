"""R1 coordination infrastructure 领域类型（Erasure/Purge/LegalHold）。

这些类型属于 control-plane coordination infrastructure（Spec §5），不成为
Message/Run 之外的第三份业务正文事实源。ORM 落在 ``agent_workspace``
（Conversation/lifecycle envelope owner），经 composition port 使用，不建
跨 bounded-context 外键或 ORM cascade。R1-S1 只定义状态与 CAS 语义，
不启动 purge scheduler、不清除任何正文。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ErasureFenceState(StrEnum):
    ACTIVE = "active"
    ERASING = "erasing"
    ERASED = "erased"
    BLOCKED = "blocked"


class PurgeOperationState(StrEnum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PurgeOwnerState(StrEnum):
    PENDING = "pending"
    ERASING = "erasing"
    BLOCKED = "blocked"
    FAILED = "failed"
    ACKED = "acked"


class LegalHoldState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"


@dataclass(frozen=True, slots=True)
class ErasureFence:
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    owner_key: str
    owner_version: int
    state: ErasureFenceState
    purge_revision: int
    hold_revision: int
    ingress_checkpoint: dict
    ingress_digest: str
    last_body_write_at: datetime | None
    ack_digest: str | None
    acked_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PurgeOperation:
    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    purge_revision: int
    state: PurgeOperationState
    registry_digest: str
    registry_snapshot: list
    retention_policy_snapshot: dict
    retention_policy_digest: str
    hold_revision_snapshot: int
    lease_epoch: int
    scheduled_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    next_retry_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PurgeOwnerCheckpoint:
    id: uuid.UUID
    tenant_id: uuid.UUID
    purge_operation_id: uuid.UUID
    owner_key: str
    owner_version: int
    capability_digest: str
    state: PurgeOwnerState
    attempt: int
    checkpoint_digest: str | None
    ack_digest: str | None
    reason_code: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationLegalHold:
    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    reason_code: str
    purpose: str
    actor_id: uuid.UUID
    state: LegalHoldState
    expires_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime
    released_at: datetime | None
    released_by: uuid.UUID | None
