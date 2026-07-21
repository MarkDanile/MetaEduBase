"""Due-diligence report store: draft / confirm / archive (REQ-046 Slice 5).

Persists report versions produced by the orchestrator (§4.6 seven-key
``report_json`` + workbench-rendered ``report_markdown``) and drives the
report lifecycle:

    draft  --confirm-->  confirmed   (locks the version; a re-run makes version+1)
    draft|confirmed --archive--> archived

Every query is tenant-scoped. ``(task_id, version)`` is unique, so
``create_draft`` always writes ``max(existing version) + 1``.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.due_diligence.domain.dd_task import DdReport
from app.contexts.due_diligence.infrastructure.dd_models import DdReportModel


class DdReportRepository:
    """Async repository over ``metaedu.dd_reports`` (tenant-scoped)."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, report: DdReport) -> DdReport:
        row = DdReportModel(
            id=report.id,
            tenant_id=report.tenant_id,
            task_id=report.task_id,
            version=report.version,
            status=report.status,
            report_json=report.report_json,
            report_markdown=report.report_markdown,
            skill_execution_audit_id=report.skill_execution_audit_id,
            confirmed_by=report.confirmed_by,
            confirmed_at=report.confirmed_at,
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_domain(row)

    async def get_by_id(
        self, tenant_id: uuid.UUID, report_id: uuid.UUID
    ) -> DdReport | None:
        stmt = select(DdReportModel).where(
            DdReportModel.id == report_id,
            DdReportModel.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list_by_task(
        self, tenant_id: uuid.UUID, task_id: uuid.UUID
    ) -> list[DdReport]:
        stmt = (
            select(DdReportModel)
            .where(
                DdReportModel.tenant_id == tenant_id,
                DdReportModel.task_id == task_id,
            )
            .order_by(DdReportModel.version.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def next_version(self, tenant_id: uuid.UUID, task_id: uuid.UUID) -> int:
        stmt = select(func.max(DdReportModel.version)).where(
            DdReportModel.tenant_id == tenant_id,
            DdReportModel.task_id == task_id,
        )
        result = await self._session.execute(stmt)
        current = result.scalar_one_or_none()
        return (current or 0) + 1

    async def save(self, report: DdReport) -> DdReport:
        stmt = select(DdReportModel).where(
            DdReportModel.id == report.id,
            DdReportModel.tenant_id == report.tenant_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return report
        row.status = report.status
        row.report_json = report.report_json
        row.report_markdown = report.report_markdown
        row.confirmed_by = report.confirmed_by
        row.confirmed_at = report.confirmed_at
        row.skill_execution_audit_id = report.skill_execution_audit_id
        await self._session.flush()
        return self._to_domain(row)

    def _to_domain(self, row: DdReportModel) -> DdReport:
        return DdReport(
            id=row.id,
            tenant_id=row.tenant_id,
            task_id=row.task_id,
            version=row.version,
            status=row.status,
            report_json=row.report_json,
            report_markdown=row.report_markdown,
            skill_execution_audit_id=row.skill_execution_audit_id,
            confirmed_by=row.confirmed_by,
            confirmed_at=row.confirmed_at,
        )
