"""BUG-017 Slice 3: 管理员建用户与角色授予入口（AC-2）。

正向：super_admin 建用户 / 变更角色 / 启停账号。
越权：普通用户（teacher）调入口 -> 403。
受控：role 不在枚举 -> 422。
"""
import uuid

import pytest
from httpx import AsyncClient

DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"


def _uname(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _teacher_token(client: AsyncClient) -> str:
    """注册一个 teacher 并登录拿 token（用于越权测试）。"""
    username = _uname("teacher")
    await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pw123456"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "pw123456"},
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_admin_creates_user_success(client: AsyncClient, auth_headers: dict):
    """AC-2 正向：super_admin 建高权用户 -> 201，新用户可登录且 role 正确。"""
    username = _uname("admin")
    resp = await client.post(
        "/api/v1/admin/users",
        headers=auth_headers,
        json={
            "username": username,
            "password": "pw123456",
            "role": "admin",
            "tenant_id": DEFAULT_TENANT,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "admin"

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "pw123456"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_admin_create_user_rejects_invalid_role(client: AsyncClient, auth_headers: dict):
    """AC-2 受控：role 不在枚举 -> 422。"""
    resp = await client.post(
        "/api/v1/admin/users",
        headers=auth_headers,
        json={
            "username": _uname("bad"),
            "password": "pw123456",
            "role": "superuser",
            "tenant_id": DEFAULT_TENANT,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_non_admin_cannot_create_user(client: AsyncClient):
    """AC-2 越权：teacher 建 admin -> 403。"""
    token = await _teacher_token(client)
    resp = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": _uname("x"),
            "password": "pw123456",
            "role": "admin",
            "tenant_id": DEFAULT_TENANT,
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_updates_user_role(client: AsyncClient, auth_headers: dict):
    """AC-2 角色授予：super_admin 把 teacher 提升为 leader。"""
    username = _uname("promote")
    create = await client.post(
        "/api/v1/admin/users",
        headers=auth_headers,
        json={
            "username": username, "password": "pw123456",
            "role": "teacher", "tenant_id": DEFAULT_TENANT,
        },
    )
    user_id = create.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers=auth_headers,
        json={"role": "leader"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "leader"


@pytest.mark.asyncio
async def test_admin_disables_user_blocks_login(client: AsyncClient, auth_headers: dict):
    """AC-2 启停：禁用后用户登录被拒（AC-5 回归点）。"""
    username = _uname("disable")
    create = await client.post(
        "/api/v1/admin/users",
        headers=auth_headers,
        json={
            "username": username, "password": "pw123456",
            "role": "teacher", "tenant_id": DEFAULT_TENANT,
        },
    )
    user_id = create.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers=auth_headers,
        json={"is_active": False},
    )
    assert resp.status_code == 200, resp.text

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "pw123456"},
    )
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_cannot_update_role(client: AsyncClient, auth_headers: dict):
    """AC-2 越权：teacher 变更角色 -> 403。"""
    token = await _teacher_token(client)
    # teacher 的 user_id 从 /auth/me 取
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    teacher_id = me.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/users/{teacher_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "super_admin"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_update_nonexistent_user_404(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        f"/api/v1/admin/users/{uuid.uuid4()}",
        headers=auth_headers,
        json={"role": "leader"},
    )
    assert resp.status_code == 404
