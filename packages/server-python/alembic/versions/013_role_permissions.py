"""013 role permissions for REQ-052.

REQ-052 Task 1: RBAC schema baseline. Defines ``role_permissions`` table that
controls per-entity column visibility (visible / masked / hidden) for each of
the five roles: employee / manager / leader / data_admin / auditor.

Revision ID: 013_role_permissions
Revises: 012_semantic_models
Create Date: 2026-07-06
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "013_role_permissions"
down_revision: str | None = "012_semantic_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "role_permissions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("visibility_rules", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "tenant_id",
            "role",
            "entity_type",
            name="uq_role_permissions_tenant_role_entity",
        ),
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_table("role_permissions", schema="metaedu")