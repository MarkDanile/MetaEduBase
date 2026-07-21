"""Skill execution audit repository for REQ-045 Task 3.

Writes and queries ``metaedu.skill_execution_audit``. Every query is
forced through ``tenant_id`` — audit rows are as strictly isolated as
the skill registrations themselves (spec §4.2, AC-7), mirroring
:class:`InvocationAuditRepository` (REQ-044).

Only sha256 *digests* of the subject / per-step results / synthesized
report are ever stored here; raw facts and report bodies never reach
this repository by contract of :class:`SkillRunner` (the sole writer).
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.skill_registry.infrastructure.skill_models import (
    SkillExecutionAuditModel,
)


class SkillExecutionAuditRepository:
    """Async repository over ``metaedu.skill_execution_audit``."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def write(
        self,
        *,
        tenant_id: uuid.UUID,
        skill_id: uuid.UUID,
        skill_code: str,
        skill_version: str,
        caller_type: str,
        caller_user_id: uuid.UUID | None,
        subject_digest: str | None,
        steps_digest: str | None,
        report_digest: str | None,
        ok: bool,
        error_code: str | None,
        error_message: str | None,
        duration_ms: int,
    ) -> SkillExecutionAuditModel:
        """Insert one audit row (flush only — caller owns the commit)."""
        row = SkillExecutionAuditModel(
            tenant_id=tenant_id,
            skill_id=skill_id,
            skill_code=skill_code,
            skill_version=skill_version,
            caller_type=caller_type,
            caller_user_id=caller_user_id,
            subject_digest=subject_digest,
            steps_digest=steps_digest,
            report_digest=report_digest,
            ok=ok,
            error_code=error_code,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_by_skill(
        self,
        tenant_id: uuid.UUID,
        skill_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SkillExecutionAuditModel], int]:
        """Paginated audit rows for one skill, tenant-forced.

        Returns ``(rows, total)`` newest-first so the management UI can
        page a deterministic, isolation-safe view (spec §4.5).
        """
        base = select(SkillExecutionAuditModel).where(
            SkillExecutionAuditModel.tenant_id == tenant_id,
            SkillExecutionAuditModel.skill_id == skill_id,
        )
        total = await self._session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        result = await self._session.execute(
            base.order_by(SkillExecutionAuditModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)
