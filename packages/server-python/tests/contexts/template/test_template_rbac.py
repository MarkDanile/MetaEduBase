"""TD-087: 模板管理 API 后端 RBAC（HIGH_PRIVILEGE_ROLES 守卫）。

所有模板端点（list/read/check/version/export + mutation）统一要求
HIGH_PRIVILEGE_ROLES（super_admin/data_admin/admin）。
- 匿名 -> 401
- leader/teacher/employee/student -> 403（不泄露存在性，先于业务逻辑）
- admin/data_admin/super_admin -> 2xx 或既有业务状态（404 等）
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.contexts.identity._helpers import register_and_login

# 代表端点（覆盖 list/create/read/update/delete/rollback/export）
_REPRESENTATIVE_ENDPOINTS = [
    ("GET", "/api/v1/templates", "list"),
    ("POST", "/api/v1/templates", "create"),
    ("GET", "/api/v1/templates/{tid}", "get"),
    ("PUT", "/api/v1/templates/{tid}", "update"),
    ("DELETE", "/api/v1/templates/{tid}", "delete"),
    ("GET", "/api/v1/templates/{tid}/export", "export"),
]

_LOW_ROLES = ["leader", "teacher", "employee", "student"]
_HIGH_ROLES = ["admin", "data_admin"]  # super_admin 用 seeded admin_token


def _uname(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _create_template(client: AsyncClient, token: str) -> str:
    """用高权 token 建模板，返回 template_id 供 get/update/delete 测试。"""
    resp = await client.post(
        "/api/v1/templates",
        json={
            "code": f"td087-{uuid.uuid4().hex[:6]}",
            "name": "td087 test",
            "doc_type": "course",
            "doc_types": ["course"],
            "fields": [{"key": "f1", "label": "F1", "type": "text"}],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --------- 匿名 401 ---------


@pytest.mark.parametrize("method,path,label", _REPRESENTATIVE_ENDPOINTS)
@pytest.mark.asyncio
async def test_anonymous_denied_401(
    client: AsyncClient, method: str, path: str, label: str
):
    """匿名调用所有模板端点 -> 401。"""
    url = path.format(tid=uuid.uuid4())
    if method == "GET":
        resp = await client.get(url)
    elif method == "POST":
        resp = await client.post(url, json={})
    elif method == "PUT":
        resp = await client.put(url, json={})
    elif method == "DELETE":
        resp = await client.delete(url)
    assert resp.status_code == 401, f"{label} 匿名期望 401，实得 {resp.status_code}"


# --------- 低权角色 403 ---------


@pytest.mark.parametrize("role", _LOW_ROLES)
@pytest.mark.asyncio
async def test_low_roles_denied_403_list(client: AsyncClient, role: str):
    """低权角色 list -> 403。"""
    token = await register_and_login(client, username=_uname(role), role=role)
    resp = await client.get("/api/v1/templates", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403, f"{role} list 期望 403，实得 {resp.status_code}"


@pytest.mark.parametrize("role", _LOW_ROLES)
@pytest.mark.asyncio
async def test_low_roles_denied_403_create(client: AsyncClient, role: str):
    """低权角色 create -> 403。"""
    token = await register_and_login(client, username=_uname(role), role=role)
    resp = await client.post(
        "/api/v1/templates",
        json={"code": "x", "name": "x", "doc_type": "course"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("role", _LOW_ROLES)
@pytest.mark.asyncio
async def test_low_roles_denied_403_get(client: AsyncClient, role: str):
    """低权角色 get -> 403（不泄露存在性，先于 404）。"""
    token = await register_and_login(client, username=_uname(role), role=role)
    resp = await client.get(
        f"/api/v1/templates/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# --------- 高权角色通过 ---------


@pytest.mark.asyncio
async def test_super_admin_list_ok(client: AsyncClient, auth_headers: dict):
    """super_admin list -> 200（既有行为不回归）。"""
    resp = await client.get("/api/v1/templates", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.parametrize("role", _HIGH_ROLES)
@pytest.mark.asyncio
async def test_high_roles_list_ok(client: AsyncClient, role: str):
    """admin/data_admin list -> 200。"""
    token = await register_and_login(client, username=_uname(role), role=role)
    resp = await client.get("/api/v1/templates", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


@pytest.mark.parametrize("role", _HIGH_ROLES)
@pytest.mark.asyncio
async def test_high_roles_create_ok(client: AsyncClient, role: str):
    """admin/data_admin create -> 201。"""
    token = await register_and_login(client, username=_uname(role), role=role)
    resp = await client.post(
        "/api/v1/templates",
        json={
            "code": f"td087-{uuid.uuid4().hex[:6]}",
            "name": "x",
            "doc_type": "course",
            "doc_types": ["course"],
            "fields": [{"key": "f1", "label": "F1", "type": "text"}],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text


# --------- 跨租户不泄露（既有 tenant isolation 保持）---------


@pytest.mark.asyncio
async def test_cross_tenant_get_returns_404_not_403(client: AsyncClient, auth_headers: dict):
    """高权用户跨租户 get 不存在的模板 -> 404（不是 403，不泄露存在性）。

    先用 auth_headers（tenant A）建模板，再用 tenant B 高权用户 get ->
    应 404（tenant isolation），而非 403（RBAC 通过）。
    """
    from tests.contexts.ai_app.test_tenant_isolation import OTHER_TENANT_ID, _ensure_other_tenant

    await _ensure_other_tenant()
    template_id = await _create_template(client, list(auth_headers.values())[0].split(" ")[1])
    # tenant B admin
    other_token = await register_and_login(
        client, username=_uname("other_admin"), role="admin", tenant_id=OTHER_TENANT_ID,
    )
    resp = await client.get(
        f"/api/v1/templates/{template_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    # RBAC 通过（admin），但跨租户 -> 404
    assert resp.status_code == 404
