"""TD-058: parse_document must return the parsed structured_data dict.

Follow-up to TD-055 / TD-056 / TD-057 slice 1. parse_document is
the 2nd in the TD-057 follow-up series (TD-058 ~ TD-066, one task
per PR per git-workflow.md#PR 范围边界).

`_do` returns `_build_parsed_structured_data(parsed.full_text,
len(parsed.sections), sections_data)` — the same dict that was
written to `metaedu.files.structured_data`. Caller can now know
"what was parsed" without re-querying SQL.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.contexts.document.application.tasks import parse as parse_task

_TENANT_STR = "00000000-0000-0000-0000-000000000001"
_FID_STR = "12345678-1234-1234-1234-123456789012"


def test_parse_document_returns_structured_data_dict() -> None:
    """`parse_document` must return the dict that `_do` yields.

    Pre-fix: returned None (asyncio.run's return discarded).
    Post-fix: returns the structured_data dict.
    """
    fake_result = {
        "full_text": "Hello world.",
        "section_count": 1,
        "sections": [
            {"title": "Intro", "level": 1, "path": "1", "page": 0, "content": "Hello world."}
        ],
    }
    with patch("asyncio.run", return_value=fake_result):
        result = parse_task.parse_document(_FID_STR, _TENANT_STR)

    assert result == fake_result, (
        f"parse_document must return the structured_data dict; "
        f"got {result!r} (None means asyncio.run's return was discarded)"
    )
    assert isinstance(result, dict), (
        f"return type must be dict, got {type(result).__name__}"
    )


def test_parse_document_dict_has_required_keys() -> None:
    """The returned dict must include full_text + section_count (TD-009
    contract). `sections` is optional (TD-051 follow-up) but if
    present, must be a list of dicts.
    """
    fake_result = {
        "full_text": "Hello world.",
        "section_count": 1,
        "sections": [],
    }
    with patch("asyncio.run", return_value=fake_result):
        result = parse_task.parse_document(_FID_STR, _TENANT_STR)

    assert "full_text" in result
    assert "section_count" in result
    assert isinstance(result["section_count"], int)


def test_parse_document_does_not_return_none() -> None:
    """Regression lock against the exact TD-058 bug.

    Pre-fix, the function returned None (asyncio.run discards the
    return value). Lock that the return value is NOT None for
    any structured_data dict shape.
    """
    for fake_result in (
        {"full_text": "", "section_count": 0},
        {"full_text": "x", "section_count": 1, "sections": []},
        {"full_text": "xy" * 100, "section_count": 5, "sections": [{"title": "T", "level": 1}]},
    ):
        with patch("asyncio.run", return_value=fake_result):
            result = parse_task.parse_document(_FID_STR, _TENANT_STR)
        assert result is not None, (
            f"parse_document returned None for {fake_result}; "
            f"this is the TD-058 bug"
        )
        assert result == fake_result


def test_parse_document_accepts_uuid_strings() -> None:
    """Calling with UUID-string file_id_str / tenant_id_str must not raise."""
    parsed_fid = uuid.UUID(_FID_STR)
    parsed_tid = uuid.UUID(_TENANT_STR)
    assert parsed_fid is not None
    assert parsed_tid is not None

    with patch("asyncio.run", return_value={"full_text": "x", "section_count": 1}):
        result = parse_task.parse_document(_FID_STR, _TENANT_STR)
    assert result is not None
