"""023 Due-diligence workbench for REQ-046.

REQ-046 Slice 0: tenant-scoped due-diligence task / report / evidence tables.

``dd_tasks`` is the minimal V0 workbench container (REQ-041 scope): a task
captures the user's raw ``subject_query`` and drives the subject-anchoring
state machine (``status``); once the user confirms a candidate, the resolved
``confirmed_subject`` (``{company_name, credit_code}``) is stored as JSONB and
the task may run. ``skill_execution_audit_id`` links the task to the skill
execution that produced its report.

``dd_reports`` stores each generated report draft / confirmed / archived
version. ``report_json`` carries the structured §4.6 seven-key contract and
``report_markdown`` the workbench-rendered body; both are business tables so
enterprise-sensitive content is allowed here (unlike audit tables, which only
hold digests). ``(task_id, version)`` is unique so re-runs produce version+1.

``dd_evidence`` is the evidence ledger (§4.7): each row binds a report section
to one source — an MCP invocation, a data query, a document, or a manual
entry — via ``evidence_type`` + ``ref_id`` (the audit / query / document id),
with a non-sensitive ``summary`` for display.

The models mirror the column layout defined here exactly.

Revision ID: 023_dd_workbench
Revises: 022_skill_registry
Create Date: 2026-07-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "023_dd_workbench"
down_revision: str | None = "022_skill_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dd_tasks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("subject_query", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'subject_pending'"),
        ),
        sa.Column("confirmed_subject", JSONB, nullable=True),
        sa.Column("confirmed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime, nullable=True),
        sa.Column("skill_execution_audit_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_dd_tasks_tenant_status",
        "dd_tasks",
        ["tenant_id", "status"],
        schema="metaedu",
    )

    op.create_table(
        "dd_reports",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("metaedu.dd_tasks.id"),
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("report_json", JSONB, nullable=False),
        sa.Column("report_markdown", sa.Text, nullable=False),
        sa.Column("skill_execution_audit_id", UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "task_id", "version", name="uq_dd_reports_task_version"
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_dd_reports_task",
        "dd_reports",
        ["task_id"],
        schema="metaedu",
    )

    op.create_table(
        "dd_evidence",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "report_id",
            UUID(as_uuid=True),
            sa.ForeignKey("metaedu.dd_reports.id"),
            nullable=False,
        ),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("ref_id", UUID(as_uuid=True), nullable=True),
        sa.Column("section", sa.String(100), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_dd_evidence_report",
        "dd_evidence",
        ["report_id"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dd_evidence_report", table_name="dd_evidence", schema="metaedu"
    )
    op.drop_index(
        "ix_dd_reports_task", table_name="dd_reports", schema="metaedu"
    )
    op.drop_index(
        "ix_dd_tasks_tenant_status", table_name="dd_tasks", schema="metaedu"
    )
    op.drop_table("dd_evidence", schema="metaedu")
    op.drop_table("dd_reports", schema="metaedu")
    op.drop_table("dd_tasks", schema="metaedu")
