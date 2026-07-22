"""BUG-017 测试 helper：经管理员入口建任意 role 用户并登录拿 token。

公开 register 已降级为只创建 teacher（AC-1），RBAC 测试需要的高权用户
（admin/data_admin/leader/super_admin）经 super_admin 入口创建（AC-2）。
各 context 测试文件统一用此 helper 替代旧的 /auth/register+role 调用。
"""
from __future__ import annotations

from httpx import AsyncClient

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


async def admin_token(client: AsyncClient) -> str:
    """登录 seeded super_admin 拿 token。"""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, f"admin login failed: {resp.text}"
    return resp.json()["access_token"]


async def register_and_login(
    client: AsyncClient,
    *,
    username: str,
    role: str,
    password: str = "Test1234!",
    tenant_id: str = DEFAULT_TENANT_ID,
    email: str | None = None,
) -> str:
    """经 super_admin 入口建用户（任意受控 role）并登录返回 token。"""
    token = await admin_token(client)
    create = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": username,
            "password": password,
            "role": role,
            "tenant_id": tenant_id,
            "email": email or f"{username}@test.local",
        },
    )
    assert create.status_code == 201, f"admin create user failed: {create.text}"
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200, f"login failed: {login.text}"
    return login.json()["access_token"]
