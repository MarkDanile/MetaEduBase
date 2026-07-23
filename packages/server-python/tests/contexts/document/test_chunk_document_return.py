"""TD-057: chunk_document must return the inserted chunk count.

Follow-up to TD-055 / TD-056: every `_run_in_session` task in the
codebase should return a meaningful int (chunk count, kg node
count, etc) instead of None. This test locks chunk_document's
contract specifically — the rest of the 9 task fixes will get
their own per-task test files in the same PR.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.contexts.document.application.tasks import chunk as chunk_task

_TENANT_STR = "00000000-0000-0000-0000-000000000001"
_FID_STR = "12345678-1234-1234-1234-123456789012"


def test_chunk_document_returns_chunk_count() -> None:
    """`chunk_document` must return the int that `_do` yields.

    Pre-fix: returned None (asyncio.run's return discarded).
    Post-fix: returns the inserted chunk count.
    """
    with patch("asyncio.run", side_effect=lambda c, r=12: (c.close(), r)[1]):
        result = chunk_task.chunk_document(_FID_STR, _TENANT_STR)

    assert result == 12, (
        f"chunk_document must return the inserted chunk count; "
        f"got {result!r} (None means asyncio.run's return was discarded)"
    )
    assert isinstance(result, int), (
        f"return type must be int, got {type(result).__name__}"
    )


def test_chunk_document_zero_returns_zero() -> None:
    """When no chunks are inserted (empty sections), return 0."""
    with patch("asyncio.run", side_effect=lambda c, r=0: (c.close(), r)[1]):
        result = chunk_task.chunk_document(_FID_STR, _TENANT_STR)
    assert result == 0
    assert isinstance(result, int)


def test_chunk_document_zero_does_not_return_none() -> None:
    """Regression lock against the exact TD-057 bug for chunk_document."""
    for fake_count in (0, 1, 5, 100, 1000):
        with patch("asyncio.run", side_effect=lambda c, r=fake_count: (c.close(), r)[1]):
            result = chunk_task.chunk_document(_FID_STR, _TENANT_STR)
        assert result is not None, (
            f"chunk_document returned None for count={fake_count}; "
            f"this is the TD-057 bug"
        )
        assert result == fake_count


def test_chunk_document_accepts_uuid_strings() -> None:
    """Calling with UUID-string file_id_str / tenant_id_str must not raise."""
    parsed_fid = uuid.UUID(_FID_STR)
    parsed_tid = uuid.UUID(_TENANT_STR)
    assert parsed_fid is not None
    assert parsed_tid is not None

    with patch("asyncio.run", side_effect=lambda c, r=42: (c.close(), r)[1]):
        result = chunk_task.chunk_document(_FID_STR, _TENANT_STR)
    assert result == 42
