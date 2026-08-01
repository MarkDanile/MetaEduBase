from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.contexts.agent_execution.application.execution_identity_service import (
    DIRECT_RAG_CAPABILITIES,
)
from app.contexts.agent_execution.domain import (
    ContextReference,
    ContextSnapshot,
    InvalidRuntimeProvenanceError,
    PersistedRuntimeReceipt,
    RunBudgetSnapshot,
    RunConfigSnapshot,
    RuntimeBindingStatus,
    RuntimeEventConflictError,
    RuntimeEventProvenance,
    RuntimeIngestAction,
    RuntimeIngestFrame,
    RuntimeSequenceGapError,
    RuntimeSessionBinding,
    SnapshotClassification,
    evaluate_runtime_ingest,
    snapshot_digest,
)

TENANT = uuid.UUID("30000000-0000-0000-0000-000000000001")
PROFILE = uuid.UUID("30000000-0000-0000-0000-000000000002")
BINDING = uuid.UUID("30000000-0000-0000-0000-000000000003")
RUN = uuid.UUID("30000000-0000-0000-0000-000000000004")
EVENT = uuid.UUID("30000000-0000-0000-0000-000000000005")


def _binding(*, next_seq: int = 4) -> RuntimeSessionBinding:
    now = datetime.now(UTC)
    return RuntimeSessionBinding(
        id=BINDING,
        tenant_id=TENANT,
        conversation_id=uuid.uuid4(),
        runtime_profile_id=PROFILE,
        runtime_session_ref="pi-session",
        status=RuntimeBindingStatus.ACTIVE,
        current_epoch=2,
        next_expected_runtime_seq=next_seq,
        acked_through_runtime_seq=next_seq - 1,
        active_stream_id=uuid.uuid4(),
        stream_lease_expires_at=now,
        revision=1,
        created_at=now,
        updated_at=now,
    )


def _frame(*, seq: int, event_id: uuid.UUID = EVENT, digest: str = "a" * 64):
    return RuntimeIngestFrame(
        tenant_id=TENANT,
        conversation_id=uuid.UUID("30000000-0000-0000-0000-000000000002"),
        run_id=RUN,
        runtime_profile_id=PROFILE,
        provenance=RuntimeEventProvenance(
            binding_id=BINDING,
            runtime_epoch=2,
            runtime_seq=seq,
            runtime_event_id=event_id,
        ),
        event_digest=digest,
    )


def test_compatibility_capabilities_are_fixed_and_versioned():
    assert DIRECT_RAG_CAPABILITIES.schema_version == 1
    assert DIRECT_RAG_CAPABILITIES.runtime_kind == "compatibility"
    assert DIRECT_RAG_CAPABILITIES.resume is False
    assert DIRECT_RAG_CAPABILITIES.steer is False
    assert DIRECT_RAG_CAPABILITIES.native_tools is False
    assert DIRECT_RAG_CAPABILITIES.tool_calls is False
    assert DIRECT_RAG_CAPABILITIES.input_requests is False
    assert DIRECT_RAG_CAPABILITIES.approvals is False
    with pytest.raises(ValidationError):
        DIRECT_RAG_CAPABILITIES.__class__(
            **DIRECT_RAG_CAPABILITIES.model_dump(),
            provider_secret="must-not-enter-snapshot",
        )
    with pytest.raises(ValidationError):
        DIRECT_RAG_CAPABILITIES.__class__(
            **{**DIRECT_RAG_CAPABILITIES.model_dump(), "schema_version": 2}
        )


def test_context_snapshot_contains_refs_not_sensitive_bodies():
    reference = ContextReference(
        owner="agent_workspace",
        ref="message:42",
        digest="b" * 64,
        classification=SnapshotClassification.INTERNAL,
    )
    snapshot = ContextSnapshot(
        conversation_id=uuid.uuid4(),
        message_ids=(uuid.uuid4(),),
        summary_refs=(reference,),
    )
    payload = snapshot.model_dump(mode="json")
    assert payload["schema_version"] == 1
    assert "body" not in str(payload)
    with pytest.raises(ValidationError):
        ContextSnapshot(
            conversation_id=snapshot.conversation_id,
            message_ids=snapshot.message_ids,
            raw_prompt="secret",
        )
    with pytest.raises(ValidationError):
        ContextReference(
            owner="agent_workspace",
            ref="https://example.test/presigned?token=secret",
            digest="b" * 64,
            classification=SnapshotClassification.RESTRICTED,
        )


