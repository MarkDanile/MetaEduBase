from abc import ABC, abstractmethod
from typing import Any


class Repository[T](ABC):
    @abstractmethod
    async def get_by_id(self, id: Any) -> T | None: ...

    @abstractmethod
    async def add(self, entity: T) -> T: ...

    @abstractmethod
    async def update(self, entity: T) -> T: ...

    @abstractmethod
    async def delete(self, id: Any) -> bool: ...

    @abstractmethod
    async def list(self, *, offset: int = 0, limit: int = 50, **filters: Any) -> list[T]: ...
