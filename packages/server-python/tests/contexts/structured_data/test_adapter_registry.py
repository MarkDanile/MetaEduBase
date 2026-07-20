"""REQ-044 Task 3: adapter registry routing tests.

Pins the :func:`default_adapter_factory` contract: it must route all
three declared :class:`DataSourceType` values (``imported_dataset``,
``direct_db``, ``mcp``) to the right concrete adapter and raise
``ValueError`` for anything else. The MCP adapter (REQ-044) is wired to
a session-bound :class:`MCPInvocationService` - it delegates to the
registry rather than raising ``CapabilityUnavailableError`` (the old
REQ-057 placeholder, now removed).

These are routing / contract tests - the imported_dataset path needs a
real session (the adapter builds a :class:`JsonbQueryBuilder` at
construction time), so the factory cases use the ``db_session`` fixture.
"""

from __future__ import annotations

import pytest

from app.contexts.structured_data.application.query_service import (
    default_adapter_factory,
)
from app.contexts.structured_data.infrastructure.direct_db_adapter import (
    DirectDBAdapter,
)
from app.contexts.structured_data.infrastructure.imported_dataset_adapter import (
    ImportedDatasetAdapter,
)
from app.contexts.structured_data.infrastructure.mcp_adapter import MCPAdapter
from app.shared.infrastructure.seed import DEFAULT_TENANT_ID

# asyncio_mode = "auto" in pyproject.toml handles async tests; sync tests
# need no mark, so we don't set a module-level pytestmark.


# ── factory routing ────────────────────────────────────────────────


async def test_factory_routes_imported_dataset(db_session):
    """type=imported_dataset -> ImportedDatasetAdapter."""
    adapter = await default_adapter_factory(
        db_session, {"type": "imported_dataset"}
    )
    assert isinstance(adapter, ImportedDatasetAdapter)
    assert adapter.get_data_source_type() == "imported_dataset"


async def test_factory_routes_direct_db(db_session):
    """type=direct_db -> DirectDBAdapter (V1 read-only SELECT)."""
    adapter = await default_adapter_factory(
        db_session,
        {
            "type": "direct_db",
            "connection_string": "postgresql://user:pass@host/db",
            "table_name": "bills",
        },
    )
    assert isinstance(adapter, DirectDBAdapter)
    assert adapter.get_data_source_type() == "direct_db"


async def test_factory_routes_mcp(db_session):
    """type=mcp -> MCPAdapter wired to a session-bound MCPInvocationService."""
    adapter = await default_adapter_factory(
        db_session,
        {
            "type": "mcp",
            "server_code": "qcc",
            "tool_name": "search_company",
        },
    )
    assert isinstance(adapter, MCPAdapter)
    assert adapter.get_data_source_type() == "mcp"


# ── MCP delegation contract ─────────────────────────────────────────


async def test_mcp_query_without_service_raises_value_error():
    """No MCPInvocationService wired -> ValueError (explicit, not silent []).

    REQ-044: the adapter delegates to ``MCPInvocationService``; without one
    it must fail explicitly rather than return ``[]`` (which would masquerade
    as "query succeeded, no data"). The old ``CapabilityUnavailableError``
    placeholder is gone - the registry now backs real MCP calls.
    """
    adapter = MCPAdapter(
        config={"server_code": "qcc", "tool_name": "search_company"}
    )
    with pytest.raises(ValueError, match="MCPInvocationService"):
        await adapter.query(
            query_plan={"limit": 100, "filters": {"company": "ACME"}},
            semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID,
            user_role="manager",
        )


# ── unknown type ───────────────────────────────────────────────────


async def test_unknown_type_raises_value_error(db_session):
    """Unknown data_source type -> ValueError (router maps to 400)."""
    with pytest.raises(ValueError, match="Unknown data_source type"):
        await default_adapter_factory(
            db_session, {"type": "totally_unknown_type"}
        )
