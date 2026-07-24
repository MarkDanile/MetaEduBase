from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_MAX_SAFE_INTEGER = 2**53 - 1


class SnapshotClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class _FrozenSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeCapabilitySnapshot(_FrozenSnapshot):
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


class RunBudgetSnapshot(_FrozenSnapshot):
    schema_version: Literal[1] = 1
    max_steps: int = Field(ge=0, le=100_000)
    max_wall_seconds: int = Field(ge=0, le=604_800)
    max_tokens: int = Field(ge=0, le=_MAX_SAFE_INTEGER)
    max_cost_micros: int = Field(ge=0, le=_MAX_SAFE_INTEGER)
    max_tool_calls: int = Field(ge=0, le=100_000)
    max_retries: int = Field(ge=0, le=10_000)


class RunConfigSnapshot(_FrozenSnapshot):
    schema_version: Literal[1] = 1
    agent_definition_version_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    model_profile_key: str | None = Field(default=None, max_length=100)
    autonomy_level: int = Field(ge=0, le=3)
    policy_version: str = Field(min_length=1, max_length=100)
    tool_keys: tuple[str, ...] = Field(default_factory=tuple, max_length=1_000)
    budget: RunBudgetSnapshot

    @field_validator("tool_keys")
    @classmethod
    def validate_tool_keys(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or len(value) > 200 for value in values):
            raise ValueError("tool keys must contain 1 to 200 characters")
        if len(set(values)) != len(values):
            raise ValueError("tool keys must be unique")
        return values


class ContextReference(_FrozenSnapshot):
    owner: str = Field(min_length=1, max_length=100)
    ref: str = Field(min_length=1, max_length=500)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    classification: SnapshotClassification

    @field_validator("ref")
    @classmethod
    def validate_opaque_ref(cls, value: str) -> str:
        if "://" in value or any(character.isspace() for character in value):
            raise ValueError("context refs must be opaque identifiers, not URLs or bodies")
        return value


class ContextSnapshot(_FrozenSnapshot):
    schema_version: Literal[1] = 1
    conversation_id: uuid.UUID
    message_ids: tuple[uuid.UUID, ...] = Field(default_factory=tuple, max_length=10_000)
    summary_refs: tuple[ContextReference, ...] = Field(
        default_factory=tuple, max_length=1_000
    )
    memory_refs: tuple[ContextReference, ...] = Field(
        default_factory=tuple, max_length=1_000
    )
    evidence_refs: tuple[ContextReference, ...] = Field(
        default_factory=tuple, max_length=10_000
    )
    tool_result_refs: tuple[ContextReference, ...] = Field(
        default_factory=tuple, max_length=10_000
    )

    @field_validator("message_ids")
    @classmethod
    def validate_message_ids(cls, values: tuple[uuid.UUID, ...]) -> tuple[uuid.UUID, ...]:
        if len(set(values)) != len(values):
            raise ValueError("message ids must be unique")
        return values


def _quoted(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("snapshot strings must be valid Unicode scalar values") from exc
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _utf16_sort_key(value: str) -> bytes:
    try:
        return value.encode("utf-16-be")
    except UnicodeEncodeError as exc:
        raise ValueError("snapshot object keys must be valid Unicode") from exc


def _canonicalize(value: Any) -> str:
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
            raise ValueError("snapshot integers must be IEEE-754 safe integers")
        return str(value)
    if isinstance(value, float):
        raise ValueError("floating-point snapshot values require a versioned field")
    if isinstance(value, list | tuple):
        return "[" + ",".join(_canonicalize(item) for item in value) + "]"
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("snapshot object keys must be strings")
        keys = sorted(value, key=_utf16_sort_key)
        return "{" + ",".join(
            f"{_quoted(key)}:{_canonicalize(value[key])}" for key in keys
        ) + "}"
    raise ValueError(f"unsupported snapshot JSON value: {type(value).__name__}")


def snapshot_digest(snapshot: _FrozenSnapshot | Mapping[str, Any]) -> str:
    if isinstance(snapshot, BaseModel):
        payload = snapshot.model_dump(mode="json")
    else:
        payload = dict(snapshot)
    canonical = _canonicalize(payload).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
