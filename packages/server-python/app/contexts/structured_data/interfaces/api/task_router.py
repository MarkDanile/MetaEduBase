"""Structured data task router — task status + retry + KG endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.document.application.dto import TaskDTO
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.structured_data.domain.entities import DS_TASK_TYPE_LABELS
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id

router = APIRouter()


def _task_row_to_dto(row: dict) -> TaskDTO:
    return TaskDTO(
        id=row["id"],
        file_id=row.get("file_id"),
        dataset_id=row.get("dataset_id"),
        task_type=row["task_type"],
        status=row["status"],
        progress=row["progress"],
        error_message=row.get("error_message"),
        label=DS_TASK_TYPE_LABELS.get(row["task_type"], row["task_type"]),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        created_at=row["created_at"],
    )


@router.get("/datasets/{dataset_id}/tasks", response_model=list[TaskDTO])
async def list_dataset_tasks(
    dataset_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    result = await session.execute(
        text(
            "SELECT * FROM metaedu.document_tasks "
            "WHERE dataset_id = :did AND tenant_id = :tid ORDER BY created_at"
        ),
        {"did": uuid.UUID(dataset_id), "tid": tid},
    )
    return [_task_row_to_dto(dict(row)) for row in result.mappings().all()]


@router.post("/datasets/{dataset_id}/retry", response_model=list[TaskDTO])
async def retry_failed_dataset_tasks(
    dataset_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    did = uuid.UUID(dataset_id)
    result = await session.execute(
        text(
            "UPDATE metaedu.document_tasks SET status = 'pending', error_message = NULL "
            "WHERE dataset_id = :did AND tenant_id = :tid AND status = 'failed' "
            "RETURNING *"
        ),
        {"did": did, "tid": tid},
    )
    rows = result.mappings().all()
    if not rows:
        raise HTTPException(status_code=404, detail="没有可重试的失败任务")
    return [_task_row_to_dto(dict(row)) for row in rows]


@router.get("/knowledge-graph/status")
async def get_kg_status(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    result = await session.execute(
        text(
            "SELECT id, name, kg_status FROM metaedu.datasets "
            "WHERE tenant_id = :tid ORDER BY created_at DESC"
        ),
        {"tid": tid},
    )
    return [{"id": str(row["id"]), "name": row["name"], "kg_status": row["kg_status"]} for row in result.mappings().all()]


@router.get("/knowledge-graph")
async def get_knowledge_graph(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    # Get knowledge nodes sourced from datasets
    nodes_result = await session.execute(
        text(
            "SELECT id, title, description, domain, level, source_dataset_id "
            "FROM metaedu.knowledge_nodes "
            "WHERE tenant_id = :tid AND source_dataset_id IS NOT NULL"
        ),
        {"tid": tid},
    )
    nodes = [
        {
            "id": str(row["id"]),
            "title": row["title"],
            "description": row.get("description"),
            "domain": row["domain"],
            "level": row["level"],
            "source_dataset_id": str(row["source_dataset_id"]) if row.get("source_dataset_id") else None,
        }
        for row in nodes_result.mappings().all()
    ]

    # Get edges
    edges_result = await session.execute(
        text(
            "SELECT id, source_id, target_id, relation_type "
            "FROM metaedu.knowledge_edges "
            "WHERE tenant_id = :tid"
        ),
        {"tid": tid},
    )
    edges = [
        {
            "id": str(row["id"]),
            "source_id": str(row["source_id"]),
            "target_id": str(row["target_id"]),
            "relation_type": row["relation_type"],
        }
        for row in edges_result.mappings().all()
    ]

    return {"nodes": nodes, "edges": edges}
