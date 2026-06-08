"""`ds_extract_kg` Celery task — structured_data pipeline step 3 of 4 (LLM KG extraction)."""

from __future__ import annotations

import json
import logging
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
                from .ds_cross_dataset_edges import ds_build_cross_dataset_edges

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
