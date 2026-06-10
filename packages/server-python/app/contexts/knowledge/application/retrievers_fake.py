"""Fake retriever / filter implementations — for unit tests + future
dependency injection override.

REQ-010 Slice 2 — 在不依赖 PostgreSQL / pgvector / tsvector / 图谱 SQL 的
情况下验证 AI Chat 编排（Slice 3 / Slice 8 测试用 fake 注入）。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.application.retrievers import (  # noqa: F401
    ChunkRetriever,
    GraphRetriever,
    MetadataFilter,
)
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.shared.domain.ner_pipeline import NERResult


class FakeChunkRetriever:
    """Returns a preset list of EvidenceItem regardless of inputs.

    Tests inject by setting `self.return_value` before calling `retrieve`.
    """

    name: str = "fake-chunk"

    def __init__(self) -> None:
        self.return_value: list[EvidenceItem] = []
        self.calls: list[dict] = []

    async def retrieve(
        self,
        query: str,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        *,
        top_k: int = 5,
        file_filter: list[str] | None = None,
    ) -> list[EvidenceItem]:
        self.calls.append(
            {
                "query": query,
                "ner_domains": list(ner_result.domains),
                "ner_levels": list(ner_result.levels),
                "tenant_id": tenant_id,
                "top_k": top_k,
                "file_filter": list(file_filter) if file_filter else None,
            }
        )
        return list(self.return_value)[:top_k]


class FakeGraphRetriever:
    name: str = "fake-graph"

    def __init__(self) -> None:
        self.return_value: list[EvidenceItem] = []
        self.calls: list[dict] = []

    async def retrieve(
        self,
        query: str,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        *,
        top_k: int = 5,
    ) -> list[EvidenceItem]:
        self.calls.append(
            {
                "query": query,
                "ner_domains": list(ner_result.domains),
                "tenant_id": tenant_id,
                "top_k": top_k,
            }
        )
        return list(self.return_value)[:top_k]


class FakeMetadataFilter:
    """Pass-through filter: returns the input candidates unchanged.

    Tests can override `self.return_value` to inject a filtered list.
    """

    name: str = "fake-metadata"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def filter(
        self,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        candidates: list[EvidenceItem],
    ) -> list[EvidenceItem]:
        self.calls.append(
            {
                "ner_domains": list(ner_result.domains),
                "tenant_id": tenant_id,
                "candidate_count": len(candidates),
            }
        )
        return list(candidates)
