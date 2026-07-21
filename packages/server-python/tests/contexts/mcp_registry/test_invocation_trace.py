"""Test MCPInvocationService.invoke_with_trace (REQ-046 PR-3).

``invoke_with_trace`` returns ``InvocationTrace(result, audit_id)`` so callers
(REQ-046 SkillRunner evidence chain) can bind each step to its
``mcp_invocation_audit`` row. ``invoke`` becomes a thin shell returning only
``result`` — zero behavior change for REQ-044/045 existing callers. Real DB,
mocked :class:`MCPClient` (no network).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
    InvocationTrace,
    MCPInvocationService,
)
from app.contexts.mcp_registry.application.mcp_registry_service import (
    MCPRegistryService,
)
from app.contexts.mcp_registry.infrastructure.mcp_client import MCPCallResult
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio

_CRED_ENV = "TEST_MCP_TOKEN_TRACE"
_CRED_VALUE = "trace-token-xyz"


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


def _caller(role: str = "admin") -> InvocationCaller:
    return InvocationCaller(
        caller_type="service", role=role, user_id=DEFAULT_ADMIN_ID
    )


async def _register_enabled(session) -> uuid.UUID:
    svc = MCPRegistryService(session)
    server = await svc.create(
        tenant_id=DEFAULT_TENANT_ID,
        code="qcc",
        name="企查查",
        server_url="https://mcp.example.com/rpc",
        credential_ref=_CRED_ENV,
        allowed_roles=["admin"],
        created_by=DEFAULT_ADMIN_ID,
        role="super_admin",
    )
    await svc.set_enabled(
        tenant_id=DEFAULT_TENANT_ID, server_id=server.id,
        enabled=True, role="super_admin",
    )
    await session.commit()
    return server.id


def _service(session) -> MCPInvocationService:
    client = AsyncMock()
    client.call_tool.return_value = MCPCallResult(
        ok=True, result={"structuredContent": [{"company": "ACME"}]}
    )
    return MCPInvocationService(session, client=client)


async def test_invoke_with_trace_returns_result_and_audit_id(
    db_session, monkeypatch
):
    monkeypatch.setenv(_CRED_ENV, _CRED_VALUE)
    server_id = await _register_enabled(db_session)
    svc = _service(db_session)
    trace = await svc.invoke_with_trace(
        tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
        tool_name="search", params={"q": "ACME"}, caller=_caller(),
    )
    assert isinstance(trace, InvocationTrace)
    assert trace.result == {"structuredContent": [{"company": "ACME"}]}
    # audit_id 指向真实 mcp_invocation_audit 行
    row_id = await db_session.scalar(
        text(
            "SELECT id FROM metaedu.mcp_invocation_audit "
            "WHERE server_id = :sid AND ok = true"
        ),
        {"sid": server_id},
    )
    assert trace.audit_id == row_id


async def test_invoke_shell_returns_result_only(db_session, monkeypatch):
    """invoke 薄壳:返回与 invoke_with_trace.result 相同,零行为变化。"""
    monkeypatch.setenv(_CRED_ENV, _CRED_VALUE)
    await _register_enabled(db_session)
    svc = _service(db_session)
    result = await svc.invoke(
        tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
        tool_name="search", params={"q": "ACME"}, caller=_caller(),
    )
    assert result == {"structuredContent": [{"company": "ACME"}]}
