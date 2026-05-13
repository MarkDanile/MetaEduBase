from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from app.shared.domain.ner_pipeline import NERResult


class RecallResult(BaseModel):
    node_id: str
    title: str
    description: str | None = None
    domain: str | None = None
    level: str | None = None
    score: float | None = None
    channel: str = ""
    path: str | None = None


@runtime_checkable
class RecallChannel(Protocol):
    @property
    def name(self) -> str: ...

    async def recall(
        self,
        query: str,
        ner_result: NERResult,
        tenant_id: str,
        top_k: int = 5,
    ) -> list[RecallResult]: ...
