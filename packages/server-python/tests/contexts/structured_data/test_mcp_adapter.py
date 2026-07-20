"""Test MCPAdapter - REQ-044 rewired to the MCP registry.

Contract (REQ-044 Task 3, replacing the REQ-054/REQ-057
``CapabilityUnavailableError`` placeholder):

- ``data_source_config`` carries ``server_code`` + ``tool_name`` (a
  registered MCP server, NOT a raw ``server_url``).
- ``validate_query`` reports missing ``server_code`` / ``tool_name``.
- ``query`` delegates to :class:`MCPInvocationService` (injected, never
  constructed by the adapter). Config gaps raise ``ValueError``;
  registry / permission / transport failures propagate as
  :class:`MCPInvocationError` / :class:`MCPInvocationServerNotFoundError`
  (audited by the invocation service); success normalizes the MCP
  ``tools/call`` result into ``list[dict]`` rows.

The invocation service is mocked here - the real service + audit +
transport are covered by ``tests/contexts/mcp_registry/``. These are
pure unit tests: no DB, no network.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
    MCPInvocationError,
    MCPInvocationServerNotFoundError,
)
from app.contexts.structured_data.domain.data_source_adapter import (
    DataSourceAdapter,
)
from app.contexts.structured_data.infrastructure.mcp_adapter import MCPAdapter
from app.shared.infrastructure.seed import DEFAULT_TENANT_ID

# ── get_data_source_type ───────────────────────────────────────────


def test_get_data_source_type_returns_mcp():
    adapter = MCPAdapter(
        config={"server_code": "qcc", "tool_name": "search_company"}
    )
    assert adapter.get_data_source_type() == "mcp"


# ── validate_query ─────────────────────────────────────────────────


def test_validate_query_missing_server_code():
    adapter = MCPAdapter(config={"tool_name": "search_company"})
    errors = adapter.validate_query({}, None)
    assert any("server_code" in e for e in errors)


def test_validate_query_missing_tool_name():
    adapter = MCPAdapter(config={"server_code": "qcc"})
    errors = adapter.validate_query({}, None)
    assert any("tool_name" in e for e in errors)


def test_validate_query_both_present_no_errors():
    adapter = MCPAdapter(
        config={"server_code": "qcc", "tool_name": "search_company"}
    )
    assert adapter.validate_query({}, None) == []


def test_validate_query_empty_config_reports_both():
    adapter = MCPAdapter(config={})
    errors = adapter.validate_query({}, None)
    assert len(errors) == 2
    assert any("server_code" in e for e in errors)
    assert any("tool_name" in e for e in errors)


# ── query - delegation to MCPInvocationService ─────────────────────


def _mock_service(result=None, raises=None) -> AsyncMock:
    """Build a mock MCPInvocationService whose ``invoke`` returns / raises."""
    svc = AsyncMock()
    if raises is not None:
        svc.invoke.side_effect = raises
    else:
        svc.invoke.return_value = result if result is not None else {}
    return svc


async def test_query_delegates_to_invocation_service_with_correct_caller():
    """query() invokes the service with server_code/tool_name + the
    adapter:structured_data caller type and the requesting user's role."""
    svc = _mock_service(result={"structuredContent": [{"name": "ACME"}]})
    adapter = MCPAdapter(
        config={"server_code": "qcc", "tool_name": "search_company"},
        invocation_service=svc,
    )
    rows = await adapter.query(
        query_plan={"limit": 50, "filters": {"name": "ACME"}},
        semantic_model=None,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )
    assert rows == [{"name": "ACME"}]
    svc.invoke.assert_awaited_once()
    kwargs = svc.invoke.await_args.kwargs
    assert kwargs["server_code"] == "qcc"
    assert kwargs["tool_name"] == "search_company"
    assert kwargs["tenant_id"] == DEFAULT_TENANT_ID
    caller: InvocationCaller = kwargs["caller"]
    assert caller.caller_type == "adapter:structured_data"
    assert caller.role == "manager"


