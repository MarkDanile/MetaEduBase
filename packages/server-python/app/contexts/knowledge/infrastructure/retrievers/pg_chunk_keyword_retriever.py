"""`PgChunkKeywordRetriever` — PostgreSQL tsvector adapter for chunk-level keyword recall.

REQ-010 Slice 3 — 复用现有 `PgKeywordRecallChannel` (knowledge_nodes) 的
关键词分词策略，但目标表换成 `document_chunks`。TD-047 后，P1 / P2 搜索
基础已切到 `content_tsvector` + `chinese_zh`；P3 可升级到 Elasticsearch /
OpenSearch 而不影响 `ChunkRetriever` 契约。
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.contexts.knowledge.infrastructure.retrievers.keyword_query import (
    bind_keyword_params,
    ilike_conditions,
    lexical_score_sql,
    merge_ranked_rows,
    toc_penalty_sql,
    tokenize_query,
)
from app.shared.domain.ner_pipeline import NERResult

logger = logging.getLogger(__name__)


def _tokenize(query: str) -> list[str]:
    return tokenize_query(query)


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
    def _to_evidence_items(
        rows: list[dict],
        *,
        search_mode: str | None = None,
    ) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for idx, row in enumerate(rows):
            content = row["content"] or ""
            keyword_rank = float(row.get("keyword_rank") or 0.0)
            row_search_mode = search_mode or row.get("_search_mode") or "unknown"
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
                        "lexical_score": float(row.get("lexical_score") or 0.0),
                        "toc_penalty": int(row.get("toc_penalty") or 0),
                        "search_mode": row_search_mode,
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
        # REQ-016 Slice 3: augment keywords with LLM expanded terms
        keywords = _tokenize(query)
        expanded_query = getattr(ner_result, "expanded_query", "") or ""
        if expanded_query:
            expanded_keywords = _tokenize(expanded_query)
            # Deduplicate while preserving order
            seen: set[str] = set()
            merged: list[str] = []
            for kw in keywords + expanded_keywords:
                if kw not in seen:
                    seen.add(kw)
                    merged.append(kw)
            keywords = merged

        if not keywords:
            return []

        tsquery = " ".join(keywords)
        params: dict = {"tid": tenant_id, "query": tsquery, "lim": top_k}
        file_where = self._file_filter_sql(params, file_filter)
        param_names = bind_keyword_params(keywords, params)
        lexical_score = lexical_score_sql(param_names)
        toc_penalty = toc_penalty_sql()

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
                "ts_rank_cd(c.content_tsvector::tsvector, keyword_query.query) AS keyword_rank, "
                f"{lexical_score} AS lexical_score, "
                f"{toc_penalty} AS toc_penalty "
                "FROM metaedu.document_chunks c, keyword_query "
                "WHERE c.tenant_id = :tid "
                "AND c.content_tsvector IS NOT NULL "
                "AND numnode(keyword_query.query) > 0 "
                "AND c.content_tsvector::tsvector @@ keyword_query.query "
                f"{file_where} "
                "ORDER BY toc_penalty ASC, lexical_score DESC, keyword_rank DESC, "
                "c.chunk_index LIMIT :lim"
            ),
            params,
        )
        rows = list(result.mappings().all())

        fallback_params = {**params}
        fallback_param_names = bind_keyword_params(keywords, fallback_params)
        fallback_conditions = ilike_conditions(fallback_param_names)
        fallback_lexical_score = lexical_score_sql(fallback_param_names)
        fallback_toc_penalty = toc_penalty_sql()
        fallback_result = await session.execute(
            text(
                "SELECT c.id, c.file_id, c.chunk_index, c.content, "
                "c.section_title, c.section_path, 0.0 AS keyword_rank, "
                f"{fallback_lexical_score} AS lexical_score, "
                f"{fallback_toc_penalty} AS toc_penalty "
                "FROM metaedu.document_chunks c "
                "WHERE c.tenant_id = :tid "
                f"AND ({' OR '.join(fallback_conditions)}) "
                f"{file_where} "
                "ORDER BY toc_penalty ASC, lexical_score DESC, c.chunk_index LIMIT :lim"
            ),
            fallback_params,
        )
        lexical_rows = list(fallback_result.mappings().all())

        if rows or lexical_rows:
            merged = merge_ranked_rows(rows, lexical_rows, limit=top_k)
            return self._to_evidence_items(merged)

        return self._to_evidence_items(
            lexical_rows,
            search_mode="ilike_fallback",
        )
