"""`backfill_chunk_embedding` — REQ-010 Slice 6 历史 chunk embedding 回填。

按 plan Step 6.2：扫描 document_chunks 缺 embedding / content_tsvector
的记录，调 get_embedding 补 embedding，写 content_tsvector（to_tsvector）。
幂等：WHERE 限制 + 分批 + 写后用 SELECT 校验。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Type alias for the embedding function (allows test stub injection)
EmbeddingFn = Callable[[str], Awaitable[list[float] | None]]


@dataclass
class EmbeddingBackfillStats:
    scanned: int = 0
    updated: int = 0
    skipped_already_present: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "updated": self.updated,
            "skipped_already_present": self.skipped_already_present,
            "failed": self.failed,
        }


async def _fetch_pending_chunks(
    session: AsyncSession, tenant_id: uuid.UUID, limit: int
) -> list[dict]:
    result = await session.execute(
        text(
            "SELECT id, content, embedding, content_tsvector "
            "FROM metaedu.document_chunks "
            "WHERE tenant_id = :tid "
            "AND (embedding IS NULL OR content_tsvector IS NULL) "
            "LIMIT :lim"
        ),
        {"tid": tenant_id, "lim": limit},
    )
    return list(result.mappings().all())


async def backfill_chunk_embedding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    embedding_fn: EmbeddingFn,
    *,
    batch_size: int = 50,
    dry_run: bool = False,
) -> EmbeddingBackfillStats:
    """Backfill missing embedding / content_tsvector on document_chunks.

    Idempotent: WHERE filter excludes chunks already with embedding +
    content_tsvector; re-run yields 0 updates.
    """
    stats = EmbeddingBackfillStats()
    while True:
        pending = await _fetch_pending_chunks(session, tenant_id, batch_size)
        if not pending:
            break
        stats.scanned += len(pending)
        for chunk in pending:
            try:
                content = chunk["content"] or ""
                if not content:
                    stats.skipped_already_present += 1
                    continue
                needs_embedding = chunk["embedding"] is None
                needs_tsvector = chunk["content_tsvector"] is None
                if not needs_embedding and not needs_tsvector:
                    stats.skipped_already_present += 1
                    continue
                if needs_embedding:
                    emb = await embedding_fn(content)
                    if not emb:
                        stats.failed += 1
                        continue
                    embedding_str = "[" + ",".join(f"{v:.6f}" for v in emb) + "]"
                else:
                    embedding_str = chunk["embedding"]
                if dry_run:
                    stats.updated += 1
                    continue
                # Use to_tsvector('chinese_zh', content) — Chinese-aware
                # (zhparser + SCWS dict, TD-047/3 P2-SEARCH 切片 3).
                # Falls back to simple-style behavior on pure ASCII (SCWS treats
                # ASCII tokens as 'e' / 'l' / etc., still indexed under simple mapping).
                await session.execute(
                    text(
                        "UPDATE metaedu.document_chunks "
                        "SET embedding = :emb, "
                        "    content_tsvector = to_tsvector('chinese_zh', :content) "
                        "WHERE id = :id AND tenant_id = :tid"
                    ),
                    {
                        "emb": embedding_str,
                        "content": content,
                        "id": chunk["id"],
                        "tid": tenant_id,
                    },
                )
                stats.updated += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "backfill_chunk_embedding: chunk=%s failed: %s",
                    chunk["id"],
                    e,
                )
                stats.failed += 1
        if dry_run:
            break  # don't loop in dry_run
        await session.commit()
    logger.info(
        "backfill_chunk_embedding tenant=%s %s",
        tenant_id,
        stats.as_dict(),
    )
    return stats
