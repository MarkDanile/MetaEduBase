"""REQ-058 Slice 1b: Internal MCP / DD Catalog tenant-scoped 读取。

- `_resolve_internal_mcp_tenant(caller_tenant_id, config_service)`:
  优先读 tenant_scoped_config.internal_mcp_binding；未配置 fallback settings。
- `_resolve_dd_catalog_id(caller_tenant_id, config_service)`: 同理读 dd_catalog_binding。

settings 作开发 fallback（spec D-4）。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.contexts.identity.application.tenant_config_service import TenantConfigService
from app.shared.infrastructure.seed import DEFAULT_TENANT_ID

OTHER_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000099")


_TEST_DB_URL = (
    "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"
)


@pytest.fixture
async def session():
    engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _ensure_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    from sqlalchemy import text
    result = await session.execute(
        text("SELECT id FROM metaedu.tenants WHERE id = :id"), {"id": str(tenant_id)},
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


def _fallback_internal_tenant() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-0000000000bb")


def _fallback_catalog_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-0000000000cc")


@pytest.mark.asyncio
async def test_internal_mcp_uses_db_binding_when_set(session: AsyncSession):
    """AC-4: tenant_scoped_config.internal_mcp_binding 优先于 settings fallback。"""
    from app.contexts.identity.infrastructure import mcp_binding_resolver

    bound = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    svc = TenantConfigService(session)
    await svc.set_config(
        DEFAULT_TENANT_ID, "internal_mcp_binding",
        {"tenant_id": str(bound)}, updated_by=uuid.uuid4(),
    )
    result = await mcp_binding_resolver.resolve_internal_mcp_tenant(
        caller_tenant_id=DEFAULT_TENANT_ID, config_service=svc,
    )
    assert result == bound


@pytest.mark.asyncio
async def test_internal_mcp_falls_back_when_no_db_config(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """未配置 DB 时 fallback settings。"""
    from app.contexts.identity.infrastructure import mcp_binding_resolver
    fallback = _fallback_internal_tenant()
    monkeypatch.setattr(
        mcp_binding_resolver.settings, "internal_mcp_tenant_id", str(fallback),
    )
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    svc = TenantConfigService(session)
    result = await mcp_binding_resolver.resolve_internal_mcp_tenant(
        caller_tenant_id=DEFAULT_TENANT_ID, config_service=svc,
    )
    assert result == fallback


@pytest.mark.asyncio
async def test_dd_catalog_falls_back_when_no_db_config(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    from app.contexts.identity.infrastructure import mcp_binding_resolver
    fallback = _fallback_catalog_id()
    monkeypatch.setattr(
        mcp_binding_resolver.settings, "dd_internal_query_catalog_id", str(fallback),
    )
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    svc = TenantConfigService(session)
    result = await mcp_binding_resolver.resolve_dd_catalog_id(
        caller_tenant_id=DEFAULT_TENANT_ID, config_service=svc,
    )
    assert result == fallback


@pytest.mark.asyncio
async def test_internal_mcp_per_caller_tenant_isolation(session: AsyncSession):
    """AC-4: 不同 caller tenant 解析不同 binding，互不串。"""
    from app.contexts.identity.infrastructure import mcp_binding_resolver

    tenant_a = DEFAULT_TENANT_ID
    tenant_b = OTHER_TENANT
    bind_a = uuid.UUID("00000000-0000-0000-0000-00000000aaaa")
    bind_b = uuid.UUID("00000000-0000-0000-0000-00000000bbbb")
    await _ensure_tenant(session, tenant_a)
    await _ensure_tenant(session, tenant_b)
    svc = TenantConfigService(session)
    await svc.set_config(tenant_a, "internal_mcp_binding",
                          {"tenant_id": str(bind_a)}, updated_by=uuid.uuid4())
    await svc.set_config(tenant_b, "internal_mcp_binding",
                          {"tenant_id": str(bind_b)}, updated_by=uuid.uuid4())
    a = await mcp_binding_resolver.resolve_internal_mcp_tenant(
        caller_tenant_id=tenant_a, config_service=svc,
    )
    b = await mcp_binding_resolver.resolve_internal_mcp_tenant(
        caller_tenant_id=tenant_b, config_service=svc,
    )
    assert a == bind_a
    assert b == bind_b


@pytest.mark.asyncio
async def test_dd_catalog_uses_db_binding_when_set(session: AsyncSession):
    """DD Catalog 同理：dd_catalog_binding 优先于 settings。"""
    from app.contexts.identity.infrastructure import mcp_binding_resolver

    bound = uuid.UUID("00000000-0000-0000-0000-0000000000cc")
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    svc = TenantConfigService(session)
    await svc.set_config(
        DEFAULT_TENANT_ID, "dd_catalog_binding",
        {"catalog_id": str(bound)}, updated_by=uuid.uuid4(),
    )
    result = await mcp_binding_resolver.resolve_dd_catalog_id(
        caller_tenant_id=DEFAULT_TENANT_ID, config_service=svc,
    )
    assert result == bound

