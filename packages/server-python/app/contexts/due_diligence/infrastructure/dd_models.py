"""Due-diligence workbench ORM for REQ-046 (metaedu.dd_tasks / dd_reports / dd_evidence).

Maps the three tables introduced in alembic migration 023. ``dd_tasks`` is the
minimal V0 workbench container (REQ-041 scope): it captures the user's raw
``subject_query`` and drives the subject-anchoring state machine via
``status`` (``subject_pending`` -> ``subject_confirmed`` -> ``running`` ->
``review`` -> ``archived`` / ``failed``). Once the user confirms a candidate,
the resolved ``confirmed_subject`` (``{company_name, credit_code}``) is stored
as JSONB and the task may run.

``dd_reports`` stores each report draft / confirmed / archived version.
``report_json`` carries the structured §4.6 seven-key contract and
``report_markdown`` the workbench-rendered body. These are business tables, so
enterprise-sensitive content is allowed here (unlike audit tables, which only
hold digests); API responses must be tenant-scoped. ``(task_id, version)`` is
unique so re-runs produce version+1.

``dd_evidence`` is the evidence ledger (§4.7): each row binds a report section
to one source — ``mcp_invocation`` / ``data_query`` / ``document`` /
``manual`` — via ``ref_id`` (the audit / query / document id), with a
non-sensitive ``summary`` for display.

The models mirror the column layout defined in the migration exactly.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base


def _utcnow() -> datetime:
    """Naive UTC datetime matching the project convention."""
    return datetime.now(UTC).replace(tzinfo=None)


class DdTaskModel(Base):
    """ORM row over ``metaedu.dd_tasks``."""

    __tablename__ = "dd_tasks"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subject_query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="subject_pending"
    )
    confirmed_subject: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    skill_execution_audit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    # REQ-058 D-3: 任务可分配给同 tenant 其他用户（创建者+分配对象+高权可见）
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class DdReportModel(Base):
    """ORM row over ``metaedu.dd_reports``."""

    __tablename__ = "dd_reports"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metaedu.dd_tasks.id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft"
    )
    report_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    report_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    skill_execution_audit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )


class DdEvidenceModel(Base):
    """ORM row over ``metaedu.dd_evidence``."""

    __tablename__ = "dd_evidence"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metaedu.dd_reports.id"),
        nullable=False,
    )
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    section: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
