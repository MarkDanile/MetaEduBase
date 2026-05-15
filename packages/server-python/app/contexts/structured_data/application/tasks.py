"""Structured data processing Celery tasks — 3-step pipeline.

Pipeline: ds_parse → ds_embed → ds_extract_kg

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
    sets = ["status = :status", "progress = :progress"]
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
    session: AsyncSession, tenant_id: uuid.UUID, dataset_id: uuid.UUID, task_type: str
) -> uuid.UUID:
    task_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await session.execute(
        text(
            "INSERT INTO metaedu.document_tasks (id, tenant_id, dataset_id, task_type, status, progress, created_at) "
            "VALUES (:id, :tid, :did, :type, 'pending', 0, :now)"
        ),
        {"id": task_id, "tid": tenant_id, "did": dataset_id, "type": task_type, "now": now},
    )
    return task_id


# --- Task 1: Parse dataset (xlsx → rows) ---


@shared_task(name="ds_parse")
def ds_parse(dataset_id_str: str, tenant_id_str: str):
    import asyncio

    dataset_id = uuid.UUID(dataset_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        # Get dataset record
        result = await session.execute(
            text("SELECT * FROM metaedu.datasets WHERE id = :did AND tenant_id = :tid"),
            {"did": dataset_id, "tid": tenant_id},
        )
        row = result.mappings().first()
        if not row:
            raise ValueError(f"Dataset {dataset_id} not found")

        task_id = await _create_task(session, tenant_id, dataset_id, "ds_parse")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            source_file = row["source_file"]
            file_path = os.path.join(settings.upload_dir, str(tenant_id), source_file)

            if source_file and source_file.endswith((".xlsx", ".xls")):
                from app.shared.parsing.xlsx_parser import extract_xlsx_rows

                parsed = extract_xlsx_rows(file_path)
            else:
                raise ValueError(f"Unsupported file type: {source_file}")

            # Bulk insert rows
            now = datetime.now(UTC).replace(tzinfo=None)
            for i, row_data in enumerate(parsed.rows):
                row_id = uuid.uuid4()
                await session.execute(
                    text(
                        "INSERT INTO metaedu.dataset_rows (id, tenant_id, dataset_id, row_index, data, created_at) "
                        "VALUES (:id, :tid, :did, :idx, :data::jsonb, :now)"
                    ),
                    {
                        "id": row_id,
                        "tid": tenant_id,
                        "did": dataset_id,
                        "idx": i,
                        "data": json.dumps(row_data),
                        "now": now,
                    },
                )

            # Update column metadata
            await session.execute(
                text(
                    "UPDATE metaedu.datasets SET column_names = :cnames::jsonb, column_types = :ctypes::jsonb, "
                    "row_count = :rcount, status = 'processed', updated_at = :now WHERE id = :did"
                ),
                {
                    "cnames": json.dumps(parsed.column_names),
                    "ctypes": json.dumps(parsed.column_types),
                    "rcount": len(parsed.rows),
                    "now": now,
                    "did": dataset_id,
                },
            )

            await _update_task_status(session, task_id, "success", 100)

            # Chain to embed
            ds_embed.delay(dataset_id_str, tenant_id_str)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.execute(
                text(
                    "UPDATE metaedu.datasets SET status = 'failed', updated_at = :now WHERE id = :did"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None), "did": dataset_id},
            )
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 2: Embed dataset rows ---


@shared_task(name="ds_embed")
def ds_embed(dataset_id_str: str, tenant_id_str: str):
    import asyncio

    dataset_id = uuid.UUID(dataset_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, dataset_id, "ds_embed")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Get all rows
            result = await session.execute(
                text(
                    "SELECT id, data FROM metaedu.dataset_rows "
                    "WHERE dataset_id = :did AND tenant_id = :tid ORDER BY row_index"
                ),
                {"did": dataset_id, "tid": tenant_id},
            )
            rows = result.mappings().all()

            api_key = settings.qwen_api_key or os.environ.get("DASHSCOPE_API_KEY", "")
            if api_key:
                import httpx

                for i, row in enumerate(rows):
                    # Build text from row data for embedding
                    text_parts = [str(v) for v in row["data"].values()]
                    embed_text = " ".join(text_parts)[:8192]

                    try:
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            resp = await client.post(
                                f"{settings.qwen_base_url}/embeddings",
                                headers={"Authorization": f"Bearer {api_key}"},
                                json={"model": settings.embedding_model, "input": [embed_text]},
                            )
                            resp.raise_for_status()
                            embedding = resp.json()["data"][0]["embedding"]
                            vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

                            # Store as a document_chunk linked to the dataset
                            chunk_id = uuid.uuid4()
                            now = datetime.now(UTC).replace(tzinfo=None)
                            await session.execute(
                                text(
                                    "INSERT INTO metaedu.document_chunks "
                                    "(id, tenant_id, file_id, chunk_index, content, embedding, created_at) "
                                    "VALUES (:id, :tid, :fid, :idx, :content, :vec::vector, :now)"
                                ),
                                {
                                    "id": chunk_id,
                                    "tid": tenant_id,
                                    "fid": dataset_id,
                                    "idx": i,
                                    "content": embed_text,
                                    "vec": vec_str,
                                    "now": now,
                                },
                            )
                    except Exception as e:
                        logger.warning(f"Embedding failed for dataset row {row['id']}: {e}")

                    progress = int((i + 1) / len(rows) * 100) if rows else 100
                    await _update_task_status(session, task_id, "running", progress)
                    await session.commit()

            # Update kg_status
            await session.execute(
                text(
                    "UPDATE metaedu.datasets SET kg_status = 'pending', updated_at = :now WHERE id = :did"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None), "did": dataset_id},
            )

            await _update_task_status(session, task_id, "success", 100)

            # Chain to KG extraction
            ds_extract_kg.delay(dataset_id_str, tenant_id_str)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 3: Extract knowledge graph from datasets ---


@shared_task(name="ds_extract_kg")
def ds_extract_kg(dataset_id_str: str, tenant_id_str: str):
    import asyncio

    dataset_id = uuid.UUID(dataset_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, dataset_id, "ds_extract_kg")
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            # Get column schema and sample data
            result = await session.execute(
                text(
                    "SELECT column_names, column_types, name FROM metaedu.datasets WHERE id = :did"
                ),
                {"did": dataset_id},
            )
            ds_row = result.mappings().first()
            if not ds_row:
                raise ValueError(f"Dataset {dataset_id} not found")

            # Get sample rows
            rows_result = await session.execute(
                text(
                    "SELECT data FROM metaedu.dataset_rows "
                    "WHERE dataset_id = :did AND tenant_id = :tid ORDER BY row_index LIMIT 10"
                ),
                {"did": dataset_id, "tid": tenant_id},
            )
            sample_rows = [row["data"] for row in rows_result.mappings().all()]

            # Call LLM (国内模型) to extract entities/relations
            api_key = settings.qwen_api_key or os.environ.get("DASHSCOPE_API_KEY", "")
            base_url = settings.qwen_base_url
            model = settings.qwen_model

            if api_key:
                import httpx

                schema_str = json.dumps(
                    {"columns": ds_row["column_names"], "types": ds_row["column_types"]},
                    ensure_ascii=False,
                )
                sample_str = json.dumps(sample_rows[:5], ensure_ascii=False)

                prompt = (
                    f"数据集名称：{ds_row['name']}\n"
                    f"表结构：{schema_str}\n"
                    f"样本数据：{sample_str}\n\n"
                    "请从以上结构化数据中提取知识实体和关系，返回JSON格式：\n"
                    '{"entities": [{"name": "实体名", "type": "类型"}], '
                    '"relations": [{"source": "实体1", "target": "实体2", "relation": "关系"}]}'
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

                # Write entities to knowledge_nodes with source_dataset_id
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
                            "(id, tenant_id, title, description, domain, level, path, source_dataset_id, created_at) "
                            "VALUES (:id, :tid, :title, '', 'general', 'concept', :path, :did, :now)"
                        ),
                        {
                            "id": node_id,
                            "tid": tenant_id,
                            "title": name,
                            "path": str(node_id)[:8],
                            "did": dataset_id,
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

            # Update kg_status
            await session.execute(
                text(
                    "UPDATE metaedu.datasets SET kg_status = 'done', updated_at = :now WHERE id = :did"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None), "did": dataset_id},
            )

            await _update_task_status(session, task_id, "success", 100)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.execute(
                text(
                    "UPDATE metaedu.datasets SET kg_status = 'failed', updated_at = :now WHERE id = :did"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None), "did": dataset_id},
            )
            raise

    asyncio.run(_run_in_session(_do))
