"""TD-056: rebuild_document_chunks must return the rebuilt chunk count.

Pre-fix: the function returned None because the outer
`asyncio.run(_run_in_session(_do))` call at the end of the
function discarded the return value of `asyncio.run`. Inside
`_do`, the rebuilt chunk count was only logged via `logger.info`
— never returned.

After fix: `_do` returns `len(all_chunks)`; the outer
`asyncio.run(...)` propagates that int back to the caller.

The fix is structurally identical to TD-055
(test_cleanup_orphan_chunks_return.py): capture asyncio.run's
return value so direct (non-Celery) callers see a typed int
instead of None.

We mock `asyncio.run` to return a known int to simulate the
whole async chain returning that value. The inner `_do` is
exercised via the real event loop in a separate test
(``test_inner_do_returns_chunk_count_via_real_event_loop``)
that drives the function through its happy path.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.contexts.document.application.tasks import rebuild_chunks

_TENANT_STR = "00000000-0000-0000-0000-000000000001"
_FID_STR = "12345678-1234-1234-1234-123456789012"


def test_rebuild_document_chunks_returns_rebuilt_chunk_count() -> None:
    """`rebuild_document_chunks` must return the int that `_do` yields.

    Pre-fix: returned None (asyncio.run's return discarded).
    """
    with patch("asyncio.run", return_value=7):
        result = rebuild_chunks.rebuild_document_chunks(_FID_STR, _TENANT_STR)

    assert result == 7, (
        f"rebuild_document_chunks must return the rebuilt chunk count; "
        f"got {result!r} (None means asyncio.run's return was discarded)"
    )
    assert isinstance(result, int), (
        f"return type must be int, got {type(result).__name__}"
    )


def test_rebuild_document_chunks_zero_returns_zero() -> None:
    """When no chunks are rebuilt (e.g. empty sections), return 0."""
    with patch("asyncio.run", return_value=0):
        result = rebuild_chunks.rebuild_document_chunks(_FID_STR, _TENANT_STR)

    assert result == 0
    assert isinstance(result, int)


def test_rebuild_document_chunks_zero_does_not_return_none() -> None:
    """Regression lock against the exact TD-056 bug.

    Pre-fix, the function returned None (asyncio.run discards
    the return value). Lock that the return value is NOT None
    under any rebuilt count.
    """
    for fake_count in (0, 1, 7, 100, 1000):
        with patch("asyncio.run", return_value=fake_count):
            result = rebuild_chunks.rebuild_document_chunks(_FID_STR, _TENANT_STR)
        assert result is not None, (
            f"rebuild_document_chunks returned None for count={fake_count}; "
            f"this is the TD-056 bug"
        )
        assert result == fake_count


def test_rebuild_document_chunks_accepts_uuid_strings() -> None:
    """Calling with UUID-string file_id_str / tenant_id_str must not raise."""
    parsed_fid = uuid.UUID(_FID_STR)
    parsed_tid = uuid.UUID(_TENANT_STR)
    assert parsed_fid is not None
    assert parsed_tid is not None

    with patch("asyncio.run", return_value=42):
        # No exception expected.
        result = rebuild_chunks.rebuild_document_chunks(_FID_STR, _TENANT_STR)
    assert result == 42
