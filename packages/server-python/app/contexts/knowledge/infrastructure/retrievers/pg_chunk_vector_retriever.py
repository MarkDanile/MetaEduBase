"""`PgChunkVectorRetriever` — PostgreSQL + pgvector adapter for chunk-level vector recall.

REQ-010 Slice 3 — P1 AI Chat 编排层依赖的真实 chunk 向量召回实现。
SQL 风格与现有 `PgVectorRecallChannel` (knowledge_nodes) 保持一致，便于
后续 P2 / P3 替换为 Milvus / Qdrant 时只看本文件的 SQL / 嵌入层。

BUG-003 (AC-2/AC-3) — 当 `get_embedding` 返回 None（API key 缺失 / 限流 /
网络错误）时，本 retriever 不再 return []，而是降级到与
`PgChunkKeywordRetriever` 同一查询策略的 tsvector + ILIKE keyword 路径，
保证 chunk 通道在 embedding 不可达时仍能返回正文 chunk。降级时 channels
标记为 `["vector", "keyword"]`，metadata 记录 `search_mode` 和
`embedding_fallback=True` 便于审计。
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.application.embedding_service import get_embedding
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.shared.domain.ner_pipeline import NERResult

logger = logging.getLogger(__name__)


# 与 `PgChunkKeywordRetriever._tokenize` 同一分词策略；保留本地副本避免
# 引入 `infrastructure → application` 反向依赖。后续如统一分词策略，把
# 这一段迁到 `app/shared/domain/` 共享。
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
            return await self._fallback_keyword_search(
                query, tenant_id, session, top_k=top_k, file_filter=file_filter
            )

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

    async def _fallback_keyword_search(
        self,
        query: str,
        tenant_id: str,
        session: AsyncSession,
        *,
        top_k: int,
        file_filter: list[str] | None,
    ) -> list[EvidenceItem]:
        """BUG-003 AC-2/AC-3 降级路径：embedding 不可达时复用 tsvector +
        ILIKE keyword 检索。结果 channels 标记为 `["vector", "keyword"]`，
        metadata 含 `embedding_fallback=True` 以让上层 UI 区分"原 vector 通道"
        vs "降级 keyword 通道"（仅在 matrix / audit 场景需要）。
        """
        keywords = _tokenize(query)
        if not keywords:
            return []

        tsquery = " ".join(keywords)
        params: dict = {"tid": tenant_id, "query": tsquery, "lim": top_k}

        if file_filter:
            placeholders = ", ".join(f":f{i}" for i in range(len(file_filter)))
            file_where = f" AND c.file_id IN ({placeholders})"
            for i, fid in enumerate(file_filter):
                params[f"f{i}"] = uuid.UUID(fid) if not isinstance(fid, uuid.UUID) else fid
        else:
            file_where = ""

        result = await session.execute(
            text(
                "WITH keyword_config AS ("
                "  SELECT COALESCE("
                "    (SELECT oid::regconfig "
                "     FROM pg_catalog.pg_ts_config "
                "     WHERE cfgname = 'chinese_zh' "
                "     LIMIT 1), "
                "    'pg_catalog.simple'::regconfig"
                "  ) AS cfg"
                "), keyword_query AS ("
                "  SELECT plainto_tsquery(keyword_config.cfg, :query) AS query, "
                "  keyword_config.cfg AS cfg "
                "  FROM keyword_config"
                ") "
                "SELECT c.id, c.file_id, c.chunk_index, c.content, "
                "c.section_title, c.section_path, "
                "ts_rank_cd(c.content_tsvector::tsvector, keyword_query.query) AS keyword_rank "
                "FROM metaedu.document_chunks c, keyword_query "
                "WHERE c.tenant_id = :tid "
                "AND c.content_tsvector IS NOT NULL "
                "AND numnode(keyword_query.query) > 0 "
                "AND c.content_tsvector::tsvector @@ keyword_query.query "
                f"{file_where} "
                "ORDER BY keyword_rank DESC, c.chunk_index LIMIT :lim"
            ),
            params,
        )
        rows = list(result.mappings().all())
        if rows:
            return self._to_evidence_items(rows, search_mode="tsvector")

        fallback_params = {**params}
        ilike_conditions: list[str] = []
        for i, kw in enumerate(keywords):
            fallback_params[f"kw{i}"] = f"%{kw}%"
            ilike_conditions.append(
                f"(c.content ILIKE :kw{i} OR COALESCE(c.section_title, '') ILIKE :kw{i})"
            )
        fallback_result = await session.execute(
            text(
                "SELECT c.id, c.file_id, c.chunk_index, c.content, "
                "c.section_title, c.section_path, 0.0 AS keyword_rank "
                "FROM metaedu.document_chunks c "
                "WHERE c.tenant_id = :tid "
                f"AND ({' OR '.join(ilike_conditions)}) "
                f"{file_where} "
                "ORDER BY c.chunk_index LIMIT :lim"
            ),
            fallback_params,
        )
        return self._to_evidence_items(
            list(fallback_result.mappings().all()),
            search_mode="ilike_fallback",
        )

    @staticmethod
    def _to_evidence_items(rows: list[dict], *, search_mode: str) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for idx, row in enumerate(rows):
            content = row["content"] or ""
            keyword_rank = float(row.get("keyword_rank") or 0.0)
            items.append(
                EvidenceItem(
                    evidence_id="",
                    source_type="chunk",
                    file_id=row["file_id"],
                    chunk_id=row["id"],
                    title=row["section_title"] or f"chunk-{row['chunk_index']}",
                    content=content,
                    snippet=content[:200],
                    score=round(max(0.3, 1.0 - idx * 0.05), 4),
                    channels=["vector", "keyword"],
                    metadata={
                        "section_path": row["section_path"],
                        "chunk_index": row["chunk_index"],
                        "keyword_rank": keyword_rank,
                        "search_mode": search_mode,
                        "embedding_fallback": True,
                    },
                )
            )
        return items
