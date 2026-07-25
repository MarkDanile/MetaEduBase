"""TD-087: 模板管理 API 后端 RBAC（管理端点 require_high_privilege；lookup 端点仅认证）。

所有 15 管理端点（list/read/check/version/export + create/update/delete/clone/
rollback/deprecate/undeprecate/import/init-by-ai）统一要求 HIGH_PRIVILEGE_ROLES
（super_admin/data_admin/admin）。
- 匿名 -> 401
- leader/teacher/employee/student -> 403（不泄露存在性，先于业务逻辑）
- admin/data_admin/super_admin -> 2xx 或既有业务状态（404 等）

另含 lookup 端点（已认证可读，资源详情字段标签用），与 15 管理端点隔离。
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.contexts.identity._helpers import register_and_login

# 15 管理端点完整列表（行方法+路径+脱敏请求体）
# TD-087 P1-2: 覆盖全部 15 端点 × 角色矩阵
_ADMIN_ENDPOINTS = [
    ("GET", "", "list"),
    ("GET", "/check-doc-type?doc_type=course", "check-doc-type"),
    ("POST", "/init-by-ai", "init-by-ai"),
    ("POST", "", "create"),
    ("GET", "/{tid}", "get"),
    ("PUT", "/{tid}", "update"),
    ("DELETE", "/{tid}", "delete"),
    ("POST", "/import", "import"),
    ("POST", "/{tid}/clone", "clone"),
    ("GET", "/{tid}/versions?limit=5&offset=0", "list-versions"),
    ("GET", "/{tid}/versions/1", "get-version"),
    ("POST", "/{tid}/rollback/1", "rollback"),
    ("GET", "/{tid}/export", "export"),
    ("POST", "/{tid}/deprecate", "deprecate"),
    ("POST", "/{tid}/undeprecate", "undeprecate"),
]
_TID = "00000000-0000-0000-0000-000000000aaa"

_LOW_ROLES = ["leader", "teacher", "employee", "student"]
_HIGH_ROLES = ["admin", "data_admin"]  # super_admin 用 seeded admin_token
_LOOKUP_FIELDS = {"id", "name", "doc_types", "fields"}

# 跨租户测试用第二租户（独立定义，不跨 context import）
OTHER_TENANT_ID = "00000000-0000-0000-0000-000000000002"


async def _ensure_other_tenant() -> None:
    from tests.conftest import TEST_DB_URL
    eng = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    try:
        async with eng.begin() as conn:
            result = await conn.execute(
                text("SELECT id FROM metaedu.tenants WHERE id = :id"),
                {"id": OTHER_TENANT_ID},
            )
            if result.scalar_one_or_none():
                return
            now = datetime.now(UTC).replace(tzinfo=None)
            await conn.execute(
                text(
                    "INSERT INTO metaedu.tenants "
                    "(id, name, school_name, isolation, is_active, created_at, updated_at) "
                    "VALUES (:id, :name, :school_name, :isolation, true, :now, :now)"
                ),
                {
                    "id": OTHER_TENANT_ID,
                    "name": "td087-other",
                    "school_name": "test",
                    "isolation": "shared",
                    "now": now,
                },
            )
    finally:
        await eng.dispose()


def _uname(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _create_payload() -> dict:
    return {
        "code": f"td087-{uuid.uuid4().hex[:6]}",
        "name": "td087 test",
        "doc_type": "course",
        "doc_types": ["course"],
        "fields": [{"key": "f1", "label": "F1", "type": "text"}],
    }


async def _create_template(client: AsyncClient, token: str) -> str:
    """用高权 token 建模板，返回 template_id 供 get/update/delete 测试。"""
    resp = await client.post(
        "/api/v1/templates",
        json=_create_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --------- 15 管理端点 × 角色矩阵（P1-2 端点清单）---------


def _call_endpoint(client: AsyncClient, token: str | None, method: str, path: str):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    url = f"/api/v1/templates{path}".format(tid=_TID)
    if method == "GET":
        return client.get(url, headers=headers)
    if method == "POST":
        return client.post(url, json={}, headers=headers)
    if method == "PUT":
        return client.put(url, json={}, headers=headers)
    if method == "DELETE":
        return client.delete(url, headers=headers)
    raise ValueError(method)


@pytest.mark.parametrize("role", _LOW_ROLES)
@pytest.mark.parametrize("method,path,label", _ADMIN_ENDPOINTS)
@pytest.mark.asyncio
async def test_low_roles_denied_403_all_15_endpoints(
    client: AsyncClient, role: str, method: str, path: str, label: str
):
    """P1-2: 4 低权角色 × 15 管理端点 = 60 拒绝矩阵。"""
    token = await register_and_login(client, username=_uname(role), role=role)
    resp = await _call_endpoint(client, token, method, path)
    assert resp.status_code == 403, (
        f"{role} {label} ({method} {path}) 期望 403，实得 {resp.status_code}"
    )


@pytest.mark.parametrize("method,path,label", _ADMIN_ENDPOINTS)
@pytest.mark.asyncio
async def test_anonymous_denied_401_all_15_endpoints(
    client: AsyncClient, method: str, path: str, label: str
):
    """P1-2: 匿名 × 15 管理端点 = 15 拒绝矩阵。"""
    resp = await _call_endpoint(client, None, method, path)
    assert resp.status_code == 401, (
        f"{label} ({method} {path}) 匿名期望 401，实得 {resp.status_code}"
    )


# --------- 高权角色 + lookup 端点（lookup 仅认证）---------


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
        json=_create_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text


# --------- lookup 端点：已认证可读（P1-1 修复）---------


@pytest.mark.parametrize("role", _LOW_ROLES + _HIGH_ROLES)
@pytest.mark.asyncio
async def test_lookup_authenticated_all_roles(
    client: AsyncClient, role: str
):
    """lookup 端点对所有已认证角色开放（资源详情字段标签用）。"""
    token = await register_and_login(client, username=_uname(role), role=role)
    resp = await client.get(
        "/api/v1/templates/lookup",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"{role} lookup 期望 200，实得 {resp.status_code}"


@pytest.mark.asyncio
async def test_super_admin_lookup_ok(client: AsyncClient, auth_headers: dict):
    """seeded super_admin 同样可读取 tenant-local lookup。"""
    resp = await client.get("/api/v1/templates/lookup", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_lookup_anonymous_denied_401(client: AsyncClient):
    """lookup 端点仍要求认证（匿名 401），但不限 role。"""
    resp = await client.get("/api/v1/templates/lookup")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_lookup_returns_only_minimal_projection(
    client: AsyncClient, auth_headers: dict
):
    """普通用户只能读取字段标签投影，不能读取模板管理元数据。"""
    token_a = next(
        value.split(" ", 1)[1]
        for key, value in auth_headers.items()
        if key == "Authorization"
    )
    template_id = await _create_template(client, token_a)
    teacher_token = await register_and_login(
        client, username=_uname("lookup_teacher"), role="teacher"
    )

    resp = await client.get(
        "/api/v1/templates/lookup",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )

    assert resp.status_code == 200
    item = next(row for row in resp.json() if row["id"] == template_id)
    assert set(item) == _LOOKUP_FIELDS


@pytest.mark.asyncio
async def test_management_denial_is_sanitized_and_audited(client: AsyncClient):
    """客户端只拿通用 403，审计日志保留授权判断所需上下文。"""
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    security_logger = logging.getLogger("metaedu.security")
    handler = _Collect(level=logging.DEBUG)
    security_logger.addHandler(handler)
    security_logger.setLevel(logging.DEBUG)
    logging.disable(logging.NOTSET)
    security_logger.disabled = False
    try:
        token = await register_and_login(
            client, username=_uname("denied_audit"), role="teacher"
        )
        resp = await client.get(
            "/api/v1/templates",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        security_logger.removeHandler(handler)

    assert resp.status_code == 403
    assert resp.json() == {"detail": "无权访问管理资源"}
    denied = [record for record in records if record.event == "admin_access_denied"]
    assert denied
    assert denied[-1].detail == {
        "role": "teacher",
        "method": "GET",
        "path": "/api/v1/templates",
    }


# --------- 跨租户不泄露（P1-2 端点清单 + 跨租户 helper 独立）---------


@pytest.mark.asyncio
async def test_cross_tenant_get_returns_404_not_403(client: AsyncClient, auth_headers: dict):
    """高权用户跨租户 get 不存在的模板 -> 404（不是 403，不泄露存在性）。

    先用 auth_headers（tenant A）建模板，再用 tenant B 高权用户 get ->
    应 404（tenant isolation），而非 403（RBAC 通过）。
    """
    await _ensure_other_tenant()
    # 从 auth_headers 提取 token（格式 "Bearer xxx"）
    token_a = next(v.split(" ", 1)[1] for k, v in auth_headers.items() if k == "Authorization")
    template_id = await _create_template(client, token_a)
    # tenant B admin
    other_token = await register_and_login(
        client, username=_uname("other_admin"), role="admin", tenant_id=OTHER_TENANT_ID,
    )
    resp = await client.get(
        f"/api/v1/templates/{template_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lookup_cross_tenant_isolated(client: AsyncClient, auth_headers: dict):
    """lookup 端点跨租户隔离：tenant B 用户看不到 tenant A 模板。"""
    await _ensure_other_tenant()
    token_a = next(v.split(" ", 1)[1] for k, v in auth_headers.items() if k == "Authorization")
    template_id = await _create_template(client, token_a)
    other_token = await register_and_login(
        client, username=_uname("other_user"), role="teacher", tenant_id=OTHER_TENANT_ID,
    )
    resp = await client.get(
        "/api/v1/templates/lookup",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert template_id not in {item["id"] for item in items}
    assert all(set(item) == _LOOKUP_FIELDS for item in items)
