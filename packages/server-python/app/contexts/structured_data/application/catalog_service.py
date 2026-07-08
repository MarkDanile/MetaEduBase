"""Catalog service: CRUD 编排 + RBAC 权限门禁.

REQ-054 Task 2: sits between :mod:`catalog_router` and
:class:`CatalogRepository`. Enforces two cross-cutting concerns:

1. **RBAC** — only ``admin`` / ``data_admin`` / ``super_admin`` may create,
   update or delete catalogs. All roles may read. The seeded admin user has
   ``role='super_admin'`` (see ``app/shared/infrastructure/seed.py``), so
   ``super_admin`` is in the admin set even though REQ-052's 5-role enum
   doesn't list it.
2. **Code uniqueness** — ``(tenant_id, code)`` is unique in the DB, but the
   service surfaces a typed :class:`CatalogCodeConflictError` *before* the
   INSERT so the router can return 409 instead of leaking a DB IntegrityError.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.domain.catalog import Catalog
from app.contexts.structured_data.infrastructure.catalog_repository import (
    CatalogRepository,
)

# Roles that may create / modify / delete catalogs. ``super_admin`` is the
# seeded dev admin's role (see app/shared/infrastructure/seed.py) — it isn't
# in REQ-052's 5-role enum but must be allowed for bootstrapping.
CATALOG_ADMIN_ROLES = {"admin", "data_admin", "super_admin"}


class CatalogPermissionError(PermissionError):
    """用户无权操作 catalog."""


class CatalogCodeConflictError(ValueError):
    """同 tenant 内 catalog code 已存在."""


class CatalogService:
    """CRUD orchestration + RBAC for :class:`Catalog`."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = CatalogRepository(session)

    def _check_admin(self, role: str) -> None:
        if role not in CATALOG_ADMIN_ROLES:
            raise CatalogPermissionError(
                f"角色 '{role}' 无权操作数据库（仅 {sorted(CATALOG_ADMIN_ROLES)} 可操作）"
            )

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        code: str,
        name: str,
        entity_types: list[str],
        created_by: uuid.UUID,
        description: str | None = None,
        icon: str | None = None,
        color: str | None = None,
        default_business_purpose: str | None = None,
        role: str = "employee",
    ) -> Catalog:
        self._check_admin(role)
        # code 唯一性校验 — 提前于 INSERT，让 router 能返回 409
        existing = await self._repo.get_by_code(tenant_id, code)
        if existing:
            raise CatalogCodeConflictError(f"数据库 code '{code}' 已存在")
        catalog = Catalog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            code=code,
            name=name,
            entity_types=entity_types,
            description=description,
            icon=icon,
            color=color,
            default_business_purpose=default_business_purpose,
            created_by=created_by,
        )
        return await self._repo.create(catalog)

    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[Catalog]:
        return await self._repo.list_by_tenant(tenant_id)

    async def get_by_id(
        self, catalog_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Catalog | None:
        return await self._repo.get_by_id(catalog_id, tenant_id)

    async def get_by_code(
        self, tenant_id: uuid.UUID, code: str
    ) -> Catalog | None:
        return await self._repo.get_by_code(tenant_id, code)

    async def update(
        self,
        *,
        catalog_id: uuid.UUID,
        tenant_id: uuid.UUID,
        role: str = "employee",
        **kwargs: object,
    ) -> Catalog | None:
        self._check_admin(role)
        return await self._repo.update(catalog_id, tenant_id, **kwargs)

    async def delete(
        self,
        *,
        catalog_id: uuid.UUID,
        tenant_id: uuid.UUID,
        role: str = "employee",
        hard: bool = False,
    ) -> bool:
        """Delete a catalog.

        - ``hard=False`` (default): soft delete — sets ``is_active=False`` so
          the catalog disappears from listings but existing FK references
          stay valid.
        - ``hard=True``: also soft-deletes (does NOT row-delete) but first
          guards against orphaning datasets by checking
          :meth:`CatalogRepository.count_datasets`. A 409 is raised if any
          dataset still references the catalog. Hard row-delete is deferred
          to a future task; the guard is what matters for V1 safety.
        """
        self._check_admin(role)
        if hard:
            count = await self._repo.count_datasets(catalog_id)
            if count > 0:
                raise ValueError(f"数据库下还有 {count} 个数据集，无法硬删")
        return await self._repo.soft_delete(catalog_id, tenant_id)

    async def validate_entity_type(
        self, catalog_id: uuid.UUID, tenant_id: uuid.UUID, entity_type: str
    ) -> None:
        """白名单校验：entity_type 必须在 catalog.entity_types 内.

        REQ-054 Task 3 will call this when binding a dataset to a catalog.
        Raises ``ValueError`` if the catalog is missing or the entity_type
        isn't whitelisted.
        """
        catalog = await self._repo.get_by_id(catalog_id, tenant_id)
        if not catalog:
            raise ValueError(f"数据库 {catalog_id} 不存在")
        if not catalog.allows_entity_type(entity_type):
            raise ValueError(
                f"entity_type '{entity_type}' 不在数据库 '{catalog.name}' 的白名单内"
                f"（支持: {catalog.entity_types}）"
            )
