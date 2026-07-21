"""022 Skill registry for REQ-045.

REQ-045 Task 1: tenant-scoped skill registry + execution audit.
``skills`` stores per-tenant skill registrations — a skill is a
*declarative SOP template* (YAML body in ``sop_template``) with
versioning, a role whitelist, and an enable flag (default disabled).
``skill_execution_audit`` records every execution attempt with sha256
digests of the subject / steps / report instead of raw content, so the
audit trail proves reproducibility without persisting enterprise
sensitive data or report bodies.

Revision ID: 022_skill_registry
Revises: 021_mcp_registry
Create Date: 2026-07-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "022_skill_registry"
down_revision: str | None = "021_mcp_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("sop_template", sa.Text, nullable=False),
        sa.Column("source_ref", sa.String(500), nullable=True),
        sa.Column(
            "allowed_roles",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
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
        sa.UniqueConstraint(
            "tenant_id", "code", "version", name="uq_skills_tenant_code_version"
        ),
        schema="metaedu",
    )

    op.create_table(
        "skill_execution_audit",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "skill_id",
            UUID(as_uuid=True),
            sa.ForeignKey("metaedu.skills.id"),
            nullable=False,
        ),
        sa.Column("skill_code", sa.String(50), nullable=False),
        sa.Column("skill_version", sa.String(20), nullable=False),
        sa.Column("caller_type", sa.String(30), nullable=False),
        sa.Column("caller_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("subject_digest", sa.String(64), nullable=True),
        sa.Column("steps_digest", sa.String(64), nullable=True),
        sa.Column("report_digest", sa.String(64), nullable=True),
        sa.Column("ok", sa.Boolean, nullable=False),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_skill_execution_audit_tenant_skill_created",
        "skill_execution_audit",
        ["tenant_id", "skill_id", "created_at"],
        schema="metaedu",
    )
    op.create_index(
        "ix_skill_execution_audit_tenant_created",
        "skill_execution_audit",
        ["tenant_id", "created_at"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_skill_execution_audit_tenant_created",
        table_name="skill_execution_audit",
        schema="metaedu",
    )
    op.drop_index(
        "ix_skill_execution_audit_tenant_skill_created",
        table_name="skill_execution_audit",
        schema="metaedu",
    )
    op.drop_table("skill_execution_audit", schema="metaedu")
    op.drop_table("skills", schema="metaedu")
