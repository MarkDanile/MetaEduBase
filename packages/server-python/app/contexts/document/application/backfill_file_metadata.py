"""`backfill_file_metadata` — REQ-010 Slice 6 历史 files 元数据回填。

按 plan Step 6.3：扫描 files 缺 doc_type / tags 的记录，按 file_type
启发式补 doc_type（不擅自动 structured_data）。幂等：跳过已有非空
值的记录。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# file_type → doc_type 启发式映射
_FILE_TYPE_TO_DOC_TYPE: dict[str, str] = {
    "pdf": "document",
    "docx": "document",
    "doc": "document",
    "txt": "document",
    "md": "document",
    "markdown": "document",
    "pptx": "document",
    "ppt": "document",
    "xlsx": "document",
    "xls": "document",
}


@dataclass
class FileMetadataBackfillStats:
    scanned: int = 0
    updated_doc_type: int = 0
    skipped_already_present: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "updated_doc_type": self.updated_doc_type,
            "skipped_already_present": self.skipped_already_present,
            "failed": self.failed,
        }


async def _fetch_pending_files(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[dict]:
    result = await session.execute(
        text(
            "SELECT id, filename, file_type, doc_type, tags "
            "FROM metaedu.files "
            "WHERE tenant_id = :tid AND (doc_type IS NULL OR cardinality(tags) = 0)"
        ),
        {"tid": tenant_id},
    )
    return list(result.mappings().all())


def infer_doc_type(file_type: str | None) -> str | None:
    """Heuristic: file_type → doc_type. Returns None for unknown types."""
    if not file_type:
        return None
    return _FILE_TYPE_TO_DOC_TYPE.get(file_type.lower())


async def backfill_file_metadata(
    session: AsyncSession, tenant_id: uuid.UUID, dry_run: bool = False
) -> FileMetadataBackfillStats:
    """Backfill doc_type for files missing it. Tags left for user / P2.

    Idempotent: re-running finds no rows with doc_type IS NULL.
    """
    stats = FileMetadataBackfillStats()
    files = await _fetch_pending_files(session, tenant_id)
    stats.scanned = len(files)

    for f in files:
        try:
            if f["doc_type"] is not None:
                # tags 缺但 doc_type 有；不动（tags 是用户/业务字段）
                stats.skipped_already_present += 1
                continue
            doc_type = infer_doc_type(f["file_type"])
            if not doc_type:
                stats.skipped_already_present += 1
                continue
            if dry_run:
                stats.updated_doc_type += 1
                continue
            await session.execute(
                text(
                    "UPDATE metaedu.files "
                    "SET doc_type = :dt "
                    "WHERE id = :id AND tenant_id = :tid"
                ),
                {"dt": doc_type, "id": f["id"], "tid": tenant_id},
            )
            stats.updated_doc_type += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "backfill_file_metadata: file=%s failed: %s", f["id"], e
            )
            stats.failed += 1

    if not dry_run:
        await session.commit()
    logger.info(
        "backfill_file_metadata tenant=%s %s", tenant_id, stats.as_dict()
    )
    return stats
