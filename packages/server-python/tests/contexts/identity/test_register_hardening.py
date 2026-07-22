"""BUG-017 Slice 2: 公开 register 降级（AC-1）。

匿名注册不得获得管理角色、不得指定 tenant。RegisterRequest 移除 role /
tenant_id 字段并 forbid 额外字段，服务端强制 role=teacher + 默认 tenant。
"""
import uuid

import pytest
from httpx import AsyncClient


def _uname(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_register_no_role_defaults_teacher(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": _uname("u"), "password": "pw123456"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "teacher"


@pytest.mark.asyncio
async def test_register_rejects_client_supplied_role(client: AsyncClient):
    """AC-1：客户端传 role -> 422，不得获得管理角色。"""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": _uname("u"), "password": "pw123456", "role": "super_admin"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_client_supplied_tenant_id(client: AsyncClient):
    """AC-1：客户端传 tenant_id -> 422，不得指定已有 tenant。"""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "username": _uname("u"),
            "password": "pw123456",
            "tenant_id": "00000000-0000-0000-0000-000000000099",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_created_user_is_teacher_in_default_tenant(client: AsyncClient):
    """注册成功的用户登录后 role=teacher、tenant=默认 tenant。"""
    username = _uname("u_verify")
    await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pw123456"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "pw123456"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "teacher"
    assert data["tenant_id"] == "00000000-0000-0000-0000-000000000001"
