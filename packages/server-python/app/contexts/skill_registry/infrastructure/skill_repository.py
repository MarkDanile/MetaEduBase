"""Skill repository: CRUD + 版本 + tenant 隔离.

REQ-045 Task 2: every query is scoped by ``tenant_id`` so that one tenant
cannot read or mutate another tenant's skill registrations. Soft delete
(``is_active = False``) is the only delete path — audit rows in
``skill_execution_audit`` hold an FK to ``skills.id``, so a registered
skill version is never hard-deleted.

Multiple versions of the same ``code`` coexist; ``(tenant_id, code,
version)`` is unique. ``sop_template`` is the YAML body of a declarative
SOP — it never contains secrets by design.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.skill_registry.domain.skill import Skill
from app.contexts.skill_registry.infrastructure.skill_models import SkillModel


class SkillRepository:
    """Async CRUD repository over ``metaedu.skills``."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, skill: Skill) -> Skill:
        row = SkillModel(
            id=skill.id,
            tenant_id=skill.tenant_id,
            code=skill.code,
            version=skill.version,
            name=skill.name,
            description=skill.description,
            sop_template=skill.sop_template,
            source_ref=skill.source_ref,
            allowed_roles=skill.allowed_roles,
            enabled=skill.enabled,
            is_active=skill.is_active,
            created_by=skill.created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_domain(row)

    async def get_by_id(
        self, tenant_id: uuid.UUID, skill_id: uuid.UUID
    ) -> Skill | None:
        stmt = select(SkillModel).where(
            SkillModel.id == skill_id,
            SkillModel.tenant_id == tenant_id,
            SkillModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_by_code_version(
        self, tenant_id: uuid.UUID, code: str, version: str
    ) -> Skill | None:
        stmt = select(SkillModel).where(
            SkillModel.tenant_id == tenant_id,
            SkillModel.code == code,
            SkillModel.version == version,
            SkillModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list_by_tenant(
        self, tenant_id: uuid.UUID, include_inactive: bool = False
    ) -> list[Skill]:
        stmt = select(SkillModel).where(SkillModel.tenant_id == tenant_id)
        if not include_inactive:
            stmt = stmt.where(SkillModel.is_active == True)  # noqa: E712
        stmt = stmt.order_by(SkillModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def list_versions(self, tenant_id: uuid.UUID, code: str) -> list[Skill]:
        """同 code 的全部 active 版本，按创建时间升序（v1 在前）。"""
        stmt = (
            select(SkillModel)
            .where(
                SkillModel.tenant_id == tenant_id,
                SkillModel.code == code,
                SkillModel.is_active == True,  # noqa: E712
            )
            .order_by(SkillModel.created_at.asc(), SkillModel.version.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def update(
        self,
        tenant_id: uuid.UUID,
        skill_id: uuid.UUID,
        **kwargs: object,
    ) -> Skill | None:
        stmt = select(SkillModel).where(
            SkillModel.id == skill_id,
            SkillModel.tenant_id == tenant_id,
            SkillModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return None
        for key, val in kwargs.items():
            if val is not None and hasattr(row, key):
                setattr(row, key, val)
        await self._session.flush()
        return self._to_domain(row)

    async def set_enabled(
        self, tenant_id: uuid.UUID, skill_id: uuid.UUID, enabled: bool
    ) -> Skill | None:
        stmt = select(SkillModel).where(
            SkillModel.id == skill_id,
            SkillModel.tenant_id == tenant_id,
            SkillModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return None
        row.enabled = enabled
        await self._session.flush()
        return self._to_domain(row)

    async def soft_delete(
        self, tenant_id: uuid.UUID, skill_id: uuid.UUID
    ) -> bool:
        """Soft delete only — never row-delete.

        ``skill_execution_audit.skill_id`` FK references this row, so hard
        delete would break audit traceability (spec §4.5: 有审计行的版本
        不硬删 — V1 统一软删）.
        """
        stmt = select(SkillModel).where(
            SkillModel.id == skill_id,
            SkillModel.tenant_id == tenant_id,
            SkillModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return False
        row.is_active = False
        await self._session.flush()
        return True

    def _to_domain(self, row: SkillModel) -> Skill:
        return Skill(
            id=row.id,
            tenant_id=row.tenant_id,
            code=row.code,
            version=row.version,
            name=row.name,
            description=row.description,
            sop_template=row.sop_template,
            source_ref=row.source_ref,
            allowed_roles=list(row.allowed_roles or []),
            enabled=row.enabled,
            is_active=row.is_active,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
