"""add tenant_config_audit table

REQ-058 Slice 4: 配置变更审计表（AC-6）。独立表，不依赖 dd_evidence
（dd_evidence.report_id NOT NULL 约束阻止配置审计写入）。

Revision ID: 027_tenant_config_audit
Revises: 026_dd_tasks_assignee
Create Date: 2026-07-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "027_tenant_config_audit"
down_revision: Union[str, None] = "026_dd_tasks_assignee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_config_audit",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("metaedu.tenants.id"),
            nullable=False,
        ),
        sa.Column("config_key", sa.String(100), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),  # set / delete
        sa.Column("old_value", JSONB, nullable=True),
        sa.Column("new_value", JSONB, nullable=False),
        sa.Column("operator", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_tenant_config_audit_tenant_id",
        "tenant_config_audit",
        ["tenant_id"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_config_audit_tenant_id",
        table_name="tenant_config_audit",
        schema="metaedu",
    )
    op.drop_table("tenant_config_audit", schema="metaedu")