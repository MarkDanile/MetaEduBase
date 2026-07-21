"""Due-diligence domain: task state machine + subject anchoring (REQ-046 Slice 1).

Pure domain logic — no DB, no HTTP. ``DdTask`` is the workbench aggregate: it
drives the subject-anchoring state machine (spec §4.2 / AC-1) so a raw company
name input can never reach downstream QCC risk/shareholder tools until the
user has confirmed a resolved subject.

State machine::

    subject_pending  --confirm_subject-->  subject_confirmed
    subject_confirmed --mark_running-->    running
    running          --mark_review-->      review
    review           --mark_archived-->    archived
    any active       --mark_failed-->      failed

The single hard invariant (AC-1): ``assert_can_run`` raises unless the task is
``subject_confirmed`` — running a due-diligence report on an unconfirmed
subject is forbidden, so a bare 简称/品牌名 can never trigger risk scans.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime

# spec §4.2 状态机合法迁移:状态 -> 允许的后继状态集合
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "subject_pending": frozenset({"subject_confirmed", "failed"}),
    "subject_confirmed": frozenset({"running", "failed"}),
    "running": frozenset({"review", "failed"}),
    "review": frozenset({"archived", "running", "failed"}),
    "archived": frozenset(),
    "failed": frozenset({"subject_pending", "subject_confirmed"}),
}


class DdTaskError(Exception):
    """Base for due-diligence task domain errors, carrying a stable error_code."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class DdTaskStateError(DdTaskError):
    """Illegal status transition or run attempted on a non-confirmed subject."""


class SubjectNotConfirmedError(DdTaskError):
    """AC-1: run attempted while the subject is not yet confirmed."""


@dataclass(frozen=True)
class SubjectCandidate:
    """A resolved subject candidate returned by the QCC entity-anchoring query."""

    company_name: str
    credit_code: str | None = None


@dataclass
class DdTask:
    """Workbench aggregate for one due-diligence task (REQ-041 V0 container)."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    subject_query: str
    created_by: uuid.UUID
    status: str = "subject_pending"
    confirmed_subject: dict | None = None
    confirmed_by: uuid.UUID | None = None
    confirmed_at: datetime | None = None
    skill_execution_audit_id: uuid.UUID | None = None

    def _transition(self, target: str) -> None:
        allowed = _ALLOWED_TRANSITIONS.get(self.status, frozenset())
        if target not in allowed:
            raise DdTaskStateError(
                "invalid_transition",
                f"任务状态不能从 '{self.status}' 迁移到 '{target}'",
            )
        self.status = target

    def confirm_subject(
        self, candidate: SubjectCandidate, by: uuid.UUID, at: datetime
    ) -> None:
        """Confirm the resolved subject (AC-1): record it and advance the state.

        The confirmed subject is stored verbatim (``{company_name, credit_code}``)
        so downstream steps run against the user-anchored entity, not the raw query.
        """
        self._transition("subject_confirmed")
        self.confirmed_subject = {
            "company_name": candidate.company_name,
            "credit_code": candidate.credit_code,
        }
        self.confirmed_by = by
        self.confirmed_at = at

    def assert_can_run(self) -> None:
        """AC-1 硬约束:主体未确认禁止运行(下游 QCC 工具不可触达)。

        ``subject_confirmed``(首次运行)与 ``review``(确认后重跑,主体仍在
        ``confirmed_subject`` 里)都允许;其余状态禁止。
        """
        if self.status == "review" and self.confirmed_subject:
            return
        if self.status != "subject_confirmed":
            raise SubjectNotConfirmedError(
                "subject_not_confirmed",
                f"主体未确认(当前状态 '{self.status}'),禁止生成背调报告",
            )

    def mark_running(self) -> None:
        self.assert_can_run()
        self._transition("running")

    def mark_review(self) -> None:
        self._transition("review")

    def mark_archived(self) -> None:
        self._transition("archived")

    def mark_failed(self) -> None:
        self._transition("failed")


@dataclass(frozen=True)
class DdReport:
    """A report draft / confirmed / archived version for a task (spec §4.6)."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    task_id: uuid.UUID
    version: int
    report_json: dict
    report_markdown: str
    status: str = "draft"
    skill_execution_audit_id: uuid.UUID | None = None
    confirmed_by: uuid.UUID | None = None
    confirmed_at: datetime | None = None

    def confirm(self, *, by: uuid.UUID, at: datetime) -> DdReport:
        """Lock a draft (spec §4.6): records confirmer + timestamp. A re-run
        produces ``version + 1`` instead of mutating the confirmed report."""
        if self.status != "draft":
            raise DdTaskStateError(
                "invalid_transition",
                f"报告状态不能从 '{self.status}' 迁移到 'confirmed'",
            )
        return replace(self, status="confirmed", confirmed_by=by, confirmed_at=at)

    def archive(self) -> DdReport:
        """Retire a draft or confirmed report."""
        if self.status not in ("draft", "confirmed"):
            raise DdTaskStateError(
                "invalid_transition",
                f"报告状态不能从 '{self.status}' 迁移到 'archived'",
            )
        return replace(self, status="archived")


@dataclass(frozen=True)
class DdEvidence:
    """One evidence-ledger row binding a report section to its source (§4.7)."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    report_id: uuid.UUID
    evidence_type: str  # mcp_invocation / data_query / document / manual
    ref_id: uuid.UUID | None = None
    section: str | None = None
    summary: str | None = None
