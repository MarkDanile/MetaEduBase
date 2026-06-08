"""Pipeline guard helpers for document 6-step Celery pipeline.

`_check_pipeline_stale` 是 reinitialize 守卫：每次进入 task 时若发现 file.updated_at
已变（说明 reinitialize 被调用过），则 abort task 并标 failed。
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _pipeline_version_key(ts: str | None) -> str:
    """Normalize datetime to space-separated string for comparison.

    Python's datetime.isoformat() uses 'T' separator (2026-05-18T06:46:54.604460)
    but PostgreSQL's text output uses space (2026-05-18 06:46:54.604460).
    """
    if not ts:
        return ""
    return ts.replace("T", " ").split(".")[0]


async def _check_pipeline_stale(
    session: AsyncSession,
    file_id: uuid.UUID,
    pipeline_version: str,
) -> bool:
    """Return True if a newer pipeline has since started (reinitialize was called)."""
    if not pipeline_version:
        return False
    result = await session.execute(
        text("SELECT updated_at FROM metaedu.files WHERE id = :fid"),
        {"fid": file_id},
    )
    row = result.mappings().first()
    if not row:
        return True
    current_version = str(row["updated_at"])
    # Normalize both to space-separated, microseconds-truncated for comparison
    is_stale = _pipeline_version_key(current_version) != _pipeline_version_key(pipeline_version)
    if is_stale:
        logger.info(
            "stale-check file=%s pipeline_version=%s current_version=%s → STALE (will abort)",
            file_id, pipeline_version, current_version,
        )
    return is_stale
