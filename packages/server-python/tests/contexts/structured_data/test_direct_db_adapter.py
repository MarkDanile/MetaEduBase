"""Test DirectDBAdapter — V1 interface skeleton (REQ-054 Task 4).

V1 contract (upgraded from REQ-052 placeholder):
- ``__init__`` accepts a ``config`` dict (no longer raises NotImplementedError).
- ``get_data_source_type`` returns ``"direct_db"``.
- ``validate_query`` reports missing ``connection_string`` / ``table_name``.
- ``query`` connects via ``asyncpg.connect`` and runs
  ``SELECT * FROM <table> LIMIT $1``.
- ``table_name`` is whitelisted via regex (``^[a-zA-Z_][a-zA-Z0-9_]*$``)
  before interpolation into SQL — SQL injection prevention.
- ``limit`` is clamped to 1000 (spec §5.5 soft cap).

All ``asyncpg`` interactions are mocked — no real PG connection is opened.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.contexts.structured_data.domain.data_source_adapter import (
    DataSourceAdapter,
)
from app.contexts.structured_data.infrastructure.direct_db_adapter import (
    DirectDBAdapter,
)
from app.shared.infrastructure.seed import DEFAULT_TENANT_ID

# asyncio_mode = "auto" in pyproject.toml handles async tests; sync tests
# need no mark, so we don't set a module-level pytestmark.


# ── get_data_source_type ───────────────────────────────────────────


def test_get_data_source_type_returns_direct_db():
    adapter = DirectDBAdapter(
        config={"connection_string": "postgresql://x", "table_name": "bills"}
    )
    assert adapter.get_data_source_type() == "direct_db"


# ── validate_query ─────────────────────────────────────────────────


def test_validate_query_missing_connection_string():
    adapter = DirectDBAdapter(config={"table_name": "bills"})
    errors = adapter.validate_query({}, None)
    assert any("connection_string" in e for e in errors)


def test_validate_query_missing_table_name():
    adapter = DirectDBAdapter(config={"connection_string": "postgresql://x"})
    errors = adapter.validate_query({}, None)
    assert any("table_name" in e for e in errors)


def test_validate_query_both_present_no_errors():
    adapter = DirectDBAdapter(
        config={"connection_string": "postgresql://x", "table_name": "bills"}
    )
    errors = adapter.validate_query({}, None)
    assert errors == []


def test_validate_query_empty_config_reports_both():
    adapter = DirectDBAdapter(config={})
    errors = adapter.validate_query({}, None)
    assert len(errors) == 2
    assert any("connection_string" in e for e in errors)
    assert any("table_name" in e for e in errors)


# ── query — happy path + mock verification ────────────────────────


@patch("asyncpg.connect", new_callable=AsyncMock)
async def test_query_uses_asyncpg_connect_with_select_and_limit(mock_connect):
    """Happy path: verify SELECT + FROM + LIMIT and the limit parameter."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(
        return_value=[
            {"id": 1, "name": "ACME"},
            {"id": 2, "name": "BetaCorp"},
        ]
    )
    mock_connect.return_value = mock_conn

    adapter = DirectDBAdapter(
        config={
            "connection_string": "postgresql://user:pass@host/db",
            "table_name": "bills",
        }
    )
    rows = await adapter.query(
        query_plan={"limit": 50},
        semantic_model=None,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )

    assert len(rows) == 2
    assert rows[0]["name"] == "ACME"
    mock_connect.assert_awaited_once_with("postgresql://user:pass@host/db")
    # Verify SELECT + FROM + LIMIT was issued with the table and parameter
    sql, limit = mock_conn.fetch.call_args.args
    assert "SELECT" in sql
    assert "FROM bills" in sql
    assert "LIMIT $1" in sql
    assert limit == 50
    mock_conn.close.assert_awaited_once()


@patch("asyncpg.connect", new_callable=AsyncMock)
async def test_query_clamps_limit_to_1000(mock_connect):
    """Spec §5.5 soft cap: limit > 1000 must be clamped to 1000."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_connect.return_value = mock_conn

    adapter = DirectDBAdapter(
        config={
            "connection_string": "postgresql://x",
            "table_name": "bills",
        }
    )
    await adapter.query(
        query_plan={"limit": 5000},
        semantic_model=None,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )

    _, limit = mock_conn.fetch.call_args.args
    assert limit == 1000


@patch("asyncpg.connect", new_callable=AsyncMock)
async def test_query_default_limit_100(mock_connect):
    """When query_plan has no limit, default to 100."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_connect.return_value = mock_conn

    adapter = DirectDBAdapter(
        config={
            "connection_string": "postgresql://x",
            "table_name": "bills",
        }
    )
    await adapter.query(
        query_plan={},
        semantic_model=None,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )

    _, limit = mock_conn.fetch.call_args.args
    assert limit == 100


