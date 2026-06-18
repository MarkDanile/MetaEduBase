"""`PgGraphRetriever` / `PgEdgeRetriever` — knowledge graph adapters (P1: PG + SQL).

REQ-010 Slice 3 — 包装现有 `PgVectorRecallChannel` + `PgKeywordRecallChannel`
(knowledge_nodes) 但返回 `EvidenceItem(source_type="knowledge_node")`。

TD-050 收口时把 `knowledge_nodes.source_file_id` / `source_chunk_id` 透传给
`EvidenceItem.file_id` / `chunk_id`，并同步写 `EvidenceItem.source_chunk_id`
字段（与 `chunk_id` 同值；详见
`docs/02-delivery-plans/01-specs/2026-06-10-req-010-rag-evidence-governance.md`
§3.1 末尾「AC-3 解读说明」）。

P2 / P3 可升级到 Neo4j / GraphRAG 风格索引。
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.application.recall_service import (
    PgEdgeRecallChannel,
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
                        file_id=r.source_file_id,        # TD-050: 由 RecallResult 透传
                        chunk_id=r.source_chunk_id,      # TD-050: 由 RecallResult 透传
                        source_chunk_id=r.source_chunk_id,  # TD-050: 与 chunk_id 同值
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
                        file_id=r.source_file_id,        # TD-050: 由 RecallResult 透传
                        chunk_id=r.source_chunk_id,      # TD-050: 由 RecallResult 透传
                        source_chunk_id=r.source_chunk_id,  # TD-050: 与 chunk_id 同值
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


class PgEdgeRetriever:
    """PgEdgeRetriever — graph edge recall via knowledge_edges.

    REQ-018 Slice 1 — wraps PgEdgeRecallChannel and returns
    EvidenceItem(source_type="knowledge_edge", channels=["graph_edge"]).
    Satisfies the runtime_checkable GraphRetriever Protocol.
    """

    name: str = "pg-edge"

    def __init__(self) -> None:
        self._channel = PgEdgeRecallChannel()

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
        try:
            results = await self._channel.recall(
                query, ner_result, tenant_id, session, top_k
            )
            for r in results:
                # edge_id is guaranteed non-None for edge-channel results
                items.append(
                    EvidenceItem(
                        source_type="knowledge_edge",
                        edge_id=r.edge_id,
                        file_id=r.source_file_id,
                        chunk_id=r.source_chunk_id,
                        source_chunk_id=r.source_chunk_id,
                        node_id=r.node_id,
                        title=r.title or "",
                        content=r.description or "",
                        snippet=(r.description or "")[:200],
                        score=r.score,
                        channels=["graph_edge"],
                        metadata={
                            "domain": r.domain,
                            "level": r.level,
                            "path": r.path,
                            "relation_type": r.description,  # description carries relation context
                        },
                    )
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("pg_edge channel failed: %s", e)
        return items
