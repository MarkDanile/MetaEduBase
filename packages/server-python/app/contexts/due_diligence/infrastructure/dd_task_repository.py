"""Due-diligence task repository: CRUD + tenant 隔离 (REQ-046 Slice 1).

Every query is scoped by ``tenant_id`` so one tenant cannot read or mutate
another tenant's due-diligence tasks. V0 keeps hard rows (no soft delete —
tasks are workbench containers, not audited entities); report / evidence
repositories arrive with Slice 5.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.due_diligence.domain.dd_task import DdTask
from app.contexts.due_diligence.infrastructure.dd_models import DdTaskModel


class DdTaskRepository:
    """Async CRUD repository over ``metaedu.dd_tasks``."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, task: DdTask) -> DdTask:
        row = DdTaskModel(
            id=task.id,
            tenant_id=task.tenant_id,
            title=task.title,
            subject_query=task.subject_query,
            status=task.status,
            confirmed_subject=task.confirmed_subject,
            confirmed_by=task.confirmed_by,
            confirmed_at=task.confirmed_at,
            skill_execution_audit_id=task.skill_execution_audit_id,
            created_by=task.created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_domain(row)

    async def get_by_id(
        self, tenant_id: uuid.UUID, task_id: uuid.UUID
    ) -> DdTask | None:
        stmt = select(DdTaskModel).where(
            DdTaskModel.id == task_id,
            DdTaskModel.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[DdTask]:
        stmt = (
            select(DdTaskModel)
            .where(DdTaskModel.tenant_id == tenant_id)
            .order_by(DdTaskModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def save(self, task: DdTask) -> DdTask:
        """Persist a mutated aggregate (status / confirmed_subject / ...)."""
        stmt = select(DdTaskModel).where(
            DdTaskModel.id == task.id,
            DdTaskModel.tenant_id == task.tenant_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return task
        row.status = task.status
        row.confirmed_subject = task.confirmed_subject
        row.confirmed_by = task.confirmed_by
        row.confirmed_at = task.confirmed_at
        row.skill_execution_audit_id = task.skill_execution_audit_id
        row.assignee_id = task.assignee_id
        await self._session.flush()
        return self._to_domain(row)

    def _to_domain(self, row: DdTaskModel) -> DdTask:
        return DdTask(
            id=row.id,
            tenant_id=row.tenant_id,
            title=row.title,
            subject_query=row.subject_query,
            status=row.status,
            confirmed_subject=row.confirmed_subject,
            confirmed_by=row.confirmed_by,
            confirmed_at=row.confirmed_at,
            skill_execution_audit_id=row.skill_execution_audit_id,
            created_by=row.created_by,
            assignee_id=row.assignee_id,
        )
