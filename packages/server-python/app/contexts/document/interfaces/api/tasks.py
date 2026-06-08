"""Document task router — list file tasks + retry."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.document.application.dto import TaskDTO
from app.contexts.document.application.tasks import parse_document
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id

_TASK_TYPE_LABELS: dict[str, str] = {
    "parse": "文档解析",
    "chunk": "结构切片",
    "embed": "向量化",
    "index_tsv": "全文索引",
    "extract_template": "模板抽取",
    "extract_kg": "知识图谱",
}


router = APIRouter()


@router.get("/files/{file_id}/tasks", response_model=list[TaskDTO])
async def list_file_tasks(
    file_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    from sqlalchemy import text

    tid = get_tenant_id()
    fid = uuid.UUID(file_id)

    result = await session.execute(
        text(
            "SELECT id, file_id, dataset_id, task_type, status, progress, "
            "error_message, started_at, completed_at, created_at "
            "FROM metaedu.document_tasks "
            "WHERE tenant_id = :tid AND file_id = :fid "
            "ORDER BY created_at ASC"
        ),
        {"tid": tid, "fid": fid},
    )
    rows = result.mappings().all()
    return [
        TaskDTO(
            id=r["id"],
            file_id=r["file_id"],
            dataset_id=r["dataset_id"],
            task_type=r["task_type"],
            status=r["status"],
            progress=r["progress"],
            error_message=r["error_message"],
            label=_TASK_TYPE_LABELS.get(r["task_type"], r["task_type"]),
            started_at=r["started_at"],
            completed_at=r["completed_at"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.post("/files/{file_id}/retry", response_model=list[TaskDTO])
async def retry_file_tasks(
    file_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    from sqlalchemy import text

    tid = get_tenant_id()
    fid = uuid.UUID(file_id)

    # Reset failed/pending tasks to pending
    await session.execute(
        text(
            "UPDATE metaedu.document_tasks "
            "SET status = 'pending', progress = 0, error_message = NULL "
            "WHERE tenant_id = :tid AND file_id = :fid AND status IN ('failed', 'pending')"
        ),
        {"tid": tid, "fid": fid},
    )
    await session.commit()

    # Re-dispatch the first pending task (parse_document chains to the rest)
    await parse_document.delay(file_id, str(tid))

    # Return updated tasks
    result = await session.execute(
        text(
            "SELECT id, file_id, dataset_id, task_type, status, progress, "
            "error_message, started_at, completed_at, created_at "
            "FROM metaedu.document_tasks "
            "WHERE tenant_id = :tid AND file_id = :fid "
            "ORDER BY created_at ASC"
        ),
        {"tid": tid, "fid": fid},
    )
    rows = result.mappings().all()
    return [
        TaskDTO(
            id=r["id"],
            file_id=r["file_id"],
            dataset_id=r["dataset_id"],
            task_type=r["task_type"],
            status=r["status"],
            progress=r["progress"],
            error_message=r["error_message"],
            label=_TASK_TYPE_LABELS.get(r["task_type"], r["task_type"]),
            started_at=r["started_at"],
            completed_at=r["completed_at"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
