"""`ds_build_cross_dataset_edges` Celery task — structured_data pipeline step 4 of 4.

Builds cross-dataset knowledge edges based on FK column patterns.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.tasks.lifecycle import _run_in_session

logger = logging.getLogger(__name__)


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

        # TD-066 fix: return the created edge count
        return edges_created

    # TD-066 fix: capture asyncio.run's return value.
    return asyncio.run(_run_in_session(_do))
