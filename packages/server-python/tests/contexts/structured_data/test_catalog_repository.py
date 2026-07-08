"""Test CatalogRepository: CRUD + tenant 隔离 + count_datasets.

REQ-054 Task 2: each test exercises one repository method against the real
PG test DB. Tenant isolation is verified by creating catalogs in two
different tenants and confirming neither sees the other's rows.

The ``db_session`` fixture (from ``tests/contexts/structured_data/conftest.py``)
yields an ``AsyncSession`` against the test DB and commits on clean teardown.
We use uuid-suffixed ``code`` values so tests are order-independent and
re-runnable without colliding on the ``uq_data_catalogs_tenant_code`` unique
constraint.
"""

from __future__ import annotations

import uuid

import pytest

from app.contexts.structured_data.domain.catalog import Catalog
from app.contexts.structured_data.infrastructure.catalog_repository import (
    CatalogRepository,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio


def _unique_code(prefix: str = "t") -> str:
    """Generate a code that satisfies the ``^[a-z][a-z0-9_]*$`` pattern
    and is unique per call (uuid hex suffix)."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _make_catalog(
    *,
    code: str,
    tenant_id: uuid.UUID = DEFAULT_TENANT_ID,
    name: str = "测试数据库",
    entity_types: list[str] | None = None,
) -> Catalog:
    return Catalog(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code=code,
        name=name,
        entity_types=entity_types or ["bill"],
        created_by=DEFAULT_ADMIN_ID,
    )


async def test_create_and_get_by_id(db_session):
    """create 写入后 get_by_id 能读到，字段一一对应。"""
    repo = CatalogRepository(db_session)
    code = _unique_code("fin")
    catalog = _make_catalog(code=code, entity_types=["bill", "contract"])
    created = await repo.create(catalog)

    fetched = await repo.get_by_id(created.id, DEFAULT_TENANT_ID)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.code == code
    assert fetched.name == "测试数据库"
    assert fetched.entity_types == ["bill", "contract"]
    assert fetched.is_active is True
    assert fetched.tenant_id == DEFAULT_TENANT_ID


async def test_get_by_code(db_session):
    """get_by_code 按 (tenant_id, code) 唯一定位。"""
    repo = CatalogRepository(db_session)
    code = _unique_code("fac")
    await repo.create(_make_catalog(code=code))

    fetched = await repo.get_by_code(DEFAULT_TENANT_ID, code)
    assert fetched is not None
    assert fetched.code == code

    # 不存在的 code → None
    missing = await repo.get_by_code(DEFAULT_TENANT_ID, "nonexistent_code_xyz")
    assert missing is None


async def test_list_by_tenant_only_returns_active(db_session):
    """list_by_tenant 只返回该 tenant 的 active catalogs。"""
    repo = CatalogRepository(db_session)
    code_a = _unique_code("lia")
    code_b = _unique_code("lib")
    await repo.create(_make_catalog(code=code_a))
    await repo.create(_make_catalog(code=code_b))
    # 软删一条 — 不应出现在 list_by_tenant 结果里
    to_delete = await repo.create(_make_catalog(code=_unique_code("lid")))
    await repo.soft_delete(to_delete.id, DEFAULT_TENANT_ID)

    catalogs = await repo.list_by_tenant(DEFAULT_TENANT_ID)
    codes = {c.code for c in catalogs}
    assert code_a in codes
    assert code_b in codes
    assert to_delete.code not in codes


async def test_update_changes_fields(db_session):
    """update 修改 name / description，未传字段保持不变。"""
    repo = CatalogRepository(db_session)
    code = _unique_code("upd")
    created = await repo.create(
        _make_catalog(code=code, name="旧名称", entity_types=["bill"])
    )

    updated = await repo.update(
        created.id,
        DEFAULT_TENANT_ID,
        name="新名称",
        description="更新后的描述",
    )
    assert updated is not None
    assert updated.name == "新名称"
    assert updated.description == "更新后的描述"
    # 未传的字段保持不变
    assert updated.code == code
    assert updated.entity_types == ["bill"]


async def test_update_unknown_id_returns_none(db_session):
    """update 不存在的 catalog_id → None（不抛异常）。"""
    repo = CatalogRepository(db_session)
    result = await repo.update(
        uuid.uuid4(), DEFAULT_TENANT_ID, name="不存在"
    )
    assert result is None


async def test_soft_delete_hides_from_get_by_id(db_session):
    """soft_delete 后 get_by_id 返回 None（is_active=False 被过滤）。"""
    repo = CatalogRepository(db_session)
    code = _unique_code("sfd")
    created = await repo.create(_make_catalog(code=code))

    ok = await repo.soft_delete(created.id, DEFAULT_TENANT_ID)
    assert ok is True

    # get_by_id 只返回 is_active=True
    fetched = await repo.get_by_id(created.id, DEFAULT_TENANT_ID)
    assert fetched is None


async def test_soft_delete_unknown_id_returns_false(db_session):
    """soft_delete 不存在的 id → False。"""
    repo = CatalogRepository(db_session)
    ok = await repo.soft_delete(uuid.uuid4(), DEFAULT_TENANT_ID)
    assert ok is False


async def test_count_datasets_returns_zero_for_empty_catalog(db_session):
    """新建的 catalog 没有关联数据集 → count_datasets == 0。"""
    repo = CatalogRepository(db_session)
    created = await repo.create(_make_catalog(code=_unique_code("cnt")))
    count = await repo.count_datasets(created.id)
    assert count == 0


async def test_count_datasets_counts_linked_datasets(
    db_session, sample_dataset
):
    """sample_dataset 关联到 education catalog → count_datasets >= 1。"""
    repo = CatalogRepository(db_session)
    # sample_dataset 依赖的 catalog 是 education（conftest 里硬编码）
    education = await repo.get_by_code(DEFAULT_TENANT_ID, "education")
    assert education is not None
    count = await repo.count_datasets(education.id)
    assert count >= 1


async def test_tenant_isolation_catalogs_scoped_by_tenant(db_session):
    """tenant A 的 catalog 对 tenant B 不可见（get_by_id / get_by_code / list_by_tenant）。"""
    repo = CatalogRepository(db_session)
    other_tenant = uuid.uuid4()
    other_code = _unique_code("oth")
    # 在另一个 tenant 建 catalog
    other_catalog = await repo.create(
        _make_catalog(
            code=other_code,
            tenant_id=other_tenant,
            name="他租户数据库",
        )
    )

    # DEFAULT_TENANT_ID 看不到 other_tenant 的 catalog
    assert await repo.get_by_id(other_catalog.id, DEFAULT_TENANT_ID) is None
    assert await repo.get_by_code(DEFAULT_TENANT_ID, other_code) is None

    # other_tenant 也看不到 DEFAULT_TENANT_ID 的 education catalog
    assert await repo.get_by_code(other_tenant, "education") is None

    # list_by_tenant 只返回对应 tenant 的 catalogs
    other_catalogs = await repo.list_by_tenant(other_tenant)
    other_codes = {c.code for c in other_catalogs}
    assert other_code in other_codes
    assert "education" not in other_codes

    # soft_delete 也按 tenant 隔离 — DEFAULT_TENANT_ID 不能删 other_tenant 的 catalog
    ok = await repo.soft_delete(other_catalog.id, DEFAULT_TENANT_ID)
    assert ok is False
    # 确认 catalog 仍然 active
    still_active = await repo.get_by_id(other_catalog.id, other_tenant)
    assert still_active is not None
    assert still_active.is_active is True


async def test_to_domain_preserves_all_fields(db_session):
    """_to_domain 完整映射 ORM → domain dataclass。"""
    repo = CatalogRepository(db_session)
    code = _unique_code("fld")
    created = await repo.create(
        _make_catalog(
            code=code,
            name="字段完整性测试",
            entity_types=["bill", "contract", "customer"],
        )
    )
    # 直接从 DB 重新读，验证所有字段映射
    fetched = await repo.get_by_id(created.id, DEFAULT_TENANT_ID)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.tenant_id == DEFAULT_TENANT_ID
    assert fetched.code == code
    assert fetched.name == "字段完整性测试"
    assert fetched.entity_types == ["bill", "contract", "customer"]
    assert fetched.is_active is True
    assert fetched.created_by == DEFAULT_ADMIN_ID
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    # 未设置的 optional 字段
    assert fetched.description is None
    assert fetched.icon is None
    assert fetched.color is None
    assert fetched.default_business_purpose is None
