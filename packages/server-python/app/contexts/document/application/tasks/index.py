"""`index_tsvector` Celery task — pipeline step 4 of 6."""

from __future__ import annotations

import logging
import uuid

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.tasks.lifecycle import (
    _create_task,
    _run_in_session,
    _update_task_status,
)

from .pipeline_guard import _check_pipeline_stale

logger = logging.getLogger(__name__)


@shared_task(name="index_tsvector")
def index_tsvector(file_id_str: str, tenant_id_str: str, pipeline_version: str = ""):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id=file_id, task_type="index_tsv")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Abort if pipeline is stale
            if await _check_pipeline_stale(session, file_id, pipeline_version):
                logger.info("index_tsvector %s: stale pipeline, aborting", file_id)
                await _update_task_status(
                    session, task_id, "failed", 0, "Stale: reinitialize was called"
                )
                await session.commit()
                return

            result = await session.execute(
                text(
                    "SELECT id FROM metaedu.document_chunks "
                    "WHERE file_id = :fid AND tenant_id = :tid ORDER BY chunk_index"
                ),
                {"fid": file_id, "tid": tenant_id},
            )
            chunk_ids = [row["id"] for row in result.mappings().all()]

            for chunk_id in chunk_ids:
                await session.execute(
                    text(
                        "UPDATE metaedu.document_chunks "
                        "SET content_tsvector = to_tsvector('chinese_zh', content) "
                        "WHERE id = :cid"
                    ),
                    {"cid": chunk_id},
                )

            # Re-check staleness before updating file status to 'processed'
            if await _check_pipeline_stale(session, file_id, pipeline_version):
                logger.info("index_tsvector %s: stale before status update, aborting", file_id)
                await _update_task_status(
                    session, task_id, "failed", 0, "Stale: reinitialize was called"
                )
                await session.commit()
                return

            # Update file status to processed — NOT updated_at (only reinitialize changes that)
            await session.execute(
                text(
                    "UPDATE metaedu.files SET status = 'processed' WHERE id = :fid"
                ),
                {"fid": file_id},
            )

            await _update_task_status(session, task_id, "success", 100)

            # Always chain to extract_template (does LLM summarization if no template defined)
            from .extract_template import extract_template

            extract_template.delay(file_id_str, tenant_id_str, pipeline_version)

            # TD-060 fix: return the indexed chunk count so the
            # outer `asyncio.run(_run_in_session(_do))` call can
            # propagate the int back to the caller. Same pattern
            # as TD-055 / TD-056 / TD-057 / TD-058 / TD-059.
            return len(chunk_ids)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()
            raise

    # TD-060 fix: capture asyncio.run's return value.
    return asyncio.run(_run_in_session(_do))
