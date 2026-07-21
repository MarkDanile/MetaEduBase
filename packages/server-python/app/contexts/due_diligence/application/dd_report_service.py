"""Due-diligence report service: draft / confirm / archive lifecycle (REQ-046 Slice 5).

Wraps :class:`DdReportRepository` with the report state machine and the
deterministic workbench rendering. ``create_draft`` renders the enterprise-profile
markdown from the structured §4.6 ``report_json`` (external / internal facts,
risk watch, human review, per-section bodies) — the markdown is a faithful
projection of the JSON, never re-synthesized, so the archived report and the
evidence ledger always agree (AC-5: facts / analysis / human-review stay
partitioned).

``confirm`` locks a draft (records confirmer + timestamp); a subsequent run of
the same task produces ``version + 1`` rather than mutating the confirmed
report. ``archive`` retires a draft or confirmed report.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.contexts.due_diligence.domain.dd_task import DdReport, DdTaskStateError
from app.contexts.due_diligence.infrastructure.dd_report_repository import (
    DdReportRepository,
)

# Re-export the domain invalid-transition error under the report-service name
# so callers/tests catch a report-scoped type with the same "invalid_transition"
# error_code.
DdReportStateError = DdTaskStateError


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class DdReportError(Exception):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class DdReportNotFoundError(DdReportError):
    def __init__(self, report_id: uuid.UUID) -> None:
        super().__init__("not_found", f"背调报告不存在: {report_id}")


def render_report_markdown(report_json: dict, *, title: str) -> str:
    """Render the enterprise-profile markdown from §4.6 structured report_json.

    Deterministic projection (no LLM): partitions 外部事实 / 内部事实 /
    风险关注点 / 待人工确认项, then any free-form ``report_sections``. Empty
    partitions render an explicit "无" so a missing dimension reads as "none
    returned", never silently omitted (AC-7).
    """

    def _bullets(key: str) -> list[str]:
        items = report_json.get(key) or []
        return [f"- {item}" for item in items] or ["- 无"]

    lines = [f"# {title}", ""]
    summary = report_json.get("summary") or []
    if summary:
        lines += ["## 摘要", *[f"- {s}" for s in summary], ""]
    lines += ["## 外部事实（企查查）", *_bullets("external_facts"), ""]
    lines += ["## 内部事实（园区）", *_bullets("internal_facts"), ""]
    lines += ["## 风险关注点", *_bullets("risk_watch_items"), ""]
    lines += ["## 待人工确认项", *_bullets("human_review_items"), ""]
    for section in report_json.get("report_sections") or []:
        lines += [f"## {section.get('title', '未命名章节')}", section.get("content", ""), ""]
    lines += [
        "## 证据来源",
        "各关键结论的来源绑定详见证据账本（evidence ledger）；"
        "缺失来源的结论一律标注'未返回 / 未接入 / 待人工补充'。",
    ]
    return "\n".join(lines).rstrip() + "\n"


class DdReportService:
    """Report draft / confirm / archive orchestration (tenant-scoped)."""

    def __init__(self, repo: DdReportRepository) -> None:
        self._repo = repo

    async def create_draft(
        self,
        *,
        tenant_id: uuid.UUID,
        task_id: uuid.UUID,
        title: str,
        report_json: dict,
        skill_execution_audit_id: uuid.UUID | None,
    ) -> DdReport:
        version = await self._repo.next_version(tenant_id, task_id)
        report = DdReport(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            task_id=task_id,
            version=version,
            status="draft",
            report_json=report_json,
            report_markdown=render_report_markdown(report_json, title=title),
            skill_execution_audit_id=skill_execution_audit_id,
        )
        return await self._repo.create(report)

    async def get_report(self, *, tenant_id: uuid.UUID, report_id: uuid.UUID) -> DdReport:
        report = await self._repo.get_by_id(tenant_id, report_id)
        if report is None:
            raise DdReportNotFoundError(report_id)
        return report

    async def list_by_task(self, *, tenant_id: uuid.UUID, task_id: uuid.UUID) -> list[DdReport]:
        return await self._repo.list_by_task(tenant_id, task_id)

    async def confirm(
        self, *, tenant_id: uuid.UUID, report_id: uuid.UUID, by: uuid.UUID
    ) -> DdReport:
        report = await self.get_report(tenant_id=tenant_id, report_id=report_id)
        return await self._repo.save(report.confirm(by=by, at=_utcnow()))

    async def archive(self, *, tenant_id: uuid.UUID, report_id: uuid.UUID) -> DdReport:
        report = await self.get_report(tenant_id=tenant_id, report_id=report_id)
        return await self._repo.save(report.archive())
