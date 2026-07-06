"""015 query audit log for REQ-052.

REQ-052 Task 1: Append-only audit trail. ``query_audit_log`` records every
intelligent data query attempt with the user's stated business purpose, the
resolved query plan, data source binding, and outcome metrics. Append-only
semantics are enforced at the application layer; DB role-level GRANT will be
added in a follow-up task.

Revision ID: 015_query_audit_log
Revises: 014_tenant_access_grants
Create Date: 2026-07-06
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "015_query_audit_log"
down_revision: str | None = "014_tenant_access_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "query_audit_log",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("business_purpose", sa.Text, nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("query_plan", JSONB, nullable=False),
        sa.Column("data_source_type", sa.String(50), nullable=False),
        sa.Column("data_source_ref", sa.String(200), nullable=True),
        sa.Column(
            "result_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
            index=True,
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_query_audit_log_tenant_created",
        "query_audit_log",
        ["tenant_id", "created_at"],
        schema="metaedu",
    )
    op.create_index(
        "ix_query_audit_log_user_created",
        "query_audit_log",
        ["user_id", "created_at"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_query_audit_log_user_created",
        table_name="query_audit_log",
        schema="metaedu",
    )
    op.drop_index(
        "ix_query_audit_log_tenant_created",
        table_name="query_audit_log",
        schema="metaedu",
    )
    op.drop_table("query_audit_log", schema="metaedu")