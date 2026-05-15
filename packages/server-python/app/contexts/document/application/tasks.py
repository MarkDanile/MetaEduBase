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
            "INSERT INTO metaedu.document_tasks (id, tenant_id, file_id, task_type, status, progress, created_at) "
            "VALUES (:id, :tid, :fid, :type, 'pending', 0, :now)"
        ),
        {"id": task_id, "tid": tenant_id, "fid": file_id, "type": task_type, "now": now},
    )
    return task_id


# --- Task 1: Parse document ---


@shared_task(name="parse_document")
def parse_document(file_id_str: str, tenant_id_str: str):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        # Get file record
        result = await session.execute(
            text("SELECT * FROM metaedu.files WHERE id = :fid AND tenant_id = :tid"),
            {"fid": file_id, "tid": tenant_id},
        )
        row = result.mappings().first()
        if not row:
            raise ValueError(f"File {file_id} not found")

        # Create task record
        task_id = await _create_task(session, tenant_id, file_id, "parse")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
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
                # Fallback: read as plain text
                with open(file_path, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                from app.shared.parsing.pdf_parser import DocumentSection, ParsedDocument

                parsed = ParsedDocument(
                    sections=[DocumentSection(title="", level=0, content=content, page=0)],
                    full_text=content,
                )

            # Store full_text in file's structured_data
            await session.execute(
                text(
                    "UPDATE metaedu.files SET structured_data = :data::jsonb, status = 'processing', updated_at = :now WHERE id = :fid"
                ),
                {
                    "data": json.dumps(
                        {"full_text": parsed.full_text, "section_count": len(parsed.sections)}
                    ),
                    "now": datetime.now(UTC).replace(tzinfo=None),
                    "fid": file_id,
                },
            )
            await _update_task_status(session, task_id, "success", 100)

            # Chain to next task
            chunk_document.delay(file_id_str, tenant_id_str)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.execute(
                text(
                    "UPDATE metaedu.files SET status = 'failed', updated_at = :now WHERE id = :fid"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None), "fid": file_id},
            )
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 2: Chunk document ---


@shared_task(name="chunk_document")
def chunk_document(file_id_str: str, tenant_id_str: str):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id, "chunk")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
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

            full_text = row["structured_data"].get("full_text", "")
            from app.shared.parsing.chunker import chunk_by_structure
            from app.shared.parsing.pdf_parser import DocumentSection, ParsedDocument

            # Rebuild a minimal ParsedDocument from stored text
            parsed = ParsedDocument(
                sections=[DocumentSection(title="", level=0, content=full_text, page=0)],
                full_text=full_text,
            )
            chunks = chunk_by_structure(parsed)

            # Delete old chunks
            await session.execute(
                text(
                    "DELETE FROM metaedu.document_chunks WHERE file_id = :fid AND tenant_id = :tid"
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
                        "(id, tenant_id, file_id, chunk_index, content, section_title, section_path, char_start, char_end, created_at) "
                        "VALUES (:id, :tid, :fid, :idx, :content, :stitle, :spath, :cstart, :cend, :now)"
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
            embed_chunks.delay(file_id_str, tenant_id_str)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 3: Embed chunks (DashScope bge-m3) ---


@shared_task(name="embed_chunks")
def embed_chunks(file_id_str: str, tenant_id_str: str):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id, "embed")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
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

            api_key = settings.qwen_api_key or os.environ.get("DASHSCOPE_API_KEY", "")
            if not api_key:
                logger.warning("No DashScope API key, skipping embedding")
                await _update_task_status(session, task_id, "success", 100)
                index_tsvector.delay(file_id_str, tenant_id_str)
                return

            import httpx

            for i, chunk in enumerate(chunks):
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(
                            f"{settings.qwen_base_url}/embeddings",
                            headers={"Authorization": f"Bearer {api_key}"},
                            json={
                                "model": settings.embedding_model,
                                "input": [chunk["content"][:8192]],
                            },
                        )
                        resp.raise_for_status()
                        embedding = resp.json()["data"][0]["embedding"]
                        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
                        await session.execute(
                            text(
                                "UPDATE metaedu.document_chunks SET embedding = :vec::vector WHERE id = :cid"
                            ),
                            {"vec": vec_str, "cid": chunk["id"]},
                        )
                except Exception as e:
                    logger.warning(f"Embedding failed for chunk {chunk['id']}: {e}")

                progress = int((i + 1) / total * 100) if total > 0 else 100
                await _update_task_status(session, task_id, "running", progress)
                await session.commit()

            await _update_task_status(session, task_id, "success", 100)

            # Chain to next task
            index_tsvector.delay(file_id_str, tenant_id_str)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 4: Index tsvector ---


@shared_task(name="index_tsvector")
def index_tsvector(file_id_str: str, tenant_id_str: str):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id, "index_tsv")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
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
                        "UPDATE metaedu.document_chunks SET content_tsvector = to_tsvector('simple', content) WHERE id = :cid"
                    ),
                    {"cid": chunk_id},
                )

            # Update file status to processed
            await session.execute(
                text(
                    "UPDATE metaedu.files SET status = 'processed', updated_at = :now WHERE id = :fid"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None), "fid": file_id},
            )

            await _update_task_status(session, task_id, "success", 100)

            # Chain to extract_template if doc_type is set
            result = await session.execute(
                text("SELECT doc_type FROM metaedu.files WHERE id = :fid"),
                {"fid": file_id},
            )
            row = result.mappings().first()
            if row and row["doc_type"]:
                extract_template.delay(file_id_str, tenant_id_str)
            else:
                extract_knowledge_graph.delay(file_id_str, tenant_id_str)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 5: Extract template (教案/教学设计) ---


