from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.contexts.agent_execution.domain import (
    ALLOWED_RUN_TRANSITIONS,
    InvalidRunTransitionError,
    RunEventPayload,
    RunEventPayloadError,
    RunStatus,
    SnapshotClassification,
    TerminalResult,
    external_event_content,
    inline_event_content,
    require_run_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (current, target)
        for current, targets in ALLOWED_RUN_TRANSITIONS.items()
        for target in targets
    ],
)
def test_every_declared_run_transition_is_allowed(
    current: RunStatus,
    target: RunStatus,
):
    require_run_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (current, target)
        for current in RunStatus
        for target in RunStatus
        if target not in ALLOWED_RUN_TRANSITIONS[current]
    ],
)
def test_every_undeclared_run_transition_is_rejected(
    current: RunStatus,
    target: RunStatus,
):
    with pytest.raises(InvalidRunTransitionError):
        require_run_transition(current, target)


def test_completed_terminal_result_requires_all_output_metadata():
    with pytest.raises(ValidationError, match="complete output metadata"):
        TerminalResult(
            outcome="completed",
            code="ok",
            reason="finished",
        )

    result = TerminalResult(
        outcome="completed",
        code="ok",
        reason="finished",
        output_ref="terminal-output:1",
        output_digest="b" * 64,
        output_size=12,
        output_media_type="text/markdown",
        output_classification=SnapshotClassification.INTERNAL,
        terminal_message_id="61000000-0000-0000-0000-000000000099",
    )
    assert result.output_digest == "b" * 64

    with pytest.raises(ValidationError):
        TerminalResult.model_validate({**result.model_dump(), "output_ref": ""})
    with pytest.raises(ValidationError):
        TerminalResult.model_validate(
            {**result.model_dump(), "output_media_type": ""}
        )
    with pytest.raises(ValidationError):
        TerminalResult.model_validate(
            {**result.model_dump(), "output_media_type": " "}
        )


def test_non_completed_terminal_result_rejects_output_metadata():
    with pytest.raises(ValidationError, match="cannot carry output metadata"):
        TerminalResult(
            outcome="failed",
            code="runtime_failed",
            reason="Runtime failed",
            output_ref="must-not-exist",
        )


def test_run_event_payload_enforces_inline_and_external_boundaries():
    with pytest.raises(RunEventPayloadError, match="restricted"):
        inline_event_content(
            RunEventPayload(summary="sensitive"),
            classification=SnapshotClassification.RESTRICTED,
        )
    oversized = RunEventPayload.model_construct(summary="x" * (33 * 1024))
    with pytest.raises(RunEventPayloadError, match="32 KiB"):
        inline_event_content(
            oversized,
            classification=SnapshotClassification.INTERNAL,
        )
    with pytest.raises(RunEventPayloadError, match="opaque"):
        external_event_content(
            payload_ref="https://example.test/presigned?token=secret",
            payload_digest="c" * 64,
            payload_size=100,
            media_type="application/json",
            classification=SnapshotClassification.RESTRICTED,
        )

    external = external_event_content(
        payload_ref="run-event-payload:42",
        payload_digest="c" * 64,
        payload_size=100,
        media_type="application/json",
        classification=SnapshotClassification.RESTRICTED,
    )
    assert external.payload_inline is None
    assert external.payload_ref == "run-event-payload:42"


def test_direct_run_event_content_cannot_forge_inline_integrity_metadata():
    payload = RunEventPayload(summary="integrity checked")
    valid = inline_event_content(
        payload,
        classification=SnapshotClassification.INTERNAL,
    )
    with pytest.raises(RunEventPayloadError, match="digest does not match"):
        replace(valid, payload_digest="d" * 64)
