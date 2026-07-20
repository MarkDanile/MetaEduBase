"""Test MCP registry tenant isolation (REQ-044 Task 3, AC-7).

Two tenants each register a ``qcc`` server (same code, different rows).
Tenant A cannot see, call, or read audit for tenant B's server, and
vice versa. The ``MCPInvocationService`` resolves by
``(tenant_id, code)``; the audit repository's ``list_by_server`` is
tenant-forced; cross-tenant invocation by the OTHER tenant's server
code resolves to the caller's own (or NotFound).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
    MCPInvocationServerNotFoundError,
    MCPInvocationService,
)
from app.contexts.mcp_registry.application.mcp_registry_service import (
    MCPRegistryService,
)
from app.contexts.mcp_registry.infrastructure.invocation_audit_repository import (
    InvocationAuditRepository,
)
from app.contexts.mcp_registry.infrastructure.mcp_client import MCPCallResult
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio

TENANT_B = uuid.uuid4()
_CRED_ENV = "TEST_MCP_TOKEN_ISO"


def _caller(role: str = "admin") -> InvocationCaller:
    return InvocationCaller(caller_type="service", role=role, user_id=DEFAULT_ADMIN_ID)


@pytest.fixture(autouse=True)
async def _clean_mcp_tables(db_session):
    """Clear prior-committed MCP rows for both tenants before each test."""
    for tid in (DEFAULT_TENANT_ID, TENANT_B):
        await db_session.execute(
            text("DELETE FROM metaedu.mcp_invocation_audit WHERE tenant_id = :tid"),
            {"tid": tid},
        )
        await db_session.execute(
            text("DELETE FROM metaedu.mcp_servers WHERE tenant_id = :tid"),
            {"tid": tid},
        )
    await db_session.flush()
    yield


async def _register(db_session, tenant_id, code="qcc"):
    svc = MCPRegistryService(db_session)
    server = await svc.create(
        tenant_id=tenant_id, code=code, name="企查查",
        server_url="https://mcp.example.com/rpc",
        credential_ref=_CRED_ENV, allowed_roles=["admin"],
        created_by=DEFAULT_ADMIN_ID, role="super_admin",
    )
    await svc.set_enabled(
        tenant_id=tenant_id, server_id=server.id,
        enabled=True, role="super_admin",
    )
    await db_session.commit()
    return server


def _service(session) -> MCPInvocationService:
    client = AsyncMock()
    client.call_tool.return_value = MCPCallResult(
        ok=True, result={"structuredContent": [{"ok": True}]}
    )
    return MCPInvocationService(session, client=client)


# ── same code, two tenants, independent ────────────────────────────


async def test_same_code_registered_independently_in_two_tenants(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, "tok")
    a = await _register(db_session, DEFAULT_TENANT_ID)
    b = await _register(db_session, TENANT_B)
    assert a.id != b.id
    assert a.tenant_id == DEFAULT_TENANT_ID
    assert b.tenant_id == TENANT_B


async def test_tenant_a_cannot_invoke_tenant_b_server_code_if_absent(
    db_session, monkeypatch
):
    """Tenant A has no 'park' server; invoking 'park' -> NotFound (no audit)."""
    monkeypatch.setenv(_CRED_ENV, "tok")
    await _register(db_session, TENANT_B, code="park")
    svc = _service(db_session)
    with pytest.raises(MCPInvocationServerNotFoundError):
        await svc.invoke(
            tenant_id=DEFAULT_TENANT_ID, server_code="park",
            tool_name="t", params={}, caller=_caller(),
        )
    # Tenant A has zero audit rows; tenant B's invocation never ran.
    cnt = await db_session.scalar(
        text("SELECT COUNT(*) FROM metaedu.mcp_invocation_audit "
             "WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    assert cnt == 0


async def test_invoke_resolves_callers_own_tenant_server(db_session, monkeypatch):
    """Both tenants register 'qcc'; each invoke hits its own server + audit."""
    monkeypatch.setenv(_CRED_ENV, "tok")
    await _register(db_session, DEFAULT_TENANT_ID)
    await _register(db_session, TENANT_B)
    svc = _service(db_session)
    await svc.invoke(
        tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
        tool_name="t", params={"who": "A"}, caller=_caller(),
    )
    await svc.invoke(
        tenant_id=TENANT_B, server_code="qcc",
        tool_name="t", params={"who": "B"}, caller=_caller(),
    )
    # Each tenant has exactly one audit row.
    for tid in (DEFAULT_TENANT_ID, TENANT_B):
        cnt = await db_session.scalar(
            text("SELECT COUNT(*) FROM metaedu.mcp_invocation_audit "
                 "WHERE tenant_id = :tid"),
            {"tid": tid},
        )
        assert cnt == 1


# ── audit query is tenant-forced ───────────────────────────────────


async def test_audit_list_by_server_is_tenant_forced(db_session, monkeypatch):
    """Tenant A's audit rows for its server are not reachable via tenant B."""
    monkeypatch.setenv(_CRED_ENV, "tok")
    server_a = await _register(db_session, DEFAULT_TENANT_ID)
    server_b = await _register(db_session, TENANT_B)
    svc = _service(db_session)
    # Two invocations on tenant A's server.
    await svc.invoke(tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
                     tool_name="t", params={}, caller=_caller())
    await svc.invoke(tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
                     tool_name="t", params={}, caller=_caller())
    # Tenant B queries ITS server's audit -> 0 rows (B never invoked).
    repo_b = InvocationAuditRepository(db_session)
    rows_b, total_b = await repo_b.list_by_server(TENANT_B, server_b.id)
    assert total_b == 0
    # Tenant A queries ITS server's audit -> 2 rows.
    repo_a = InvocationAuditRepository(db_session)
    rows_a, total_a = await repo_a.list_by_server(DEFAULT_TENANT_ID, server_a.id)
    assert total_a == 2
    # Tenant B cannot read tenant A's rows even with A's server_id.
    rows_leak, total_leak = await repo_b.list_by_server(TENANT_B, server_a.id)
    assert total_leak == 0
