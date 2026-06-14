"""TD-064: ds_extract_kg must return KG entity/relation counts.

Follow-up to TD-063. Same pattern.
Returns {entities: N, relations: M} dict instead of None.
"""

from __future__ import annotations

from unittest.mock import patch

from app.contexts.structured_data.application.tasks.ds_extract_kg import ds_extract_kg

_TENANT_STR = "00000000-0000-0000-0000-000000000001"
_DID_STR = "12345678-1234-1234-1234-123456789012"


def test_ds_extract_kg_returns_summary_dict() -> None:
    fake_result = {"entities": 10, "relations": 5}
    with patch("asyncio.run", return_value=fake_result):
        result = ds_extract_kg(_DID_STR, _TENANT_STR)
    assert result == fake_result
    assert isinstance(result, dict)


def test_ds_extract_kg_zero_returns_zero() -> None:
    empty = {"entities": 0, "relations": 0}
    with patch("asyncio.run", return_value=empty):
        result = ds_extract_kg(_DID_STR, _TENANT_STR)
    assert result == empty


def test_ds_extract_kg_does_not_return_none() -> None:
    for fake in (
        {"entities": 0, "relations": 0},
        {"entities": 1, "relations": 5},
        {"entities": 100, "relations": 200},
    ):
        with patch("asyncio.run", return_value=fake):
            result = ds_extract_kg(_DID_STR, _TENANT_STR)
        assert result is not None
        assert result == fake


def test_ds_extract_kg_accepts_uuid_strings() -> None:
    with patch("asyncio.run", return_value={"entities": 1, "relations": 1}):
        result = ds_extract_kg(_DID_STR, _TENANT_STR)
    assert result is not None
