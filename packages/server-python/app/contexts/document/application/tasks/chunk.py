"""`chunk_document` Celery task — pipeline step 2 of 6."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.parsing.chunker import Chunk, chunk_by_structure
from app.shared.parsing.pdf_parser import DocumentSection, ParsedDocument
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

            # TD-051: Prefer structured_data["sections"] (new path) over regex
            # reconstruction (legacy). When sections exist, use them directly so
            # section.path / page / level are preserved. When absent (old files
            # uploaded before this fix), fall back to the regex reconstruction.
            raw_sections = sd.get("sections")
            if raw_sections:
                # New path: deserialize from structured_data
                sections = [
                    DocumentSection(
                        title=s.get("title", "") or "",
                        level=s.get("level", 0) or 0,
                        content=s.get("content", "") or "",
                        page=s.get("page", 0) or 0,
                        path=s.get("path", "") or "",
                    )
                    for s in raw_sections
                ]
            else:
                # Legacy path: reconstruct sections from full_text via regex
                sections = []
                if full_text:
                    import re
                    parts = re.split(r'\n(?=##\s)', full_text)
                    for part in parts:
                        part = part.strip()
                        if not part:
                            continue
                        if part.startswith("## "):
                            first_newline = part.index("\n") if "\n" in part else -1
                            if first_newline > 0:
                                title = part[2:first_newline].strip()
                                content = part[first_newline + 1:].strip()
                            else:
                                title = part[2:].strip()
                                content = ""
                            sections.append(
                                DocumentSection(title=title, level=1, content=content, page=0)
                            )
                        elif sections:
                            sections[-1].content += "\n" + part
                        else:
                            sections.append(
                                DocumentSection(title="", level=0, content=part, page=0)
                            )

            # TD-051: compute the absolute offset of each section's content within
            # full_text so that char_start/char_end are globally correct (not
            # reset to 0 at each section boundary).
            #
            # full_text is built as: "## title\ncontent" (titled) or "content" (no title)
            # per section, joined with "\n\n".  We walk through sections sequentially
            # to find each one's starting position.
            section_offsets: list[int] = []
            cursor = 0
            for sec in sections:
                section_offsets.append(cursor)
                if sec.title:
                    # "## title\ncontent\n\n"
                    cursor += 4 + len(sec.title) + 1 + len(sec.content)
                else:
                    cursor += len(sec.content)
                cursor += 2  # "\n\n" separator (over-count on last section is harmless)

            # Process each section independently with its correct offset so
            # char_start/char_end are globally monotonic across the full_text.
            all_chunks: list[Chunk] = []
            for sec, sec_offset in zip(sections, section_offsets, strict=False):
                parsed = ParsedDocument(sections=[sec], full_text=sec.content)
                section_chunks = chunk_by_structure(parsed, section_offset=sec_offset)
                # Re-index relative to the full document
                for c in section_chunks:
                    c.section_path = sec.path
                all_chunks.extend(section_chunks)

            # Re-index chunks globally
            for i, c in enumerate(all_chunks):
                c.index = i
            chunks = all_chunks

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

            # TD-057 fix: return the chunk count so the outer
            # `asyncio.run(_run_in_session(_do))` call (L204) can
            # propagate the int back to the caller. Previously
            # this function returned None — silently swallowed
            # the result. Same pattern as TD-055 / TD-056.
            return len(chunks)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()
            raise

    # TD-057 fix: capture asyncio.run's return value.
    return asyncio.run(_run_in_session(_do))
