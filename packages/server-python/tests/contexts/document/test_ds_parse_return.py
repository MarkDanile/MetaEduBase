"""TD-063: ds_parse must return the parsed row count.

Follow-up to TD-062. Same pattern as TD-055/056/057/058/059/060/061/062.
"""

from __future__ import annotations

from unittest.mock import patch

from app.contexts.structured_data.application.tasks.ds_parse import ds_parse

_TENANT_STR = "00000000-0000-0000-0000-000000000001"
_DID_STR = "12345678-1234-1234-1234-123456789012"


def test_ds_parse_returns_parsed_row_count() -> None:
    with patch("asyncio.run", side_effect=lambda c, r=12: (c.close(), r)[1]):
        result = ds_parse(_DID_STR, _TENANT_STR)
    assert result == 12
    assert isinstance(result, int)


def test_ds_parse_zero_returns_zero() -> None:
    with patch("asyncio.run", side_effect=lambda c, r=0: (c.close(), r)[1]):
        result = ds_parse(_DID_STR, _TENANT_STR)
    assert result == 0


def test_ds_parse_does_not_return_none() -> None:
    for fake_count in (0, 1, 5, 100, 1000):
        with patch("asyncio.run", side_effect=lambda c, r=fake_count: (c.close(), r)[1]):
            result = ds_parse(_DID_STR, _TENANT_STR)
        assert result is not None
        assert result == fake_count


def test_ds_parse_accepts_uuid_strings() -> None:
    with patch("asyncio.run", side_effect=lambda c, r=42: (c.close(), r)[1]):
        result = ds_parse(_DID_STR, _TENANT_STR)
    assert result == 42
