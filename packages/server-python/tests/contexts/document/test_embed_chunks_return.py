"""TD-059: embed_chunks must return the embedded chunk count.

Follow-up to TD-058 (TD-057 9-task follow-up series slice 2).
Same pattern as TD-055 / TD-056 / TD-057 slice 1 / TD-058.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.contexts.document.application.tasks import embed as embed_task

_TENANT_STR = "00000000-0000-0000-0000-000000000001"
_FID_STR = "12345678-1234-1234-1234-123456789012"


def test_embed_chunks_returns_embedded_count() -> None:
    """`embed_chunks` must return the int that `_do` yields.

    Pre-fix: returned None (asyncio.run's return discarded).
    Post-fix: returns the embedded chunk count.
    """
    with patch("asyncio.run", side_effect=lambda c, r=12: (c.close(), r)[1]):
        result = embed_task.embed_chunks(_FID_STR, _TENANT_STR)

    assert result == 12, (
        f"embed_chunks must return the embedded chunk count; "
        f"got {result!r} (None means asyncio.run's return was discarded)"
    )
    assert isinstance(result, int), (
        f"return type must be int, got {type(result).__name__}"
    )


def test_embed_chunks_zero_returns_zero() -> None:
    """When no chunks are embedded (e.g. no chunks for file), return 0."""
    with patch("asyncio.run", side_effect=lambda c, r=0: (c.close(), r)[1]):
        result = embed_task.embed_chunks(_FID_STR, _TENANT_STR)
    assert result == 0
    assert isinstance(result, int)


def test_embed_chunks_zero_does_not_return_none() -> None:
    """Regression lock against the exact TD-059 bug."""
    for fake_count in (0, 1, 5, 100, 1000):
        with patch("asyncio.run", side_effect=lambda c, r=fake_count: (c.close(), r)[1]):
            result = embed_task.embed_chunks(_FID_STR, _TENANT_STR)
        assert result is not None, (
            f"embed_chunks returned None for count={fake_count}; "
            f"this is the TD-059 bug"
        )
        assert result == fake_count


def test_embed_chunks_accepts_uuid_strings() -> None:
    """Calling with UUID-string file_id_str / tenant_id_str must not raise."""
    parsed_fid = uuid.UUID(_FID_STR)
    parsed_tid = uuid.UUID(_TENANT_STR)
    assert parsed_fid is not None
    assert parsed_tid is not None

    with patch("asyncio.run", side_effect=lambda c, r=42: (c.close(), r)[1]):
        result = embed_task.embed_chunks(_FID_STR, _TENANT_STR)
    assert result == 42
