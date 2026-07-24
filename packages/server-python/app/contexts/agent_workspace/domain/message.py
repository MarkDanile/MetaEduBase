from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MessageKind(StrEnum):
    USER_INPUT = "user_input"
    ASSISTANT_OUTPUT = "assistant_output"
    SYSTEM_NOTICE = "system_notice"


class AuthorType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class TurnDispatchState(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DEAD_LETTER = "dead_letter"
    ABANDONED = "abandoned"


class MessageContentState(StrEnum):
    VISIBLE = "visible"
    REDACTED = "redacted"
    SUPERSEDED = "superseded"


class MessagePartType(StrEnum):
    TEXT = "text"
    RESOURCE_REF = "resource_ref"


class ContentClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


@dataclass(frozen=True, slots=True)
class MessagePart:
    id: uuid.UUID
    tenant_id: uuid.UUID
    message_id: uuid.UUID
    part_seq: int
    part_type: MessagePartType
    text_content: str | None
    content_format: str | None
    resource_id: uuid.UUID | None
    media_type: str | None
    display_name: str | None
    digest: str
    classification: ContentClassification


@dataclass(frozen=True, slots=True)
class Message:
    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    seq: int
    message_kind: MessageKind
    author_type: AuthorType
    author_id: uuid.UUID | None
    client_message_id: uuid.UUID | None
    requested_run_id: uuid.UUID | None
    requested_run_queue_seq: int | None
    turn_request_digest: str | None
    turn_dispatch_state: TurnDispatchState | None
    turn_dispatch_error_code: str | None
    turn_dispatch_updated_at: datetime | None
    origin_run_id: uuid.UUID | None
    output_ordinal: int | None
    reply_to_message_id: uuid.UUID | None
    content_state: MessageContentState
    content_digest: str
    created_at: datetime
    redacted_at: datetime | None
    redacted_reason: str | None
    parts: tuple[MessagePart, ...] = ()
