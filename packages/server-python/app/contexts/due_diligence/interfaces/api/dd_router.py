"""Due-diligence workbench API for REQ-046 (Slice 1).

Endpoints (subject anchoring container, AC-1):
- ``POST /api/v1/dd/tasks``                       — create task (subject_pending)
- ``GET  /api/v1/dd/tasks``                       — list own-tenant tasks
- ``GET  /api/v1/dd/tasks/{id}``                  — task detail
- ``POST /api/v1/dd/tasks/{id}/resolve-subject``  — anchor query -> candidates
- ``POST /api/v1/dd/tasks/{id}/confirm-subject``  — confirm candidate -> confirmed

The router is intentionally light: auth + payload parsing + typed-error
mapping (403 / 404 / 422). Candidate subjects and confirmed subjects are
enterprise identifiers returned to the owning tenant's business caller only;
the MCP invocation layer records digests only, never raw subjects (REQ-044).
Report running (AC-1 enforcement) arrives with Slice 5.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.due_diligence.application.dd_task_service import (
    DdTaskNotFoundError,
    DdTaskService,
)
from app.contexts.due_diligence.application.subject_resolver import SubjectResolver
from app.contexts.due_diligence.domain.dd_task import (
    DdTaskStateError,
    SubjectCandidate,
)
from app.contexts.due_diligence.infrastructure.dd_task_repository import (
    DdTaskRepository,
)
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
    MCPInvocationError,
    MCPInvocationService,
)
from app.shared.infrastructure.database import get_session

router = APIRouter(prefix="/api/v1/dd", tags=["due-diligence"])


# --- DTO ---


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    subject_query: str = Field(..., min_length=1)


class SubjectConfirm(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    credit_code: str | None = Field(default=None, max_length=50)


class CandidateDTO(BaseModel):
    company_name: str
    credit_code: str | None


class TaskDTO(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    subject_query: str
    status: str
    confirmed_subject: dict | None
    created_by: uuid.UUID


def _to_dto(task) -> TaskDTO:
    return TaskDTO(
        id=task.id,
        tenant_id=task.tenant_id,
        title=task.title,
        subject_query=task.subject_query,
        status=task.status,
        confirmed_subject=task.confirmed_subject,
        created_by=task.created_by,
    )


def _service(session: AsyncSession) -> DdTaskService:
    resolver = SubjectResolver(MCPInvocationService(session))
    return DdTaskService(DdTaskRepository(session), resolver)


def _caller(user: dict) -> InvocationCaller:
    return InvocationCaller(
        caller_type="http_api", role=user["role"], user_id=user["id"]
    )


# --- Endpoints ---


@router.post("/tasks", status_code=201)
async def create_task(
    payload: TaskCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    user: dict = Depends(get_current_user),  # noqa: B008
) -> TaskDTO:
    task = await _service(session).create_task(
        tenant_id=user["tenant_id"],
        title=payload.title,
        subject_query=payload.subject_query,
        by=user["id"],
    )
    return _to_dto(task)


@router.get("/tasks")
async def list_tasks(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    user: dict = Depends(get_current_user),  # noqa: B008
) -> list[TaskDTO]:
    tasks = await _service(session).list_tasks(tenant_id=user["tenant_id"])
    return [_to_dto(t) for t in tasks]


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    user: dict = Depends(get_current_user),  # noqa: B008
) -> TaskDTO:
    try:
        task = await _service(session).get_task(
            tenant_id=user["tenant_id"], task_id=task_id
        )
    except DdTaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _to_dto(task)


@router.post("/tasks/{task_id}/resolve-subject")
async def resolve_subject(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    user: dict = Depends(get_current_user),  # noqa: B008
) -> list[CandidateDTO]:
    try:
        candidates: list[SubjectCandidate] = await _service(session).resolve_subject(
            tenant_id=user["tenant_id"], task_id=task_id, caller=_caller(user)
        )
    except DdTaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except MCPInvocationError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return [
        CandidateDTO(company_name=c.company_name, credit_code=c.credit_code)
        for c in candidates
    ]


@router.post("/tasks/{task_id}/confirm-subject")
async def confirm_subject(
    task_id: uuid.UUID,
    payload: SubjectConfirm,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    user: dict = Depends(get_current_user),  # noqa: B008
) -> TaskDTO:
    try:
        task = await _service(session).confirm_subject(
            tenant_id=user["tenant_id"],
            task_id=task_id,
            company_name=payload.company_name,
            credit_code=payload.credit_code,
            by=user["id"],
        )
    except DdTaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DdTaskStateError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _to_dto(task)