@shared_task(name="extract_template")
def extract_template(file_id_str: str, tenant_id_str: str):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id, "extract_template")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Get chunks content
            result = await session.execute(
                text(
                    "SELECT content FROM metaedu.document_chunks "
                    "WHERE file_id = :fid AND tenant_id = :tid ORDER BY chunk_index LIMIT 10"
                ),
                {"fid": file_id, "tid": tenant_id},
            )
            chunks_text = "\n".join(row["content"] for row in result.mappings().all())

            # Call LLM (Qwen/DeepSeek via OpenAI-compatible API — 国内模型)
            api_key = settings.qwen_api_key or os.environ.get("DASHSCOPE_API_KEY", "")
            base_url = settings.qwen_base_url
            model = settings.qwen_model

            template_data = {}
            if api_key:
                import httpx

                prompt = (
                    "请从以下教案内容中提取结构化信息，返回JSON格式：\n"
                    "包含字段：course_name(课程名), chapter(章节), objectives(教学目标数组), "
                    "key_points(重点数组), difficulties(难点数组), methods(教学方法数组), duration(课时)。\n\n"
                    f"内容：\n{chunks_text[:6000]}"
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
                    # Try to parse JSON from response
                    try:
                        json_start = content.index("{")
                        json_end = content.rindex("}") + 1
                        template_data = json.loads(content[json_start:json_end])
                    except (ValueError, json.JSONDecodeError):
                        template_data = {"raw_extraction": content}

            # Save to file structured_data
            result = await session.execute(
                text("SELECT structured_data FROM metaedu.files WHERE id = :fid"),
                {"fid": file_id},
            )
            existing = result.mappings().first()
            existing_data = (
                existing["structured_data"] if existing and existing["structured_data"] else {}
            )
            existing_data["template"] = template_data

            await session.execute(
                text(
                    "UPDATE metaedu.files SET structured_data = :data::jsonb, updated_at = :now WHERE id = :fid"
                ),
                {
                    "data": json.dumps(existing_data),
                    "now": datetime.now(UTC).replace(tzinfo=None),
                    "fid": file_id,
                },
            )

            await _update_task_status(session, task_id, "success", 100)

            # Chain to KG extraction
            extract_knowledge_graph.delay(file_id_str, tenant_id_str)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 6: Extract knowledge graph ---


@shared_task(name="extract_knowledge_graph")
def extract_knowledge_graph(file_id_str: str, tenant_id_str: str):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id, "extract_kg")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
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

            # Call LLM to extract entities and relations (国内模型)
            api_key = settings.qwen_api_key or os.environ.get("DASHSCOPE_API_KEY", "")
            base_url = settings.qwen_base_url
            model = settings.qwen_model

            if api_key:
                import httpx

                chunks_text = "\n".join(
                    f"[{c['section_title'] or '段落'}] {c['content'][:500]}" for c in chunks
                )
                prompt = (
                    "请从以下文本中提取知识实体和关系，返回JSON格式：\n"
                    '{"entities": [{"name": "实体名", "type": "类型"}], '
                    '"relations": [{"source": "实体1", "target": "实体2", "relation": "关系"}]}\n\n'
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
                    try:
                        json_start = content.index("{")
                        json_end = content.rindex("}") + 1
                        kg_data = json.loads(content[json_start:json_end])
                    except (ValueError, json.JSONDecodeError):
                        kg_data = {"entities": [], "relations": []}

                # Write entities to knowledge_nodes with source tracking
                from app.contexts.knowledge.application.embedding_service import get_embedding

                for entity in kg_data.get("entities", []):
                    name = entity.get("name", "")
                    if not name:
                        continue
                    node_id = uuid.uuid4()
                    embedding = await get_embedding(name)
                    vec_str = None
                    if embedding:
                        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

                    await session.execute(
                        text(
                            "INSERT INTO metaedu.knowledge_nodes "
                            "(id, tenant_id, title, description, domain, level, path, source_file_id, created_at) "
                            "VALUES (:id, :tid, :title, '', 'general', 'concept', :path, :fid, :now)"
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
                    if vec_str:
                        await session.execute(
                            text(
                                "UPDATE metaedu.knowledge_nodes SET embedding = :vec::vector WHERE id = :nid"
                            ),
                            {"vec": vec_str, "nid": node_id},
                        )

            await _update_task_status(session, task_id, "success", 100)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            raise

    asyncio.run(_run_in_session(_do))
