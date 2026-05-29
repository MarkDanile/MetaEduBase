from abc import ABC, abstractmethod
from uuid import UUID

from app.contexts.template.domain.entity import Template


class TemplateRepository(ABC):
    @abstractmethod
    async def list(self, tenant_id: UUID) -> list[Template]: ...

    @abstractmethod
    async def get(self, template_id: UUID, tenant_id: UUID) -> Template | None: ...

    @abstractmethod
    async def get_by_doc_type(self, doc_type: str, tenant_id: UUID) -> Template | None: ...

    @abstractmethod
    async def create(self, template: Template) -> Template: ...

    @abstractmethod
    async def update(self, template: Template) -> Template: ...

    @abstractmethod
    async def delete(self, template_id: UUID, tenant_id: UUID) -> None: ...
