from abc import abstractmethod
from typing import Any

from app.contexts.knowledge.domain.entities.knowledge_node import KnowledgeNode
from app.shared.domain.repository import Repository


class KnowledgeNodeRepository(Repository[KnowledgeNode]):
    @abstractmethod
    async def get_by_path(self, path: str) -> KnowledgeNode | None: ...

    @abstractmethod
    async def get_children(self, parent_id: Any) -> list[KnowledgeNode]: ...

    @abstractmethod
    async def get_by_domain(self, domain: str, *, offset: int = 0, limit: int = 50) -> list[KnowledgeNode]: ...

    @abstractmethod
    async def search_semantic(self, query_vector: list[float], *, top_k: int = 5, domain: str | None = None) -> list[KnowledgeNode]: ...

    @abstractmethod
    async def search_fulltext(self, query: str, *, top_k: int = 5, domain: str | None = None) -> list[KnowledgeNode]: ...

    @abstractmethod
    async def search_hybrid(self, query: str, query_vector: list[float], *, top_k: int = 5, domain: str | None = None) -> list[KnowledgeNode]: ...
