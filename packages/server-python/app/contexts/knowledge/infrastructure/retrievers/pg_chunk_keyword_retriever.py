"""`PgChunkKeywordRetriever` — PostgreSQL tsvector / ILIKE adapter for chunk-level keyword recall.

REQ-010 Slice 3 — 复用现有 `PgKeywordRecallChannel` (knowledge_nodes) 的
关键词分词策略，但目标表换成 `document_chunks`；P1 用 `ILIKE` 简单实现，
P2 / P3 可升级到 Elasticsearch / OpenSearch。
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.shared.domain.ner_pipeline import NERResult

logger = logging.getLogger(__name__)


def _tokenize(query: str) -> list[str]:
    raw_words = re.split(r"[，。？、！\s,?.!]+", query[:80])
    keywords: list[str] = []
    for w in raw_words:
        if len(w) >= 2:
            keywords.append(w)
        if len(w) > 6:
            for i in range(0, len(w) - 1, 2):
                keywords.append(w[i:i + 4])
    return list(dict.fromkeys(keywords))[:8]


class PgChunkKeywordRetriever:
    name: str = "pg-chunk-keyword"

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
        keywords = _tokenize(query)
        if not keywords:
            return []

        params: dict = {"tid": tenant_id, "lim": top_k}
        conditions: list[str] = ["c.tenant_id = :tid"]
        for i, kw in enumerate(keywords):
            params[f"q{i}"] = f"%{kw}%"
            conditions.append(
                f"(c.content ILIKE :q{i} OR COALESCE(c.section_title, '') ILIKE :q{i})"
            )
        where = " AND ".join(conditions)

        if file_filter:
            placeholders = ", ".join(f":f{i}" for i in range(len(file_filter)))
            where += f" AND c.file_id IN ({placeholders})"
            for i, fid in enumerate(file_filter):
                params[f"f{i}"] = uuid.UUID(fid) if not isinstance(fid, uuid.UUID) else fid

        result = await session.execute(
            text(
                "SELECT c.id, c.file_id, c.chunk_index, c.content, "
                "c.section_title, c.section_path "
                "FROM metaedu.document_chunks c "
                f"WHERE {where} "
                "ORDER BY c.chunk_index LIMIT :lim"
            ),
            params,
        )

        items: list[EvidenceItem] = []
        for idx, row in enumerate(result.mappings().all()):
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
                    score=round(1.0 - idx * 0.05, 4),
                    channels=["keyword"],
                    metadata={
                        "section_path": row["section_path"],
                        "chunk_index": row["chunk_index"],
                    },
                )
            )
        return items
