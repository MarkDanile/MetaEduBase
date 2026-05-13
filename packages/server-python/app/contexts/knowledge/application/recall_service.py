from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.application.embedding_service import (
    get_embedding as get_embedding_vec,
)
from app.shared.domain.ner_pipeline import NERResult
from app.shared.domain.recall_channel import RecallResult

logger = logging.getLogger(__name__)


class PgVectorRecallChannel:
    @property
    def name(self) -> str:
        return "vector"

    async def recall(
        self,
        query: str,
        _ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        top_k: int = 5,
    ) -> list[RecallResult]:
        embedding = await get_embedding_vec(query)
        if not embedding:
            return []

        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
        result = await session.execute(
            text(
                "SELECT n.id, n.title, n.description, n.domain, n.level, n.path, "
                "1 - (n.embedding <=> :vec::vector) AS score "
                "FROM metaedu.knowledge_nodes n "
                "WHERE n.tenant_id = :tid AND n.embedding IS NOT NULL "
                "ORDER BY n.embedding <=> :vec::vector LIMIT :lim"
            ),
            {"tid": tenant_id, "vec": vec_str, "lim": top_k},
        )

        results: list[RecallResult] = []
        for row in result.mappings().all():
            results.append(RecallResult(
                node_id=str(row["id"]),
                title=row["title"],
                description=row["description"],
                domain=row["domain"],
                level=row["level"],
                score=round(float(row["score"]), 4),
                channel=self.name,
                path=row.get("path"),
            ))
        return results


class PgKeywordRecallChannel:
    @property
    def name(self) -> str:
        return "keyword"

    async def recall(
        self,
        query: str,
        _ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        top_k: int = 5,
    ) -> list[RecallResult]:
        raw_words = re.split(r"[，。？、！\s,?.!]+", query[:80])
        keywords: list[str] = []
        for w in raw_words:
            if len(w) >= 2:
                keywords.append(w)
            if len(w) > 6:
                for i in range(0, len(w) - 1, 2):
                    keywords.append(w[i:i + 4])
        keywords = list(dict.fromkeys(keywords))[:8]
        if not keywords:
            return []

        params: dict = {"tid": tenant_id, "lim": top_k}
        conditions: list[str] = []
        for i, kw in enumerate(keywords):
            params[f"q{i}"] = f"%{kw}%"
            conditions.append(f"(n.title ILIKE :q{i} OR n.description ILIKE :q{i})")

        where_clause = " OR ".join(conditions)
        result = await session.execute(
            text(
                "SELECT n.id, n.title, n.description, n.domain, n.level, n.path "
                "FROM metaedu.knowledge_nodes n "
                f"WHERE n.tenant_id = :tid AND ({where_clause}) "
                "LIMIT :lim"
            ),
            params,
        )

        results: list[RecallResult] = []
        for idx, row in enumerate(result.mappings().all()):
            results.append(RecallResult(
                node_id=str(row["id"]),
                title=row["title"],
                description=row["description"],
                domain=row["domain"],
                level=row["level"],
                score=round(1.0 - idx * 0.05, 4),
                channel=self.name,
                path=row.get("path"),
            ))
        return results


class PgMetadataRecallChannel:
    @property
    def name(self) -> str:
        return "metadata"

    async def recall(
        self,
        _query: str,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        top_k: int = 5,
    ) -> list[RecallResult]:
        if not ner_result.domains and not ner_result.levels:
            return []

        conditions: list[str] = ["n.tenant_id = :tid"]
        params: dict = {"tid": tenant_id, "lim": top_k}

        if ner_result.domains:
            domain_placeholders = ", ".join([f":d{i}" for i in range(len(ner_result.domains))])
            conditions.append(f"n.domain IN ({domain_placeholders})")
            for i, d in enumerate(ner_result.domains):
                params[f"d{i}"] = d

        if ner_result.levels:
            level_placeholders = ", ".join([f":l{i}" for i in range(len(ner_result.levels))])
            conditions.append(f"n.level IN ({level_placeholders})")
            for i, lv in enumerate(ner_result.levels):
                params[f"l{i}"] = lv

        where_clause = " AND ".join(conditions)
        result = await session.execute(
            text(
                "SELECT n.id, n.title, n.description, n.domain, n.level, n.path "
                "FROM metaedu.knowledge_nodes n "
                f"WHERE {where_clause} "
                "ORDER BY n.created_at DESC LIMIT :lim"
            ),
            params,
        )

        results: list[RecallResult] = []
        for idx, row in enumerate(result.mappings().all()):
            results.append(RecallResult(
                node_id=str(row["id"]),
                title=row["title"],
                description=row["description"],
                domain=row["domain"],
                level=row["level"],
                score=round(0.8 - idx * 0.04, 4),
                channel=self.name,
                path=row.get("path"),
            ))
        return results
