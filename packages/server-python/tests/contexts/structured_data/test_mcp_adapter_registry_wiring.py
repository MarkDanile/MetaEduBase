"""Test MCPAdapter registry wiring (REQ-044 Task 3, AC-8).

The adapter delegates to ``MCPInvocationService``; this test wires the
REAL invocation service + REAL registry + REAL audit against the test
DB, with only the MCP transport (``MCPClient``) mocked. Verifies:

- registered + enabled + permitted -> ``query`` returns rows AND an
  ``mcp_invocation_audit`` row is written;
- disabled / forbidden / unregistered -> explicit failure (raises
  ``MCPInvocationError`` / ``MCPInvocationServerNotFoundError``), NEVER an
  empty-list success and NEVER the old ``CapabilityUnavailableError``
  masquerade.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    MCPInvocationError,
    MCPInvocationServerNotFoundError,
    MCPInvocationService,
)
from app.contexts.mcp_registry.application.mcp_registry_service import (
    MCPRegistryService,
)
from app.contexts.mcp_registry.infrastructure.mcp_client import MCPCallResult
from app.contexts.structured_data.infrastructure.mcp_adapter import MCPAdapter
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio

_CRED_ENV = "TEST_MCP_TOKEN_WIRE"


@pytest.fixture(autouse=True)
async def _clean_mcp_tables(db_session):
    await db_session.execute(
        text("DELETE FROM metaedu.mcp_invocation_audit WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.execute(
        text("DELETE FROM metaedu.mcp_servers WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.flush()
    yield


async def _register(db_session, *, code="qcc", allowed_roles=None, enabled=True):
    svc = MCPRegistryService(db_session)
    server = await svc.create(
        tenant_id=DEFAULT_TENANT_ID, code=code, name="企查查",
        server_url="https://mcp.example.com/rpc",
        credential_ref=_CRED_ENV,
        allowed_roles=allowed_roles if allowed_roles is not None else ["admin"],
        created_by=DEFAULT_ADMIN_ID, role="super_admin",
    )
    if enabled:
        await svc.set_enabled(
            tenant_id=DEFAULT_TENANT_ID, server_id=server.id,
            enabled=True, role="super_admin",
        )
    await db_session.commit()
    return server


def _adapter(db_session, *, server_code="qcc", tool_name="search",
             client_result=None, raises=None) -> MCPAdapter:
    client = AsyncMock()
    if raises is not None:
        client.call_tool.side_effect = raises
    else:
        client.call_tool.return_value = client_result or MCPCallResult(
            ok=True, result={"structuredContent": [{"company": "ACME"}]}
        )
    svc = MCPInvocationService(db_session, client=client)
    return MCPAdapter(
        config={"server_code": server_code, "tool_name": tool_name},
        invocation_service=svc,
    )


async def _audit_count(db_session) -> int:
    return await db_session.scalar(
        text("SELECT COUNT(*) FROM metaedu.mcp_invocation_audit "
             "WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )


# ── success ────────────────────────────────────────────────────────


async def test_registered_enabled_returns_rows_and_audits(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, "tok")
    await _register(db_session)
    adapter = _adapter(db_session)
    rows = await adapter.query(
        query_plan={"limit": 50}, semantic_model=None,
        tenant_id=DEFAULT_TENANT_ID, user_role="admin",
    )
    assert rows == [{"company": "ACME"}]
    assert await _audit_count(db_session) == 1


# ── explicit failures (no masquerade) ──────────────────────────────


async def test_disabled_raises_invocation_error_not_empty(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, "tok")
    await _register(db_session, enabled=False)
    adapter = _adapter(db_session)
    with pytest.raises(MCPInvocationError) as exc:
        await adapter.query(
            query_plan={}, semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID, user_role="admin",
        )
    assert exc.value.error_code == "disabled"
    # Audit still written (fail-closed) for the disabled attempt.
    assert await _audit_count(db_session) == 1


async def test_forbidden_raises_invocation_error(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, "tok")
    await _register(db_session, allowed_roles=["data_admin"])
    adapter = _adapter(db_session)
    with pytest.raises(MCPInvocationError) as exc:
        await adapter.query(
            query_plan={}, semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID, user_role="employee",
        )
    assert exc.value.error_code == "forbidden"


async def test_unregistered_raises_not_found_not_empty(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, "tok")
    # No server registered; adapter points at a missing code.
    adapter = _adapter(db_session, server_code="no_such")
    with pytest.raises(MCPInvocationServerNotFoundError):
        await adapter.query(
            query_plan={}, semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID, user_role="admin",
        )
    # Unregistered -> no audit row (nothing to associate).
    assert await _audit_count(db_session) == 0


async def test_transport_error_raises_invocation_error(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, "tok")
    await _register(db_session)
    adapter = _adapter(
        db_session,
        client_result=MCPCallResult(
            ok=False, error_code="transport_error", error_message="HTTP 502",
        ),
    )
    with pytest.raises(MCPInvocationError) as exc:
        await adapter.query(
            query_plan={}, semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID, user_role="admin",
        )
    assert exc.value.error_code == "transport_error"


# ── config gaps ────────────────────────────────────────────────────


async def test_incomplete_config_raises_value_error(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, "tok")
    await _register(db_session)
    # Missing tool_name.
    adapter = MCPAdapter(
        config={"server_code": "qcc"},
        invocation_service=MCPInvocationService(db_session, client=AsyncMock()),
    )
    with pytest.raises(ValueError, match="tool_name"):
        await adapter.query(
            query_plan={}, semantic_model=None,
            tenant_id=DEFAULT_TENANT_ID, user_role="admin",
        )
