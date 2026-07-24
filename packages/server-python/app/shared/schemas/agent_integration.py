from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.shared.schemas.canonical_json import canonical_json_bytes

TURN_REQUESTED_V1 = "turn.requested.v1"
ASSISTANT_MESSAGE_PUBLISH_REQUESTED_V1 = (
    "assistant_message.publish_requested.v1"
)
MAX_INLINE_INTEGRATION_BYTES = 24 * 1024


class _FrozenIntegrationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeCapabilitySnapshotV1(_FrozenIntegrationSchema):
    schema_version: Literal[1] = 1
    runtime_kind: str = Field(min_length=1, max_length=50)
    adapter_key: str = Field(min_length=1, max_length=100)
    resume: bool
    steer: bool
    native_tools: bool
    tool_calls: bool
    input_requests: bool
    approvals: bool
    event_ack: bool


class RunBudgetSnapshotV1(_FrozenIntegrationSchema):
    schema_version: Literal[1] = 1
    max_steps: int = Field(ge=0, le=100_000)
    max_wall_seconds: int = Field(ge=0, le=604_800)
    max_tokens: int = Field(ge=0, le=2**53 - 1)
    max_cost_micros: int = Field(ge=0, le=2**53 - 1)
    max_tool_calls: int = Field(ge=0, le=100_000)
    max_retries: int = Field(ge=0, le=10_000)


class RunConfigSnapshotV1(_FrozenIntegrationSchema):
    schema_version: Literal[1] = 1
    agent_definition_version_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    model_profile_key: str | None = Field(default=None, max_length=100)
    autonomy_level: int = Field(ge=0, le=3)
    policy_version: str = Field(min_length=1, max_length=100)
    tool_keys: tuple[str, ...] = Field(default_factory=tuple, max_length=1_000)
    budget: RunBudgetSnapshotV1

    @field_validator("tool_keys")
    @classmethod
    def validate_tool_keys(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or len(value) > 200 for value in values):
            raise ValueError("tool keys must contain 1 to 200 characters")
        if len(set(values)) != len(values):
            raise ValueError("tool keys must be unique")
        return values


class TurnLaunchSpecV1(_FrozenIntegrationSchema):
    """Server-selected immutable execution inputs for a queued root turn."""

    agent_definition_version_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    runtime_binding_id: uuid.UUID | None = None
    runtime_capability_snapshot: RuntimeCapabilitySnapshotV1
    run_config_snapshot: RunConfigSnapshotV1
    context_snapshot_ref: str | None = Field(default=None, max_length=500)
    context_snapshot_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    context_snapshot_classification: Literal[
        "public", "internal", "restricted"
    ] | None = None
    budget_snapshot: RunBudgetSnapshotV1
    parent_run_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_context_snapshot(self) -> TurnLaunchSpecV1:
        values = (
            self.context_snapshot_ref,
            self.context_snapshot_digest,
            self.context_snapshot_classification,
        )
        if any(value is not None for value in values) and any(
            value is None for value in values
        ):
            raise ValueError("context snapshot metadata must be all-null or all-present")
        if self.run_config_snapshot.budget != self.budget_snapshot:
            raise ValueError("run config budget does not match launch budget snapshot")
        if (
            len(canonical_json_bytes(self.model_dump(mode="json")))
            > MAX_INLINE_INTEGRATION_BYTES
        ):
            raise ValueError("turn launch exceeds the B1 inline integration limit")
        return self


class TurnRequestedV1(_FrozenIntegrationSchema):
    event_id: uuid.UUID
    event_type: Literal["turn.requested.v1"] = "turn.requested.v1"
    schema_version: Literal[1] = 1
    tenant_id: uuid.UUID
    aggregate_id: uuid.UUID
    aggregate_type: Literal["workspace.message"] = "workspace.message"
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    run_id: uuid.UUID
    queue_seq: int = Field(ge=1)
    root_request_id: uuid.UUID
    root_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_by: uuid.UUID
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None = None
    launch: TurnLaunchSpecV1
    occurred_at: datetime

    @model_validator(mode="after")
    def validate_identity(self) -> TurnRequestedV1:
        if self.aggregate_id != self.message_id:
            raise ValueError("turn aggregate_id must equal message_id")
        if (
            self.launch.run_config_snapshot.agent_definition_version_id
            != self.launch.agent_definition_version_id
        ):
            raise ValueError("run config Agent definition does not match launch identity")
        if (
            self.launch.run_config_snapshot.runtime_profile_id
            != self.launch.runtime_profile_id
        ):
            raise ValueError("run config Runtime profile does not match launch identity")
        if len(canonical_json_bytes(self.model_dump(mode="json"))) > 32 * 1024:
            raise ValueError("turn event exceeds the durable inline payload limit")
        return self


class AssistantMessagePublishRequestedV1(_FrozenIntegrationSchema):
    event_id: uuid.UUID
    event_type: Literal["assistant_message.publish_requested.v1"] = (
        "assistant_message.publish_requested.v1"
    )
    schema_version: Literal[1] = 1
    tenant_id: uuid.UUID
    aggregate_id: uuid.UUID
    aggregate_type: Literal["execution.run"] = "execution.run"
    conversation_id: uuid.UUID
    run_id: uuid.UUID
    message_id: uuid.UUID
    output_ordinal: Literal[0] = 0
    reply_to_message_id: uuid.UUID
    agent_definition_version_id: uuid.UUID
    output_ref: str = Field(min_length=1, max_length=500)
    output_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_size: int = Field(ge=0, le=2**53 - 1)
    output_media_type: str = Field(
        min_length=3,
        max_length=100,
        pattern=(
            r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/"
            r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$"
        ),
    )
    output_classification: Literal["public", "internal", "restricted"]
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None = None
    occurred_at: datetime

    @model_validator(mode="after")
    def validate_identity(self) -> AssistantMessagePublishRequestedV1:
        if self.aggregate_id != self.run_id:
            raise ValueError("publish aggregate_id must equal run_id")
        if len(canonical_json_bytes(self.model_dump(mode="json"))) > 32 * 1024:
            raise ValueError("publish event exceeds the durable inline payload limit")
        return self


class InboxAckV1(_FrozenIntegrationSchema):
    event_id: uuid.UUID
    tenant_id: uuid.UUID
    consumer_name: str = Field(min_length=1, max_length=100)
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_attempt: int = Field(ge=1)
    claimant_id: str = Field(min_length=1, max_length=100)
    status: Literal["consumed"] = "consumed"
    consumed_at: datetime


AgentIntegrationEventV1 = TurnRequestedV1 | AssistantMessagePublishRequestedV1
