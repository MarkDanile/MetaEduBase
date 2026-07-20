"""021 MCP registry for REQ-044.

REQ-044 Task 1: tenant-scoped MCP server registry + invocation audit.
``mcp_servers`` stores per-tenant MCP server registrations (transport,
URL, credential *reference name* — never the secret value, allowed
roles, enable flag). ``mcp_invocation_audit`` records every invocation
attempt with sha256 digests of params / response instead of raw content,
so the audit trail proves reproducibility without persisting secrets or
payloads.

Revision ID: 021_mcp_registry
Revises: 020_audit_bp_nullable
Create Date: 2026-07-20
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "021_mcp_registry"
down_revision: str | None = "020_audit_bp_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "transport",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'streamable_http'"),
        ),
        sa.Column("server_url", sa.String(500), nullable=False),
        sa.Column("credential_ref", sa.String(200), nullable=True),
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
            "timeout_ms",
            sa.Integer,
            nullable=False,
            server_default=sa.text("30000"),
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
        sa.UniqueConstraint("tenant_id", "code", name="uq_mcp_servers_tenant_code"),
        schema="metaedu",
    )

    op.create_table(
        "mcp_invocation_audit",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "server_id",
            UUID(as_uuid=True),
            sa.ForeignKey("metaedu.mcp_servers.id"),
            nullable=False,
        ),
        sa.Column("server_code", sa.String(50), nullable=False),
        sa.Column("tool_name", sa.String(200), nullable=False),
        sa.Column("caller_type", sa.String(30), nullable=False),
        sa.Column("caller_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("params_digest", sa.String(64), nullable=True),
        sa.Column("response_digest", sa.String(64), nullable=True),
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
        "ix_mcp_invocation_audit_tenant_server_created",
        "mcp_invocation_audit",
        ["tenant_id", "server_id", "created_at"],
        schema="metaedu",
    )
    op.create_index(
        "ix_mcp_invocation_audit_tenant_created",
        "mcp_invocation_audit",
        ["tenant_id", "created_at"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mcp_invocation_audit_tenant_created",
        table_name="mcp_invocation_audit",
        schema="metaedu",
    )
    op.drop_index(
        "ix_mcp_invocation_audit_tenant_server_created",
        table_name="mcp_invocation_audit",
        schema="metaedu",
    )
    op.drop_table("mcp_invocation_audit", schema="metaedu")
    op.drop_table("mcp_servers", schema="metaedu")
