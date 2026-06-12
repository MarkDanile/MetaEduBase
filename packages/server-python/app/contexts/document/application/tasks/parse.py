"""`parse_document` Celery task — pipeline step 1 of 6."""

from __future__ import annotations

import json
import logging
import os
import uuid

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.shared.tasks.lifecycle import (
    _create_task,
    _run_in_session,
    _update_task_status,
)

from .extract_template_prompts import _build_parsed_structured_data
from .pipeline_guard import _check_pipeline_stale

logger = logging.getLogger(__name__)


@shared_task(name="parse_document")
def parse_document(file_id_str: str, tenant_id_str: str, pipeline_version: str = ""):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        created_task_id: uuid.UUID | None = None

        result = await session.execute(
            text("SELECT * FROM metaedu.files WHERE id = :fid AND tenant_id = :tid"),
            {"fid": file_id, "tid": tenant_id},
        )
        row = result.mappings().first()
        if not row:
            task_id = await _create_task(session, tenant_id, file_id=file_id, task_type="parse")
            await _update_task_status(session, task_id, "failed", 0, f"File {file_id} not found")
            await session.commit()
            return

        task_id = await _create_task(session, tenant_id, file_id=file_id, task_type="parse")
        created_task_id = task_id
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Abort if pipeline is stale (reinitialize was called)
            if await _check_pipeline_stale(session, file_id, pipeline_version):
                logger.info("parse_document %s: stale pipeline, aborting", file_id)
                await _update_task_status(
                    session, task_id, "failed", 0, "Stale: reinitialize was called"
                )
                await session.commit()
                return

            storage_key = row["storage_key"]
            file_type = row["file_type"]
            file_path = os.path.join(settings.upload_dir, storage_key)

            if file_type == "pdf":
                from app.shared.parsing.pdf_parser import extract_pdf_text

                parsed = extract_pdf_text(file_path)
            elif file_type in ("docx", "doc"):
                from app.shared.parsing.docx_parser import extract_docx_text

                parsed = extract_docx_text(file_path)
            else:
                with open(file_path, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                from app.shared.parsing.pdf_parser import DocumentSection, ParsedDocument

                parsed = ParsedDocument(
                    sections=[DocumentSection(title="", level=0, content=content, page=0)],
                    full_text=content,
                )

            # Verify still not stale before writing
            if await _check_pipeline_stale(session, file_id, pipeline_version):
                logger.info("parse_document %s: stale after parsing, aborting", file_id)
                await _update_task_status(
                    session, task_id, "failed", 0, "Stale: reinitialize was called"
                )
                await session.commit()
                return

            # Store full_text in file's structured_data — NOT updated_at
            # (only reinitialize changes updated_at, used as pipeline version marker)
            # TD-051: preserve parser sections so chunk_document can read them directly
            sections_data: list[dict[str, object]] = [
                {
                    "title": s.title,
                    "level": s.level,
                    "path": s.path,
                    "page": s.page,
                    "content": s.content,
                }
                for s in parsed.sections
            ]
            await session.execute(
                text(
                    "UPDATE metaedu.files "
                    "SET structured_data = CAST(:data AS JSONB), "
                    "status = 'processing' "
                    "WHERE id = :fid"
                ),
                {
                    "data": json.dumps(
                        _build_parsed_structured_data(
                            parsed.full_text,
                            len(parsed.sections),
                            sections_data,
                        )
                    ),
                    "fid": file_id,
                },
            )
            await _update_task_status(session, task_id, "success", 100)

            # Chain to next task (pass version forward)
            from .chunk import chunk_document

            chunk_document.delay(file_id_str, tenant_id_str, pipeline_version)

        except Exception as e:
            if created_task_id:
                try:
                    await _update_task_status(session, created_task_id, "failed", 0, str(e))
                    await session.execute(
                        text(
                            "UPDATE metaedu.files SET status = 'failed' WHERE id = :fid"
                        ),
                        {"fid": file_id},
                    )
                    await session.commit()
                except Exception:
                    pass  # Status update failed, don't hide original error
            raise

    try:
        asyncio.run(_run_in_session(_do))
    except Exception:
        raise  # Celery will mark task as FAILED
