"""Report store + evidence ledger (REQ-046 Slice 5, AC-2/5/6/7).

Covers the report lifecycle against the real DB:
- ``create_draft`` renders the §4.6 markdown deterministically and bumps version.
- ``confirm`` locks a draft (confirmer + timestamp); a re-run makes version+1.
- ``archive`` retires a draft / confirmed report; illegal transitions raise.
- evidence rows bind a report section to mcp_invocation / data_query refs and
  round-trip tenant-scoped.
Real DB session, no network / LLM.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.contexts.due_diligence.application.dd_report_service import (
    DdReportNotFoundError,
    DdReportService,
    DdReportStateError,
    render_report_markdown,
)
from app.contexts.due_diligence.domain.dd_task import DdEvidence
from app.contexts.due_diligence.infrastructure.dd_evidence_repository import (
    DdEvidenceRepository,
)
from app.contexts.due_diligence.infrastructure.dd_report_repository import (
    DdReportRepository,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio

_OTHER_TENANT = uuid.UUID("99999999-9999-9999-9999-999999999999")


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


async def _make_task(db_session) -> uuid.UUID:
    tid = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO metaedu.dd_tasks "
            "(id, tenant_id, title, subject_query, status, created_by, created_at, updated_at) "
            "VALUES (:id, :tid, 't', 'q', 'subject_confirmed', :cb, now(), now())"
        ),
        {"id": tid, "tid": DEFAULT_TENANT_ID, "cb": DEFAULT_ADMIN_ID},
    )
    await db_session.flush()
    return tid


_SEVEN_KEY_JSON = {
    "summary": ["总体良好"],
    "external_facts": ["工商存续"],
    "internal_facts": ["在租 1 间"],
    "risk_watch_items": ["6 个月内租约到期"],
    "human_review_items": ["核实欠费口径"],
    "evidence_refs": [],
    "report_sections": [{"title": "经营概况", "content": "稳定"}],
}


def _service(db_session) -> DdReportService:
    return DdReportService(DdReportRepository(db_session))


async def test_create_draft_renders_markdown_and_version_one(db_session):
    task_id = await _make_task(db_session)
    report = await _service(db_session).create_draft(
        tenant_id=DEFAULT_TENANT_ID,
        task_id=task_id,
        title="ACME 背调",
        report_json=_SEVEN_KEY_JSON,
        skill_execution_audit_id=uuid.uuid4(),
    )
    assert report.version == 1
    assert report.status == "draft"
    assert "外部事实" in report.report_markdown
    assert "内部事实" in report.report_markdown
    assert "在租 1 间" in report.report_markdown
    assert "经营概况" in report.report_markdown


async def test_second_run_bumps_version(db_session):
    task_id = await _make_task(db_session)
    svc = _service(db_session)
    first = await svc.create_draft(
        tenant_id=DEFAULT_TENANT_ID, task_id=task_id, title="t",
        report_json=_SEVEN_KEY_JSON, skill_execution_audit_id=None,
    )
    second = await svc.create_draft(
        tenant_id=DEFAULT_TENANT_ID, task_id=task_id, title="t",
        report_json=_SEVEN_KEY_JSON, skill_execution_audit_id=None,
    )
    assert first.version == 1
    assert second.version == 2


async def test_confirm_locks_draft(db_session):
    task_id = await _make_task(db_session)
    svc = _service(db_session)
    report = await svc.create_draft(
        tenant_id=DEFAULT_TENANT_ID, task_id=task_id, title="t",
        report_json=_SEVEN_KEY_JSON, skill_execution_audit_id=None,
    )
    confirmed = await svc.confirm(
        tenant_id=DEFAULT_TENANT_ID, report_id=report.id, by=DEFAULT_ADMIN_ID
    )
    assert confirmed.status == "confirmed"
    assert confirmed.confirmed_by == DEFAULT_ADMIN_ID
    assert confirmed.confirmed_at is not None


async def test_confirm_confirmed_report_rejected(db_session):
    task_id = await _make_task(db_session)
    svc = _service(db_session)
    report = await svc.create_draft(
        tenant_id=DEFAULT_TENANT_ID, task_id=task_id, title="t",
        report_json=_SEVEN_KEY_JSON, skill_execution_audit_id=None,
    )
    await svc.confirm(tenant_id=DEFAULT_TENANT_ID, report_id=report.id, by=DEFAULT_ADMIN_ID)
    with pytest.raises(DdReportStateError):
        await svc.confirm(
            tenant_id=DEFAULT_TENANT_ID, report_id=report.id, by=DEFAULT_ADMIN_ID
        )


async def test_archive_draft(db_session):
    task_id = await _make_task(db_session)
    svc = _service(db_session)
    report = await svc.create_draft(
        tenant_id=DEFAULT_TENANT_ID, task_id=task_id, title="t",
        report_json=_SEVEN_KEY_JSON, skill_execution_audit_id=None,
    )
    archived = await svc.archive(tenant_id=DEFAULT_TENANT_ID, report_id=report.id)
    assert archived.status == "archived"


async def test_get_report_tenant_isolated(db_session):
    task_id = await _make_task(db_session)
    svc = _service(db_session)
    report = await svc.create_draft(
        tenant_id=DEFAULT_TENANT_ID, task_id=task_id, title="t",
        report_json=_SEVEN_KEY_JSON, skill_execution_audit_id=None,
    )
    with pytest.raises(DdReportNotFoundError):
        await svc.get_report(tenant_id=_OTHER_TENANT, report_id=report.id)


async def test_evidence_roundtrip_and_order(db_session):
    task_id = await _make_task(db_session)
    svc = _service(db_session)
    report = await svc.create_draft(
        tenant_id=DEFAULT_TENANT_ID, task_id=task_id, title="t",
        report_json=_SEVEN_KEY_JSON, skill_execution_audit_id=None,
    )
    repo = DdEvidenceRepository(db_session)
    inv_id, query_id = uuid.uuid4(), uuid.uuid4()
    await repo.create(DdEvidence(
        id=uuid.uuid4(), tenant_id=DEFAULT_TENANT_ID, report_id=report.id,
        evidence_type="mcp_invocation", ref_id=inv_id,
        section="外部事实", summary="工商核验",
    ))
    await repo.create(DdEvidence(
        id=uuid.uuid4(), tenant_id=DEFAULT_TENANT_ID, report_id=report.id,
        evidence_type="data_query", ref_id=query_id,
        section="内部事实", summary="欠费问数",
    ))
    rows = await repo.list_by_report(DEFAULT_TENANT_ID, report.id)
    assert [r.evidence_type for r in rows] == ["mcp_invocation", "data_query"]
    assert rows[0].ref_id == inv_id
    assert rows[1].ref_id == query_id


async def test_render_markdown_empty_partitions_explicit():
    md = render_report_markdown(
        {"summary": [], "external_facts": [], "internal_facts": [],
         "risk_watch_items": [], "human_review_items": [],
         "evidence_refs": [], "report_sections": []},
        title="空报告",
    )
    # 空分区显式渲染"无"，不静默省略（AC-7）
    assert md.count("- 无") == 4
