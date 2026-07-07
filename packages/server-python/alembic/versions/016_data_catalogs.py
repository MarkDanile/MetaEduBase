"""016 data catalogs for REQ-054.

REQ-054 Task 1: Platform-level database (catalog) domain. ``data_catalogs``
groups datasets / semantic_models / knowledge_nodes into thematic databases
within each tenant. Each tenant gets its own set of catalogs — tenant_id
isolation (REQ-052 security boundary) is preserved; catalog is an orthogonal
grouping dimension inside the tenant.

Revision ID: 016_data_catalogs
Revises: 015_query_audit_log
Create Date: 2026-07-07
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "016_data_catalogs"
down_revision: str | None = "015_query_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_catalogs",
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
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column(
            "entity_types",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("default_business_purpose", sa.String(200), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "code", name="uq_data_catalogs_tenant_code"),
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_table("data_catalogs", schema="metaedu")
