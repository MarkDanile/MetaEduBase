"""014 tenant access grants for REQ-052.

REQ-052 Task 1: Cross-tenant data sharing grants. ``tenant_access_grants``
records when one tenant (grantee) is approved to query another tenant's
(grantor's) entity data, with an optional expiry.

Revision ID: 014_tenant_access_grants
Revises: 013_role_permissions
Create Date: 2026-07-06
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "014_tenant_access_grants"
down_revision: str | None = "013_role_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_access_grants",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("grantee_tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        schema="metaedu",
    )
    op.create_index(
        "ix_tenant_access_grants_grantee",
        "tenant_access_grants",
        ["grantee_tenant_id", "entity_type"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_access_grants_grantee",
        table_name="tenant_access_grants",
        schema="metaedu",
    )
    op.drop_table("tenant_access_grants", schema="metaedu")