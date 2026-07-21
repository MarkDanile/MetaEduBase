"""Due-diligence orchestrator: run a confirmed task into a report (REQ-046 Slice 5).

The single entry point that turns a ``subject_confirmed`` task into an archived
enterprise-360 report:

    DdTask.assert_can_run          (AC-1 state gate — never run unconfirmed)
      -> SkillRunner.run(park_investment_dd, confirmed_subject)
         (three-channel SOP: QCC + internal customer + internal_query; the
         runner binds real audit ids per step and validates §4.6 report_contract)
      -> ReportService.create_draft(report_json + rendered markdown, version+1)
      -> Evidence ledger: one row per step evidence_ref (mcp_invocation /
         data_query) so every key fact traces to an auditable source (§4.7/AC-6)
      -> task.mark_review + skill_execution_audit_id persisted

The skill execution audit row (digests only) is written by the SkillRunner; the
report + evidence are business tables (raw content allowed, tenant-scoped).
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.due_diligence.application.dd_report_service import DdReportService
from app.contexts.due_diligence.domain.dd_task import DdEvidence, DdReport, DdTask
from app.contexts.due_diligence.infrastructure.dd_evidence_repository import (
    DdEvidenceRepository,
)
from app.contexts.due_diligence.infrastructure.dd_task_repository import (
    DdTaskRepository,
)
from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
)
from app.contexts.skill_registry.application.skill_runner import (
    SkillResult,
    SkillRunner,
)

DD_SKILL_CODE = "park_investment_dd"
DD_SKILL_VERSION = "1.0.0"

# evidence_ref.evidence_type -> section label shown in the ledger (§4.7).
_TYPE_TO_SECTION = {
    "mcp_invocation": "外部/内部客户事实",
    "data_query": "内部问数",
}


class DdOrchestrator:
    """Run a confirmed DD task through the skill engine into report + evidence."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        runner: SkillRunner,
        report_service: DdReportService,
    ) -> None:
        self._session = session
        self._runner = runner
        self._reports = report_service
        self._tasks = DdTaskRepository(session)
        self._evidence = DdEvidenceRepository(session)

    async def run(
        self, *, tenant_id: uuid.UUID, task: DdTask, caller: InvocationCaller
    ) -> DdReport:
        """Execute the DD skill for ``task`` and persist report + evidence.

        Raises the domain ``SubjectNotConfirmedError`` (AC-1) before any skill
        call when the task is not in a runnable state.
        """
        task.assert_can_run()
        task.mark_running()
        subject = task.confirmed_subject or {}
        result: SkillResult = await self._runner.run(
            tenant_id=tenant_id,
            skill_code=DD_SKILL_CODE,
            version=DD_SKILL_VERSION,
            subject=subject,
            caller=caller,
        )
        report_json = result.report_json or {}
        report = await self._reports.create_draft(
            tenant_id=tenant_id,
            task_id=task.id,
            title=task.title,
            report_json=report_json,
            skill_execution_audit_id=result.execution_audit_id,
        )
        await self._record_evidence(tenant_id=tenant_id, report=report, result=result)

        task.mark_review()
        task.skill_execution_audit_id = result.execution_audit_id
        await self._tasks.save(task)
        return report

    async def _record_evidence(
        self, *, tenant_id: uuid.UUID, report: DdReport, result: SkillResult
    ) -> None:
        """Persist one ledger row per evidence_ref the runner bound (§4.7).

        The runner already replaced LLM-declared refs with real audit ids; we
        only translate them into ledger rows. Refs that carry no resolvable id
        are skipped (they would point at nothing auditable).
        """
        for ref in (result.report_json or {}).get("evidence_refs") or []:
            ref_id_raw = ref.get("ref_id")
            try:
                ref_id = uuid.UUID(str(ref_id_raw)) if ref_id_raw else None
            except (TypeError, ValueError):
                ref_id = None
            if ref_id is None:
                continue
            evidence_type = ref.get("evidence_type", "")
            await self._evidence.create(
                DdEvidence(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    report_id=report.id,
                    evidence_type=evidence_type,
                    ref_id=ref_id,
                    section=_TYPE_TO_SECTION.get(evidence_type, "其他"),
                    summary=f"step {ref.get('source_step', '')}".strip(),
                )
            )
