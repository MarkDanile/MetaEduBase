"""Composite retrievers for AI Chat evidence retrieval."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.application.retrievers import ChunkRetriever
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.shared.domain.ner_pipeline import NERResult

logger = logging.getLogger(__name__)


class CompositeChunkRetriever:
    """Run multiple chunk retrievers and return one combined candidate list.

    The AI Chat service should keep depending on the `ChunkRetriever` protocol.
    This adapter lets P1 combine pgvector + keyword/tsvector without teaching the
    orchestration layer about individual storage engines.
    """

    name = "composite-chunk"

    def __init__(self, retrievers: list[ChunkRetriever]) -> None:
        self.retrievers = retrievers

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
        tasks = [
            retriever.retrieve(
                query,
                ner_result,
                tenant_id,
                session,
                top_k=top_k,
                file_filter=file_filter,
            )
            for retriever in self.retrievers
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[EvidenceItem] = []
        for retriever, result in zip(self.retrievers, raw_results, strict=True):
            if isinstance(result, Exception):
                logger.warning(
                    "chunk retriever %s failed: %s",
                    getattr(retriever, "name", retriever.__class__.__name__),
                    result,
                )
                continue
            items.extend(result)
        return items
