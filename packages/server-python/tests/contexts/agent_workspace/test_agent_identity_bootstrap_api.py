"""TD-114 bootstrap API 端点的真实 PostgreSQL contract tests。

契约验收归属（§10-A 组，API 侧）：

- A-1：未认证 401；请求体含任何字段（含 tenant_id）422；空体合法
- A-3：重复调用 200 幂等；响应恰两字段、禁带 launch 字段
- 409 identity_conflict 分支（预置冲突）
- disabled_existing 语义（200 + disabled_existing=true，不自动启用）
- tenant 仅从认证令牌派生

测试直验 HTTP 响应与数据库最终状态；真实 PostgreSQL；不 mock repository。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID
from tests.contexts.identity._helpers import register_and_login

pytestmark = pytest.mark.asyncio

_BOOTSTRAP_PATH = "/api/v1/agent-workspace/agent-identity/bootstrap"


async def _make_tenant_and_headers(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[uuid.UUID, dict[str, str]]:
    """建独立 tenant + 用户并登录；返回 (tenant_id, headers)。"""
    tenant_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :school, 'shared', true, :now, :now)"
        ),
        {"id": tenant_id, "name": f"td114-{tenant_id.hex[:8]}", "school": "TD-114", "now": now},
    )
    await db_session.commit()
    token = await register_and_login(
        client,
        username=f"td114_{uuid.uuid4().hex[:12]}",
        role="teacher",
        tenant_id=str(tenant_id),
    )
    return tenant_id, {"Authorization": f"Bearer {token}"}


async def _cleanup_tenant(db_session: AsyncSession, tenant_id: uuid.UUID) -> None:
    for statement in (
        "DELETE FROM metaedu.users WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_runtime_profiles WHERE tenant_id = :tid",
        "DELETE FROM metaedu.agent_definition_versions WHERE tenant_id = :tid",
        "DELETE FROM metaedu.tenants WHERE id = :tid",
    ):
        await db_session.execute(text(statement), {"tid": tenant_id})
    await db_session.commit()


async def _identity_counts(db_session: AsyncSession, tenant_id: uuid.UUID) -> tuple[int, int]:
    definitions = (
        await db_session.execute(
            text("SELECT count(*) FROM metaedu.agent_definition_versions WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
    ).scalar_one()
    profiles = (
        await db_session.execute(
            text("SELECT count(*) FROM metaedu.agent_runtime_profiles WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
    ).scalar_one()
    return definitions, profiles


async def test_bootstrap_requires_auth(client: AsyncClient):
    resp = await client.post(_BOOTSTRAP_PATH)
    # HTTPBearer 缺凭证在本仓 FastAPI 版本下返回 401 或 403（与既有 submit 测试同口径）
    assert resp.status_code in (401, 403)


async def test_bootstrap_rejects_any_body_field(client: AsyncClient, db_session):
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        # 含 tenant_id 字段 → 422（不信任客户端传入的 tenant）
        resp = await client.post(
            _BOOTSTRAP_PATH, headers=headers, json={"tenant_id": str(uuid.uuid4())}
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "validation_error"
        # 任意其他字段 → 422
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers, json={"force": True})
        assert resp.status_code == 422
        # 零写入
        assert await _identity_counts(db_session, tenant_id) == (0, 0)
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_bootstrap_happy_path_and_idempotent_replay(client: AsyncClient, db_session):
    """A-3 API 侧：首次 200 创建；重复 200 幂等零新增；响应恰两字段。"""
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body.keys()) == {"initialized", "disabled_existing"}
        assert body == {"initialized": True, "disabled_existing": False}
        assert await _identity_counts(db_session, tenant_id) == (1, 1)

        # 空 JSON 体 {} 也合法（无字段）
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers, json={})
        assert resp.status_code == 200
        assert resp.json() == {"initialized": True, "disabled_existing": False}
        assert await _identity_counts(db_session, tenant_id) == (1, 1)

        # 响应不携带任何 server-selected launch 字段
        for forbidden in (
            "runtime_profile_id",
            "capability_digest",
            "config_digest",
            "budget",
            "definition_id",
            "created",
        ):
            assert forbidden not in body
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_bootstrap_conflict_returns_409_without_writes(client: AsyncClient, db_session):
    """409 identity_conflict：预置 digest 漂移的 definition → 409，零写入。"""
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        await db_session.execute(
            text(
                "INSERT INTO metaedu.agent_definition_versions "
                "(id, tenant_id, definition_key, version, status, "
                " definition_digest, created_by, created_at) "
                "VALUES (:id, :tid, 'system.direct_rag', 1, 'published', "
                "        :digest, :actor, now())"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "digest": "f" * 64,
                "actor": DEFAULT_ADMIN_ID,
            },
        )
        await db_session.commit()

        resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "identity_conflict"
        # 409 分支零写入：profile 未被创建
        assert await _identity_counts(db_session, tenant_id) == (1, 0)
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_bootstrap_reports_disabled_without_reenabling(client: AsyncClient, db_session):
    """disabled profile：200 + disabled_existing=true；enabled 保持 false。"""
    tenant_id, headers = await _make_tenant_and_headers(client, db_session)
    try:
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
        assert resp.status_code == 200
        await db_session.execute(
            text(
                "UPDATE metaedu.agent_runtime_profiles SET enabled = false WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
        await db_session.commit()

        resp = await client.post(_BOOTSTRAP_PATH, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"initialized": True, "disabled_existing": True}
        enabled = (
            await db_session.execute(
                text("SELECT enabled FROM metaedu.agent_runtime_profiles WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        ).scalar_one()
        assert enabled is False
    finally:
        await _cleanup_tenant(db_session, tenant_id)


async def test_bootstrap_writes_only_token_tenant(client: AsyncClient, db_session):
    """tenant 仅从令牌派生：tenant A 的调用不写 tenant B。"""
    tenant_a, headers_a = await _make_tenant_and_headers(client, db_session)
    tenant_b, _headers_b = await _make_tenant_and_headers(client, db_session)
    try:
        resp = await client.post(_BOOTSTRAP_PATH, headers=headers_a)
        assert resp.status_code == 200
        assert await _identity_counts(db_session, tenant_a) == (1, 1)
        assert await _identity_counts(db_session, tenant_b) == (0, 0)
    finally:
        await _cleanup_tenant(db_session, tenant_a)
        await _cleanup_tenant(db_session, tenant_b)