async def test_query_missing_service_raises_value_error():
    """No invocation service wired -> ValueError (explicit, not a silent [])."""
    adapter = MCPAdapter(
        config={"server_code": "qcc", "tool_name": "search_company"}
    )
    with pytest.raises(ValueError, match="MCPInvocationService"):
        await adapter.query(
            query_plan={},
            semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID,
            user_role="manager",
        )


async def test_query_incomplete_config_raises_value_error():
    """Config gaps surface as ValueError before the service is called."""
    svc = _mock_service()
    adapter = MCPAdapter(config={"tool_name": "search_company"}, invocation_service=svc)
    with pytest.raises(ValueError, match="server_code"):
        await adapter.query(
            query_plan={},
            semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID,
            user_role="manager",
        )
    svc.invoke.assert_not_awaited()


async def test_query_propagates_invocation_error():
    """Audited failures (disabled/forbidden/transport/...) propagate."""
    svc = _mock_service(raises=MCPInvocationError("disabled", "server 已停用"))
    adapter = MCPAdapter(
        config={"server_code": "qcc", "tool_name": "search_company"},
        invocation_service=svc,
    )
    with pytest.raises(MCPInvocationError, match="停用"):
        await adapter.query(
            query_plan={},
            semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID,
            user_role="manager",
        )


async def test_query_propagates_server_not_found():
    """Unregistered server -> MCPInvocationServerNotFoundError (no audit row)."""
    svc = _mock_service(raises=MCPInvocationServerNotFoundError("qcc"))
    adapter = MCPAdapter(
        config={"server_code": "qcc", "tool_name": "search_company"},
        invocation_service=svc,
    )
    with pytest.raises(MCPInvocationServerNotFoundError):
        await adapter.query(
            query_plan={},
            semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID,
            user_role="manager",
        )


# ── _rows_from_result normalization ────────────────────────────────


async def test_query_normalizes_structured_content_list():
    svc = _mock_service(result={"structuredContent": [{"a": 1}, {"b": 2}]})
    adapter = MCPAdapter(
        config={"server_code": "qcc", "tool_name": "t"},
        invocation_service=svc,
    )
    rows = await adapter.query({}, None, DEFAULT_TENANT_ID, "manager")
    assert rows == [{"a": 1}, {"b": 2}]


async def test_query_normalizes_structured_content_dict_with_rows():
    svc = _mock_service(result={"structuredContent": {"rows": [{"x": 9}]}})
    adapter = MCPAdapter(
        config={"server_code": "qcc", "tool_name": "t"},
        invocation_service=svc,
    )
    rows = await adapter.query({}, None, DEFAULT_TENANT_ID, "manager")
    assert rows == [{"x": 9}]


async def test_query_normalizes_content_text_json():
    """MCP text content carrying JSON arrays/dicts is parsed into rows."""
    svc = _mock_service(
        result={
            "content": [
                {"type": "text", "text": '[{"company": "ACME"}, {"company": "Beta"}]'}
            ]
        }
    )
    adapter = MCPAdapter(
        config={"server_code": "qcc", "tool_name": "t"},
        invocation_service=svc,
    )
    rows = await adapter.query({}, None, DEFAULT_TENANT_ID, "manager")
    assert rows == [{"company": "ACME"}, {"company": "Beta"}]


async def test_query_falls_back_to_wrapping_raw_result():
    svc = _mock_service(result={"unrecognized": "shape"})
    adapter = MCPAdapter(
        config={"server_code": "qcc", "tool_name": "t"},
        invocation_service=svc,
    )
    rows = await adapter.query({}, None, DEFAULT_TENANT_ID, "manager")
    assert rows == [{"unrecognized": "shape"}]


# ── ABC inheritance ────────────────────────────────────────────────


def test_inherits_from_data_source_adapter_abc():
    assert issubclass(MCPAdapter, DataSourceAdapter)
