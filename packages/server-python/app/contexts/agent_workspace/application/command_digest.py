from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from app.contexts.agent_workspace.application.dto import MessagePartInput
from app.contexts.agent_workspace.domain import MessagePartType

_MAX_SAFE_INTEGER = 2**53 - 1


def _quoted(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("command strings must be valid Unicode scalar values") from exc
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _utf16_sort_key(value: str) -> bytes:
    try:
        return value.encode("utf-16-be")
    except UnicodeEncodeError as exc:
        raise ValueError("command object keys must be valid Unicode") from exc


def _canonicalize(value: Any) -> str:
    """RFC 8785 ordering over the I-JSON subset accepted by turn commands.

    V1 command options deliberately reject floats and integers outside the
    IEEE-754 safe range. This avoids cross-runtime numeric drift until a typed
    option schema defines the exact number representation.
    """
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _quoted(value)
    if isinstance(value, int):
        if not -_MAX_SAFE_INTEGER <= value <= _MAX_SAFE_INTEGER:
            raise ValueError("command integers must be IEEE-754 safe integers")
        return str(value)
    if isinstance(value, float):
        raise ValueError("floating-point command options require a typed schema")
    if isinstance(value, list | tuple):
        return "[" + ",".join(_canonicalize(item) for item in value) + "]"
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("command object keys must be strings")
        keys = sorted(value, key=_utf16_sort_key)
        return "{" + ",".join(
            f"{_quoted(key)}:{_canonicalize(value[key])}" for key in keys
        ) + "}"
    raise ValueError(f"unsupported command JSON value: {type(value).__name__}")


def _canonical_json(value: Any) -> bytes:
    return _canonicalize(value).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


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
