"""`PgMetadataFilter` — PostgreSQL files metadata adapter for evidence candidate filtering.

REQ-010 Slice 3 — 读 `metaedu.files.doc_type` / `tags` / `structured_data`
顶层 key，对 candidate evidence 的 `file_id` 做命中打分。P1 实现：硬过滤
（不匹配 doc_type 的 evidence 直接 drop），同时把 `doc_type` / `tags` 写入
evidence.metadata 便于前端展示。

P2 / P3 可升级到标签服务 / 用户画像服务。
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.shared.domain.ner_pipeline import NERResult

logger = logging.getLogger(__name__)


class PgMetadataFilter:
    name: str = "pg-metadata"

    async def filter(
        self,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        candidates: list[EvidenceItem],
    ) -> list[EvidenceItem]:
        if not candidates:
            return []

        # Collect unique file_ids
        file_ids: set[uuid.UUID] = set()
        for ev in candidates:
            if ev.file_id is not None:
                file_ids.add(ev.file_id)
        if not file_ids:
            return candidates

        placeholders = ", ".join(f":f{i}" for i in range(len(file_ids)))
        params: dict = {"tid": tenant_id}
        for i, fid in enumerate(file_ids):
            params[f"f{i}"] = fid

        result = await session.execute(
            text(
                "SELECT id, doc_type, tags, structured_data "
                "FROM metaedu.files "
                f"WHERE tenant_id = :tid AND id IN ({placeholders})"
            ),
            params,
        )
        files_meta: dict[uuid.UUID, dict] = {}
        for row in result.mappings().all():
            files_meta[row["id"]] = {
                "doc_type": row["doc_type"],
                "tags": list(row["tags"] or []),
                "structured_data": row["structured_data"] or {},
            }

        # P1: hard filter — only keep candidates whose file has a known
        # doc_type (i.e. metadata is populated). Files with no doc_type are
        # excluded from filtered results to enforce "evidence must be
        # attributable" principle. P2 may relax to scoring-based weighting.
        filtered: list[EvidenceItem] = []
        for ev in candidates:
            if ev.file_id is None:
                continue
            meta = files_meta.get(ev.file_id)
            if meta is None or meta["doc_type"] is None:
                continue
            ev.metadata = {**(ev.metadata or {}), **meta}
            filtered.append(ev)
        return filtered
