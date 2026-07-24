from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.contexts.agent_execution.domain.errors import (
    InvalidRuntimeProvenanceError,
    RuntimeEpochMismatchError,
    RuntimeEventConflictError,
    RuntimeSequenceGapError,
)
from app.contexts.agent_execution.domain.identity import RuntimeSessionBinding


class RuntimeIngestAction(StrEnum):
    ACCEPT = "accept"
    IDEMPOTENT_REPLAY = "idempotent_replay"


@dataclass(frozen=True, slots=True)
class RuntimeEventProvenance:
    binding_id: uuid.UUID | None = None
    runtime_epoch: int | None = None
    runtime_seq: int | None = None
    runtime_event_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        values = (
            self.binding_id,
            self.runtime_epoch,
            self.runtime_seq,
            self.runtime_event_id,
        )
        if any(value is None for value in values) and any(
            value is not None for value in values
        ):
            raise InvalidRuntimeProvenanceError(
                "binding_id/runtime_epoch/runtime_seq/runtime_event_id "
                "must be all empty or all present"
            )
        if self.runtime_epoch is not None and self.runtime_epoch < 1:
            raise InvalidRuntimeProvenanceError("runtime_epoch must be positive")
        if self.runtime_seq is not None and self.runtime_seq < 1:
            raise InvalidRuntimeProvenanceError("runtime_seq must be positive")

    @property
    def is_native(self) -> bool:
        return self.binding_id is not None


@dataclass(frozen=True, slots=True)
class RuntimeIngestFrame:
    tenant_id: uuid.UUID
    run_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    provenance: RuntimeEventProvenance
    event_digest: str

    def __post_init__(self) -> None:
        if len(self.event_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.event_digest
        ):
            raise InvalidRuntimeProvenanceError(
                "runtime event digest must be lowercase SHA-256"
            )


@dataclass(frozen=True, slots=True)
class PersistedRuntimeReceipt:
    tenant_id: uuid.UUID
    run_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    binding_id: uuid.UUID
    runtime_epoch: int
    runtime_seq: int
    runtime_event_id: uuid.UUID
    event_digest: str


@dataclass(frozen=True, slots=True)
class RuntimeIngestDecision:
    action: RuntimeIngestAction
    acked_through_runtime_seq: int


def evaluate_runtime_ingest(
    *,
    binding: RuntimeSessionBinding,
    expected_run_id: uuid.UUID,
    frame: RuntimeIngestFrame,
    persisted_receipt: PersistedRuntimeReceipt | None = None,
) -> RuntimeIngestDecision:
    provenance = frame.provenance
    if not provenance.is_native:
        raise InvalidRuntimeProvenanceError(
            "Runtime binding ingestion requires complete native provenance"
        )
    if (
        frame.tenant_id != binding.tenant_id
        or frame.runtime_profile_id != binding.runtime_profile_id
        or frame.run_id != expected_run_id
        or provenance.binding_id != binding.id
    ):
        raise InvalidRuntimeProvenanceError(
            "runtime frame crosses tenant/run/profile/binding boundary"
        )
    if provenance.runtime_epoch != binding.current_epoch:
        raise RuntimeEpochMismatchError(
            f"expected epoch {binding.current_epoch}, got {provenance.runtime_epoch}"
        )
    runtime_seq = provenance.runtime_seq
    if runtime_seq is None:
        raise InvalidRuntimeProvenanceError("runtime_seq is required")
    if runtime_seq == binding.next_expected_runtime_seq:
        return RuntimeIngestDecision(
            action=RuntimeIngestAction.ACCEPT,
            acked_through_runtime_seq=binding.acked_through_runtime_seq,
        )
    if runtime_seq > binding.next_expected_runtime_seq:
        raise RuntimeSequenceGapError(
            expected=binding.next_expected_runtime_seq,
            received=runtime_seq,
        )
    if persisted_receipt is None:
        raise RuntimeEventConflictError(
            "persisted receipt is required to validate a replayed runtime sequence"
        )
    receipt_identity = (
        persisted_receipt.tenant_id,
        persisted_receipt.run_id,
        persisted_receipt.runtime_profile_id,
        persisted_receipt.binding_id,
        persisted_receipt.runtime_epoch,
        persisted_receipt.runtime_seq,
        persisted_receipt.runtime_event_id,
        persisted_receipt.event_digest,
    )
    frame_identity = (
        frame.tenant_id,
        frame.run_id,
        frame.runtime_profile_id,
        provenance.binding_id,
        provenance.runtime_epoch,
        runtime_seq,
        provenance.runtime_event_id,
        frame.event_digest,
    )
    if receipt_identity != frame_identity:
        raise RuntimeEventConflictError(
            "runtime sequence was replayed with conflicting identity or digest"
        )
    return RuntimeIngestDecision(
        action=RuntimeIngestAction.IDEMPOTENT_REPLAY,
        acked_through_runtime_seq=binding.acked_through_runtime_seq,
    )
