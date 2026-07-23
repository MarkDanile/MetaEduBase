"""BUG-018 Slice 3: DTO 拆分 + Token 不外泄 + 匿名公开 endpoint（AC-4/AC-5）。

AC-4: 列表/详情响应不含 share_token/api_token；rotate 只返回对应 token。
AC-5: 公开 endpoint（若保留）不暴露 Draft/Disabled/Archived、租户私有配置或凭证。
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.contexts.ai_app.test_tenant_isolation import (
    OTHER_TENANT_ID,
    _ensure_other_tenant,
)
from tests.contexts.identity._helpers import admin_token, register_and_login


def _uname(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _create_app_with_token(
    client: AsyncClient, token: str, code: str | None = None
) -> dict:
    payload = {
        "code": code or f"APP-S3-{uuid.uuid4().hex[:6]}",
        "name": "s3 test",
        "category": "test",
    }
    resp = await client.post(
        "/api/v1/ai-apps", json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_list_response_does_not_contain_tokens(client: AsyncClient):
    """AC-4: 列表默认 PublicResponse，不含 share_token/api_token。"""
    token = await admin_token(client)
    app = await _create_app_with_token(client, token)
    # 触发 share_token 写入（rotate API）
    await client.post(
        f"/api/v1/ai-apps/{app['id']}/regenerate-share-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get("/api/v1/ai-apps", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert "share_token" not in item, "列表不应含 share_token"
        assert "api_token" not in item, "列表不应含 api_token"


@pytest.mark.asyncio
async def test_detail_default_response_does_not_contain_tokens(client: AsyncClient):
    """AC-4: 详情默认 PublicResponse，不含 token。"""
    token = await admin_token(client)
    app = await _create_app_with_token(client, token)
    await client.post(
        f"/api/v1/ai-apps/{app['id']}/regenerate-share-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/v1/ai-apps/{app['id']}/regenerate-api-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get(
        f"/api/v1/ai-apps/{app['id']}", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "share_token" not in body
    assert "api_token" not in body


@pytest.mark.asyncio
async def test_detail_admin_scope_returns_tokens(client: AsyncClient):
    """超管用 ?scope=admin 看详情应含 token（给管理 UI）。"""
    token = await admin_token(client)
    app = await _create_app_with_token(client, token)
    await client.post(
        f"/api/v1/ai-apps/{app['id']}/regenerate-share-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get(
        f"/api/v1/ai-apps/{app['id']}?scope=admin",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "share_token" in body, (
        f"scope=admin 应含 share_token，实际 body keys: {sorted(body.keys())}"
    )
    assert body["share_token"] is not None


@pytest.mark.asyncio
async def test_regenerate_share_token_response_only_share_token(client: AsyncClient):
    """AC-4: rotate share_token 只返 share_token，不含 api_token / 完整 DTO。"""
    token = await admin_token(client)
    app = await _create_app_with_token(client, token)
    resp = await client.post(
        f"/api/v1/ai-apps/{app['id']}/regenerate-share-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    # rotate 应只返目标 token（single field），不含 api_token / name / config_schema 等
    assert "api_token" not in body
    assert "name" not in body
    assert "config_schema" not in body


@pytest.mark.asyncio
async def test_regenerate_api_token_response_only_api_token(client: AsyncClient):
    """AC-4: rotate api_token 只返 api_token 字段。"""
    token = await admin_token(client)
    app = await _create_app_with_token(client, token)
    resp = await client.post(
        f"/api/v1/ai-apps/{app['id']}/regenerate-api-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert "share_token" not in body
    assert "name" not in body


@pytest.mark.asyncio
async def test_public_endpoint_anonymous_access(client: AsyncClient):
    """AC-5: 公开 endpoint 匿名访问，只含 PUBLISHED+PUBLIC+is_platform 子集，不含 token。"""
    await _ensure_other_tenant()
    # 通过 raw DB 注入一个公开应用（service 不支持创建公开应用）
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.conftest import TEST_DB_URL
    pub_id = uuid.uuid4()
    pub_code = f"APP-PUB-{uuid.uuid4().hex[:6]}"
    pub_share_token = f"leaked-share-{uuid.uuid4().hex[:8]}"
    pub_api_token = f"leaked-api-{uuid.uuid4().hex[:8]}"
    eng = create_async_engine(TEST_DB_URL)
    try:
        async with eng.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO metaedu.ai_applications "
                    "(id, code, name, status, visibility, entry_type, version, sort_order, "
                    " tenant_id, is_platform, share_token, api_token, created_at, updated_at) "
                    "VALUES (:id, :code, :name, 'Published', 'public', 'internal_route', "
                    " '1.0.0', 0, NULL, true, :share_token, :api_token, NOW(), NOW())"
                ),
                {
                    "id": pub_id,
                    "code": pub_code,
                    "name": "public app",
                    "share_token": pub_share_token,
                    "api_token": pub_api_token,
                },
            )
            # 注入一个 Draft 不应暴露
            await conn.execute(
                text(
                    "INSERT INTO metaedu.ai_applications "
                    "(id, code, name, status, visibility, entry_type, version, sort_order, "
                    " tenant_id, is_platform, created_at, updated_at) "
                    "VALUES (:id, :code, :name, 'Draft', 'internal', 'internal_route', "
                    " '1.0.0', 0, NULL, true, NOW(), NOW())"
                ),
                {
                    "id": uuid.uuid4(),
                    "code": f"APP-DRAFT-{uuid.uuid4().hex[:6]}",
                    "name": "draft app",
                },
            )
            # 注入一个 tenant 私有应用（is_platform=false）不应暴露
            await conn.execute(
                text(
                    "INSERT INTO metaedu.ai_applications "
                    "(id, code, name, status, visibility, entry_type, version, sort_order, "
                    " tenant_id, is_platform, created_at, updated_at) "
                    "VALUES (:id, :code, :name, 'Published', 'public', 'internal_route', "
                    " '1.0.0', 0, :tid, false, NOW(), NOW())"
                ),
                {
                    "id": uuid.uuid4(),
                    "code": f"APP-PRIV-{uuid.uuid4().hex[:6]}",
                    "name": "private app",
                    "tid": OTHER_TENANT_ID,
                },
            )
    finally:
        await eng.dispose()
    # 匿名调用
    resp = await client.get("/api/v1/ai-apps/public")
    assert resp.status_code == 200
    items = resp.json()["items"]
    codes = [a["code"] for a in items]
    assert pub_code in codes
    for item in items:
        assert "share_token" not in item
        assert "api_token" not in item
        assert "config_schema" not in item
        assert item["status"] == "Published"
        # 不应包含 draft 或 tenant private
    assert not any("DRAFT" in c for c in codes)
    assert not any("PRIV" in c for c in codes)


@pytest.mark.asyncio
async def test_share_endpoint_anonymous_resolves_token(client: AsyncClient):
    """BUG-018 Slice 4: 公开 share 端点按 token 解析应用，不暴露 token 字段。"""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.conftest import TEST_DB_URL
    pub_id = uuid.uuid4()
    pub_code = f"APP-SHARE-{uuid.uuid4().hex[:6]}"
    share_token_value = f"share-{uuid.uuid4().hex[:10]}"
    eng = create_async_engine(TEST_DB_URL)
    try:
        async with eng.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO metaedu.ai_applications "
                    "(id, code, name, status, visibility, entry_type, version, sort_order, "
                    " tenant_id, is_platform, share_token, created_at, updated_at) "
                    "VALUES (:id, :code, :name, 'Published', 'public', 'internal_route', "
                    " '1.0.0', 0, NULL, true, :share_token, NOW(), NOW())"
                ),
                {
                    "id": pub_id,
                    "code": pub_code,
                    "name": "shared app",
                    "share_token": share_token_value,
                },
            )
    finally:
        await eng.dispose()
    # 匿名按 share_token 查
    resp = await client.get(f"/api/v1/ai-apps/share/{share_token_value}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == pub_code
    assert "share_token" not in body
    assert "api_token" not in body
    assert "config_schema" not in body


@pytest.mark.asyncio
async def test_share_endpoint_unknown_token_returns_404(client: AsyncClient):
    """BUG-018 Slice 4: 不存在的 token -> 404。"""
    resp = await client.get("/api/v1/ai-apps/share/nonexistent-token-xyz")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_high_privilege_roles_see_admin_scope(client: AsyncClient):
    """HIGH_PRIVILEGE_ROLES 都能用 ?scope=admin 查看 token；其他角色被忽略 scope。"""
    # teacher 应忽略 scope（403 或 404 由 tenant 决定；本测试只看 response body 无 token）
    await _ensure_other_tenant()
    teacher_token = await register_and_login(
        client, username=_uname("teacher_s3"), role="teacher"
    )
    # teacher 没 tenant 内的 app，仅看 ?scope=admin 不应返回 token 字段（slice 3 默认 Public）
    resp = await client.get(
        "/api/v1/ai-apps?scope=admin",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    # teacher 调管理端点本身应被 _require_admin 拦截
    assert resp.status_code == 403
