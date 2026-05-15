"""Document task router — task status + retry."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.document.application.dto import TaskDTO
from app.contexts.document.domain.entities import TASK_TYPE_LABELS
from app.contexts.identity.interfaces.api.dependencies import get_current_user
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
        label=TASK_TYPE_LABELS.get(row["task_type"], row["task_type"]),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        created_at=row["created_at"],
    )


@router.get("/files/{file_id}/tasks", response_model=list[TaskDTO])
async def list_file_tasks(
    file_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    result = await session.execute(
        text(
            "SELECT * FROM metaedu.document_tasks "
            "WHERE file_id = :fid AND tenant_id = :tid ORDER BY created_at"
        ),
        {"fid": uuid.UUID(file_id), "tid": tid},
    )
    return [_task_row_to_dto(dict(row)) for row in result.mappings().all()]


@router.post("/files/{file_id}/retry", response_model=list[TaskDTO])
async def retry_failed_tasks(
    file_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    fid = uuid.UUID(file_id)
    result = await session.execute(
        text(
            "UPDATE metaedu.document_tasks SET status = 'pending', error_message = NULL "
            "WHERE file_id = :fid AND tenant_id = :tid AND status = 'failed' "
            "RETURNING *"
        ),
        {"fid": fid, "tid": tid},
    )
    rows = result.mappings().all()
    if not rows:
        raise HTTPException(status_code=404, detail="没有可重试的失败任务")
    # TODO: Re-dispatch Celery tasks for the retried items
    return [_task_row_to_dto(dict(row)) for row in rows]
