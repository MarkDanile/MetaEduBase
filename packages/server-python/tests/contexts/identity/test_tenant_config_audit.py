"""REQ-058 Slice 4: tenant_config_audit 配置变更审计（AC-6）。

``TenantConfigService.set_config`` 写独立 ``tenant_config_audit`` 表
（不依赖 dd_evidence，因 dd_evidence.report_id NOT NULL 约束）。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.contexts.identity.application.tenant_config_service import TenantConfigService
from app.shared.infrastructure.seed import DEFAULT_TENANT_ID

_TEST_DB_URL = (
    "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"
)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        # 清理 Slice 1/4 测试残留（test isolation）
        await s.execute(text("DELETE FROM metaedu.tenant_config_audit"))
        await s.execute(
            text("DELETE FROM metaedu.tenant_scoped_config"),
        )
        await s.commit()
        yield s
    await engine.dispose()


async def _ensure_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
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


@pytest.mark.asyncio
async def test_set_config_writes_audit_row(session: AsyncSession):
    """AC-6: set_config 写 tenant_config_audit 行（action=set）。"""
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    svc = TenantConfigService(session)
    operator = uuid.uuid4()
    await svc.set_config(
        DEFAULT_TENANT_ID, "internal_mcp_binding",
        {"server_id": "srv-001"}, updated_by=operator,
    )
    await session.commit()
    result = await session.execute(
        text(
            "SELECT action, config_key, operator FROM metaedu.tenant_config_audit "
            "WHERE tenant_id = :tid ORDER BY created_at DESC LIMIT 1"
        ),
        {"tid": str(DEFAULT_TENANT_ID)},
    )
    row = result.mappings().first()
    assert row is not None, "set_config 应写 audit row"
    assert row["action"] == "set"
    assert row["config_key"] == "internal_mcp_binding"
    assert row["operator"] == operator


@pytest.mark.asyncio
async def test_set_config_audit_records_new_value(session: AsyncSession):
    """审计行记录 new_value JSON。"""
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    svc = TenantConfigService(session)
    await svc.set_config(
        DEFAULT_TENANT_ID, "dd_catalog_binding",
        {"catalog_id": "cat-X"}, updated_by=uuid.uuid4(),
    )
    await session.commit()
    result = await session.execute(
        text(
            "SELECT new_value FROM metaedu.tenant_config_audit "
            "WHERE tenant_id = :tid AND config_key = 'dd_catalog_binding' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"tid": str(DEFAULT_TENANT_ID)},
    )
    row = result.mappings().first()
    assert row is not None
    assert row["new_value"]["catalog_id"] == "cat-X"


@pytest.mark.asyncio
async def test_upsert_writes_audit_each_time(session: AsyncSession):
    """每次 set_config（同 key 覆盖）都写新审计行。"""
    await _ensure_tenant(session, DEFAULT_TENANT_ID)
    svc = TenantConfigService(session)
    op = uuid.uuid4()
    await svc.set_config(
        DEFAULT_TENANT_ID, "skill_bindings", ["s1"], updated_by=op,
    )
    await session.commit()
    await svc.set_config(
        DEFAULT_TENANT_ID, "skill_bindings", ["s1", "s2"], updated_by=op,
    )
    await session.commit()
    result = await session.execute(
        text(
            "SELECT COUNT(*) AS n FROM metaedu.tenant_config_audit "
            "WHERE tenant_id = :tid AND config_key = 'skill_bindings'"
        ),
        {"tid": str(DEFAULT_TENANT_ID)},
    )
    n = result.scalar_one()
    assert n == 2, f"upsert 应每次都写审计行，got {n}"
