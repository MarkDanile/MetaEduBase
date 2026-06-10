"""`PgChunkVectorRetriever` — PostgreSQL + pgvector adapter for chunk-level vector recall.

REQ-010 Slice 3 — P1 AI Chat 编排层依赖的真实 chunk 向量召回实现。
SQL 风格与现有 `PgVectorRecallChannel` (knowledge_nodes) 保持一致，便于
后续 P2 / P3 替换为 Milvus / Qdrant 时只看本文件的 SQL / 嵌入层。
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.application.embedding_service import get_embedding
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.shared.domain.ner_pipeline import NERResult

logger = logging.getLogger(__name__)


class PgChunkVectorRetriever:
    name: str = "pg-chunk-vector"

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
        embedding = await get_embedding(query)
        if not embedding:
            logger.warning("pg_chunk_vector: empty embedding for query=%r", query[:60])
            return []

        vec_str = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"

        where_extra = ""
        params: dict = {"tid": tenant_id, "vec": vec_str, "lim": top_k}
        if file_filter:
            placeholders = ", ".join(f":f{i}" for i in range(len(file_filter)))
            where_extra = f" AND c.file_id IN ({placeholders})"
            for i, fid in enumerate(file_filter):
                params[f"f{i}"] = uuid.UUID(fid) if not isinstance(fid, uuid.UUID) else fid

        result = await session.execute(
            text(
                "SELECT c.id, c.file_id, c.chunk_index, c.content, "
                "c.section_title, c.section_path, "
                "1 - (c.embedding <=> :vec::vector) AS score "
                "FROM metaedu.document_chunks c "
                "WHERE c.tenant_id = :tid AND c.embedding IS NOT NULL"
                f"{where_extra} "
                "ORDER BY c.embedding <=> :vec::vector LIMIT :lim"
            ),
            params,
        )

        items: list[EvidenceItem] = []
        for row in result.mappings().all():
            content = row["content"] or ""
            items.append(
                EvidenceItem(
                    evidence_id="",
                    source_type="chunk",
                    file_id=row["file_id"],
                    chunk_id=row["id"],
                    title=row["section_title"] or f"chunk-{row['chunk_index']}",
                    content=content,
                    snippet=content[:200],
                    score=round(float(row["score"]), 4),
                    channels=["vector"],
                    metadata={
                        "section_path": row["section_path"],
                        "chunk_index": row["chunk_index"],
                    },
                )
            )
        return items
