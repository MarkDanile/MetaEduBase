from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.template.domain.template_version import TemplateVersion
from app.contexts.template.infrastructure.models import TemplateVersionModel


class TemplateVersionRepository:
    async def create(self, session: AsyncSession, version: TemplateVersion) -> TemplateVersion:
        raise NotImplementedError

    async def list(
        self,
        session: AsyncSession,
        template_id: UUID,
        tenant_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[TemplateVersion]:
        raise NotImplementedError

    async def get(
        self,
        session: AsyncSession,
        template_id: UUID,
        tenant_id: UUID,
        version_number: int,
    ) -> TemplateVersion | None:
        raise NotImplementedError

    async def max_version_number(self, session: AsyncSession, template_id: UUID) -> int:
        raise NotImplementedError


class TemplateVersionRepositoryImpl(TemplateVersionRepository):
    async def create(self, session: AsyncSession, version: TemplateVersion) -> TemplateVersion:
        model = TemplateVersionModel(
            id=version.id,
            template_id=version.template_id,
            tenant_id=version.tenant_id,
            version_number=version.version_number,
            name=version.name,
            doc_types=version.doc_types,
            fields=version.fields,
            ai_prompt=version.ai_prompt,
            ai_context=version.ai_context,
            schema_version=version.schema_version,
            snapshot_at=version.snapshot_at,
        )
        session.add(model)
        await session.flush()
        return version

    async def list(
        self,
        session: AsyncSession,
        template_id: UUID,
        tenant_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[TemplateVersion]:
        stmt = (
            select(TemplateVersionModel)
            .where(
                TemplateVersionModel.template_id == template_id,
                TemplateVersionModel.tenant_id == tenant_id,
            )
            .order_by(TemplateVersionModel.version_number.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = await session.execute(stmt)
        return [_to_entity(r) for r in rows.scalars()]

    async def get(
        self,
        session: AsyncSession,
        template_id: UUID,
        tenant_id: UUID,
        version_number: int,
    ) -> TemplateVersion | None:
        stmt = select(TemplateVersionModel).where(
            TemplateVersionModel.template_id == template_id,
            TemplateVersionModel.tenant_id == tenant_id,
            TemplateVersionModel.version_number == version_number,
        )
        row = await session.scalar(stmt)
        return _to_entity(row) if row else None

    async def max_version_number(self, session: AsyncSession, template_id: UUID) -> int:
        stmt = select(func.max(TemplateVersionModel.version_number)).where(
            TemplateVersionModel.template_id == template_id
        )
        result = await session.scalar(stmt)
        return result or 0


def _to_entity(row: TemplateVersionModel) -> TemplateVersion:
    return TemplateVersion(
        id=row.id,
        template_id=row.template_id,
        tenant_id=row.tenant_id,
        version_number=row.version_number,
        name=row.name,
        doc_types=list(row.doc_types or []),
        fields=list(row.fields or []),
        ai_prompt=row.ai_prompt,
        ai_context=row.ai_context,
        schema_version=row.schema_version,
        snapshot_at=row.snapshot_at,
    )
