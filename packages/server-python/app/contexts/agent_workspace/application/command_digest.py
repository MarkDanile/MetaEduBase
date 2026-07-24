from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from app.contexts.agent_workspace.application.dto import MessagePartInput
from app.contexts.agent_workspace.domain import MessagePartType
from app.shared.schemas.canonical_json import canonical_digest


def canonical_part(part: MessagePartInput) -> dict[str, Any]:
    if part.type is MessagePartType.TEXT:
        return {
            "classification": part.classification.value,
            "format": part.format or "plain_text",
            "text": part.text,
            "type": part.type.value,
        }
    return {
        "classification": part.classification.value,
        "display_name": part.display_name,
        "media_type": part.media_type,
        "resource_id": str(part.resource_id) if part.resource_id else None,
        "type": part.type.value,
    }


def message_content_digest(parts: Sequence[MessagePartInput]) -> str:
    return canonical_digest(
        {
            "parts": [canonical_part(part) for part in parts],
            "schema_version": 1,
        }
    )


def message_part_digest(part: MessagePartInput) -> str:
    return canonical_digest({"part": canonical_part(part), "schema_version": 1})


def turn_request_digest(
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    conversation_id: uuid.UUID,
    client_message_id: uuid.UUID,
    parts: Sequence[MessagePartInput],
    agent_definition_version_id: uuid.UUID,
    client_options: Mapping[str, Any],
) -> str:
    """Digest every client-controlled submit field, not only message text."""
    return canonical_digest(
        {
            "actor_id": str(actor_id),
            "agent_definition_version_id": str(agent_definition_version_id),
            "client_options": dict(client_options),
            "client_message_id": str(client_message_id),
            "conversation_id": str(conversation_id),
            "parts": [canonical_part(part) for part in parts],
            "schema_version": 1,
            "tenant_id": str(tenant_id),
        }
    )
