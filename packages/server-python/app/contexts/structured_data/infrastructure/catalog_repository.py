"""Catalog repository: CRUD + tenant 隔离 + entity_types 白名单.

REQ-054 Task 2: every query is scoped by ``tenant_id`` so that one tenant
cannot read or mutate another tenant's catalogs. Soft delete
(``is_active = False``) is the default delete path; hard delete is gated by
``count_datasets`` so a catalog with live datasets can't be silently dropped.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.domain.catalog import Catalog
from app.contexts.structured_data.infrastructure.catalog_models import CatalogModel
from app.contexts.structured_data.infrastructure.models import DatasetModel


class CatalogRepository:
    """Async CRUD repository over ``metaedu.data_catalogs``."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, catalog: Catalog) -> Catalog:
        row = CatalogModel(
            id=catalog.id,
            tenant_id=catalog.tenant_id,
            code=catalog.code,
            name=catalog.name,
            description=catalog.description,
            icon=catalog.icon,
            color=catalog.color,
            entity_types=catalog.entity_types,
            default_business_purpose=catalog.default_business_purpose,
            is_active=catalog.is_active,
            created_by=catalog.created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_domain(row)

    async def get_by_id(
        self, catalog_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Catalog | None:
        stmt = select(CatalogModel).where(
            CatalogModel.id == catalog_id,
            CatalogModel.tenant_id == tenant_id,
            CatalogModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_by_code(
        self, tenant_id: uuid.UUID, code: str
    ) -> Catalog | None:
        stmt = select(CatalogModel).where(
            CatalogModel.tenant_id == tenant_id,
            CatalogModel.code == code,
            CatalogModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[Catalog]:
        stmt = (
            select(CatalogModel)
            .where(
                CatalogModel.tenant_id == tenant_id,
                CatalogModel.is_active == True,  # noqa: E712
            )
            .order_by(CatalogModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def update(
        self,
        catalog_id: uuid.UUID,
        tenant_id: uuid.UUID,
        **kwargs: object,
    ) -> Catalog | None:
        stmt = select(CatalogModel).where(
            CatalogModel.id == catalog_id,
            CatalogModel.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return None
        for key, val in kwargs.items():
            if val is not None and hasattr(row, key):
                setattr(row, key, val)
        await self._session.flush()
        return self._to_domain(row)

    async def soft_delete(
        self, catalog_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> bool:
        stmt = select(CatalogModel).where(
            CatalogModel.id == catalog_id,
            CatalogModel.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return False
        row.is_active = False
        await self._session.flush()
        return True

    async def count_datasets(self, catalog_id: uuid.UUID) -> int:
        """Return the number of datasets linked to this catalog.

        Used by :class:`CatalogService.delete` as the hard-delete guard so
        we never orphan ``datasets.catalog_id`` (FK is ``ON DELETE RESTRICT``
        in migration 017). Cross-tenant safety is not needed here because
        ``catalog_id`` is globally unique.
        """
        stmt = select(func.count()).select_from(DatasetModel).where(
            DatasetModel.catalog_id == catalog_id
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    def _to_domain(self, row: CatalogModel) -> Catalog:
        return Catalog(
            id=row.id,
            tenant_id=row.tenant_id,
            code=row.code,
            name=row.name,
            description=row.description,
            icon=row.icon,
            color=row.color,
            entity_types=row.entity_types or [],
            default_business_purpose=row.default_business_purpose,
            is_active=row.is_active,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
