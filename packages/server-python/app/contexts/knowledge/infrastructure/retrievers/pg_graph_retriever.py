"""`PgGraphRetriever` — knowledge graph adapter (P1: PG + SQL).

REQ-010 Slice 3 — 包装现有 `PgVectorRecallChannel` + `PgKeywordRecallChannel`
(knowledge_nodes) 但返回 `EvidenceItem(source_type="knowledge_node")`；P1
阶段实现尽量回填 `source_chunk_id` / `source_file_id`（Slice 5 KG 抽取按
chunk 切片后才有；本 Slice 如未填则 file_id 设 source_file_id、chunk_id
留空）。

P2 / P3 可升级到 Neo4j / GraphRAG 风格索引。
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.application.recall_service import (
    PgKeywordRecallChannel,
    PgVectorRecallChannel,
)
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.shared.domain.ner_pipeline import NERResult

logger = logging.getLogger(__name__)


class PgGraphRetriever:
    name: str = "pg-graph"

    def __init__(self) -> None:
        self._vector_channel = PgVectorRecallChannel()
        self._keyword_channel = PgKeywordRecallChannel()

    async def retrieve(
        self,
        query: str,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        *,
        top_k: int = 5,
    ) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []

        # vector channel
        try:
            vector_results = await self._vector_channel.recall(
                query, ner_result, tenant_id, session, top_k
            )
            for r in vector_results:
                items.append(
                    EvidenceItem(
                        evidence_id="",
                        source_type="knowledge_node",
                        file_id=None,  # P1: knowledge_nodes.source_file_id not
                                       # surfaced in RecallResult; filled in Slice 5
                        chunk_id=None,
                        node_id=r.node_id,
                        title=r.title or "",
                        content=r.description or "",
                        snippet=(r.description or "")[:200],
                        score=r.score,
                        channels=[r.channel or "vector"],
                        metadata={
                            "domain": r.domain,
                            "level": r.level,
                            "path": r.path,
                        },
                    )
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("pg_graph vector channel failed: %s", e)

        # keyword channel
        try:
            keyword_results = await self._keyword_channel.recall(
                query, ner_result, tenant_id, session, top_k
            )
            for r in keyword_results:
                items.append(
                    EvidenceItem(
                        evidence_id="",
                        source_type="knowledge_node",
                        file_id=None,
                        chunk_id=None,
                        node_id=r.node_id,
                        title=r.title or "",
                        content=r.description or "",
                        snippet=(r.description or "")[:200],
                        score=r.score,
                        channels=[r.channel or "keyword"],
                        metadata={
                            "domain": r.domain,
                            "level": r.level,
                            "path": r.path,
                        },
                    )
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("pg_graph keyword channel failed: %s", e)

        return items
