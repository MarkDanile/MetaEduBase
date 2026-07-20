"""Test MCPInvocationService audit + failure branches (REQ-044 Task 3, spec §4.6).

Real DB (mcp_servers + mcp_invocation_audit), mocked :class:`MCPClient`
so no network. Verifies every §4.6 failure branch writes an audit row
with the correct ``error_code`` and ``ok=False``; success writes
``ok=True`` with digests; unregistered server raises NotFound with NO
audit row; digests never equal raw input; the resolved credential never
appears in ``error_message``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
    MCPInvocationError,
    MCPInvocationServerNotFoundError,
    MCPInvocationService,
    canonical_digest,
)
from app.contexts.mcp_registry.application.mcp_registry_service import (
    MCPRegistryService,
)
from app.contexts.mcp_registry.infrastructure.mcp_client import MCPCallResult
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio

_CRED_ENV = "TEST_MCP_TOKEN_044"
_CRED_VALUE = "super-secret-token-value-xyz"


@pytest.fixture(autouse=True)
async def _clean_mcp_tables(db_session):
    """Clear prior-committed MCP rows for the default tenant before each test.

    ``db_session`` commits on teardown, so a previous test's ``qcc`` server
    (and its audit rows) persist into the next run and trip the
    ``(tenant_id, code)`` unique constraint. FK-safe order: audit first
    (it references mcp_servers), then servers.
    """
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


async def _register_enabled(
    session,
    *,
    code: str = "qcc",
    allowed_roles: list[str] | None = None,
    credential_ref: str | None = _CRED_ENV,
    enabled: bool = True,
) -> uuid.UUID:
    """Register a server via the service and optionally enable it."""
    svc = MCPRegistryService(session)
    server = await svc.create(
        tenant_id=DEFAULT_TENANT_ID,
        code=code,
        name="企查查",
        server_url="https://mcp.example.com/rpc",
        credential_ref=credential_ref,
        allowed_roles=allowed_roles if allowed_roles is not None else ["admin"],
        created_by=DEFAULT_ADMIN_ID,
        role="super_admin",
    )
    if enabled:
        await svc.set_enabled(
            tenant_id=DEFAULT_TENANT_ID, server_id=server.id,
            enabled=True, role="super_admin",
        )
    await session.commit()
    return server.id


async def _audit_rows_async(session, server_id: uuid.UUID) -> list[dict]:
    result = await session.execute(
        text(
            "SELECT tool_name, ok, error_code, error_message, params_digest, "
            "response_digest, duration_ms, caller_type, caller_user_id "
            "FROM metaedu.mcp_invocation_audit "
            "WHERE server_id = :sid ORDER BY created_at ASC"
        ),
        {"sid": server_id},
    )
    return [
        {
            "tool_name": r[0], "ok": r[1], "error_code": r[2],
            "error_message": r[3], "params_digest": r[4],
            "response_digest": r[5], "duration_ms": r[6],
            "caller_type": r[7], "caller_user_id": r[8],
        }
        for r in result.all()
    ]


def _service(session, client_result: MCPCallResult | None = None,
             raises=None) -> MCPInvocationService:
    client = AsyncMock()
    if raises is not None:
        client.call_tool.side_effect = raises
    else:
        client.call_tool.return_value = client_result or MCPCallResult(
            ok=True, result={"structuredContent": [{"company": "ACME"}]}
        )
    return MCPInvocationService(session, client=client)


# ── success ────────────────────────────────────────────────────────


async def test_invoke_success_writes_audit_with_digests(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, _CRED_VALUE)
    server_id = await _register_enabled(db_session)
    svc = _service(db_session)
    result = await svc.invoke(
        tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
        tool_name="search", params={"q": "ACME"}, caller=_caller(),
    )
    assert result == {"structuredContent": [{"company": "ACME"}]}
    rows = await _audit_rows_async(db_session, server_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["ok"] is True
    assert row["error_code"] is None
    assert row["tool_name"] == "search"
    # digests present and NOT equal to raw input
    assert row["params_digest"] == canonical_digest({"q": "ACME"})
    assert row["params_digest"] != '{"q": "ACME"}'
    assert row["response_digest"] == canonical_digest(result)
    assert row["duration_ms"] >= 0
    assert row["caller_type"] == "service"


# ── failure branches (each audited ok=False) ──────────────────────


async def test_invoke_disabled_audits(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, _CRED_VALUE)
    server_id = await _register_enabled(db_session, enabled=False)
    svc = _service(db_session)
    with pytest.raises(MCPInvocationError) as exc:
        await svc.invoke(
            tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
            tool_name="t", params={}, caller=_caller(),
        )
    assert exc.value.error_code == "disabled"
    rows = await _audit_rows_async(db_session, server_id)
    assert len(rows) == 1
    assert rows[0]["ok"] is False
    assert rows[0]["error_code"] == "disabled"


async def test_invoke_forbidden_audits(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, _CRED_VALUE)
    server_id = await _register_enabled(db_session, allowed_roles=["data_admin"])
    svc = _service(db_session)
    with pytest.raises(MCPInvocationError) as exc:
        await svc.invoke(
            tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
            tool_name="t", params={}, caller=_caller(role="employee"),
        )
    assert exc.value.error_code == "forbidden"
    rows = await _audit_rows_async(db_session, server_id)
    assert rows[0]["ok"] is False
    assert rows[0]["error_code"] == "forbidden"


async def test_invoke_credential_unavailable_audits(db_session):
    # Do NOT set the env var -> resolve() fails.
    import os
    os.environ.pop(_CRED_ENV, None)
    server_id = await _register_enabled(db_session)
    svc = _service(db_session)
    with pytest.raises(MCPInvocationError) as exc:
        await svc.invoke(
            tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
            tool_name="t", params={}, caller=_caller(),
        )
    assert exc.value.error_code == "credential_unavailable"
    rows = await _audit_rows_async(db_session, server_id)
    assert rows[0]["ok"] is False
    assert rows[0]["error_code"] == "credential_unavailable"


async def test_invoke_transport_error_audits(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, _CRED_VALUE)
    server_id = await _register_enabled(db_session)
    svc = _service(
        db_session,
        client_result=MCPCallResult(
            ok=False, error_code="transport_error",
            error_message="HTTP 503 boom",
        ),
    )
    with pytest.raises(MCPInvocationError) as exc:
        await svc.invoke(
            tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
            tool_name="t", params={}, caller=_caller(),
        )
    assert exc.value.error_code == "transport_error"
    rows = await _audit_rows_async(db_session, server_id)
    assert rows[0]["ok"] is False
    assert rows[0]["error_code"] == "transport_error"


async def test_invoke_tool_error_audits(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, _CRED_VALUE)
    await _register_enabled(db_session)
    svc = _service(
        db_session,
        client_result=MCPCallResult(
            ok=False, error_code="tool_error",
            error_message="company not found",
        ),
    )
    with pytest.raises(MCPInvocationError) as exc:
        await svc.invoke(
            tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
            tool_name="t", params={}, caller=_caller(),
        )
    assert exc.value.error_code == "tool_error"


# ── unregistered: NO audit row ─────────────────────────────────────


async def test_invoke_unregistered_raises_not_found_no_audit(db_session):
    svc = _service(db_session)
    with pytest.raises(MCPInvocationServerNotFoundError):
        await svc.invoke(
            tenant_id=DEFAULT_TENANT_ID, server_code="no_such_server",
            tool_name="t", params={}, caller=_caller(),
        )
    # No server -> no audit row at all for this tenant.
    result = await db_session.execute(
        text("SELECT COUNT(*) FROM metaedu.mcp_invocation_audit "
             "WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    assert result.scalar() == 0


# ── credential never leaks into error_message ─────────────────────


async def test_credential_never_appears_in_error_message(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, _CRED_VALUE)
    server_id = await _register_enabled(db_session)
    # Tool error whose message echoes the credential (malicious server).
    svc = _service(
        db_session,
        client_result=MCPCallResult(
            ok=False, error_code="tool_error",
            error_message=f"failed for token={_CRED_VALUE}",
        ),
    )
    with pytest.raises(MCPInvocationError):
        await svc.invoke(
            tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
            tool_name="t", params={}, caller=_caller(),
        )
    rows = await _audit_rows_async(db_session, server_id)
    assert _CRED_VALUE not in (rows[0]["error_message"] or "")


# ── params_digest nullable when params is None ─────────────────────


async def test_params_digest_null_when_params_none(db_session, monkeypatch):
    monkeypatch.setenv(_CRED_ENV, _CRED_VALUE)
    server_id = await _register_enabled(db_session)
    svc = _service(db_session)
    await svc.invoke(
        tenant_id=DEFAULT_TENANT_ID, server_code="qcc",
        tool_name="t", params=None, caller=_caller(),
    )
    rows = await _audit_rows_async(db_session, server_id)
    assert rows[0]["params_digest"] is None
    assert rows[0]["ok"] is True
