"""TD-065: ds_embed must return the embedded count.

Follow-up to TD-064. Same pattern.
Returns int (success_count) instead of None.
"""

from __future__ import annotations

from unittest.mock import patch

from app.contexts.structured_data.application.tasks.ds_embed import ds_embed

_TENANT_STR = "00000000-0000-0000-0000-000000000001"
_DID_STR = "12345678-1234-1234-1234-123456789012"


def test_ds_embed_returns_embedded_count() -> None:
    with patch("asyncio.run", return_value=7):
        result = ds_embed(_DID_STR, _TENANT_STR)
    assert result == 7
    assert isinstance(result, int)


def test_ds_embed_zero_returns_zero() -> None:
    with patch("asyncio.run", return_value=0):
        result = ds_embed(_DID_STR, _TENANT_STR)
    assert result == 0


def test_ds_embed_does_not_return_none() -> None:
    for fake_count in (0, 1, 5, 100, 1000):
        with patch("asyncio.run", return_value=fake_count):
            result = ds_embed(_DID_STR, _TENANT_STR)
        assert result is not None
        assert result == fake_count


def test_ds_embed_accepts_uuid_strings() -> None:
    with patch("asyncio.run", return_value=42):
        result = ds_embed(_DID_STR, _TENANT_STR)
    assert result == 42
