"""Router tests for /api/v1/skills/{id}/run + /executions (REQ-045 Task 3).

HTTP-level contract for the two Task-3 endpoints (spec §4.5 last two
rows). MCP invocation and LLM synthesis are mocked at the
``skill_runner`` module boundary (``MCPInvocationService`` default ctor
+ ``chat``) - the real :class:`SkillRunner` runs end-to-end with a real
DB session, only the network leaves are stubbed.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationTrace,
    MCPInvocationError,
)
from app.contexts.skill_registry.application import skill_runner as runner_mod

pytestmark = pytest.mark.asyncio

NON_ADMIN_ROLES = ["employee", "teacher", "student"]


def _unique_code(prefix: str = "skl") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _sop_template(server_code: str) -> str:
    return (
        "name: enterprise-360-dd\n"
        "description: 企业 360 背调 SOP\n"
        f"mcp_dependencies:\n  - {{server: {server_code}, required: true}}\n"
        "principles:\n  - 缺失数据显式标注\n"
        "steps:\n"
        f"  - id: step_0\n    title: 主体核验\n"
        f"    server: {server_code}\n    tool: get_company\n"
        "    output: 主体档案\n"
        f"  - id: step_1\n    title: 风险扫描\n"
        f"    server: {server_code}\n    tool: scan_risk\n"
        "    output: 风险清单\n"
        "report_template: |\n  ## 事实数据\n  ## AI 分析\n  ## 待人工确认项\n"
    )


async def _register_and_login(
    client: AsyncClient, *, username: str, role: str
) -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "password": "Test1234!",
            "email": f"{username}@test.local",
            "role": role,
        },
    )
    assert resp.status_code == 201, f"register failed: {resp.text}"
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Test1234!"},
    )
    assert resp.status_code == 200, f"login failed: {resp.text}"
    return resp.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register_server_via_api(client: AsyncClient, auth_headers: dict) -> str:
    code = _unique_code("srv")
    resp = await client.post(
        "/api/v1/mcp-servers",
        json={
            "code": code,
            "name": f"MCP-{code}",
            "server_url": "https://mcp.example.com/rpc",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return code


async def _create_and_enable_skill(
    client: AsyncClient,
    auth_headers: dict,
    server_code: str,
    *,
    code: str | None = None,
    allowed_roles: list[str] | None = None,
    version: str = "1.0.0",
) -> dict:
    code = code or _unique_code("run")
    payload = {
        "code": code,
        "version": version,
        "name": f"Skill-{code}",
        "sop_template": _sop_template(server_code),
        "allowed_roles": allowed_roles if allowed_roles is not None else ["admin"],
    }
    resp = await client.post("/api/v1/skills", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    resp = await client.post(
        f"/api/v1/skills/{body['id']}/enable", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    return body


def _patch_invocation(monkeypatch, *, tool_results=None, raises=None):
    """Stub ``MCPInvocationService`` so ``SkillRunner(session)`` uses it."""

    class _FakeInvocation:
        def __init__(self, session):
            self._session = session

        async def invoke_with_trace(
            self, *, tenant_id, server_code, tool_name, params, caller
        ):
            if raises is not None:
                raise raises
            return InvocationTrace(
                result=(tool_results or {}).get(tool_name, {"ok": True}),
                audit_id=uuid.uuid4(),
            )

    monkeypatch.setattr(runner_mod, "MCPInvocationService", _FakeInvocation)


def _patch_chat(monkeypatch, *, return_value="## 事实数据\n报告草案", raises=None):
    mock = AsyncMock(
        return_value=return_value, side_effect=raises if raises else None
    )
    monkeypatch.setattr(runner_mod, "chat", mock)
    return mock


# ---------------------------------------------------------------------------
# POST /{id}/run
# ---------------------------------------------------------------------------


async def test_run_success_returns_artifact_and_audit_id(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    server_code = await _register_server_via_api(client, auth_headers)
    skill = await _create_and_enable_skill(client, auth_headers, server_code)
    _patch_invocation(
        monkeypatch,
        tool_results={
            "get_company": {"company": "ACME", "credit_code": "91110000"},
            "scan_risk": {"risk_level": "low"},
        },
    )
    chat_mock = _patch_chat(monkeypatch, return_value="## 事实数据\nACME 低风险")
    resp = await client.post(
        f"/api/v1/skills/{skill['id']}/run",
        json={"version": "1.0.0", "subject": {"company_name": "ACME"}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["report"] == "## 事实数据\nACME 低风险"
    assert "execution_audit_id" in body
    assert body["duration_ms"] >= 0
    assert [s["id"] for s in body["steps"]] == ["step_0", "step_1"]
    assert all(s["ok"] for s in body["steps"])
    chat_mock.assert_awaited_once()


async def test_run_step_failure_500_with_error_code(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    server_code = await _register_server_via_api(client, auth_headers)
    skill = await _create_and_enable_skill(client, auth_headers, server_code)
    _patch_invocation(
        monkeypatch, raises=MCPInvocationError("tool_error", "公司未找到")
    )
    _patch_chat(monkeypatch)
    resp = await client.post(
        f"/api/v1/skills/{skill['id']}/run",
        json={"version": "1.0.0", "subject": {"company_name": "ACME"}},
        headers=auth_headers,
    )
    assert resp.status_code == 500
    assert "tool_error" in resp.json()["detail"]
    # failure audit row persisted before the 500 (committed by router)
    resp2 = await client.get(
        f"/api/v1/skills/{skill['id']}/executions", headers=auth_headers
    )
    items = resp2.json()["items"]
    assert any(i["error_code"] == "tool_error" and not i["ok"] for i in items)


async def test_run_forbidden_role_403(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    server_code = await _register_server_via_api(client, auth_headers)
    # allowed_roles 不含 data_admin，但 router 管理门禁允许 data_admin
    skill = await _create_and_enable_skill(
        client, auth_headers, server_code, allowed_roles=["admin"]
    )
    _patch_invocation(monkeypatch, tool_results={"get_company": {}})
    _patch_chat(monkeypatch)
    token = await _register_and_login(
        client, username=f"da_{uuid.uuid4().hex[:6]}", role="data_admin"
    )
    resp = await client.post(
        f"/api/v1/skills/{skill['id']}/run",
        json={"version": "1.0.0", "subject": {"company_name": "ACME"}},
        headers=_headers(token),
    )
    assert resp.status_code == 403
    assert "无权" in resp.json()["detail"]
    # forbidden 审计行也落库
    resp2 = await client.get(
        f"/api/v1/skills/{skill['id']}/executions", headers=auth_headers
    )
    items = resp2.json()["items"]
    assert any(i["error_code"] == "forbidden" for i in items)


async def test_run_unknown_version_404(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    server_code = await _register_server_via_api(client, auth_headers)
    skill = await _create_and_enable_skill(client, auth_headers, server_code)
    _patch_invocation(monkeypatch)
    _patch_chat(monkeypatch)
    resp = await client.post(
        f"/api/v1/skills/{skill['id']}/run",
        json={"version": "9.9.9", "subject": {"company_name": "ACME"}},
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_run_unknown_skill_404(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    _patch_invocation(monkeypatch)
    _patch_chat(monkeypatch)
    resp = await client.post(
        f"/api/v1/skills/{uuid.uuid4()}/run",
        json={"version": "1.0.0", "subject": {"company_name": "ACME"}},
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_run_disabled_skill_409_with_error_code(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """disabled -> 409 (client-state conflict, not a server error)."""
    server_code = await _register_server_via_api(client, auth_headers)
    skill = await _create_and_enable_skill(client, auth_headers, server_code)
    # 显式停用
    await client.post(
        f"/api/v1/skills/{skill['id']}/disable", headers=auth_headers
    )
    _patch_invocation(monkeypatch)
    _patch_chat(monkeypatch)
    resp = await client.post(
        f"/api/v1/skills/{skill['id']}/run",
        json={"version": "1.0.0", "subject": {"company_name": "ACME"}},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "disabled" in resp.json()["detail"]


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
async def test_run_403_non_admin_role(
    client: AsyncClient, auth_headers: dict, monkeypatch, role: str
):
    server_code = await _register_server_via_api(client, auth_headers)
    skill = await _create_and_enable_skill(client, auth_headers, server_code)
    _patch_invocation(monkeypatch)
    _patch_chat(monkeypatch)
    token = await _register_and_login(
        client, username=f"{role[:2]}_{uuid.uuid4().hex[:6]}", role=role
    )
    resp = await client.post(
        f"/api/v1/skills/{skill['id']}/run",
        json={"version": "1.0.0", "subject": {"company_name": "ACME"}},
        headers=_headers(token),
    )
    assert resp.status_code == 403


async def test_run_401_unauthenticated(client: AsyncClient):
    resp = await client.post(
        f"/api/v1/skills/{uuid.uuid4()}/run",
        json={"version": "1.0.0", "subject": {"company_name": "ACME"}},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /{id}/executions
# ---------------------------------------------------------------------------


async def test_executions_pagination(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    server_code = await _register_server_via_api(client, auth_headers)
    skill = await _create_and_enable_skill(client, auth_headers, server_code)
    _patch_invocation(
        monkeypatch,
        tool_results={"get_company": {"c": 1}, "scan_risk": {"r": 2}},
    )
    _patch_chat(monkeypatch)
    for _ in range(3):
        resp = await client.post(
            f"/api/v1/skills/{skill['id']}/run",
            json={"version": "1.0.0", "subject": {"company_name": "ACME"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

    resp = await client.get(
        f"/api/v1/skills/{skill['id']}/executions"
        "?limit=2&offset=0",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0
    # 审计行只含 digest，不含原文
    row = body["items"][0]
    assert row["ok"] is True
    assert len(row["subject_digest"]) == 64
    assert len(row["steps_digest"]) == 64
    assert len(row["report_digest"]) == 64
    assert "ACME" not in str(row)
    # 第二页
    resp2 = await client.get(
        f"/api/v1/skills/{skill['id']}/executions?limit=2&offset=2",
        headers=auth_headers,
    )
    assert len(resp2.json()["items"]) == 1


async def test_executions_404_unknown_skill(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get(
        f"/api/v1/skills/{uuid.uuid4()}/executions", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
async def test_executions_403_non_admin(
    client: AsyncClient, auth_headers: dict, role: str
):
    server_code = await _register_server_via_api(client, auth_headers)
    skill = await _create_and_enable_skill(client, auth_headers, server_code)
    token = await _register_and_login(
        client, username=f"ex_{role[:2]}_{uuid.uuid4().hex[:6]}", role=role
    )
    resp = await client.get(
        f"/api/v1/skills/{skill['id']}/executions", headers=_headers(token)
    )
    assert resp.status_code == 403


async def test_executions_401_unauthenticated(client: AsyncClient):
    resp = await client.get(
        f"/api/v1/skills/{uuid.uuid4()}/executions"
    )
    assert resp.status_code == 401
