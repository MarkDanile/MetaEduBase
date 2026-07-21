"""Due-diligence evidence ledger repository (REQ-046 Slice 5, §4.7).

Each row binds a report section to one auditable source — an MCP invocation
(``mcp_invocation``), a structured data query (``data_query``), a document, or
a manual entry — via ``ref_id``. The ledger is what lets a reviewer trace every
key fact back to its origin; ``summary`` is non-sensitive display text only.
Tenant-scoped reads.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.due_diligence.domain.dd_task import DdEvidence
from app.contexts.due_diligence.infrastructure.dd_models import DdEvidenceModel


class DdEvidenceRepository:
    """Async repository over ``metaedu.dd_evidence`` (tenant-scoped)."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, evidence: DdEvidence) -> DdEvidence:
        row = DdEvidenceModel(
            id=evidence.id,
            tenant_id=evidence.tenant_id,
            report_id=evidence.report_id,
            evidence_type=evidence.evidence_type,
            ref_id=evidence.ref_id,
            section=evidence.section,
            summary=evidence.summary,
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_domain(row)

    async def list_by_report(
        self, tenant_id: uuid.UUID, report_id: uuid.UUID
    ) -> list[DdEvidence]:
        stmt = (
            select(DdEvidenceModel)
            .where(
                DdEvidenceModel.tenant_id == tenant_id,
                DdEvidenceModel.report_id == report_id,
            )
            .order_by(DdEvidenceModel.created_at.asc(), DdEvidenceModel.id.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    def _to_domain(self, row: DdEvidenceModel) -> DdEvidence:
        return DdEvidence(
            id=row.id,
            tenant_id=row.tenant_id,
            report_id=row.report_id,
            evidence_type=row.evidence_type,
            ref_id=row.ref_id,
            section=row.section,
            summary=row.summary,
        )
