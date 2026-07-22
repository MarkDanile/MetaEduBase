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
        self, *, tenant_id: uuid.UUID, title: str, subject_query: str, by: uuid.UUID,
        assignee_id: uuid.UUID | None = None,
    ) -> DdTask:
        task = DdTask(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            title=title,
            subject_query=subject_query,
            created_by=by,
            assignee_id=assignee_id,
        )
        return await self._repo.create(task)

    async def get_task(
        self, *, tenant_id: uuid.UUID, task_id: uuid.UUID,
        viewer_id: uuid.UUID | None = None, viewer_role: str | None = None,
    ) -> DdTask:
        task = await self._repo.get_by_id(tenant_id, task_id)
        # REQ-058 AC-1/AC-2: 跨租户 / 不可见 -> 404（不暴露存在性）
        if task is None or (
            viewer_id is not None
            and viewer_role is not None
            and not task.visible_to(viewer_id, role=viewer_role)
        ):
            raise DdTaskNotFoundError(task_id)
        return task

    async def list_tasks(
        self, *, tenant_id: uuid.UUID,
        viewer_id: uuid.UUID | None = None, viewer_role: str | None = None,
    ) -> list[DdTask]:
        tasks = await self._repo.list_by_tenant(tenant_id)
        # REQ-058 D-3: 可见性过滤（创建者 + 分配对象 + 高权）
        if viewer_id is not None and viewer_role is not None:
            tasks = [t for t in tasks if t.visible_to(viewer_id, role=viewer_role)]
        return tasks

    async def assign_task(
        self, *, tenant_id: uuid.UUID, task_id: uuid.UUID, assignee_id: uuid.UUID,
    ) -> DdTask:
        """REQ-058 D-3: 设置任务 assignee。"""
        task = await self.get_task(tenant_id=tenant_id, task_id=task_id)
        task.assignee_id = assignee_id
        return await self._repo.update(task)

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
