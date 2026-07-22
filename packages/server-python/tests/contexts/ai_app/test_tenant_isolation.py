"""BUG-018 Slice 2: AI App tenant-scoped service + 反伪造 tenant。

AC-2: tenant A 无法读取、修改、归档或轮换 tenant B 的应用 -> 跨租户操作返回 404。
AC-3: 创建请求不能伪造 tenant；服务层所有 ID 查询强制 tenant 条件；client 传
tenant_id 字段一律被忽略（extra='forbid'），服务端强制为 current_user.tenant_id。

平台应用（is_platform=True）跨租户可见但只能 super_admin 写；匿名公开广场
仅 PUBLISHED + PUBLIC 子集。
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.contexts.identity._helpers import (
    DEFAULT_TENANT_ID as HELPER_DEFAULT_TENANT_ID,
)
from tests.contexts.identity._helpers import (
    admin_token,
    register_and_login,
)

# 跨租户测试用第二租户 UUID（不同于 seeded DEFAULT_TENANT_ID）
OTHER_TENANT_ID = "00000000-0000-0000-0000-000000000002"


async def _ensure_other_tenant() -> None:
    """测试用第二租户：直接 INSERT metaedu.tenants 到测试库（不走 settings 全局 engine）。"""
    from datetime import UTC, datetime

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    # 复用 conftest 同一 TEST_DATABASE_URL env 解析（无 env 时走 DEFAULT_TEST_DB_URL fallback），
    # 保持与 client fixture 同一 DB。
    from tests.conftest import TEST_DB_URL
    eng = create_async_engine(TEST_DB_URL)
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
                    "name": "other",
                    "school_name": "其他学校",
                    "isolation": "shared",
                    "now": now,
                },
            )
    finally:
        await eng.dispose()


def _uname(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _admin_headers(client: AsyncClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client}"}

# helper 已定义 admin_token + register_and_login + DEFAULT_TENANT_ID


async def _create_app(
    client: AsyncClient, headers: dict[str, str], *, code: str | None = None, **extra
) -> dict:
    payload = {
        "code": code or f"APP-T-{uuid.uuid4().hex[:6]}",
        "name": "test app",
        "category": "test",
    }
    payload.update(extra)
    resp = await client.post("/api/v1/ai-apps", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_tenant_a_cannot_read_tenant_b_app(client: AsyncClient):
    """AC-2: 跨租户读 -> 404。"""
    await _ensure_other_tenant()
    token_a = await admin_token(client)
    app = await _create_app(client, {"Authorization": f"Bearer {token_a}"})
    app_id = app["id"]
    # tenant B 用独立 super_admin（建在 OTHER_TENANT_ID）
    token_b = await register_and_login(
        client, username=_uname("other_admin"), role="super_admin",
        tenant_id=OTHER_TENANT_ID,
    )
    resp = await client.get(
        f"/api/v1/ai-apps/{app_id}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404, f"跨租户读期望 404，实得 {resp.status_code}"


@pytest.mark.asyncio
async def test_tenant_a_cannot_update_tenant_b_app(client: AsyncClient):
    """AC-2: 跨租户改 -> 404。"""
    await _ensure_other_tenant()
    token_a = await admin_token(client)
    app = await _create_app(client, {"Authorization": f"Bearer {token_a}"})
    token_b = await register_and_login(
        client, username=_uname("other_admin"), role="super_admin",
        tenant_id=OTHER_TENANT_ID,
    )
    resp = await client.put(
        f"/api/v1/ai-apps/{app['id']}",
        json={"name": "hacked"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tenant_a_cannot_archive_tenant_b_app(client: AsyncClient):
    """AC-2: 跨租户归档 -> 404。"""
    await _ensure_other_tenant()
    token_a = await admin_token(client)
    app = await _create_app(client, {"Authorization": f"Bearer {token_a}"})
    token_b = await register_and_login(
        client, username=_uname("other_admin"), role="super_admin",
        tenant_id=OTHER_TENANT_ID,
    )
    resp = await client.delete(
        f"/api/v1/ai-apps/{app['id']}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404
    # 二次校验：app 仍在 tenant_a 下且未归档
    resp = await client.get(
        f"/api/v1/ai-apps/{app['id']}", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] != "Archived"


@pytest.mark.asyncio
async def test_tenant_a_cannot_regenerate_tenant_b_token(client: AsyncClient):
    """AC-2: 跨租户轮换 share/api token -> 404。"""
    await _ensure_other_tenant()
    token_a = await admin_token(client)
    app = await _create_app(client, {"Authorization": f"Bearer {token_a}"})
    token_b = await register_and_login(
        client, username=_uname("other_admin"), role="super_admin",
        tenant_id=OTHER_TENANT_ID,
    )
    for action in ("regenerate-share-token", "regenerate-api-token"):
        resp = await client.post(
            f"/api/v1/ai-apps/{app['id']}/{action}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, f"{action} 期望 404，实得 {resp.status_code}"


@pytest.mark.asyncio
async def test_create_with_client_tenant_id_is_rejected(client: AsyncClient):
    """AC-3: client 传 tenant_id 应被 422 拒绝（RegisterRequest 模式：extra='forbid'）。"""
    token = await admin_token(client)
    resp = await client.post(
        "/api/v1/ai-apps",
        json={
            "code": f"APP-T-{uuid.uuid4().hex[:6]}",
            "name": "forged",
            "tenant_id": OTHER_TENANT_ID,  # client 试图伪造到 OTHER_TENANT_ID
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, (
        f"client tenant_id 期望 422，实得 {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_create_assigns_current_user_tenant(client: AsyncClient):
    """AC-3: 创建后 server 强制写入 current_user.tenant_id。"""
    token = await admin_token(client)
    app = await _create_app(client, {"Authorization": f"Bearer {token}"})
    assert app["tenant_id"] == HELPER_DEFAULT_TENANT_ID


@pytest.mark.asyncio
async def test_platform_app_listed_for_other_tenant(client: AsyncClient):
    """AC-3: 平台应用 is_platform=True 对其他租户 super_admin 可见（管理 + 公开）。"""
    await _ensure_other_tenant()
    # 先创建普通应用（tenant A）
    token_a = await admin_token(client)
    normal = await _create_app(client, {"Authorization": f"Bearer {token_a}"})
    # 直接 INSERT is_platform=True 应用（service.create V0 不支持 is_platform 客户端设）
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.conftest import TEST_DB_URL
    platform_id = uuid.uuid4()
    platform_code = f"APP-PLAT-{uuid.uuid4().hex[:6]}"
    eng = create_async_engine(TEST_DB_URL)
    try:
        async with eng.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO metaedu.ai_applications "
                    "(id, code, name, status, visibility, entry_type, version, sort_order, "
                    " tenant_id, is_platform, created_at, updated_at) "
                    "VALUES (:id, :code, :name, 'Published', 'public', 'internal_route', "
                    " '1.0.0', 0, NULL, true, NOW(), NOW())"
                ),
                {"id": platform_id, "code": platform_code, "name": "platform app"},
            )
    finally:
        await eng.dispose()
    # tenant B super_admin 应能在 list 看到 platform app（跨租户可见）
    token_b = await register_and_login(
        client, username=_uname("other_admin"), role="super_admin",
        tenant_id=OTHER_TENANT_ID,
    )
    resp = await client.get(
        "/api/v1/ai-apps", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 200
    codes = [a["code"] for a in resp.json()["items"]]
    assert platform_code in codes
    assert normal["code"] not in codes  # tenant_a 的普通应用不可见
    # platform app 不能被 tenant_b 普通 admin 改
    token_b_admin = await register_and_login(
        client, username=_uname("other_admin_role"), role="admin",
        tenant_id=OTHER_TENANT_ID,
    )
    resp = await client.put(
        f"/api/v1/ai-apps/{platform_id}",
        json={"name": "tampered"},
        headers={"Authorization": f"Bearer {token_b_admin}"},
    )
    # 非超管管理员写 platform app 应 404（仅 super_admin 可跨租户写）
    assert resp.status_code == 404
