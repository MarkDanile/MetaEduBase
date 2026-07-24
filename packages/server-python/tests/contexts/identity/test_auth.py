import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "super_admin"
    assert data["username"] == "admin"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "nonexistent", "password": "test"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    username = f"user_{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "password": "password123",
            "email": f"{username}@test.local",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == username
    assert data["role"] == "teacher"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient):
    username = f"dup_{uuid.uuid4().hex[:8]}"
    await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pass123"},
    )
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pass456"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_then_login(client: AsyncClient):
    username = f"login_{uuid.uuid4().hex[:8]}"
    await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "mypassword"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "mypassword"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_me_with_valid_token(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {
        "id",
        "tenant_id",
        "username",
        "role",
        "domain",
        "clearance_level",
        "is_active",
    }
    assert data["username"] == "admin"
    assert data["role"] == "super_admin"


@pytest.mark.asyncio
async def test_me_without_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_me_with_invalid_token(client: AsyncClient):
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401
