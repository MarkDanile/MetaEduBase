"""TD-060: index_tsvector must return the indexed chunk count.

Follow-up to TD-059 (TD-057 9-task series slice 4).
Same pattern as TD-055/056/057/058/059.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.contexts.document.application.tasks import index as index_task

_TENANT_STR = "00000000-0000-0000-0000-000000000001"
_FID_STR = "12345678-1234-1234-1234-123456789012"


def test_index_tsvector_returns_indexed_count() -> None:
    """`index_tsvector` must return the int that `_do` yields.

    Pre-fix: returned None (asyncio.run's return discarded).
    Post-fix: returns the indexed chunk count.
    """
    with patch("asyncio.run", return_value=12):
        result = index_task.index_tsvector(_FID_STR, _TENANT_STR)

    assert result == 12
    assert isinstance(result, int)


def test_index_tsvector_zero_returns_zero() -> None:
    with patch("asyncio.run", return_value=0):
        result = index_task.index_tsvector(_FID_STR, _TENANT_STR)
    assert result == 0
    assert isinstance(result, int)


def test_index_tsvector_does_not_return_none() -> None:
    """Regression lock against the exact TD-060 bug."""
    for fake_count in (0, 1, 5, 100, 1000):
        with patch("asyncio.run", return_value=fake_count):
            result = index_task.index_tsvector(_FID_STR, _TENANT_STR)
        assert result is not None
        assert result == fake_count


def test_index_tsvector_accepts_uuid_strings() -> None:
    parsed_fid = uuid.UUID(_FID_STR)
    parsed_tid = uuid.UUID(_TENANT_STR)
    assert parsed_fid is not None
    assert parsed_tid is not None

    with patch("asyncio.run", return_value=42):
        result = index_task.index_tsvector(_FID_STR, _TENANT_STR)
    assert result == 42
