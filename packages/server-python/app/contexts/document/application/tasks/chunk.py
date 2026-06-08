"""`chunk_document` Celery task — pipeline step 2 of 6."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

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


@shared_task(name="chunk_document")
def chunk_document(file_id_str: str, tenant_id_str: str, pipeline_version: str = ""):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id=file_id, task_type="chunk")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Abort if pipeline is stale
            if await _check_pipeline_stale(session, file_id, pipeline_version):
                logger.info("chunk_document %s: stale pipeline, aborting", file_id)
                await _update_task_status(
                    session, task_id, "failed", 0, "Stale: reinitialize was called"
                )
                await session.commit()
                return

            # Read parsed data
            result = await session.execute(
                text(
                    "SELECT structured_data FROM metaedu.files WHERE id = :fid AND tenant_id = :tid"
                ),
                {"fid": file_id, "tid": tenant_id},
            )
            row = result.mappings().first()
            if not row or not row["structured_data"]:
                raise ValueError("No parsed data found for file")

            # Handle both dict (new) and string (legacy) storage
            sd = row["structured_data"]
            if isinstance(sd, str):
                sd = json.loads(sd)
            if not isinstance(sd, dict):
                raise ValueError("No parsed data found for file")

            full_text = sd.get("full_text", "") or ""
            from app.shared.parsing.chunker import chunk_by_structure
            from app.shared.parsing.pdf_parser import DocumentSection, ParsedDocument

            # Reconstruct sections from full_text (which has markdown ## headings)
            # Format: "## 标题\n内容\n\n## 标题2\n内容2"
            sections = []
            if full_text:
                # Split on ## headings (at line start only)
                import re
                parts = re.split(r'\n(?=##\s)', full_text)
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    if part.startswith("## "):
                        # "## 标题\n内容" format
                        first_newline = part.index("\n") if "\n" in part else -1
                        if first_newline > 0:
                            title = part[2:first_newline].strip()
                            content = part[first_newline + 1:].strip()
                        else:
                            # Heading without content (e.g., at end of text)
                            title = part[2:].strip()
                            content = ""
                        sections.append(
                            DocumentSection(title=title, level=1, content=content, page=0)
                        )
                    elif sections:
                        # Continuation of previous section (indented content without heading)
                        sections[-1].content += "\n" + part
                    else:
                        # No heading at all, treat as first section
                        sections.append(DocumentSection(title="", level=0, content=part, page=0))

            parsed = ParsedDocument(sections=sections, full_text=full_text)
            chunks = chunk_by_structure(parsed)

            # Abort if pipeline became stale while processing
            if await _check_pipeline_stale(session, file_id, pipeline_version):
                logger.info("chunk_document %s: stale after chunking, aborting", file_id)
                await _update_task_status(
                    session, task_id, "failed", 0, "Stale: reinitialize was called"
                )
                await session.commit()
                return

            # Delete old chunks
            await session.execute(
                text(
                    "DELETE FROM metaedu.document_chunks "
                    "WHERE file_id = :fid AND tenant_id = :tid"
                ),
                {"fid": file_id, "tid": tenant_id},
            )

            # Bulk insert new chunks
            now = datetime.now(UTC).replace(tzinfo=None)
            for chunk in chunks:
                chunk_id = uuid.uuid4()
                await session.execute(
                    text(
                        "INSERT INTO metaedu.document_chunks "
                        "(id, tenant_id, file_id, chunk_index, content, "
                        "section_title, section_path, char_start, char_end, created_at) "
                        "VALUES (:id, :tid, :fid, :idx, :content, "
                        ":stitle, :spath, :cstart, :cend, :now)"
                    ),
                    {
                        "id": chunk_id,
                        "tid": tenant_id,
                        "fid": file_id,
                        "idx": chunk.index,
                        "content": chunk.content,
                        "stitle": chunk.section_title,
                        "spath": chunk.section_path,
                        "cstart": chunk.char_start,
                        "cend": chunk.char_end,
                        "now": now,
                    },
                )

            await _update_task_status(session, task_id, "success", 100)

            # Chain to next task
            from .embed import embed_chunks

            embed_chunks.delay(file_id_str, tenant_id_str, pipeline_version)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()
            raise

    asyncio.run(_run_in_session(_do))