def test_run_config_snapshot_is_versioned_bounded_and_immutable():
    config = RunConfigSnapshot(
        agent_definition_version_id=uuid.uuid4(),
        runtime_profile_id=uuid.uuid4(),
        model_profile_key="model.readonly.v1",
        autonomy_level=1,
        policy_version="policy.v1",
        tool_keys=("knowledge.hybrid_search.v1",),
        budget=RunBudgetSnapshot(
            max_steps=8,
            max_wall_seconds=120,
            max_tokens=100_000,
            max_cost_micros=1_000_000,
            max_tool_calls=12,
            max_retries=2,
        ),
    )
    assert config.schema_version == 1
    assert config.budget.schema_version == 1
    with pytest.raises(ValidationError):
        RunConfigSnapshot(
            **{
                **config.model_dump(),
                "tool_keys": ("duplicate", "duplicate"),
            }
        )
    with pytest.raises(ValidationError):
        RunConfigSnapshot(
            **{**config.model_dump(), "autonomy_level": 4}
        )


def test_snapshot_digest_is_order_stable_and_rejects_untyped_float():
    first = snapshot_digest(
        {"schema_version": 1, "z": [1, True], "a": {"nested": "value"}}
    )
    second = snapshot_digest(
        {"a": {"nested": "value"}, "z": [1, True], "schema_version": 1}
    )
    assert first == second
    with pytest.raises(ValueError, match="floating-point"):
        snapshot_digest({"schema_version": 1, "temperature": 0.2})


def test_runtime_provenance_is_all_empty_or_all_present():
    assert RuntimeEventProvenance().is_native is False
    with pytest.raises(InvalidRuntimeProvenanceError, match="all empty or all present"):
        RuntimeEventProvenance(binding_id=BINDING, runtime_epoch=2)


def test_gap_is_rejected_without_advancing_ack():
    binding = _binding(next_seq=4)
    with pytest.raises(RuntimeSequenceGapError) as error:
        evaluate_runtime_ingest(
            binding=binding,
            expected_run_id=RUN,
            frame=_frame(seq=5),
        )
    assert error.value.expected == 4
    assert error.value.received == 5
    assert binding.acked_through_runtime_seq == 3


def test_expected_sequence_is_accepted_and_replay_requires_identical_receipt():
    binding = _binding(next_seq=4)
    accepted = evaluate_runtime_ingest(
        binding=binding,
        expected_run_id=RUN,
        frame=_frame(seq=4),
    )
    assert accepted.action is RuntimeIngestAction.ACCEPT

    replay_frame = _frame(seq=3)
    receipt = PersistedRuntimeReceipt(
        tenant_id=TENANT,
        run_id=RUN,
        runtime_profile_id=PROFILE,
        binding_id=BINDING,
        runtime_epoch=2,
        runtime_seq=3,
        runtime_event_id=EVENT,
        event_digest="a" * 64,
    )
    replay = evaluate_runtime_ingest(
        binding=binding,
        expected_run_id=RUN,
        frame=replay_frame,
        persisted_receipt=receipt,
    )
    assert replay.action is RuntimeIngestAction.IDEMPOTENT_REPLAY
    assert replay.acked_through_runtime_seq == 3

    with pytest.raises(RuntimeEventConflictError):
        evaluate_runtime_ingest(
            binding=binding,
            expected_run_id=RUN,
            frame=_frame(seq=3, digest="c" * 64),
            persisted_receipt=receipt,
        )


@pytest.mark.parametrize("boundary", ["tenant", "run", "profile", "binding"])
def test_runtime_frame_cannot_cross_run_tenant_profile_or_binding(boundary: str):
    binding = _binding()
    frame = _frame(seq=4)
    expected_run_id = RUN
    if boundary == "tenant":
        frame = replace(frame, tenant_id=uuid.uuid4())
    elif boundary == "run":
        expected_run_id = uuid.uuid4()
    elif boundary == "profile":
        frame = replace(frame, runtime_profile_id=uuid.uuid4())
    else:
        frame = replace(
            frame,
            provenance=replace(frame.provenance, binding_id=uuid.uuid4()),
        )
    with pytest.raises(InvalidRuntimeProvenanceError, match="crosses"):
        evaluate_runtime_ingest(
            binding=binding,
            expected_run_id=expected_run_id,
            frame=frame,
        )
