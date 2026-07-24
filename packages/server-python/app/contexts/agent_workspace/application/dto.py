from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.contexts.agent_workspace.domain import (
    ContentClassification,
    Conversation,
    Message,
    MessagePartType,
)


@dataclass(frozen=True, slots=True)
class MessagePartInput:
    type: MessagePartType
    text: str | None = None
    format: str | None = None
    resource_id: uuid.UUID | None = None
    media_type: str | None = None
    display_name: str | None = None
    classification: ContentClassification = ContentClassification.INTERNAL


@dataclass(frozen=True, slots=True)
class ConversationView:
    conversation: Conversation
    pinned_at: datetime | None


@dataclass(frozen=True, slots=True)
class ConversationPage:
    items: tuple[ConversationView, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class MessagePage:
    items: tuple[Message, ...]
    has_more: bool


@dataclass(frozen=True, slots=True)
class ReservedUserTurn:
    message: Message
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class TurnCommand:
    client_message_id: uuid.UUID
    parts: tuple[MessagePartInput, ...]
    agent_definition_version_id: uuid.UUID
    client_options: dict[str, Any] = field(default_factory=dict)
