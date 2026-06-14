"""`extract_knowledge_graph` Celery task — pipeline step 6 of 6."""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import suppress
from datetime import UTC, datetime

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.llm.chat import chat
from app.shared.tasks.lifecycle import (
    _create_task,
    _run_in_session,
    _update_task_status,
)

logger = logging.getLogger(__name__)


def find_chunk_for_entity(
    chunks: list[dict], entity_name: str
) -> uuid.UUID | None:
    """REQ-010 Slice 5: find the first chunk whose `content` contains
    `entity_name` (substring match, case-sensitive).

    Returns the chunk's id (UUID) or None when no chunk contains the name.
    Used as a heuristic for KG entity→chunk traceability when the LLM does
    not explicitly tag the entity with a chunk_index.
    """
    if not entity_name:
        return None
    for c in chunks:
        if entity_name and entity_name in (c["content"] or ""):
            return c["id"]
    return None


@shared_task(name="extract_knowledge_graph")
def extract_knowledge_graph(file_id_str: str, tenant_id_str: str, pipeline_version: str = ""):
    import asyncio

    file_id = uuid.UUID(file_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async def _do(session: AsyncSession):
        task_id = await _create_task(session, tenant_id, file_id=file_id, task_type="extract_kg")
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

            chunks_text = "\n".join(
                f"[{c['section_title'] or '段落'}] {c['content'][:500]}" for c in chunks
            )
            prompt = (
                "请从以下文本中提取知识实体和关系，将所有实体名称翻译为中文，只返回JSON不要任何解释：\n"
                '{"entities": [{"name": "中文实体名", "type": "类型"}], '
                '"relations": [{"source": "中文实体1", "target": "中文实体2", '
                '"relation": "关系描述"}]}\n\n'
                f"文本：\n{chunks_text[:6000]}"
            )
            content = await chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                timeout=60.0,
            )
            import re as regexmod
            stripped = regexmod.sub(
                r"<think>.*?</think>", "", content, flags=regexmod.DOTALL
            ).strip()
            kg_data = {"entities": [], "relations": []}
            m = regexmod.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, regexmod.DOTALL)
            if m:
                with suppress(json.JSONDecodeError):
                    kg_data = json.loads(m.group(1))
            if not kg_data.get("entities"):
                try:
                    json_start = stripped.index("{")
                    json_end = stripped.rindex("}") + 1
                    kg_data = json.loads(stripped[json_start:json_end])
                except (ValueError, json.JSONDecodeError):
                    logger.warning(
                        "KG extraction JSON parse failed, raw content: %s", content[:300]
                    )

                # REQ-010 Slice 5 — KG 抽取按 chunk 切片：每条 entity 写入时尝试
                # 在 chunks 中模糊匹配（content 包含 entity name），把首个匹配
                # chunk 的 id 写入 source_chunk_id；匹配失败则只保留
                # source_file_id，标记 node_source_resolution='file_only'。
                # 历史 / e2e 行为：source_file_id 必填不变（plan Slice 5 Step 5.4）。
                # (find_chunk_for_entity 在模块级，供测试直接 import。)

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

                    # REQ-010 Slice 5: 找首个包含 entity name 的 chunk
                    resolved_chunk_id = find_chunk_for_entity(chunks, name)
                    resolution = "chunk_resolved" if resolved_chunk_id else "file_only"

                    await session.execute(
                        text(
                            "INSERT INTO metaedu.knowledge_nodes "
                            "(id, tenant_id, title, description, domain, level, "
                            "path, source_file_id, source_chunk_id, "
                            "node_source_resolution, created_at, updated_at) "
                            "VALUES (:id, :tid, :title, '', 'education_sports', "
                            "'knowledge_point', :path, :fid, :scid, :res, :now, :now)"
                        ),
                        {
                            "id": node_id,
                            "tid": tenant_id,
                            "title": name,
                            "path": str(node_id)[:8],
                            "fid": file_id,
                            "scid": resolved_chunk_id,
                            "res": resolution,
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
                            "(id, tenant_id, source_id, target_id, relation_type, "
                            "weight, metadata, created_at) "
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

            # TD-062 fix: return the KG extraction summary so the
            # outer `asyncio.run(_run_in_session(_do))` call can
            # propagate it back to the caller. Returns a dict
            # with the count of inserted nodes and edges.
            return {"nodes": len(node_name_map), "edges": edges_inserted}

        except Exception as e:
            await _update_task_status(session, task_id, "failed", 0, str(e))
            await session.commit()  # Commit failure status before re-raising
            raise

    # TD-062 fix: capture asyncio.run's return value.
    return asyncio.run(_run_in_session(_do))
