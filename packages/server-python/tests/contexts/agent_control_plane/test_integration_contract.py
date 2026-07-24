from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.shared.schemas.agent_integration import TurnLaunchSpecV1, TurnRequestedV1
from app.shared.schemas.agent_integration_codec import (
    integration_event_digest,
    parse_integration_event,
)
from app.shared.schemas.canonical_json import canonical_json_bytes


def _launch() -> TurnLaunchSpecV1:
    definition_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    return TurnLaunchSpecV1(
        agent_definition_version_id=definition_id,
        runtime_profile_id=profile_id,
        runtime_capability_snapshot={
            "schema_version": 1,
            "runtime_kind": "direct_rag",
            "adapter_key": "compat",
            "resume": False,
            "steer": False,
            "native_tools": False,
            "tool_calls": False,
            "input_requests": False,
            "approvals": False,
            "event_ack": False,
        },
        run_config_snapshot={
            "schema_version": 1,
            "agent_definition_version_id": str(definition_id),
            "runtime_profile_id": str(profile_id),
            "model_profile_key": "model.readonly.v1",
            "autonomy_level": 1,
            "policy_version": "policy.v1",
            "tool_keys": [],
            "budget": {
                "schema_version": 1,
                "max_steps": 1,
                "max_wall_seconds": 1,
                "max_tokens": 1,
                "max_cost_micros": 1,
                "max_tool_calls": 0,
                "max_retries": 0,
            },
        },
        budget_snapshot={
            "schema_version": 1,
            "max_steps": 1,
            "max_wall_seconds": 1,
            "max_tokens": 1,
            "max_cost_micros": 1,
            "max_tool_calls": 0,
            "max_retries": 0,
        },
    )


def test_turn_requested_v1_is_strict_round_trippable_and_digest_stable():
    message_id = uuid.uuid4()
    event = TurnRequestedV1(
        event_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        aggregate_id=message_id,
        conversation_id=uuid.uuid4(),
        message_id=message_id,
        run_id=uuid.uuid4(),
        queue_seq=1,
        root_request_id=uuid.uuid4(),
        root_context_digest="a" * 64,
        created_by=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        launch=_launch(),
        occurred_at=datetime.now(UTC),
    )

    parsed = parse_integration_event(event.model_dump(mode="json"))

    assert parsed == event
    assert integration_event_digest(parsed) == integration_event_digest(event)
    with pytest.raises(ValidationError, match="aggregate_id"):
        TurnRequestedV1.model_validate(
            {**event.model_dump(mode="json"), "aggregate_id": str(uuid.uuid4())}
        )


def test_integration_codec_uses_rfc8785_utf16_key_order_without_ascii_escaping():
    assert canonical_json_bytes({"\ue000": 1, "\U00010000": 2}) == (
        '{"\U00010000":2,"\ue000":1}'.encode()
    )


def test_turn_launch_rejects_schema_valid_data_that_cannot_fit_inline():
    launch = _launch().model_dump(mode="json")
    launch["run_config_snapshot"]["tool_keys"] = [
        f"{index:03d}" + "x" * 197 for index in range(200)
    ]

    with pytest.raises(ValidationError, match="inline integration limit"):
        TurnLaunchSpecV1.model_validate(launch)
