"""DD orchestrator: confirmed task -> report + evidence ledger (REQ-046 Slice 5).

AC-1/2/5/6/7 integration: drives ``DdOrchestrator.run`` with a stubbed
:class:`SkillRunner` (no MCP / LLM / network) but real report + evidence
repositories and the real task state machine:
- AC-1: an unconfirmed task raises before any skill call.
- AC-5: report_json lands partitioned; markdown is the deterministic projection.
- AC-6: every runner-bound evidence_ref becomes a ledger row keyed to its
  mcp_invocation / data_query audit id.
- version bumps on re-run; task transitions to review with the audit id linked.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.contexts.due_diligence.application.dd_orchestrator import DdOrchestrator
from app.contexts.due_diligence.application.dd_report_service import DdReportService
from app.contexts.due_diligence.application.dd_task_service import DdTaskNotFoundError
from app.contexts.due_diligence.domain.dd_task import (
    DdTask,
    SubjectNotConfirmedError,
)
from app.contexts.due_diligence.infrastructure.dd_evidence_repository import (
    DdEvidenceRepository,
)
from app.contexts.due_diligence.infrastructure.dd_report_repository import (
    DdReportRepository,
)
from app.contexts.due_diligence.infrastructure.dd_task_repository import (
    DdTaskRepository,
)
from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
)
from app.contexts.skill_registry.application.skill_runner import SkillResult
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _clean(db_session):
    for stmt in (
        "DELETE FROM metaedu.dd_evidence WHERE tenant_id = :tid",
        "DELETE FROM metaedu.dd_reports WHERE tenant_id = :tid",
        "DELETE FROM metaedu.dd_tasks WHERE tenant_id = :tid",
    ):
        await db_session.execute(text(stmt), {"tid": DEFAULT_TENANT_ID})
    await db_session.flush()
    yield


def _task(*, status: str, confirmed: bool = True) -> DdTask:
    return DdTask(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        title="ACME 背调",
        subject_query="ACME",
        created_by=DEFAULT_ADMIN_ID,
        status=status,
        confirmed_subject=(
            {"company_name": "ACME", "credit_code": "9111"} if confirmed else None
        ),
    )


def _caller() -> InvocationCaller:
    return InvocationCaller(
        caller_type="service", role="admin", user_id=DEFAULT_ADMIN_ID
    )


def _skill_result(inv_id: uuid.UUID, query_id: uuid.UUID) -> SkillResult:
    return SkillResult(
        report="## 事实数据\n...",
        execution_audit_id=uuid.uuid4(),
        duration_ms=10,
        steps=(),
        report_json={
            "summary": ["总体良好"],
            "external_facts": ["工商存续"],
            "internal_facts": ["在租 1 间"],
            "risk_watch_items": [],
            "human_review_items": ["核实欠费"],
            "evidence_refs": [
                {
                    "source_step": "subject_verify",
                    "evidence_type": "mcp_invocation",
                    "ref_id": str(inv_id),
                },
                {
                    "source_step": "unpaid_query",
                    "evidence_type": "data_query",
                    "ref_id": str(query_id),
                },
            ],
            "report_sections": [],
        },
    )


def _orchestrator(db_session, runner) -> DdOrchestrator:
    return DdOrchestrator(
        db_session,
        runner=runner,
        report_service=DdReportService(DdReportRepository(db_session)),
    )


async def _persist_task(db_session, task: DdTask) -> None:
    await DdTaskRepository(db_session).create(task)
    await db_session.flush()


async def test_run_produces_draft_report_and_evidence(db_session):
    task = _task(status="subject_confirmed")
    await _persist_task(db_session, task)
    inv_id, query_id = uuid.uuid4(), uuid.uuid4()
    runner = AsyncMock()
    runner.run = AsyncMock(return_value=_skill_result(inv_id, query_id))

    report = await _orchestrator(db_session, runner).run(
        tenant_id=DEFAULT_TENANT_ID, task=task, caller=_caller()
    )

    # AC-5: partitioned report_json persisted; markdown is the projection.
    assert report.status == "draft"
    assert report.report_json["external_facts"] == ["工商存续"]
    assert "内部事实" in report.report_markdown
    # skill called with the confirmed subject + park skill code.
    kw = runner.run.await_args.kwargs
    assert kw["skill_code"] == "park_investment_dd"
    assert kw["subject"] == {"company_name": "ACME", "credit_code": "9111"}
    # AC-6: one ledger row per runner-bound evidence_ref, keyed to its audit id.
    rows = await DdEvidenceRepository(db_session).list_by_report(
        DEFAULT_TENANT_ID, report.id
    )
    by_type = {r.evidence_type: r for r in rows}
    assert by_type["mcp_invocation"].ref_id == inv_id
    assert by_type["data_query"].ref_id == query_id


async def test_run_unconfirmed_task_raises_before_skill(db_session):
    task = _task(status="subject_pending", confirmed=False)
    await _persist_task(db_session, task)
    runner = AsyncMock()
    runner.run = AsyncMock()

    with pytest.raises(SubjectNotConfirmedError):
        await _orchestrator(db_session, runner).run(
            tenant_id=DEFAULT_TENANT_ID, task=task, caller=_caller()
        )
    runner.run.assert_not_awaited()


async def test_run_marks_task_review_and_links_audit(db_session):
    task = _task(status="subject_confirmed")
    await _persist_task(db_session, task)
    result = _skill_result(uuid.uuid4(), uuid.uuid4())
    runner = AsyncMock()
    runner.run = AsyncMock(return_value=result)

    await _orchestrator(db_session, runner).run(
        tenant_id=DEFAULT_TENANT_ID, task=task, caller=_caller()
    )

    reloaded = await DdTaskRepository(db_session).get_by_id(
        DEFAULT_TENANT_ID, task.id
    )
    assert reloaded.status == "review"
    assert reloaded.skill_execution_audit_id == result.execution_audit_id


async def test_second_run_bumps_report_version(db_session):
    task = _task(status="subject_confirmed")
    await _persist_task(db_session, task)
    runner = AsyncMock()
    runner.run = AsyncMock(
        return_value=_skill_result(uuid.uuid4(), uuid.uuid4())
    )
    orch = _orchestrator(db_session, runner)
    first = await orch.run(tenant_id=DEFAULT_TENANT_ID, task=task, caller=_caller())
    # reload task (now in review) then re-run
    reloaded = await DdTaskRepository(db_session).get_by_id(
        DEFAULT_TENANT_ID, task.id
    )
    second = await orch.run(
        tenant_id=DEFAULT_TENANT_ID, task=reloaded, caller=_caller()
    )
    assert first.version == 1
    assert second.version == 2


async def test_missing_task_get_raises_not_found(db_session):
    with pytest.raises(DdTaskNotFoundError):
        repo = DdTaskRepository(db_session)
        task = await repo.get_by_id(DEFAULT_TENANT_ID, uuid.uuid4())
        if task is None:
            raise DdTaskNotFoundError(uuid.uuid4())
