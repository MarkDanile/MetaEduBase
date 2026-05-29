"""Document processing Celery tasks — 6-step pipeline.

Pipeline: parse → chunk → embed → index_tsv → extract_template → extract_kg

Embedding uses DashScope (BAAI/bge-m3) — 国内模型.
LLM uses Qwen/DeepSeek via OpenAI-compatible API — 国内模型.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.contexts.template.infrastructure.repository import TemplateRepositoryImpl

logger = logging.getLogger(__name__)


def _get_sync_session():
    """Create a synchronous DB session for Celery tasks (which run in their own event loop)."""

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    class _SyncSession:
        def __init__(self):
            self._engine = engine
            self._session: AsyncSession | None = None

        async def __aenter__(self):
            self._session = factory()
            return self._session

        async def __aexit__(self, *exc):
            if self._session:
                await self._session.close()
            await self._engine.dispose()

    return _SyncSession()


async def _run_in_session(coro):
    """Run an async coroutine with a DB session, handling commit/rollback."""
    async with _get_sync_session() as session:
        try:
            result = await coro(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


async def _update_task_status(
    session: AsyncSession,
    task_id: uuid.UUID,
    status: str,
    progress: int = 0,
    error_message: str | None = None,
):
    now = datetime.now(UTC).replace(tzinfo=None)
    sets = ["status = :status", "progress = :progress", "updated_at = :now"]
    params = {"tid": task_id, "status": status, "progress": progress, "now": now}
    if status == "running" and progress == 0:
        sets.append("started_at = :now")
    if status in ("success", "failed"):
        sets.append("completed_at = :now")
    if error_message:
        sets.append("error_message = :err")
        params["err"] = error_message
    await session.execute(
        text(f"UPDATE metaedu.document_tasks SET {', '.join(sets)} WHERE id = :tid"),
        params,
    )


async def _create_task(
    session: AsyncSession, tenant_id: uuid.UUID, file_id: uuid.UUID, task_type: str
) -> uuid.UUID:
    task_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await session.execute(
        text(
            "INSERT INTO metaedu.document_tasks "
            "(id, tenant_id, file_id, task_type, status, progress, created_at) "
            "VALUES (:id, :tid, :fid, :type, 'pending', 0, :now)"
        ),
        {"id": task_id, "tid": tenant_id, "fid": file_id, "type": task_type, "now": now},
    )
    return task_id


# --- Task 1: Parse document ---


def _pipeline_version_key(ts: str | None) -> str:
    """Normalize datetime to space-separated string for comparison.

    Python's datetime.isoformat() uses 'T' separator (2026-05-18T06:46:54.604460)
    but PostgreSQL's text output uses space (2026-05-18 06:46:54.604460).
    """
    if not ts:
        return ""
    return ts.replace("T", " ").split(".")[0]


async def _check_pipeline_stale(session: AsyncSession, file_id: uuid.UUID, pipeline_version: str) -> bool:
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
            task_id = await _create_task(session, tenant_id, file_id, "parse")
            await _update_task_status(session, task_id, "failed", 0, f"File {file_id} not found")
            await session.commit()
            return

        task_id = await _create_task(session, tenant_id, file_id, "parse")
        created_task_id = task_id
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Abort if pipeline is stale (reinitialize was called)
            if await _check_pipeline_stale(session, file_id, pipeline_version):
                logger.info("parse_document %s: stale pipeline, aborting", file_id)
                await _update_task_status(session, task_id, "failed", 0, "Stale: reinitialize was called")
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
                await _update_task_status(session, task_id, "failed", 0, "Stale: reinitialize was called")
                await session.commit()
                return

            # Store full_text in file's structured_data — NOT updated_at
            # (only reinitialize changes updated_at, used as pipeline version marker)
            await session.execute(
                text(
                    "UPDATE metaedu.files "
                    "SET structured_data = CAST(:data AS JSONB), "
                    "status = 'processing' "
                    "WHERE id = :fid"
                ),
                {
                    "data": json.dumps({
                        "full_text": parsed.full_text,
                        "section_count": len(parsed.sections),
                    }),
                    "fid": file_id,
                },
            )
            await _update_task_status(session, task_id, "success", 100)

            # Chain to next task (pass version forward)
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


# --- Task 2: Chunk document ---


@shared_task(name="chunk_document")
def chunk_document(file_id_str: str, tenant_id_str: str, pipeline_version: str = ""):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id, "chunk")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Abort if pipeline is stale
            if await _check_pipeline_stale(session, file_id, pipeline_version):
                logger.info("chunk_document %s: stale pipeline, aborting", file_id)
                await _update_task_status(session, task_id, "failed", 0, "Stale: reinitialize was called")
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
                await _update_task_status(session, task_id, "failed", 0, "Stale: reinitialize was called")
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
            embed_chunks.delay(file_id_str, tenant_id_str, pipeline_version)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 3: Embed chunks (DashScope bge-m3) ---


@shared_task(name="embed_chunks")
def embed_chunks(file_id_str: str, tenant_id_str: str, pipeline_version: str = ""):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id, "embed")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Abort if pipeline is stale
            if await _check_pipeline_stale(session, file_id, pipeline_version):
                logger.info("embed_chunks %s: stale pipeline, aborting", file_id)
                await _update_task_status(session, task_id, "failed", 0, "Stale: reinitialize was called")
                await session.commit()
                return

            result = await session.execute(
                text(
                    "SELECT id, content FROM metaedu.document_chunks "
                    "WHERE file_id = :fid AND tenant_id = :tid AND embedding IS NULL "
                    "ORDER BY chunk_index"
                ),
                {"fid": file_id, "tid": tenant_id},
            )
            chunks = result.mappings().all()
            total = len(chunks)

            import httpx

            if not chunks:
                await _update_task_status(session, task_id, "success", 100)
                index_tsvector.delay(file_id_str, tenant_id_str, pipeline_version)
                return

            # Batch embedding — SiliconFlow supports batch input
            texts = [chunk["content"][:8192] for chunk in chunks]

            async def batch_embed_siliconflow(texts: list[str]) -> list[list[float]] | None:
                if not settings.siliconflow_api_key:
                    return None
                try:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        resp = await client.post(
                            f"{settings.siliconflow_base_url}/embeddings",
                            headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
                            json={"model": settings.siliconflow_embedding_model, "input": texts},
                        )
                        resp.raise_for_status()
                        return [item["embedding"] for item in resp.json()["data"]]
                except Exception as e:
                    logger.warning(f"SiliconFlow batch embedding failed: {e}")
                    return None

            async def batch_embed_minimax(texts: list[str]) -> list[list[float]] | None:
                if not settings.minimax_api_key:
                    return None
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        resp = await client.post(
                            f"{settings.minimax_base_url}/embeddings",
                            headers={"Authorization": f"Bearer {settings.minimax_api_key}"},
                            json={"model": settings.minimax_embedding_model, "input": texts},
                        )
                        resp.raise_for_status()
                        return [item["embedding"] for item in resp.json()["data"]]
                except Exception as e:
                    logger.warning(f"MiniMax batch embedding failed: {e}")
                    return None

            # Try MiniMax batch first, fallback to SiliconFlow batch
            embeddings = await batch_embed_minimax(texts)
            if not embeddings:
                embeddings = await batch_embed_siliconflow(texts)

            if not embeddings:
                logger.error("All embedding providers failed for all %d chunks (file=%s)", total, file_id)
                await _update_task_status(session, task_id, "failed", 0, "Embedding API failed: MiniMax and SiliconFlow both returned no results")
                await session.commit()
                return

            # Batch update all chunks
            for chunk, embedding in zip(chunks, embeddings):
                vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
                await session.execute(
                    text("UPDATE metaedu.document_chunks SET embedding = :vec WHERE id = :cid"),
                    {"vec": vec_str, "cid": chunk["id"]},
                )

            await _update_task_status(session, task_id, "running", 90)
            await session.commit()

            await _update_task_status(session, task_id, "success", 100)

            # Chain to next task
            index_tsvector.delay(file_id_str, tenant_id_str, pipeline_version)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 4: Index tsvector ---


@shared_task(name="index_tsvector")
def index_tsvector(file_id_str: str, tenant_id_str: str, pipeline_version: str = ""):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id, "index_tsv")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Abort if pipeline is stale
            if await _check_pipeline_stale(session, file_id, pipeline_version):
                logger.info("index_tsvector %s: stale pipeline, aborting", file_id)
                await _update_task_status(session, task_id, "failed", 0, "Stale: reinitialize was called")
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
                        "SET content_tsvector = to_tsvector('simple', content) "
                        "WHERE id = :cid"
                    ),
                    {"cid": chunk_id},
                )

            # Re-check staleness before updating file status to 'processed'
            if await _check_pipeline_stale(session, file_id, pipeline_version):
                logger.info("index_tsvector %s: stale before status update, aborting", file_id)
                await _update_task_status(session, task_id, "failed", 0, "Stale: reinitialize was called")
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
            extract_template.delay(file_id_str, tenant_id_str, pipeline_version)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 5: Extract template (教案/教学设计) ---


@shared_task(name="extract_template")
def extract_template(file_id_str: str, tenant_id_str: str, pipeline_version: str = ""):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id, "extract_template")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Note: extract_template skips stale check — it's idempotent and runs at
            # the end of the pipeline. The stale check (comparing updated_at) is
            # unreliable here because upstream tasks (index_tsvector) may have
            # already updated updated_at to mark the pipeline as done.

            # Get chunks content and doc_type hint
            result = await session.execute(
                text(
                    "SELECT dc.content, f.doc_type "
                    "FROM metaedu.document_chunks dc "
                    "JOIN metaedu.files f ON f.id = dc.file_id "
                    "WHERE dc.file_id = :fid AND dc.tenant_id = :tid "
                    "ORDER BY dc.chunk_index LIMIT 10"
                ),
                {"fid": file_id, "tid": tenant_id},
            )
            rows = result.mappings().all()
            chunks_text = "\n".join(row["content"] for row in rows)
            doc_type = rows[0]["doc_type"] if rows else None

            # Query template by doc_type, fall back to default prompt if not found
            template_obj = await TemplateRepositoryImpl(session).get_by_doc_type(doc_type, tenant_id) if doc_type else None

            # Build prompt: use template.ai_prompt > template.fields > default
            if template_obj and template_obj.ai_prompt:
                prompt_template = template_obj.ai_prompt
            elif template_obj and template_obj.fields:
                fields_desc = ", ".join(f["key"] + (f"({f['label']})" if f.get("label") else "") for f in [f.to_dict() if hasattr(f, 'to_dict') else f for f in template_obj.fields])
                prompt_template = (
                    f"请从以下文档内容中提取JSON格式的结构化信息，将所有字段翻译为中文，只返回JSON不要任何解释：\n"
                    f"字段：{fields_desc}\n\n"
                    f"内容：\n{chunks_text[:6000]}"
                )
            elif doc_type == "教案":
                prompt_template = (
                    "请从以下教案内容中提取JSON格式的结构化信息，将所有字段翻译为中文，只返回JSON不要任何解释：\n"
                    "字段：course_name(课程名), chapter(章节), objectives[教学目标数组], key_points[重点数组], difficulties[难点数组], methods[教学方法数组], duration(课时)\n\n"
                    f"内容：\n{chunks_text[:6000]}"
                )
            else:
                prompt_template = (
                    "请对以下文档内容提取结构化摘要，将所有字段翻译为中文，只返回JSON不要任何解释：\n"
                    "字段：title(中文标题), summary(100字内中文摘要), sections[中文章节列表], key_points[中文关键要点], keywords[中文关键词最多5个]\n\n"
                    f"内容：\n{chunks_text[:6000]}"
                )

            # Call LLM (MiniMax via OpenAI-compatible API)
            api_key = settings.minimax_api_key
            base_url = settings.minimax_base_url
            model = settings.minimax_model

            template_data = {}
            if api_key:
                import httpx

                prompt = prompt_template

                def try_parse(content: str) -> dict:
                    import re as regexmod
                    # Strip MiniMax-M2 thinking tags that may appear before JSON
                    stripped = regexmod.sub(r"<think>.*?</think>", "", content, flags=regexmod.DOTALL).strip()
                    m = regexmod.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, regexmod.DOTALL)
                    if m:
                        try:
                            return json.loads(m.group(1))
                        except json.JSONDecodeError:
                            pass
                    try:
                        json_start = stripped.index("{")
                        json_end = stripped.rindex("}") + 1
                        return json.loads(stripped[json_start:json_end])
                    except (ValueError, json.JSONDecodeError):
                        return {}

                # Try MiniMax first
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        resp = await client.post(
                            f"{base_url}/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}"},
                            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
                        )
                        resp.raise_for_status()
                        content = resp.json()["choices"][0]["message"]["content"]
                        template_data = try_parse(content)
                except Exception as e:
                    logger.warning(f"extract_template MiniMax failed: {e}")

                # Fallback to SiliconFlow (use chat model, not embedding model)
                if not template_data and settings.siliconflow_api_key:
                    try:
                        async with httpx.AsyncClient(timeout=60.0) as client:
                            resp = await client.post(
                                f"{settings.siliconflow_base_url}/chat/completions",
                                headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
                                json={
                                    "model": "Qwen/Qwen2.5-7B-Instruct",
                                    "messages": [{"role": "user", "content": prompt}],
                                    "temperature": 0.1,
                                },
                            )
                            resp.raise_for_status()
                            content = resp.json()["choices"][0]["message"]["content"]
                            template_data = try_parse(content)
                    except Exception as e:
                        logger.warning(f"extract_template SiliconFlow failed: {e}")

            if not template_data:
                logger.warning("extract_template: LLM returned no template data for file=%s (chunks=%d)", file_id, len(rows))

            # Save to file structured_data
            result = await session.execute(
                text("SELECT structured_data FROM metaedu.files WHERE id = :fid"),
                {"fid": file_id},
            )
            existing = result.mappings().first()
            existing_raw = existing["structured_data"] if existing and existing["structured_data"] else "{}"
            if isinstance(existing_raw, str):
                existing_data = json.loads(existing_raw)
            else:
                existing_data = dict(existing_raw)
            existing_data["template"] = template_data

            await session.execute(
                text(
                    "UPDATE metaedu.files SET structured_data = CAST(:data AS JSONB) WHERE id = :fid"
                ),
                {
                    "data": json.dumps(existing_data),
                    "fid": file_id,
                },
            )

            await _update_task_status(session, task_id, "success", 100)

            # Chain to KG extraction
            extract_knowledge_graph.delay(file_id_str, tenant_id_str, pipeline_version)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 6: Extract knowledge graph ---


@shared_task(name="extract_knowledge_graph")
def extract_knowledge_graph(file_id_str: str, tenant_id_str: str, pipeline_version: str = ""):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id, "extract_kg")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Note: extract_knowledge_graph skips stale check — it's idempotent and
            # downstream. Removing the updated_at-based stale check avoids false
            # positives from index_tsvector marking the file as processed.

            # Get chunks with embeddings
            result = await session.execute(
                text(
                    "SELECT id, content, section_title FROM metaedu.document_chunks "
                    "WHERE file_id = :fid AND tenant_id = :tid ORDER BY chunk_index LIMIT 20"
                ),
                {"fid": file_id, "tid": tenant_id},
            )
            chunks = result.mappings().all()

            if not chunks:
                await _update_task_status(session, task_id, "success", 100)
                return

            # Call LLM to extract entities and relations (MiniMax)
            api_key = settings.minimax_api_key
            base_url = settings.minimax_base_url
            model = settings.minimax_model

            if api_key:
                import httpx

                chunks_text = "\n".join(
                    f"[{c['section_title'] or '段落'}] {c['content'][:500]}" for c in chunks
                )
                prompt = (
                    "请从以下文本中提取知识实体和关系，将所有实体名称翻译为中文，只返回JSON不要任何解释：\n"
                    '{"entities": [{"name": "中文实体名", "type": "类型"}], '
                    '"relations": [{"source": "中文实体1", "target": "中文实体2", "relation": "关系描述"}]}\n\n'
                    f"文本：\n{chunks_text[:6000]}"
                )
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.1,
                        },
                    )
                    resp.raise_for_status()
                    content = resp.json()["choices"][0]["message"]["content"]
                    import re as regexmod
                    stripped = regexmod.sub(r"<think>.*?</think>", "", content, flags=regexmod.DOTALL).strip()
                    kg_data = {"entities": [], "relations": []}
                    m = regexmod.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, regexmod.DOTALL)
                    if m:
                        try:
                            kg_data = json.loads(m.group(1))
                        except json.JSONDecodeError:
                            pass
                    if not kg_data.get("entities"):
                        try:
                            json_start = stripped.index("{")
                            json_end = stripped.rindex("}") + 1
                            kg_data = json.loads(stripped[json_start:json_end])
                        except (ValueError, json.JSONDecodeError):
                            logger.warning("KG extraction JSON parse failed, raw content: %s", content[:300])

                # Fallback to SiliconFlow if MiniMax returned empty
                if not kg_data.get("entities") and settings.siliconflow_api_key:
                    try:
                        async with httpx.AsyncClient(timeout=60.0) as client:
                            resp = await client.post(
                                f"{settings.siliconflow_base_url}/chat/completions",
                                headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
                                json={
                                    "model": "Qwen/Qwen3-8B",
                                    "messages": [{"role": "user", "content": prompt}],
                                    "temperature": 0.1,
                                },
                            )
                            resp.raise_for_status()
                            content = resp.json()["choices"][0]["message"]["content"]
                            m = regexmod.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, regexmod.DOTALL)
                            if m:
                                kg_data = json.loads(m.group(1))
                            else:
                                try:
                                    json_start = content.index("{")
                                    json_end = content.rindex("}") + 1
                                    kg_data = json.loads(content[json_start:json_end])
                                except (ValueError, json.JSONDecodeError):
                                    logger.warning("KG extraction SiliconFlow JSON parse failed: %s", content[:300])
                    except Exception as e:
                        logger.warning("KG extraction SiliconFlow fallback failed: %s", e)

                # Write entities to knowledge_nodes with source tracking
                # Build name→id map so relations can reference nodes by name
                node_name_map: dict[str, uuid.UUID] = {}
                for entity in kg_data.get("entities", []):
                    name = entity.get("name", "")
                    if not name:
                        continue
                    node_id = uuid.uuid4()
                    node_name_map[name] = node_id
                    # Store normalized forms too
                    node_name_map[name.strip().strip('"')] = node_id

                    await session.execute(
                        text(
                            "INSERT INTO metaedu.knowledge_nodes "
                            "(id, tenant_id, title, description, domain, level, path, source_file_id, created_at, updated_at) "
                            "VALUES (:id, :tid, :title, '', 'education_sports', 'knowledge_point', :path, :fid, :now, :now)"
                        ),
                        {
                            "id": node_id,
                            "tid": tenant_id,
                            "title": name,
                            "path": str(node_id)[:8],
                            "fid": file_id,
                            "now": datetime.now(UTC).replace(tzinfo=None),
                        },
                    )

                # Insert edges — source/target are entity names, resolve to node IDs
                # Priority: exact match > stripped match > substring match (case-insensitive)
                def find_node_id(raw_name: str) -> uuid.UUID | None:
                    name = raw_name.strip().strip('"')
                    if name in node_name_map:
                        return node_name_map[name]
                    # Substring match: entity name is contained in the relation reference
                    name_lower = name.lower()
                    for entity_name, nid in node_name_map.items():
                        if entity_name.lower() == name_lower:
                            return nid
                    for entity_name, nid in node_name_map.items():
                        if name_lower in entity_name.lower() or entity_name.lower() in name_lower:
                            return nid
                    return None

                edges_inserted = 0
                skipped_edges: list[tuple[str, str]] = []
                for rel in kg_data.get("relations", []):
                    src_id = find_node_id(rel.get("source", ""))
                    tgt_id = find_node_id(rel.get("target", ""))
                    if not src_id or not tgt_id:
                        skipped_edges.append((rel.get("source", ""), rel.get("target", "")))
                        continue
                    edge_id = uuid.uuid4()
                    await session.execute(
                        text(
                            "INSERT INTO metaedu.knowledge_edges "
                            "(id, tenant_id, source_id, target_id, relation_type, weight, metadata, created_at) "
                            "VALUES (:id, :tid, :src, :tgt, :rtype, :wt, :meta, :now)"
                        ),
                        {
                            "id": edge_id,
                            "tid": tenant_id,
                            "src": src_id,
                            "tgt": tgt_id,
                            "rtype": rel.get("relation", "related"),
                            "wt": 1.0,
                            "meta": json.dumps({}),
                            "now": datetime.now(UTC).replace(tzinfo=None),
                        },
                    )
                    edges_inserted += 1
                logger.info(
                    "KG extraction: %d nodes, %d edges inserted, %d skipped (unmatched: %s)",
                    len(node_name_map), edges_inserted, len(skipped_edges), skipped_edges[:5],
                )

            await _update_task_status(session, task_id, "success", 100)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()  # Commit failure status before re-raising
            raise

    asyncio.run(_run_in_session(_do))
