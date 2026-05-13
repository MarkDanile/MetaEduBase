from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class NERResult(BaseModel):
    domains: list[str] = []
    levels: list[str] = []
    raw_entities: list[str] = []


@runtime_checkable
class NERPipeline(Protocol):
    async def extract(self, query: str) -> NERResult: ...
