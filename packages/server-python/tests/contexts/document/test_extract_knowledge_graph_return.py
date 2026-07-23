"""TD-062: extract_knowledge_graph must return the KG extraction summary.

Follow-up to TD-061. Same pattern as TD-055/056/057/058/059/060/061.
Returns a dict {nodes: int, edges: int} instead of None.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.contexts.document.application.tasks.extract_knowledge_graph import (
    extract_knowledge_graph,
)

_TENANT_STR = "00000000-0000-0000-0000-000000000001"
_FID_STR = "12345678-1234-1234-1234-123456789012"


def test_extract_knowledge_graph_returns_summary_dict() -> None:
    """Pre-fix: returned None. Post-fix: returns {nodes: N, edges: M} dict."""
    fake_result = {"nodes": 5, "edges": 3}
    with patch("asyncio.run", side_effect=lambda c, r=fake_result: (c.close(), r)[1]):
        result = extract_knowledge_graph(_FID_STR, _TENANT_STR)

    assert result == fake_result
    assert isinstance(result, dict)
    assert "nodes" in result
    assert "edges" in result


def test_extract_knowledge_graph_zero_returns_zero() -> None:
    """Idempotent: empty KG returns 0 nodes / 0 edges."""
    empty_result = {"nodes": 0, "edges": 0}
    with patch("asyncio.run", side_effect=lambda c, r=empty_result: (c.close(), r)[1]):
        result = extract_knowledge_graph(_FID_STR, _TENANT_STR)
    assert result == empty_result


def test_extract_knowledge_graph_does_not_return_none() -> None:
    """Regression lock against TD-062 bug."""
    for fake_result in (
        {"nodes": 0, "edges": 0},
        {"nodes": 1, "edges": 5},
        {"nodes": 10, "edges": 0},
        {"nodes": 100, "edges": 200},
    ):
        with patch("asyncio.run", side_effect=lambda c, r=fake_result: (c.close(), r)[1]):
            result = extract_knowledge_graph(_FID_STR, _TENANT_STR)
        assert result is not None
        assert result == fake_result


def test_extract_knowledge_graph_accepts_uuid_strings() -> None:
    parsed_fid = uuid.UUID(_FID_STR)
    parsed_tid = uuid.UUID(_TENANT_STR)
    assert parsed_fid is not None
    assert parsed_tid is not None

    with patch("asyncio.run", return_value={"nodes": 1, "edges": 1}):
        result = extract_knowledge_graph(_FID_STR, _TENANT_STR)
    assert result is not None
