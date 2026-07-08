"""Test CatalogService: 5-role RBAC matrix + code 冲突 + entity_types 白名单.

REQ-054 Task 2: the service is the RBAC enforcement point — only
``admin`` / ``data_admin`` / ``super_admin`` may write. The 5 roles from
REQ-052 (employee / manager / leader / data_admin / auditor) are exercised
plus ``super_admin`` (the seeded dev admin's role).

Fixture: ``db_session`` yields an ``AsyncSession`` against the test DB.
uuid-suffixed ``code`` values keep tests order-independent and re-runnable.
"""

from __future__ import annotations

import uuid

import pytest

from app.contexts.structured_data.application.catalog_service import (
    CATALOG_ADMIN_ROLES,
    CatalogCodeConflictError,
    CatalogPermissionError,
    CatalogService,
)
from app.contexts.structured_data.domain.catalog import Catalog
from app.contexts.structured_data.infrastructure.catalog_repository import (
    CatalogRepository,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio


def _unique_code(prefix: str = "s") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _make_catalog_via_service(
    service: CatalogService,
    *,
    code: str,
    role: str = "super_admin",
    entity_types: list[str] | None = None,
) -> Catalog:
    return await service.create(
        tenant_id=DEFAULT_TENANT_ID,
        code=code,
        name=f"数据库-{code}",
        entity_types=entity_types or ["bill"],
        created_by=DEFAULT_ADMIN_ID,
        role=role,
    )


# ---------------------------------------------------------------------------
# RBAC 5-role matrix: who can create catalogs
# ---------------------------------------------------------------------------


async def test_super_admin_can_create(db_session):
    """super_admin（seeded dev admin 角色）→ 可创建。"""
    service = CatalogService(db_session)
    catalog = await _make_catalog_via_service(service, code=_unique_code("sa"))
    assert catalog.is_active is True


async def test_data_admin_can_create(db_session):
    """data_admin → 可创建（在 CATALOG_ADMIN_ROLES 内）。"""
    service = CatalogService(db_session)
    catalog = await _make_catalog_via_service(
        service, code=_unique_code("da"), role="data_admin"
    )
    assert catalog.is_active is True


async def test_admin_can_create(db_session):
    """admin → 可创建（在 CATALOG_ADMIN_ROLES 内）。"""
    service = CatalogService(db_session)
    catalog = await _make_catalog_via_service(
        service, code=_unique_code("adm"), role="admin"
    )
    assert catalog.is_active is True


async def test_employee_cannot_create(db_session):
    """employee → CatalogPermissionError（不在 admin 集合内）。"""
    service = CatalogService(db_session)
    with pytest.raises(CatalogPermissionError):
        await _make_catalog_via_service(
            service, code=_unique_code("emp"), role="employee"
        )


async def test_manager_cannot_create(db_session):
    """manager → CatalogPermissionError。"""
    service = CatalogService(db_session)
    with pytest.raises(CatalogPermissionError):
        await _make_catalog_via_service(
            service, code=_unique_code("mgr"), role="manager"
        )


async def test_leader_cannot_create(db_session):
    """leader → CatalogPermissionError。"""
    service = CatalogService(db_session)
    with pytest.raises(CatalogPermissionError):
        await _make_catalog_via_service(
            service, code=_unique_code("ldr"), role="leader"
        )


async def test_auditor_cannot_create(db_session):
    """auditor → CatalogPermissionError。"""
    service = CatalogService(db_session)
    with pytest.raises(CatalogPermissionError):
        await _make_catalog_via_service(
            service, code=_unique_code("aud"), role="auditor"
        )


async def test_catalog_admin_roles_constant():
    """CATALOG_ADMIN_ROLES 包含 admin / data_admin / super_admin，不含其他 4 角色。"""
    expected_admin_roles = {"admin", "data_admin", "super_admin"}
    assert CATALOG_ADMIN_ROLES == expected_admin_roles  # noqa: SIM300
    # REQ-052 的 5 角色中，只有 data_admin 在 admin 集合内
    req052_roles = {"employee", "manager", "leader", "data_admin", "auditor"}
    assert req052_roles & CATALOG_ADMIN_ROLES == {"data_admin"}


# ---------------------------------------------------------------------------
# Code 冲突
# ---------------------------------------------------------------------------


async def test_create_code_conflict_raises_typed_error(db_session):
    """同 tenant 内 code 重复 → CatalogCodeConflictError（不是 DB IntegrityError）。"""
    service = CatalogService(db_session)
    code = _unique_code("cfl")
    await _make_catalog_via_service(service, code=code)
    with pytest.raises(CatalogCodeConflictError):
        await _make_catalog_via_service(service, code=code)


async def test_same_code_different_tenants_no_conflict(db_session):
    """不同 tenant 可以有相同 code（tenant 隔离）。"""
    service = CatalogService(db_session)
    other_tenant = uuid.uuid4()
    code = _unique_code("shc")
    # tenant A 创建
    await service.create(
        tenant_id=DEFAULT_TENANT_ID,
        code=code,
        name="租户A的库",
        entity_types=["bill"],
        created_by=DEFAULT_ADMIN_ID,
        role="super_admin",
    )
    # tenant B 用同样的 code 创建 — 不应报冲突
    catalog_b = await service.create(
        tenant_id=other_tenant,
        code=code,
        name="租户B的库",
        entity_types=["bill"],
        created_by=DEFAULT_ADMIN_ID,
        role="super_admin",
    )
    assert catalog_b.code == code
    assert catalog_b.tenant_id == other_tenant


# ---------------------------------------------------------------------------
# update / delete RBAC
# ---------------------------------------------------------------------------


async def test_update_rbac_blocks_non_admin(db_session):
    """employee 调用 update → CatalogPermissionError。"""
    service = CatalogService(db_session)
    catalog = await _make_catalog_via_service(service, code=_unique_code("urb"))
    with pytest.raises(CatalogPermissionError):
        await service.update(
            catalog_id=catalog.id,
            tenant_id=DEFAULT_TENANT_ID,
            role="employee",
            name="employee 试图改名",
        )


async def test_update_allows_admin(db_session):
    """data_admin 调用 update → 成功。"""
    service = CatalogService(db_session)
    catalog = await _make_catalog_via_service(service, code=_unique_code("uad"))
    updated = await service.update(
        catalog_id=catalog.id,
        tenant_id=DEFAULT_TENANT_ID,
        role="data_admin",
        name="data_admin 改的名",
    )
    assert updated is not None
    assert updated.name == "data_admin 改的名"


async def test_delete_rbac_blocks_non_admin(db_session):
    """manager 调用 delete → CatalogPermissionError。"""
    service = CatalogService(db_session)
    catalog = await _make_catalog_via_service(service, code=_unique_code("drb"))
    with pytest.raises(CatalogPermissionError):
        await service.delete(
            catalog_id=catalog.id,
            tenant_id=DEFAULT_TENANT_ID,
            role="manager",
        )


async def test_delete_soft_deletes_by_default(db_session):
    """delete(hard=False) → is_active=False（soft delete）。"""
    service = CatalogService(db_session)
    catalog = await _make_catalog_via_service(service, code=_unique_code("dsf"))
    ok = await service.delete(
        catalog_id=catalog.id,
        tenant_id=DEFAULT_TENANT_ID,
        role="super_admin",
    )
    assert ok is True
    # 软删后 get_by_id 返回 None
    fetched = await service.get_by_id(catalog.id, DEFAULT_TENANT_ID)
    assert fetched is None


async def test_delete_hard_with_datasets_raises(db_session, sample_dataset):
    """delete(hard=True) on catalog with datasets → ValueError（不删）。"""
    service = CatalogService(db_session)
    repo = CatalogRepository(db_session)
    # sample_dataset 的 catalog 是 education
    education = await repo.get_by_code(DEFAULT_TENANT_ID, "education")
    assert education is not None
    with pytest.raises(ValueError, match="数据集"):
        await service.delete(
            catalog_id=education.id,
            tenant_id=DEFAULT_TENANT_ID,
            role="super_admin",
            hard=True,
        )
    # 验证 catalog 仍然 active（guard 在删之前就 raise）
    still_active = await repo.get_by_id(education.id, DEFAULT_TENANT_ID)
    assert still_active is not None
    assert still_active.is_active is True


async def test_delete_hard_on_empty_catalog_succeeds(db_session):
    """delete(hard=True) on catalog with no datasets → soft delete 成功。"""
    service = CatalogService(db_session)
    catalog = await _make_catalog_via_service(service, code=_unique_code("dhe"))
    ok = await service.delete(
        catalog_id=catalog.id,
        tenant_id=DEFAULT_TENANT_ID,
        role="super_admin",
        hard=True,
    )
    assert ok is True
    fetched = await service.get_by_id(catalog.id, DEFAULT_TENANT_ID)
    assert fetched is None


async def test_delete_unknown_id_returns_false(db_session):
    """delete 不存在的 catalog_id → False（不抛）。"""
    service = CatalogService(db_session)
    ok = await service.delete(
        catalog_id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        role="super_admin",
    )
    assert ok is False


# ---------------------------------------------------------------------------
# entity_types 白名单校验
# ---------------------------------------------------------------------------


async def test_validate_entity_type_accepts_whitelisted(db_session):
    """entity_type 在白名单内 → 不抛异常。"""
    service = CatalogService(db_session)
    catalog = await _make_catalog_via_service(
        service, code=_unique_code("wok"), entity_types=["bill", "contract"]
    )
    # 不抛异常即通过
    await service.validate_entity_type(catalog.id, DEFAULT_TENANT_ID, "bill")
    await service.validate_entity_type(catalog.id, DEFAULT_TENANT_ID, "contract")


async def test_validate_entity_type_rejects_non_whitelisted(db_session):
    """entity_type 不在白名单内 → ValueError（带支持列表提示）。"""
    service = CatalogService(db_session)
    catalog = await _make_catalog_via_service(
        service, code=_unique_code("wrj"), entity_types=["bill", "contract"]
    )
    with pytest.raises(ValueError, match="白名单"):
        await service.validate_entity_type(
            catalog.id, DEFAULT_TENANT_ID, "payment"
        )


async def test_validate_entity_type_unknown_catalog(db_session):
    """validate_entity_type 不存在的 catalog_id → ValueError。"""
    service = CatalogService(db_session)
    with pytest.raises(ValueError, match="不存在"):
        await service.validate_entity_type(
            uuid.uuid4(), DEFAULT_TENANT_ID, "bill"
        )


async def test_validate_entity_type_cross_tenant_catalog(db_session):
    """validate_entity_type 跨 tenant 访问 → 视为不存在（tenant 隔离）。"""
    service = CatalogService(db_session)
    other_tenant = uuid.uuid4()
    # 在 other_tenant 建 catalog
    other_catalog = await service.create(
        tenant_id=other_tenant,
        code=_unique_code("ctt"),
        name="他租户的库",
        entity_types=["bill"],
        created_by=DEFAULT_ADMIN_ID,
        role="super_admin",
    )
    # 用 DEFAULT_TENANT_ID 去查 other_tenant 的 catalog → 不存在
    with pytest.raises(ValueError, match="不存在"):
        await service.validate_entity_type(
            other_catalog.id, DEFAULT_TENANT_ID, "bill"
        )


# ---------------------------------------------------------------------------
# list / get 读路径不校验 RBAC（所有角色可读）
# ---------------------------------------------------------------------------


async def test_list_by_tenant_returns_all_active(db_session):
    """list_by_tenant 返回 tenant 下所有 active catalogs（含 seeded education）。"""
    service = CatalogService(db_session)
    code_a = _unique_code("lsv")
    code_b = _unique_code("lsv2")
    await _make_catalog_via_service(service, code=code_a)
    await _make_catalog_via_service(service, code=code_b)

    catalogs = await service.list_by_tenant(DEFAULT_TENANT_ID)
    codes = {c.code for c in catalogs}
    assert code_a in codes
    assert code_b in codes
    # education 是 alembic 018 seed 的，也应该在
    assert "education" in codes


async def test_get_by_code_returns_none_for_missing(db_session):
    """get_by_code 不存在的 code → None（不抛）。"""
    service = CatalogService(db_session)
    fetched = await service.get_by_code(DEFAULT_TENANT_ID, "no_such_code_xyz_999")
    assert fetched is None
