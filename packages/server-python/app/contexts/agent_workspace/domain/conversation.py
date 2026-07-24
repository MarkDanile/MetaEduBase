from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ConversationTitleSource(StrEnum):
    NONE = "none"
    AUTO = "auto"
    USER = "user"


class ConversationState(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class PurgeState(StrEnum):
    NOT_SCHEDULED = "not_scheduled"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class Conversation:
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by: uuid.UUID
    creation_digest: str
    title: str | None
    title_source: ConversationTitleSource
    state: ConversationState
    parent_conversation_id: uuid.UUID | None
    forked_from_message_id: uuid.UUID | None
    next_message_seq: int
    next_run_queue_seq: int
    last_activity_at: datetime
    archived_at: datetime | None
    archived_by: uuid.UUID | None
    deleted_at: datetime | None
    deleted_by: uuid.UUID | None
    purge_after: datetime | None
    purge_state: PurgeState
    purge_revision: int
    purged_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationUserState:
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    pinned_at: datetime | None
    last_read_message_seq: int
    updated_at: datetime
