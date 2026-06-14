"""TD-066: ds_build_cross_dataset_edges must return edge count.

Follow-up to TD-065. Same pattern.
Returns edges_created int instead of None.
"""

from __future__ import annotations

from unittest.mock import patch

from app.contexts.structured_data.application.tasks.ds_cross_dataset_edges import (
    ds_build_cross_dataset_edges,
)

_TENANT_STR = "00000000-0000-0000-0000-000000000001"


def test_ds_build_cross_dataset_edges_returns_edge_count() -> None:
    fake_result = 7
    with patch("asyncio.run", return_value=fake_result):
        result = ds_build_cross_dataset_edges(_TENANT_STR)
    assert result == fake_result
    assert isinstance(result, int)


def test_ds_build_cross_dataset_edges_zero_returns_zero() -> None:
    with patch("asyncio.run", return_value=0):
        result = ds_build_cross_dataset_edges(_TENANT_STR)
    assert result == 0


def test_ds_build_cross_dataset_edges_does_not_return_none() -> None:
    for fake in (0, 1, 50, 999):
        with patch("asyncio.run", return_value=fake):
            result = ds_build_cross_dataset_edges(_TENANT_STR)
        assert result is not None
        assert result == fake


def test_ds_build_cross_dataset_edges_accepts_uuid_string() -> None:
    with patch("asyncio.run", return_value=3):
        result = ds_build_cross_dataset_edges(_TENANT_STR)
    assert result is not None
