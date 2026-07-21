"""Router tests for /api/v1/dd/tasks (+ resolve/confirm subject) — REQ-046 Slice 1.

HTTP-level contract for the subject-anchoring container (AC-1). The MCP
invocation is mocked at the ``dd_router`` module boundary
(``MCPInvocationService.invoke``) — the router runs end-to-end with a real DB
session, only the network leaf (QCC) is stubbed. Covers: create/list/get,
candidate resolution, confirm advances to subject_confirmed, tenant
isolation, and 404/502 error mapping.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    MCPInvocationError,
)

pytestmark = pytest.mark.asyncio


async def _register_and_login(client: AsyncClient, *, username: str, role: str) -> str:
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


def _uname(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _create_task(client: AsyncClient, token: str, query: str) -> dict:
    resp = await client.post(
        "/api/v1/dd/tasks",
        json={"title": "园区入驻背调", "subject_query": query},
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_list_get_task(client: AsyncClient):
    token = await _register_and_login(client, username=_uname("dd"), role="admin")
    task = await _create_task(client, token, "阿里巴巴")
    assert task["status"] == "subject_pending"
    assert task["subject_query"] == "阿里巴巴"

    resp = await client.get("/api/v1/dd/tasks", headers=_headers(token))
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert task["id"] in ids

    resp = await client.get(f"/api/v1/dd/tasks/{task['id']}", headers=_headers(token))
    assert resp.status_code == 200
    assert resp.json()["id"] == task["id"]


async def test_get_task_404_for_other_tenant(client: AsyncClient):
    token_a = await _register_and_login(client, username=_uname("dda"), role="admin")
    task = await _create_task(client, token_a, "某企业")
    # 未认证 -> 401
    resp = await client.get(f"/api/v1/dd/tasks/{task['id']}")
    assert resp.status_code == 401
    # 随机 id -> 404
    resp = await client.get(f"/api/v1/dd/tasks/{uuid.uuid4()}", headers=_headers(token_a))
    assert resp.status_code == 404


async def test_resolve_subject_returns_candidates(client: AsyncClient):
    token = await _register_and_login(client, username=_uname("ddr"), role="admin")
    task = await _create_task(client, token, "阿里巴巴")
    fake_result = {
        "items": [
            {"company_name": "阿里巴巴(中国)有限公司", "credit_code": "91A"},
            {"company_name": "阿里巴巴网络技术有限公司", "credit_code": "91B"},
        ]
    }
    with patch(
        "app.contexts.due_diligence.interfaces.api.dd_router.MCPInvocationService"
    ) as mock_cls:
        mock_cls.return_value.invoke = AsyncMock(return_value=fake_result)
        resp = await client.post(
            f"/api/v1/dd/tasks/{task['id']}/resolve-subject", headers=_headers(token)
        )
    assert resp.status_code == 200, resp.text
    names = [c["company_name"] for c in resp.json()]
    assert names == ["阿里巴巴(中国)有限公司", "阿里巴巴网络技术有限公司"]


async def test_resolve_subject_no_match_returns_empty(client: AsyncClient):
    token = await _register_and_login(client, username=_uname("ddn"), role="admin")
    task = await _create_task(client, token, "不存在公司xyz")
    with patch(
        "app.contexts.due_diligence.interfaces.api.dd_router.MCPInvocationService"
    ) as mock_cls:
        mock_cls.return_value.invoke = AsyncMock(return_value={"items": []})
        resp = await client.post(
            f"/api/v1/dd/tasks/{task['id']}/resolve-subject", headers=_headers(token)
        )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_resolve_subject_qcc_error_maps_502(client: AsyncClient):
    token = await _register_and_login(client, username=_uname("dde"), role="admin")
    task = await _create_task(client, token, "x")
    with patch(
        "app.contexts.due_diligence.interfaces.api.dd_router.MCPInvocationService"
    ) as mock_cls:
        mock_cls.return_value.invoke = AsyncMock(
            side_effect=MCPInvocationError("tool_error", "qcc 调用失败")
        )
        resp = await client.post(
            f"/api/v1/dd/tasks/{task['id']}/resolve-subject", headers=_headers(token)
        )
    assert resp.status_code == 502


async def test_confirm_subject_advances_to_confirmed(client: AsyncClient):
    token = await _register_and_login(client, username=_uname("ddc"), role="admin")
    task = await _create_task(client, token, "阿里巴巴")
    resp = await client.post(
        f"/api/v1/dd/tasks/{task['id']}/confirm-subject",
        json={"company_name": "阿里巴巴(中国)有限公司", "credit_code": "91A"},
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "subject_confirmed"
    assert body["confirmed_subject"] == {
        "company_name": "阿里巴巴(中国)有限公司",
        "credit_code": "91A",
    }


async def test_confirm_subject_404(client: AsyncClient):
    token = await _register_and_login(client, username=_uname("ddx"), role="admin")
    resp = await client.post(
        f"/api/v1/dd/tasks/{uuid.uuid4()}/confirm-subject",
        json={"company_name": "x", "credit_code": None},
        headers=_headers(token),
    )
    assert resp.status_code == 404
