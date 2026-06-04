"""Structured data processing Celery tasks — 3-step pipeline + cross-dataset edges.

Pipeline: ds_parse → ds_extract_kg → ds_build_cross_dataset_edges

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
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.shared.tasks.lifecycle import (
    _create_task,
    _run_in_session,
    _update_task_status,
)

logger = logging.getLogger(__name__)


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

        task_id = await _create_task(
            session, tenant_id, dataset_id=dataset_id, task_type="ds_parse"
        )
        await _update_task_status(session, task_id, "running", 0)
        await session.commit()

        try:
            source_file = row["source_file"]
            file_path = os.path.join(settings.upload_dir, source_file)

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
                        "INSERT INTO metaedu.dataset_rows "
                        "(id, tenant_id, dataset_id, row_index, data, created_at) "
                        "VALUES (:id, :tid, :did, :idx, CAST(:data AS jsonb), :now)"
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
                    "UPDATE metaedu.datasets "
                    "SET column_names = CAST(:cnames AS jsonb), "
                    "    column_types = CAST(:ctypes AS jsonb), "
                    "    row_count = :rcount, status = 'processed', "
                    "    updated_at = :now "
                    "WHERE id = :did"
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

            # Chain directly to KG extraction (vectorization skipped — KG uses raw row samples)
            ds_extract_kg.delay(dataset_id_str, tenant_id_str)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.execute(
                text(
                    "UPDATE metaedu.datasets SET status = 'failed', updated_at = :now "
                    "WHERE id = :did"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None), "did": dataset_id},
            )
            await session.commit()  # Commit failure status before re-raising
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 2: Embed dataset rows ---


@shared_task(name="ds_embed")
def ds_embed(dataset_id_str: str, tenant_id_str: str):
    import asyncio

    dataset_id = uuid.UUID(dataset_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(
            session, tenant_id, dataset_id=dataset_id, task_type="ds_embed"
        )
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

            # Use same embedding approach as document tasks: MiniMax first, SiliconFlow fallback
            mm_key = settings.minimax_api_key
            sf_key = settings.siliconflow_api_key
            if not mm_key and not sf_key:
                raise RuntimeError(
                    "No embedding API key configured "
                    "(MINIMAX_API_KEY or SILICONFLOW_API_KEY required)"
                )

            import httpx

            async def embed_one(client: httpx.AsyncClient, text_in: str) -> list[float] | None:
                if mm_key:
                    try:
                        resp = await client.post(
                            f"{settings.minimax_base_url}/embeddings",
                            headers={"Authorization": f"Bearer {mm_key}"},
                            json={"model": settings.minimax_embedding_model, "input": [text_in]},
                        )
                        resp.raise_for_status()
                        return resp.json()["data"][0]["embedding"]
                    except Exception as e:
                        logger.warning(f"MiniMax embed failed: {e}")
                if sf_key:
                    try:
                        resp = await client.post(
                            f"{settings.siliconflow_base_url}/embeddings",
                            headers={"Authorization": f"Bearer {sf_key}"},
                            json={
                                "model": settings.siliconflow_embedding_model,
                                "input": [text_in],
                            },
                        )
                        resp.raise_for_status()
                        return resp.json()["data"][0]["embedding"]
                    except Exception as e:
                        logger.warning(f"SiliconFlow embed failed: {e}")
                return None

            success_count = 0
            async with httpx.AsyncClient(timeout=60.0) as client:
                for i, row in enumerate(rows):
                    text_parts = [str(v) for v in row["data"].values()]
                    embed_text = " ".join(text_parts)[:8192]
                    embedding = await embed_one(client, embed_text)
                    if not embedding:
                        continue
                    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

                    # Insert chunk first (without embedding), then update embedding
                    chunk_id = uuid.uuid4()
                    now = datetime.now(UTC).replace(tzinfo=None)
                    await session.execute(
                        text(
                            "INSERT INTO metaedu.document_chunks "
                            "(id, tenant_id, file_id, chunk_index, content, created_at) "
                            "VALUES (:id, :tid, :fid, :idx, :content, :now)"
                        ),
                        {
                            "id": chunk_id,
                            "tid": tenant_id,
                            "fid": dataset_id,
                            "idx": i,
                            "content": embed_text,
                            "now": now,
                        },
                    )
                    await session.execute(
                        text("UPDATE metaedu.document_chunks SET embedding = :vec WHERE id = :cid"),
                        {"vec": vec_str, "cid": chunk_id},
                    )
                    success_count += 1
                    progress = int((i + 1) / len(rows) * 100) if rows else 100
                    await _update_task_status(session, task_id, "running", progress)
                    await session.commit()

            if rows and success_count == 0:
                raise RuntimeError(f"All embeddings failed (0 of {len(rows)} rows succeeded)")

            # Update kg_status
            await session.execute(
                text(
                    "UPDATE metaedu.datasets SET kg_status = 'pending', "
                    "updated_at = :now WHERE id = :did"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None), "did": dataset_id},
            )

            await _update_task_status(session, task_id, "success", 100)

            # Chain to KG extraction
            ds_extract_kg.delay(dataset_id_str, tenant_id_str)

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()  # Commit failure status before re-raising
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 3: Extract knowledge graph from datasets ---


@shared_task(name="ds_extract_kg")
def ds_extract_kg(dataset_id_str: str, tenant_id_str: str):
    import asyncio

    dataset_id = uuid.UUID(dataset_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(
            session, tenant_id, dataset_id=dataset_id, task_type="ds_extract_kg"
        )
        await _update_task_status(session, task_id, "running", 0)
        await session.execute(
            text(
                "UPDATE metaedu.datasets SET kg_status = 'building', "
                "updated_at = :now WHERE id = :did"
            ),
            {"now": datetime.now(UTC).replace(tzinfo=None), "did": dataset_id},
        )
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

            # Call LLM (MiniMax, SiliconFlow fallback — same as document tasks)
            api_key = settings.minimax_api_key
            base_url = settings.minimax_base_url
            model = settings.minimax_model

            if not api_key and not settings.siliconflow_api_key:
                raise RuntimeError(
                    "No LLM API key configured (MINIMAX_API_KEY or SILICONFLOW_API_KEY required)"
                )

            import httpx

            schema_str = json.dumps(
                {"columns": ds_row["column_names"], "types": ds_row["column_types"]},
                ensure_ascii=False,
            )
            sample_str = json.dumps(sample_rows[:5], ensure_ascii=False)

            system_msg = (
                "你是一个知识图谱抽取专家。用户会给你一个数据集的表结构和样本数据，"
                "你需要从中提取知识实体和关系。"
                "直接输出JSON，不要输出思考过程，不要输出markdown代码块。"
            )
            user_msg = (
                f"数据集名称：{ds_row['name']}\n"
                f"表结构：{schema_str}\n"
                f"样本数据：{sample_str}\n\n"
                "请从以上结构化数据中提取知识实体和关系，返回JSON格式"
                "（relations中的source/target必须是entities数组中的name字段值）：\n"
                '{"entities": [{"name": "实体名", "type": "类型"}], '
                '"relations": [{"source": "实体1名称", "target": "实体2名称", '
                '"relation": "关系描述"}]}'
            )

            def parse_kg_json(content: str) -> dict:
                import re
                # Strip <think>...</think> blocks (reasoning models)
                cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
                if "<think>" in cleaned and "</think>" not in cleaned:
                    cleaned = cleaned.split("<think>")[0]
                # Strip markdown code fences
                cleaned = re.sub(r"```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"```", "", cleaned)
                cleaned = cleaned.strip()
                try:
                    json_start = cleaned.index("{")
                    json_end = cleaned.rindex("}") + 1
                    return json.loads(cleaned[json_start:json_end])
                except (ValueError, json.JSONDecodeError):
                    return {}

            kg_data: dict = {"entities": [], "relations": []}
            if api_key:
                try:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        resp = await client.post(
                            f"{base_url}/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}"},
                            json={
                                "model": model,
                                "messages": [
                                    {"role": "system", "content": system_msg},
                                    {"role": "user", "content": user_msg},
                                ],
                                "temperature": 0.1,
                                "max_tokens": 8192,
                            },
                        )
                        resp.raise_for_status()
                        content = resp.json()["choices"][0]["message"]["content"]
                        parsed = parse_kg_json(content)
                        if parsed:
                            kg_data = parsed
                        else:
                            logger.warning("MiniMax KG JSON parse failed, raw: %s", content[:1000])
                except Exception as e:
                    logger.warning(f"MiniMax KG extraction failed: {e}")

            # Fallback to SiliconFlow if MiniMax returned empty
            if not kg_data.get("entities") and settings.siliconflow_api_key:
                try:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        resp = await client.post(
                            f"{settings.siliconflow_base_url}/chat/completions",
                            headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
                            json={
                                "model": "Qwen/Qwen2.5-7B-Instruct",
                                "messages": [
                                    {"role": "system", "content": system_msg},
                                    {"role": "user", "content": user_msg},
                                ],
                                "temperature": 0.1,
                                "max_tokens": 8192,
                            },
                        )
                        resp.raise_for_status()
                        content = resp.json()["choices"][0]["message"]["content"]
                        parsed = parse_kg_json(content)
                        if parsed:
                            kg_data = parsed
                        else:
                            logger.warning(
                                "SiliconFlow KG JSON parse failed, raw: %s", content[:1000]
                            )
                except Exception as e:
                    logger.warning(f"SiliconFlow KG fallback failed: {e}")

            if not kg_data.get("entities"):
                raise RuntimeError("KG extraction returned no entities from any LLM provider")

            # Write entities to knowledge_nodes with source_dataset_id
            from app.contexts.knowledge.application.embedding_service import get_embedding

            name_to_node_id: dict[str, uuid.UUID] = {}
            for entity in kg_data.get("entities", []):
                name = entity.get("name", "")
                if not name:
                    continue
                node_id = uuid.uuid4()
                name_to_node_id[name] = node_id
                embedding = await get_embedding(name)
                vec_str = None
                if embedding:
                    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

                await session.execute(
                    text(
                        "INSERT INTO metaedu.knowledge_nodes "
                        "(id, tenant_id, title, description, domain, level, "
                        "path, source_dataset_id, created_at) "
                        "VALUES (:id, :tid, :title, '', 'general', 'concept', "
                        ":path, :did, :now)"
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
                            "UPDATE metaedu.knowledge_nodes SET embedding = :vec WHERE id = :nid"
                        ),
                        {"vec": vec_str, "nid": node_id},
                    )

            # Write relations to knowledge_edges
            for relation in kg_data.get("relations", []):
                src = relation.get("source", "")
                tgt = relation.get("target", "")
                rel_type = relation.get("relation", "")
                if not src or not tgt or not rel_type:
                    continue
                src_id = name_to_node_id.get(src)
                tgt_id = name_to_node_id.get(tgt)
                if not src_id or not tgt_id:
                    continue
                edge_id = uuid.uuid4()
                await session.execute(
                    text(
                        "INSERT INTO metaedu.knowledge_edges "
                        "(id, tenant_id, source_id, target_id, relation_type, created_at) "
                        "VALUES (:id, :tid, :src, :tgt, :rtype, :now)"
                    ),
                    {
                        "id": edge_id,
                        "tid": tenant_id,
                        "src": src_id,
                        "tgt": tgt_id,
                        "rtype": rel_type,
                        "now": datetime.now(UTC).replace(tzinfo=None),
                    },
                )

            # Update kg_status
            await session.execute(
                text(
                    "UPDATE metaedu.datasets SET kg_status = 'done', "
                    "updated_at = :now WHERE id = :did"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None), "did": dataset_id},
            )

            await _update_task_status(session, task_id, "success", 100)

            # Check if all datasets' KG extraction is done — trigger cross-dataset edges
            pending = await session.execute(
                text(
                    "SELECT COUNT(*) FROM metaedu.datasets "
                    "WHERE tenant_id = :tid AND status = 'processed' AND kg_status NOT IN ('done')"
                ),
                {"tid": tenant_id},
            )
            if pending.scalar() == 0:
                ds_build_cross_dataset_edges.delay(str(tenant_id))

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.execute(
                text(
                    "UPDATE metaedu.datasets SET kg_status = 'failed', "
                    "updated_at = :now WHERE id = :did"
                ),
                {"now": datetime.now(UTC).replace(tzinfo=None), "did": dataset_id},
            )
            await session.commit()  # Commit failure status before re-raising
            raise

    asyncio.run(_run_in_session(_do))


# --- Task 4: Build cross-dataset edges based on FK column patterns ---


def _extract_entity_name(dataset_name: str) -> str:
    """Strip common suffixes: 院系表 → 院系, 专业表 → 专业."""
    return dataset_name.rstrip("表").rstrip("数据").rstrip("信息")


def _extract_fk_reference(column_name: str, self_pk: str) -> str | None:
    """所属院系ID → 院系, 专业ID → None (self PK)."""
    if column_name == self_pk:
        return None
    for suffix in ("ID", "Id", "id"):
        if column_name.endswith(suffix):
            ref = column_name[: -len(suffix)]
            for prefix in ("所属", "授课", "关联", "对应", "相关"):
                if ref.startswith(prefix):
                    ref = ref[len(prefix) :]
            return ref if ref else None
    return None


@shared_task(name="ds_build_cross_dataset_edges")
def ds_build_cross_dataset_edges(tenant_id_str: str):
    import asyncio

    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        result = await session.execute(
            text(
                "SELECT id, name, column_names FROM metaedu.datasets "
                "WHERE tenant_id = :tid AND status = 'processed'"
            ),
            {"tid": tenant_id},
        )
        datasets = result.mappings().all()
        if not datasets:
            return

        ds_map: dict[str, dict] = {}
        for ds in datasets:
            entity_name = _extract_entity_name(ds["name"])
            ds_map[str(ds["id"])] = {
                "name": ds["name"],
                "entity_name": entity_name,
                "column_names": ds["column_names"] or [],
                "id": ds["id"],
            }

        # Create a virtual representative node for each dataset
        now = datetime.now(UTC).replace(tzinfo=None)
        for _ds_id, ds_info in ds_map.items():
            # Check if virtual node already exists
            existing = await session.execute(
                text(
                    "SELECT id FROM metaedu.knowledge_nodes "
                    "WHERE tenant_id = :tid AND source_dataset_id = :did "
                    "AND title = :title"
                ),
                {"tid": tenant_id, "did": ds_info["id"], "title": ds_info["entity_name"]},
            )
            if existing.scalar_one_or_none():
                node_result = await session.execute(
                    text(
                        "SELECT id FROM metaedu.knowledge_nodes "
                        "WHERE tenant_id = :tid AND source_dataset_id = :did "
                        "AND title = :title"
                    ),
                    {"tid": tenant_id, "did": ds_info["id"], "title": ds_info["entity_name"]},
                )
                ds_info["node_id"] = node_result.scalar_one()
            else:
                node_id = uuid.uuid4()
                await session.execute(
                    text(
                        "INSERT INTO metaedu.knowledge_nodes "
                        "(id, tenant_id, title, description, domain, level, "
                        "source_dataset_id, created_at) "
                        "VALUES (:id, :tid, :title, :desc, 'public_service', "
                        "'professional', :did, :now)"
                    ),
                    {
                        "id": node_id,
                        "tid": tenant_id,
                        "title": ds_info["entity_name"],
                        "desc": f"{ds_info['name']}的代表性实体节点",
                        "did": ds_info["id"],
                        "now": now,
                    },
                )
                ds_info["node_id"] = node_id

        edges_created = 0
        for ds_id, ds_info in ds_map.items():
            entity_name = ds_info["entity_name"]
            self_pk = f"{entity_name}ID"

            for col in ds_info["column_names"]:
                ref = _extract_fk_reference(col, self_pk)
                if not ref:
                    continue

                for other_id, other_info in ds_map.items():
                    if other_id == ds_id:
                        continue
                    other_entity = other_info["entity_name"]
                    if ref not in other_entity and other_entity not in ref:
                        continue

                    existing = await session.execute(
                        text(
                            "SELECT id FROM metaedu.knowledge_edges "
                            "WHERE tenant_id = :tid AND source_id = :src AND target_id = :tgt "
                            "AND relation_type = :rtype"
                        ),
                        {
                            "tid": tenant_id,
                            "src": ds_info["node_id"],
                            "tgt": other_info["node_id"],
                            "rtype": col,
                        },
                    )
                    if existing.scalar_one_or_none():
                        continue

                    edge_id = uuid.uuid4()
                    await session.execute(
                        text(
                            "INSERT INTO metaedu.knowledge_edges "
                            "(id, tenant_id, source_id, target_id, relation_type, "
                            "metadata, created_at) "
                            "VALUES (:id, :tid, :src, :tgt, :rtype, "
                            "CAST(:meta AS jsonb), :now)"
                        ),
                        {
                            "id": edge_id,
                            "tid": tenant_id,
                            "src": ds_info["node_id"],
                            "tgt": other_info["node_id"],
                            "rtype": col,
                            "meta": json.dumps({
                                "cross_dataset": True,
                                "fk_column": col,
                                "source_dataset_id": ds_id,
                                "target_dataset_id": other_id,
                            }),
                            "now": now,
                        },
                    )
                    edges_created += 1

        logger.info("Cross-dataset edges created: %d", edges_created)

    asyncio.run(_run_in_session(_do))
