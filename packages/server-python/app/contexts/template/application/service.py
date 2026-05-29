from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.contexts.template.application.dto import FieldDTO, TemplateCreate, TemplateUpdate
from app.contexts.template.domain.entity import Field, TableColumn, Template
from app.contexts.template.domain.repository import TemplateRepository


def _dto_to_entity(dto: FieldDTO) -> Field:
    return Field(
        key=dto.key,
        label=dto.label,
        type=dto.type,
        description=dto.description,
        children=[_dto_to_entity(c) for c in dto.children],
        columns=[TableColumn(**c.model_dump()) for c in dto.columns],
        items=[_dto_to_entity(i) for i in dto.items],
    )

def _entity_to_dto(entity: Template) -> dict:
    return {
        "id": str(entity.id),
        "tenant_id": str(entity.tenant_id),
        "name": entity.name,
        "doc_types": entity.doc_types,
        "fields": [f.to_dict() for f in entity.fields],
        "ai_prompt": entity.ai_prompt,
        "source_file_id": str(entity.source_file_id) if entity.source_file_id else None,
        "created_at": entity.created_at.isoformat(),
        "updated_at": entity.updated_at.isoformat(),
    }

class TemplateService:
    def __init__(self, repo: TemplateRepository):
        self.repo = repo

    async def list(self, tenant_id: UUID) -> list[dict]:
        templates = await self.repo.list(tenant_id)
        return [_entity_to_dto(t) for t in templates]

    async def get(self, template_id: UUID, tenant_id: UUID) -> dict | None:
        template = await self.repo.get(template_id, tenant_id)
        return _entity_to_dto(template) if template else None

    async def create(self, dto: TemplateCreate, tenant_id: UUID) -> dict:
        template = Template(
            id=uuid4(),
            tenant_id=tenant_id,
            name=dto.name,
            doc_types=dto.doc_types,
            fields=[_dto_to_entity(f) for f in dto.fields],
            ai_prompt=dto.ai_prompt,
            source_file_id=UUID(dto.source_file_id) if dto.source_file_id else None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await self.repo.create(template)
        return _entity_to_dto(template)

    async def update(self, template_id: UUID, dto: TemplateUpdate, tenant_id: UUID) -> dict | None:
        existing = await self.repo.get(template_id, tenant_id)
        if not existing:
            return None
        if dto.name is not None:
            existing.name = dto.name
        if dto.doc_types is not None:
            existing.doc_types = dto.doc_types
        if dto.fields is not None:
            existing.fields = [_dto_to_entity(f) for f in dto.fields]
        if dto.ai_prompt is not None:
            existing.ai_prompt = dto.ai_prompt
        if dto.source_file_id is not None:
            existing.source_file_id = UUID(dto.source_file_id)
        existing.updated_at = datetime.now(UTC)
        await self.repo.update(existing)
        return _entity_to_dto(existing)

    async def delete(self, template_id: UUID, tenant_id: UUID) -> None:
        await self.repo.delete(template_id, tenant_id)