@patch("asyncpg.connect", new_callable=AsyncMock)
async def test_query_closes_connection_in_finally(mock_connect):
    """Even if fetch succeeds, conn.close() must be called (no leak)."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_connect.return_value = mock_conn

    adapter = DirectDBAdapter(
        config={
            "connection_string": "postgresql://x",
            "table_name": "bills",
        }
    )
    await adapter.query(
        query_plan={},
        semantic_model=None,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )

    mock_conn.close.assert_awaited_once()


@patch("asyncpg.connect", new_callable=AsyncMock)
async def test_query_closes_connection_on_fetch_error(mock_connect):
    """If fetch raises, conn.close() must still be called (finally block)."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(side_effect=RuntimeError("fetch failed"))
    mock_connect.return_value = mock_conn

    adapter = DirectDBAdapter(
        config={
            "connection_string": "postgresql://x",
            "table_name": "bills",
        }
    )
    with pytest.raises(RuntimeError, match="fetch failed"):
        await adapter.query(
            query_plan={},
            semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID,
            user_role="manager",
        )

    mock_conn.close.assert_awaited_once()


# ── query — missing config returns empty (no connection) ──────────


@patch("asyncpg.connect", new_callable=AsyncMock)
async def test_query_returns_empty_when_connection_string_missing(mock_connect):
    """Missing connection_string → return [] without connecting."""
    adapter = DirectDBAdapter(config={"table_name": "bills"})
    rows = await adapter.query(
        query_plan={},
        semantic_model=None,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )
    assert rows == []
    mock_connect.assert_not_awaited()


@patch("asyncpg.connect", new_callable=AsyncMock)
async def test_query_returns_empty_when_table_name_missing(mock_connect):
    """Missing table_name → return [] without connecting."""
    adapter = DirectDBAdapter(config={"connection_string": "postgresql://x"})
    rows = await adapter.query(
        query_plan={},
        semantic_model=None,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )
    assert rows == []
    mock_connect.assert_not_awaited()


# ── query — table_name SQL injection prevention ───────────────────


async def test_query_invalid_table_name_semicolon_raises_value_error():
    """table_name with SQL injection chars must raise ValueError before SQL."""
    adapter = DirectDBAdapter(
        config={
            "connection_string": "postgresql://x",
            "table_name": "bills; DROP TABLE users; --",
        }
    )
    with pytest.raises(ValueError, match="table_name"):
        await adapter.query(
            query_plan={},
            semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID,
            user_role="manager",
        )


async def test_query_invalid_table_name_with_space_raises():
    adapter = DirectDBAdapter(
        config={
            "connection_string": "postgresql://x",
            "table_name": "bad name",
        }
    )
    with pytest.raises(ValueError):
        await adapter.query(
            query_plan={},
            semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID,
            user_role="manager",
        )


async def test_query_invalid_table_name_with_hyphen_raises():
    adapter = DirectDBAdapter(
        config={
            "connection_string": "postgresql://x",
            "table_name": "bad-name",
        }
    )
    with pytest.raises(ValueError):
        await adapter.query(
            query_plan={},
            semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID,
            user_role="manager",
        )


async def test_query_invalid_table_name_starting_digit_raises():
    """table_name must start with letter or underscore."""
    adapter = DirectDBAdapter(
        config={
            "connection_string": "postgresql://x",
            "table_name": "1table",
        }
    )
    with pytest.raises(ValueError):
        await adapter.query(
            query_plan={},
            semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID,
            user_role="manager",
        )


async def test_query_valid_table_name_with_underscore_passes():
    """Underscore and digits (not first char) are valid."""
    with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect:
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_connect.return_value = mock_conn

        adapter = DirectDBAdapter(
            config={
                "connection_string": "postgresql://x",
                "table_name": "bill_data_2026",
            }
        )
        rows = await adapter.query(
            query_plan={},
            semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID,
            user_role="manager",
        )
        assert rows == []
        sql, _ = mock_conn.fetch.call_args.args
        assert "FROM bill_data_2026" in sql


# ── ABC inheritance ────────────────────────────────────────────────


def test_inherits_from_data_source_adapter_abc():
    assert issubclass(DirectDBAdapter, DataSourceAdapter)


def test_init_no_longer_raises_not_implemented():
    """V1 upgrade: __init__ must accept config without raising."""
    adapter = DirectDBAdapter(
        config={"connection_string": "postgresql://x", "table_name": "bills"}
    )
    assert adapter is not None
