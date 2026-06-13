"""TD-051 historical data rebuild + orphan chunk cleanup tasks.

``rebuild_document_chunks``: re-chunks already-parsed files using the post-TD-051
strategy. Unlike ``chunk_document``, this task skips the pipeline-stale check
(rebuild is intentional) and does not chain to ``embed_chunks`` automatically,
giving operators control over sequencing.

``cleanup_orphan_chunks``: deletes chunks whose ``file_id`` has no corresponding
entry in ``files`` — removes the ~100 orphan chunks observed in production data.
"""

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
from app.shared.tasks.lifecycle import _create_task, _run_in_session, _update_task_status

logger = logging.getLogger(__name__)


@shared_task(name="rebuild_document_chunks")
def rebuild_document_chunks(
    file_id_str: str,
    tenant_id_str: str,
    chain_embed: bool = False,
):
    """Re-chunk a file using the current (TD-051) strategy.

    Args:
        file_id_str: UUID of the file to rebuild.
        tenant_id_str: UUID of the tenant.
        chain_embed: If True, chain to embed_chunks after rebuilding chunks.
                     Default False (operator triggers embedding manually).
    """
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(
            session, tenant_id, file_id=file_id, task_type="chunk"
        )
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Read structured_data (may or may not have sections key)
            result = await session.execute(
                text(
                    "SELECT structured_data FROM metaedu.files "
                    "WHERE id = :fid AND tenant_id = :tid"
                ),
                {"fid": file_id, "tid": tenant_id},
            )
            row = result.mappings().first()
            if not row or not row["structured_data"]:
                raise ValueError("No structured_data found for file — parse first")

            sd = row["structured_data"]
            if isinstance(sd, str):
                sd = json.loads(sd)
            if not isinstance(sd, dict):
                raise ValueError("structured_data is not a dict")

            full_text = sd.get("full_text", "") or ""

            # Prefer structured_data["sections"] (TD-051 new path)
            raw_sections = sd.get("sections")
            if raw_sections:
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
                # Legacy: reconstruct from full_text (better than nothing)
                sections = _reconstruct_sections_from_full_text(full_text)

            # Compute absolute offsets per section
            section_offsets: list[int] = []
            cursor = 0
            for sec in sections:
                section_offsets.append(cursor)
                if sec.title:
                    cursor += 4 + len(sec.title) + 1 + len(sec.content)
                else:
                    cursor += len(sec.content)
                cursor += 2  # "\n\n" separator

            # Chunk each section with correct offsets
            all_chunks: list[Chunk] = []
            for sec, sec_offset in zip(sections, section_offsets, strict=False):
                parsed = ParsedDocument(sections=[sec], full_text=sec.content)
                section_chunks = chunk_by_structure(parsed, section_offset=sec_offset)
                for c in section_chunks:
                    c.section_path = sec.path
                all_chunks.extend(section_chunks)

            for i, c in enumerate(all_chunks):
                c.index = i

            # Delete old chunks
            await session.execute(
                text(
                    "DELETE FROM metaedu.document_chunks "
                    "WHERE file_id = :fid AND tenant_id = :tid"
                ),
                {"fid": file_id, "tid": tenant_id},
            )

            # Insert rebuilt chunks
            now = datetime.now(UTC).replace(tzinfo=None)
            for chunk in all_chunks:
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
            await session.commit()

            logger.info(
                "rebuild_document_chunks %s: rebuilt %d chunks (chain_embed=%s)",
                file_id,
                len(all_chunks),
                chain_embed,
            )

            # Optionally chain to embed
            if chain_embed:
                from .embed import embed_chunks

                embed_chunks.delay(file_id_str, tenant_id_str)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()
            raise

    asyncio.run(_run_in_session(_do))


def _reconstruct_sections_from_full_text(full_text: str) -> list[DocumentSection]:
    """Fallback: reconstruct sections from full_text via regex.

    Mirrors the legacy chunk_document section reconstruction.
    Used when structured_data has no sections key (files uploaded before TD-051).

    TD-053: also synthesizes a hierarchical `path` (e.g. "0/0", "0/1", "1/0")
    per level-1 heading index, so legacy data gets meaningful paths
    instead of the default DocumentSection.path = "". The path format
    is "L1_index" — single-level because the regex only matches "## "
    (level 1); a future enhancement to detect nested headings would
    extend this to "L1/L2/...".
    """
    import re

    sections: list[DocumentSection] = []
    if not full_text:
        return sections

    parts = re.split(r'\n(?=##\s)', full_text)
    sibling_index = 0
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
            # TD-053: synthesise a non-empty hierarchical path for legacy data.
            # Format: "<sibling_index>" (level-1 only since regex matches "## ").
            path = f"{sibling_index}"
            sections.append(
                DocumentSection(
                    title=title, level=1, content=content, page=0, path=path
                )
            )
            sibling_index += 1
        elif sections:
            sections[-1].content += "\n" + part
        else:
            sections.append(
                DocumentSection(title="", level=0, content=part, page=0, path="")
            )

    return sections


@shared_task(name="cleanup_orphan_chunks")
def cleanup_orphan_chunks(tenant_id_str: str):
    """Delete chunks whose file_id has no corresponding entry in files.

    TD-051 AC-6: removes 100 orphan chunks observed in production data.
    Safe to run multiple times — deletes zero rows once orphans are cleared.
    """
    import asyncio

    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        result = await session.execute(
            text(
                "DELETE FROM metaedu.document_chunks "
                "WHERE tenant_id = :tid "
                "AND file_id NOT IN (SELECT id FROM metaedu.files WHERE tenant_id = :tid)"
            ),
            {"tid": tenant_id},
        )
        await session.commit()
        deleted = result.rowcount
        logger.info(
            "cleanup_orphan_chunks tenant=%s: deleted %d orphan chunks", tenant_id, deleted
        )
        return deleted

    # TD-055: capture asyncio.run's return value so direct (non-Celery)
    # callers see the deleted count instead of None. `_do` returns the
    # SQL DELETE rowcount; `run_in_session` already passes it through;
    # the previous outer `asyncio.run(_run_in_session(_do))` call dropped
    # it on the floor.
    return asyncio.run(_run_in_session(_do))
