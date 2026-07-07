"""Test MCPAdapter — V1 interface skeleton (REQ-054 Task 4).

V1 contract (upgraded from REQ-052 placeholder):
- ``__init__`` accepts a ``config`` dict (no longer raises NotImplementedError).
- ``get_data_source_type`` returns ``"mcp"``.
- ``validate_query`` reports missing ``server_url`` / ``tool_name``.
- ``query`` returns an empty list (V1 does not connect to a real MCP server;
  V2 will wire up the QCC MCP server).

These tests are pure unit tests — no DB, no network, no mocks needed.
"""

from __future__ import annotations

from app.contexts.structured_data.domain.data_source_adapter import (
    DataSourceAdapter,
)
from app.contexts.structured_data.infrastructure.mcp_adapter import MCPAdapter
from app.shared.infrastructure.seed import DEFAULT_TENANT_ID

# asyncio_mode = "auto" in pyproject.toml handles async tests; sync tests
# need no mark, so we don't set a module-level pytestmark.


# ── get_data_source_type ───────────────────────────────────────────


def test_get_data_source_type_returns_mcp():
    adapter = MCPAdapter(
        config={"server_url": "http://mcp.local", "tool_name": "query_bills"}
    )
    assert adapter.get_data_source_type() == "mcp"


# ── validate_query ─────────────────────────────────────────────────


def test_validate_query_missing_server_url():
    adapter = MCPAdapter(config={"tool_name": "query_bills"})
    errors = adapter.validate_query({}, None)
    assert any("server_url" in e for e in errors)


def test_validate_query_missing_tool_name():
    adapter = MCPAdapter(config={"server_url": "http://mcp.local"})
    errors = adapter.validate_query({}, None)
    assert any("tool_name" in e for e in errors)


def test_validate_query_both_present_no_errors():
    adapter = MCPAdapter(
        config={"server_url": "http://mcp.local", "tool_name": "query_bills"}
    )
    errors = adapter.validate_query({}, None)
    assert errors == []


def test_validate_query_empty_config_reports_both():
    adapter = MCPAdapter(config={})
    errors = adapter.validate_query({}, None)
    assert len(errors) == 2
    assert any("server_url" in e for e in errors)
    assert any("tool_name" in e for e in errors)


# ── query — V1 returns empty list ─────────────────────────────────


async def test_query_returns_empty_list():
    """V1: query does not connect to a real MCP server — returns []."""
    adapter = MCPAdapter(
        config={"server_url": "http://mcp.local", "tool_name": "query_bills"}
    )
    rows = await adapter.query(
        query_plan={},
        semantic_model=None,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )
    assert rows == []


async def test_query_returns_empty_list_even_without_config():
    """V1: query is a no-op skeleton — returns [] regardless of config."""
    adapter = MCPAdapter(config={})
    rows = await adapter.query(
        query_plan={},
        semantic_model=None,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )
    assert rows == []


async def test_query_returns_empty_list_with_limit():
    """V1: query ignores query_plan and returns [] (no real server)."""
    adapter = MCPAdapter(
        config={"server_url": "http://mcp.local", "tool_name": "query_bills"}
    )
    rows = await adapter.query(
        query_plan={"limit": 100, "filters": {"company": "ACME"}},
        semantic_model=None,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )
    assert rows == []


# ── ABC inheritance ────────────────────────────────────────────────


def test_inherits_from_data_source_adapter_abc():
    assert issubclass(MCPAdapter, DataSourceAdapter)


def test_init_no_longer_raises_not_implemented():
    """V1 upgrade: __init__ must accept config without raising."""
    adapter = MCPAdapter(
        config={"server_url": "http://mcp.local", "tool_name": "query_bills"}
    )
    assert adapter is not None
