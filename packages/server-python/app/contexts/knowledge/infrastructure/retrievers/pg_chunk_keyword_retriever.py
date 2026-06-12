"""`PgChunkKeywordRetriever` — PostgreSQL tsvector adapter for chunk-level keyword recall.

REQ-010 Slice 3 — 复用现有 `PgKeywordRecallChannel` (knowledge_nodes) 的
关键词分词策略，但目标表换成 `document_chunks`。TD-047 后，P1 / P2 搜索
基础已切到 `content_tsvector` + `chinese_zh`；P3 可升级到 Elasticsearch /
OpenSearch 而不影响 `ChunkRetriever` 契约。
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

    @staticmethod
    def _file_filter_sql(params: dict, file_filter: list[str] | None) -> str:
        if not file_filter:
            return ""
        placeholders = ", ".join(f":f{i}" for i in range(len(file_filter)))
        for i, fid in enumerate(file_filter):
            params[f"f{i}"] = uuid.UUID(fid) if not isinstance(fid, uuid.UUID) else fid
        return f" AND c.file_id IN ({placeholders})"

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
                    channels=["keyword"],
                    metadata={
                        "section_path": row["section_path"],
                        "chunk_index": row["chunk_index"],
                        "keyword_rank": keyword_rank,
                        "search_mode": search_mode,
                    },
                )
            )
        return items

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

        tsquery = " ".join(keywords)
        params: dict = {"tid": tenant_id, "query": tsquery, "lim": top_k}
        file_where = self._file_filter_sql(params, file_filter)

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
