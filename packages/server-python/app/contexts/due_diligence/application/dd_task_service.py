"""Due-diligence task service: workbench container orchestration (REQ-046 Slice 1).

Thin application service over ``DdTaskRepository`` + ``SubjectResolver``. It
owns the task lifecycle entry points used by the API: create (subject_pending)
-> resolve candidates -> confirm (subject_confirmed). Running a report is
gated by the domain invariant ``DdTask.assert_can_run`` (AC-1) and arrives
with Slice 5; this slice only delivers the anchoring container.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.contexts.due_diligence.application.subject_resolver import SubjectResolver
from app.contexts.due_diligence.domain.dd_task import DdTask, SubjectCandidate
from app.contexts.due_diligence.infrastructure.dd_task_repository import (
    DdTaskRepository,
)
from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
)


def _utcnow() -> datetime:
    """Naive UTC datetime matching the project convention (TIMESTAMP WITHOUT TZ)."""
    return datetime.now(UTC).replace(tzinfo=None)


class DdTaskError(Exception):
    """Base for due-diligence task service errors, carrying a stable error_code."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class DdTaskNotFoundError(DdTaskError):
    def __init__(self, task_id: uuid.UUID) -> None:
        super().__init__("not_found", f"背调任务不存在: {task_id}")


class DdTaskService:
    """Workbench task container orchestration (tenant-scoped)."""

    def __init__(self, repo: DdTaskRepository, resolver: SubjectResolver) -> None:
        self._repo = repo
        self._resolver = resolver

    async def create_task(
        self, *, tenant_id: uuid.UUID, title: str, subject_query: str, by: uuid.UUID
    ) -> DdTask:
        task = DdTask(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            title=title,
            subject_query=subject_query,
            created_by=by,
        )
        return await self._repo.create(task)

    async def get_task(self, *, tenant_id: uuid.UUID, task_id: uuid.UUID) -> DdTask:
        task = await self._repo.get_by_id(tenant_id, task_id)
        if task is None:
            raise DdTaskNotFoundError(task_id)
        return task

    async def list_tasks(self, *, tenant_id: uuid.UUID) -> list[DdTask]:
        return await self._repo.list_by_tenant(tenant_id)

    async def resolve_subject(
        self, *, tenant_id: uuid.UUID, task_id: uuid.UUID, caller: InvocationCaller
    ) -> list[SubjectCandidate]:
        task = await self.get_task(tenant_id=tenant_id, task_id=task_id)
        return await self._resolver.resolve(
            tenant_id=tenant_id, query=task.subject_query, caller=caller
        )

    async def confirm_subject(
        self,
        *,
        tenant_id: uuid.UUID,
        task_id: uuid.UUID,
        company_name: str,
        credit_code: str | None,
        by: uuid.UUID,
    ) -> DdTask:
        task = await self.get_task(tenant_id=tenant_id, task_id=task_id)
        candidate = SubjectResolver.to_candidate(company_name, credit_code)
        task.confirm_subject(candidate, by=by, at=_utcnow())
        return await self._repo.save(task)
