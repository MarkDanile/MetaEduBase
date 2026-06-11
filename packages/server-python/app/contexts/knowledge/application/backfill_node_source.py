"""`backfill_knowledge_node_source` — REQ-010 Slice 6 历史数据回填。

按 plan Step 6.1：扫描历史 knowledge_nodes 缺 source_chunk_id 的记录，
按"name + 同一 source_file_id + chunk 内容关键词子串"模糊匹配；无法
确定的标记 node_source_resolution='file_only'。

幂等：WHERE 条件限制 + INSERT 复用 SELECT 校验（不依赖 PG ON CONFLICT，
因为本操作是 UPDATE 已有 node）。输出 scanned / updated / skipped /
failed 统计。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class BackfillStats:
    scanned: int = 0
    updated: int = 0
    skipped_file_only: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "updated": self.updated,
            "skipped_file_only": self.skipped_file_only,
            "failed": self.failed,
        }


async def _fetch_pending_nodes(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[dict]:
    """Return nodes missing source_chunk_id or node_source_resolution."""
    result = await session.execute(
        text(
            "SELECT id, title, source_file_id, source_chunk_id, "
            "node_source_resolution "
            "FROM metaedu.knowledge_nodes "
            "WHERE tenant_id = :tid "
            "AND (source_chunk_id IS NULL "
            "     OR node_source_resolution IS NULL)"
        ),
        {"tid": tenant_id},
    )
    return list(result.mappings().all())


async def _find_chunk_for_node(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    file_id: uuid.UUID | None,
    node_title: str,
) -> uuid.UUID | None:
    """Find the first chunk in the same file whose content's Chinese-tsvector
    matches the node title tsquery (TD-047 切片 4).

    Uses ``to_tsvector('chinese_zh', content) @@ plainto_tsquery('chinese_zh', :title)``
    (replaces TD-046 era's byte-level ``ILIKE '%{title}%'``). ``plainto_tsquery``
    auto-escapes title input — no manual SQL escape needed; bind param via
    ``:title`` parameter for defense-in-depth.

    Coverage edges:
    - 标题逐字命中 chunk: tsquery 拆 token 后 chunk 同样 token → 命中 (与旧 ILIKE 等价)
    - 标题在 chunk 中拆字 / 多 token 共享: 升级命中 (旧 ILIKE 失败的场景)
    - 同义 / 翻译 / 抽象语义匹配: **仍不命中** (SCWS 词表不连接同义词；REQ-012 后续 embedding 召回)
    - 空标题 / 标题被 SCWS 切成空 tsquery: 返回 None → 业务侧 ``file_only`` 兜底

    Returns None when no file_id is known, title is empty, or no chunk matches.
    """
    if file_id is None or not node_title:
        return None
    result = await session.execute(
        text(
            "SELECT id FROM metaedu.document_chunks "
            "WHERE tenant_id = :tid AND file_id = :fid "
            "AND to_tsvector('chinese_zh', content) "
            "    @@ plainto_tsquery('chinese_zh', :title) "
            "ORDER BY chunk_index LIMIT 1"
        ),
        {
            "tid": tenant_id,
            "fid": file_id,
            "title": node_title,
        },
    )
    row = result.first()
    if row is None:
        return None
    return row[0]


async def backfill_knowledge_node_source(
    session: AsyncSession, tenant_id: uuid.UUID, dry_run: bool = False
) -> BackfillStats:
    """Backfill source_chunk_id + node_source_resolution for one tenant.

    Idempotent: re-running finds no pending rows (WHERE filter excludes
    nodes already resolved).
    """
    stats = BackfillStats()
    nodes = await _fetch_pending_nodes(session, tenant_id)
    stats.scanned = len(nodes)

    for node in nodes:
        try:
            chunk_id = await _find_chunk_for_node(
                session, tenant_id, node["source_file_id"], node["title"]
            )
            resolution = "chunk_resolved" if chunk_id else "file_only"
            if dry_run:
                if resolution == "chunk_resolved":
                    stats.updated += 1
                else:
                    stats.skipped_file_only += 1
                continue
            await session.execute(
                text(
                    "UPDATE metaedu.knowledge_nodes "
                    "SET source_chunk_id = :scid, "
                    "    node_source_resolution = :res, "
                    "    updated_at = NOW() "
                    "WHERE id = :id AND tenant_id = :tid"
                ),
                {
                    "scid": chunk_id,
                    "res": resolution,
                    "id": node["id"],
                    "tid": tenant_id,
                },
            )
            if resolution == "chunk_resolved":
                stats.updated += 1
            else:
                stats.skipped_file_only += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "backfill_knowledge_node_source: node=%s failed: %s",
                node["id"],
                e,
            )
            stats.failed += 1

    if not dry_run:
        await session.commit()

    logger.info(
        "backfill_knowledge_node_source tenant=%s %s",
        tenant_id,
        stats.as_dict(),
    )
    return stats


async def list_distinct_tenants(session: AsyncSession) -> list[uuid.UUID]:
    result = await session.execute(
        text("SELECT DISTINCT id FROM metaedu.tenants")
    )
    return [row[0] for row in result.all()]
