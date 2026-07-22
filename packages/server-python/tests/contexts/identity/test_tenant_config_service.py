"""REQ-058 Slice 1: tenant_scoped_config service 测试（AC-4/AC-6）。

tenant_scoped_config 表按 (tenant_id, config_key) 存储 Internal MCP / DD Catalog /
Skill binding 等 tenant 级配置；跨 tenant 隔离。
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.contexts.identity.application.tenant_config_service import (
    TenantConfigNotFoundError,
    TenantConfigService,
)
from app.shared.infrastructure.seed import DEFAULT_TENANT_ID

OTHER_TENANT = uuid.uuid4()

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test",
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _ensure_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import text
    result = await session.execute(
        text("SELECT id FROM metaedu.tenants WHERE id = :id"),
        {"id": str(tenant_id)},
    )
    if result.scalar_one_or_none():
        return
    now = datetime.now(UTC).replace(tzinfo=None)
    await session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :school_name, :isolation, true, :now, :now)"
        ),
        {
            "id": str(tenant_id),
            "name": f"t-{tenant_id.hex[:6]}",
            "school_name": "test",
            "isolation": "shared",
            "now": now,
        },
    )
    await session.commit()


@pytest.mark.asyncio
async def test_set_and_get_config(session: AsyncSession):
    """set_config 后 get_config 返回相同 value。"""
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    svc = TenantConfigService(session)
    await svc.set_config(
        DEFAULT_TENANT_ID, "internal_mcp_binding",
        {"server_id": "srv-001"}, updated_by=uuid.uuid4(),
    )
    val = await svc.get_config(DEFAULT_TENANT_ID, "internal_mcp_binding")
    assert val == {"server_id": "srv-001"}


@pytest.mark.asyncio
async def test_get_config_missing_raises(session: AsyncSession):
    """未配置 key -> TenantConfigNotFoundError（fail-closed）。"""
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    svc = TenantConfigService(session)
    with pytest.raises(TenantConfigNotFoundError):
        await svc.get_config(DEFAULT_TENANT_ID, "nonexistent_key")


@pytest.mark.asyncio
async def test_config_is_tenant_scoped(session: AsyncSession):
    """AC-4: tenant A 的配置对 tenant B 不可见。"""
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    await _ensure_tenant(session, OTHER_TENANT)
    svc = TenantConfigService(session)
    await svc.set_config(
        DEFAULT_TENANT_ID, "dd_catalog_binding",
        {"catalog_id": "cat-A"}, updated_by=uuid.uuid4(),
    )
    await svc.set_config(
        OTHER_TENANT, "dd_catalog_binding",
        {"catalog_id": "cat-B"}, updated_by=uuid.uuid4(),
    )
    a = await svc.get_config(DEFAULT_TENANT_ID, "dd_catalog_binding")
    b = await svc.get_config(OTHER_TENANT, "dd_catalog_binding")
    assert a["catalog_id"] == "cat-A"
    assert b["catalog_id"] == "cat-B"


@pytest.mark.asyncio
async def test_set_config_overwrites(session: AsyncSession):
    """同 key 重复 set 覆盖旧值（UPSERT）。"""
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    svc = TenantConfigService(session)
    uid = uuid.uuid4()
    await svc.set_config(DEFAULT_TENANT_ID, "skill_bindings", ["s1"], updated_by=uid)
    await svc.set_config(DEFAULT_TENANT_ID, "skill_bindings", ["s1", "s2"], updated_by=uid)
    val = await svc.get_config(DEFAULT_TENANT_ID, "skill_bindings")
    assert val == ["s1", "s2"]


@pytest.mark.asyncio
async def test_list_configs(session: AsyncSession):
    """list_configs 返回该 tenant 全部配置（不含其他 tenant）。"""
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    await _ensure_tenant(session, OTHER_TENANT)
    svc = TenantConfigService(session)
    await svc.set_config(DEFAULT_TENANT_ID, "k1", {"v": 1}, updated_by=uuid.uuid4())
    await svc.set_config(DEFAULT_TENANT_ID, "k2", {"v": 2}, updated_by=uuid.uuid4())
    await svc.set_config(OTHER_TENANT, "k3", {"v": 3}, updated_by=uuid.uuid4())
    configs = await svc.list_configs(DEFAULT_TENANT_ID)
    keys = {c["config_key"] for c in configs}
    assert keys == {"k1", "k2"}
    assert "k3" not in keys


@pytest.mark.asyncio
async def test_get_config_with_fallback(session: AsyncSession):
    """未配置时返回 fallback 值（供 settings 兜底场景）。"""
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    svc = TenantConfigService(session)
    val = await svc.get_config_or(
        DEFAULT_TENANT_ID, "missing_key", default={"fallback": True},
    )
    assert val == {"fallback": True}
    # 配置后返回真实值
    await svc.set_config(
        DEFAULT_TENANT_ID, "missing_key", {"real": True}, updated_by=uuid.uuid4(),
    )
    val2 = await svc.get_config_or(
        DEFAULT_TENANT_ID, "missing_key", default={"fallback": True},
    )
    assert val2 == {"real": True}
