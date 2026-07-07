"""End-to-end test for /api/v1/catalogs CRUD endpoints.

REQ-054 Task 2: the router is the user-facing entry point. Tests cover:

- POST 201 (admin token) + GET 200 (list + by id) + PATCH 200 + DELETE 204
- POST 403 (employee token — RBAC blocks non-admin)
- POST 409 (code conflict — second create with same code)
- GET / PATCH / DELETE 404 (unknown catalog_id)
- POST 401 (no auth header)

Auth flow: the ``client`` fixture (from ``tests/conftest.py``) overrides
``get_session`` with a per-test session and seeds the default admin user
(role=``super_admin``). ``auth_headers`` logs in as admin and yields the
Bearer header. For the 403 test we register a fresh ``employee`` user via
``/api/v1/auth/register`` and log in as them.

uuid-suffixed codes keep tests re-runnable without colliding on the
``uq_data_catalogs_tenant_code`` unique constraint across test runs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_code(prefix: str = "api") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _register_and_login(
    client: AsyncClient, *, username: str, role: str
) -> str:
    """Register a new user with the given role and return their access token.

    Uses the default tenant (DEFAULT_TENANT_ID) so the FK on users.tenant_id
    is satisfied by the seeded tenant row.
    """
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


def _make_create_payload(code: str) -> dict:
    return {
        "code": code,
        "name": f"测试数据库-{code}",
        "entity_types": ["bill", "contract"],
        "description": "API 测试创建",
        "icon": "database",
        "color": "#3B82F6",
        "default_business_purpose": "财务数据分析",
    }


# ---------------------------------------------------------------------------
# POST /api/v1/catalogs — create
# ---------------------------------------------------------------------------


async def test_create_catalog_201(client: AsyncClient, auth_headers: dict):
    """admin (super_admin) 创建 catalog → 201 + DTO 完整字段。"""
    code = _unique_code("fin")
    payload = _make_create_payload(code)
    resp = await client.post("/api/v1/catalogs", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == code
    assert body["name"] == f"测试数据库-{code}"
    assert body["entity_types"] == ["bill", "contract"]
    assert body["is_active"] is True
    assert body["description"] == "API 测试创建"
    assert body["icon"] == "database"
    assert body["color"] == "#3B82F6"
    assert body["default_business_purpose"] == "财务数据分析"
    assert body["id"]
    assert body["tenant_id"]
    assert body["created_by"]
    assert body["created_at"]
    assert body["updated_at"]


async def test_create_catalog_403_employee(client: AsyncClient):
    """employee 角色创建 catalog → 403。"""
    token = await _register_and_login(
        client, username=f"emp_{uuid.uuid4().hex[:6]}", role="employee"
    )
    payload = _make_create_payload(_unique_code("forb"))
    resp = await client.post(
        "/api/v1/catalogs", json=payload, headers=_headers(token)
    )
    assert resp.status_code == 403
    assert "无权" in resp.json()["detail"]


async def test_create_catalog_409_code_conflict(
    client: AsyncClient, auth_headers: dict
):
    """同 tenant 内 code 重复 → 409。"""
    code = _unique_code("cfl")
    payload = _make_create_payload(code)
    resp1 = await client.post(
        "/api/v1/catalogs", json=payload, headers=auth_headers
    )
    assert resp1.status_code == 201
    resp2 = await client.post(
        "/api/v1/catalogs", json=payload, headers=auth_headers
    )
    assert resp2.status_code == 409
    assert "已存在" in resp2.json()["detail"]


async def test_create_catalog_401_unauthenticated(client: AsyncClient):
    """无 Authorization header → 401（HTTPBearer 拒绝）。"""
    payload = _make_create_payload(_unique_code("noauth"))
    resp = await client.post("/api/v1/catalogs", json=payload)
    assert resp.status_code == 401


async def test_create_catalog_422_invalid_code(
    client: AsyncClient, auth_headers: dict
):
    """code 不符合 pattern（大写）→ 422。"""
    payload = _make_create_payload("InvalidCode")
    resp = await client.post(
        "/api/v1/catalogs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


async def test_create_catalog_422_empty_entity_types(
    client: AsyncClient, auth_headers: dict
):
    """entity_types 为空数组 → 422（min_length=1）。"""
    payload = _make_create_payload(_unique_code("empty"))
    payload["entity_types"] = []
    resp = await client.post(
        "/api/v1/catalogs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 422


async def test_create_catalog_201_data_admin(client: AsyncClient):
    """data_admin 角色创建 catalog → 201（data_admin 在 CATALOG_ADMIN_ROLES 内）。"""
    token = await _register_and_login(
        client, username=f"da_{uuid.uuid4().hex[:6]}", role="data_admin"
    )
    payload = _make_create_payload(_unique_code("da"))
    resp = await client.post(
        "/api/v1/catalogs", json=payload, headers=_headers(token)
    )
    assert resp.status_code == 201
    assert resp.json()["code"] == payload["code"]


# ---------------------------------------------------------------------------
# GET /api/v1/catalogs — list + get by id
# ---------------------------------------------------------------------------


async def test_list_catalogs_200(client: AsyncClient, auth_headers: dict):
    """GET /api/v1/catalogs → 200 + array（至少含 education seed）。"""
    resp = await client.get("/api/v1/catalogs", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    codes = {c["code"] for c in body}
    # education 是 alembic 018 seed 的
    assert "education" in codes


async def test_list_catalogs_includes_newly_created(
    client: AsyncClient, auth_headers: dict
):
    """创建后 list 能看到新 catalog。"""
    code = _unique_code("lst")
    payload = _make_create_payload(code)
    resp = await client.post(
        "/api/v1/catalogs", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201
    resp = await client.get("/api/v1/catalogs", headers=auth_headers)
    assert resp.status_code == 200
    codes = {c["code"] for c in resp.json()}
    assert code in codes


async def test_get_catalog_200(client: AsyncClient, auth_headers: dict):
    """GET /api/v1/catalogs/{id} → 200 + 完整 DTO。"""
    code = _unique_code("get")
    payload = _make_create_payload(code)
    create_resp = await client.post(
        "/api/v1/catalogs", json=payload, headers=auth_headers
    )
    assert create_resp.status_code == 201
    catalog_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/catalogs/{catalog_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == code


async def test_get_catalog_404(client: AsyncClient, auth_headers: dict):
    """GET 不存在的 catalog_id → 404。"""
    resp = await client.get(
        f"/api/v1/catalogs/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404
    assert "不存在" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# PATCH /api/v1/catalogs/{id} — update
# ---------------------------------------------------------------------------


async def test_update_catalog_200(client: AsyncClient, auth_headers: dict):
    """PATCH 修改 name + description → 200 + 更新后的 DTO。"""
    code = _unique_code("pat")
    payload = _make_create_payload(code)
    create_resp = await client.post(
        "/api/v1/catalogs", json=payload, headers=auth_headers
    )
    catalog_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/catalogs/{catalog_id}",
        json={"name": "改后的名称", "description": "改后的描述"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "改后的名称"
    assert body["description"] == "改后的描述"
    # 未改的字段保持
    assert body["code"] == code
    assert body["entity_types"] == ["bill", "contract"]


async def test_update_catalog_404(client: AsyncClient, auth_headers: dict):
    """PATCH 不存在的 catalog_id → 404。"""
    resp = await client.patch(
        f"/api/v1/catalogs/{uuid.uuid4()}",
        json={"name": "不存在"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_update_catalog_403_employee(
    client: AsyncClient, auth_headers: dict
):
    """employee PATCH → 403（RBAC 阻止非 admin 修改）。"""
    # admin 先建一个
    payload = _make_create_payload(_unique_code("p403"))
    create_resp = await client.post(
        "/api/v1/catalogs", json=payload, headers=auth_headers
    )
    catalog_id = create_resp.json()["id"]

    # employee 试图改
    token = await _register_and_login(
        client, username=f"emp_{uuid.uuid4().hex[:6]}", role="employee"
    )
    resp = await client.patch(
        f"/api/v1/catalogs/{catalog_id}",
        json={"name": "employee 改名"},
        headers=_headers(token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/v1/catalogs/{id}
# ---------------------------------------------------------------------------


async def test_delete_catalog_204(client: AsyncClient, auth_headers: dict):
    """DELETE 已存在的 catalog → 204（soft delete）。"""
    payload = _make_create_payload(_unique_code("del"))
    create_resp = await client.post(
        "/api/v1/catalogs", json=payload, headers=auth_headers
    )
    catalog_id = create_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/catalogs/{catalog_id}", headers=auth_headers
    )
    assert resp.status_code == 204

    # 软删后 GET → 404
    get_resp = await client.get(
        f"/api/v1/catalogs/{catalog_id}", headers=auth_headers
    )
    assert get_resp.status_code == 404


async def test_delete_catalog_404(client: AsyncClient, auth_headers: dict):
    """DELETE 不存在的 catalog_id → 404。"""
    resp = await client.delete(
        f"/api/v1/catalogs/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_delete_catalog_403_employee(
    client: AsyncClient, auth_headers: dict
):
    """employee DELETE → 403（RBAC 阻止非 admin 删除）。"""
    payload = _make_create_payload(_unique_code("d403"))
    create_resp = await client.post(
        "/api/v1/catalogs", json=payload, headers=auth_headers
    )
    catalog_id = create_resp.json()["id"]

    token = await _register_and_login(
        client, username=f"emp_{uuid.uuid4().hex[:6]}", role="employee"
    )
    resp = await client.delete(
        f"/api/v1/catalogs/{catalog_id}", headers=_headers(token)
    )
    assert resp.status_code == 403


async def test_delete_catalog_hard_409_with_datasets(
    client: AsyncClient, auth_headers: dict, db_session
):
    """DELETE ?hard=true on catalog with datasets → 409。

    Insert a dataset via SQL pointing at the newly created catalog,
    commit (so it's visible to the router's session), then attempt
    hard-delete → 409 with 数据集 message.
    """
    # 1. admin 建 catalog
    code = _unique_code("dhrd")
    payload = _make_create_payload(code)
    create_resp = await client.post(
        "/api/v1/catalogs", json=payload, headers=auth_headers
    )
    assert create_resp.status_code == 201
    catalog_id = create_resp.json()["id"]

    # 2. 通过 db_session 插入一条 dataset 指向该 catalog，并 commit（对 router 可见）
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.datasets "
            "(id, tenant_id, catalog_id, name, column_names, column_types, "
            "row_count, status, kg_status, sort_order, created_by, "
            "created_at, updated_at) "
            "VALUES (:id, :tid, :cid, :name, NULL, NULL, 0, 'uploaded', "
            "'pending', 0, :uid, :now, :now)"
        ),
        {
            "id": uuid.uuid4(),
            "tid": "00000000-0000-0000-0000-000000000001",
            "cid": catalog_id,
            "name": "hard-delete-guard-test",
            "uid": "00000000-0000-0000-0000-000000000002",
            "now": now,
        },
    )
    await db_session.commit()

    # 3. 硬删 → 409
    resp = await client.delete(
        f"/api/v1/catalogs/{catalog_id}?hard=true", headers=auth_headers
    )
    assert resp.status_code == 409
    assert "数据集" in resp.json()["detail"]
