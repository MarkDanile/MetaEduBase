from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from app.shared.schemas.agent_integration import AgentIntegrationEventV1
from app.shared.schemas.canonical_json import canonical_digest

_EVENT_ADAPTER: TypeAdapter[AgentIntegrationEventV1] = TypeAdapter(
    AgentIntegrationEventV1
)


def integration_event_payload(event: AgentIntegrationEventV1) -> dict[str, Any]:
    return event.model_dump(mode="json")


def integration_event_digest(event: AgentIntegrationEventV1) -> str:
    return canonical_digest(integration_event_payload(event))


def parse_integration_event(payload: dict[str, Any]) -> AgentIntegrationEventV1:
    return _EVENT_ADAPTER.validate_python(payload)
