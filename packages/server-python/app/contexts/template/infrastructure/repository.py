from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.template.domain.entity import Template
from app.contexts.template.domain.repository import TemplateRepository
from app.contexts.template.infrastructure.models import TemplateModel


class TemplateRepositoryImpl(TemplateRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, tenant_id: UUID) -> list[Template]:
        stmt = select(TemplateModel).where(TemplateModel.tenant_id == tenant_id)
        rows = await self.session.execute(stmt)
        return [Template.from_db_row(r) for r in rows.scalars()]

    async def get(self, template_id: UUID, tenant_id: UUID) -> Template | None:
        stmt = select(TemplateModel).where(
            TemplateModel.id == template_id,
            TemplateModel.tenant_id == tenant_id,
        )
        row = await self.session.scalar(stmt)
        return Template.from_db_row(row) if row else None

    async def get_by_doc_type(self, doc_type: str, tenant_id: UUID) -> Template | None:
        stmt = select(TemplateModel).where(
            TemplateModel.tenant_id == tenant_id,
            TemplateModel.doc_types.contains([doc_type]),
        ).limit(1)
        row = await self.session.scalar(stmt)
        return Template.from_db_row(row) if row else None

    async def create(self, template: Template) -> Template:
        model = TemplateModel(
            id=template.id,
            tenant_id=template.tenant_id,
            name=template.name,
            doc_types=template.doc_types,
            fields=[f.to_dict() for f in template.fields],
            ai_prompt=template.ai_prompt,
            ai_context=template.ai_context,
            source_file_id=template.source_file_id,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )
        self.session.add(model)
        await self.session.flush()
        return template

    async def update(self, template: Template) -> Template:
        stmt = select(TemplateModel).where(
            TemplateModel.id == template.id,
            TemplateModel.tenant_id == template.tenant_id,
        )
        model = await self.session.scalar(stmt)
        if model:
            model.name = template.name
            model.doc_types = template.doc_types
            model.fields = [f.to_dict() for f in template.fields]
            model.ai_prompt = template.ai_prompt
            model.ai_context = template.ai_context
            model.source_file_id = template.source_file_id
            model.updated_at = template.updated_at
        await self.session.flush()
        return template

    async def delete(self, template_id: UUID, tenant_id: UUID) -> None:
        stmt = delete(TemplateModel).where(
            TemplateModel.id == template_id,
            TemplateModel.tenant_id == tenant_id,
        )
        await self.session.execute(stmt)
