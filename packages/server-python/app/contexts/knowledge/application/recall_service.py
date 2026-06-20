from __future__ import annotations

import logging
import re
import uuid

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
        ner_result: NERResult,
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
                "n.source_file_id, n.source_chunk_id, "
                "1 - (n.embedding <=> CAST(:vec AS vector)) AS score "
                "FROM metaedu.knowledge_nodes n "
                "WHERE n.tenant_id = :tid AND n.embedding IS NOT NULL "
                "ORDER BY n.embedding <=> CAST(:vec AS vector) LIMIT :lim"
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
                source_file_id=row.get("source_file_id"),
                source_chunk_id=row.get("source_chunk_id"),
            ))
        return results


class PgKeywordRecallChannel:
    @property
    def name(self) -> str:
        return "keyword"

    async def recall(
        self,
        query: str,
        ner_result: NERResult,
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
                "SELECT n.id, n.title, n.description, n.domain, n.level, n.path, "
                "n.source_file_id, n.source_chunk_id "
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
                source_file_id=row.get("source_file_id"),
                source_chunk_id=row.get("source_chunk_id"),
            ))
        return results


class PgEdgeRecallChannel:
    """Edge-based recall: seed nodes (ILIKE) → knowledge_edges → related nodes.

    REQ-018 Slice 1 — returns RecallResult with edge_id set so PgEdgeRetriever
    can emit EvidenceItem(source_type="knowledge_edge").
    """

    @property
    def name(self) -> str:
        return "graph_edge"

    async def recall(
        self,
        query: str,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        top_k: int = 5,
    ) -> list[RecallResult]:
        # Step 1: seed nodes via ILIKE on title
        raw_words = re.split(r"[，。？、！\s,?.!]+", query[:80])
        keywords: list[str] = []
        for w in raw_words:
            if len(w) >= 2:
                keywords.append(w)
            if len(w) > 6:
                for i in range(0, len(w) - 1, 2):
                    keywords.append(w[i : i + 4])
        keywords = list(dict.fromkeys(keywords))[:8]
        if not keywords:
            return []

        seed_params: dict = {"tid": tenant_id, "lim": top_k}
        seed_conditions: list[str] = []
        for i, kw in enumerate(keywords):
            seed_params[f"q{i}"] = f"%{kw}%"
            seed_conditions.append(f"n.title ILIKE :q{i}")
        seed_where = " OR ".join(seed_conditions)

        seed_result = await session.execute(
            text(
                f"SELECT n.id, n.title, n.description, n.domain, n.level, n.path, "
                f"n.source_file_id, n.source_chunk_id "
                f"FROM metaedu.knowledge_nodes n "
                f"WHERE n.tenant_id = :tid AND ({seed_where}) "
                f"LIMIT :lim"
            ),
            seed_params,
        )
        seed_rows = list(seed_result.mappings().all())
        if not seed_rows:
            return []

        seed_ids = [str(row["id"]) for row in seed_rows]

        # Step 2: edges where source_id OR target_id is a seed node
        edge_params: dict = {"tid": tenant_id, "lim": top_k}
        seed_in_clause = ", ".join([f":s{i}" for i in range(len(seed_ids))])
        for i, sid in enumerate(seed_ids):
            edge_params[f"s{i}"] = uuid.UUID(sid)

        edge_result = await session.execute(
            text(
                f"SELECT e.id, e.source_id, e.target_id, e.relation_type, e.weight, "
                f"CASE WHEN e.source_id IN ({seed_in_clause}) "
                f"THEN e.target_id ELSE e.source_id END AS related_node_id "
                f"FROM metaedu.knowledge_edges e "
                f"WHERE e.tenant_id = :tid "
                f"AND (e.source_id IN ({seed_in_clause}) OR e.target_id IN ({seed_in_clause})) "
                f"ORDER BY e.weight DESC "
                f"LIMIT :lim"
            ),
            edge_params,
        )
        edge_rows = list(edge_result.mappings().all())
        if not edge_rows:
            return []

        # Step 3: hydrate related node ids
        related_ids = list({str(row["related_node_id"]) for row in edge_rows})
        related_in_clause = ", ".join([f":r{i}" for i in range(len(related_ids))])
        node_params: dict = {"tid2": tenant_id}
        for i, nid in enumerate(related_ids):
            node_params[f"r{i}"] = uuid.UUID(nid)

        node_result = await session.execute(
            text(
                f"SELECT n.id, n.title, n.description, n.domain, n.level, n.path, "
                f"n.source_file_id, n.source_chunk_id "
                f"FROM metaedu.knowledge_nodes n "
                f"WHERE n.tenant_id = :tid2 AND n.id IN ({related_in_clause})"
            ),
            node_params,
        )
        node_map: dict[str, dict] = {
            str(row["id"]): dict(row) for row in node_result.mappings().all()
        }

        results: list[RecallResult] = []
        seen_edges: set[str] = set()
        for row in edge_rows:
            edge_id_str = str(row["id"])
            if edge_id_str in seen_edges:
                continue
            seen_edges.add(edge_id_str)
            related_node_id = str(row["related_node_id"])
            node = node_map.get(related_node_id)
            if not node:
                continue
            results.append(
                RecallResult(
                    node_id=related_node_id,
                    title=node["title"] or "",
                    description=node["description"],
                    domain=node["domain"],
                    level=node["level"],
                    score=round(float(row["weight"] or 1.0), 4),
                    channel=self.name,
                    path=node.get("path"),
                    source_file_id=node.get("source_file_id"),
                    source_chunk_id=node.get("source_chunk_id"),
                    edge_id=row["id"],
                )
            )
        return results


class PgMetadataRecallChannel:
    @property
    def name(self) -> str:
        return "metadata"

    async def recall(
        self,
        query: str,
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
                "SELECT n.id, n.title, n.description, n.domain, n.level, n.path, "
                "n.source_file_id, n.source_chunk_id "
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
                source_file_id=row.get("source_file_id"),
                source_chunk_id=row.get("source_chunk_id"),
            ))
        return results
