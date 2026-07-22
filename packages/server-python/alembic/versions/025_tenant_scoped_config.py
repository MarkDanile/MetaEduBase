"""add tenant_scoped_config table

REQ-058 Slice 1: tenant 级配置表，存储 Internal MCP / DD Catalog / Skill binding
等 tenant-scoped 配置，替代 settings 全局单值。按 (tenant_id, config_key) 唯一。

Revision ID: 025_tenant_scoped_config
Revises: 024_ai_app_is_platform
Create Date: 2026-07-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "025_tenant_scoped_config"
down_revision: Union[str, None] = "024_ai_app_is_platform"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_scoped_config",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("metaedu.tenants.id"),
            nullable=False,
        ),
        sa.Column("config_key", sa.String(100), nullable=False),
        sa.Column("config_value", JSONB(), nullable=False),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("tenant_id", "config_key"),
        schema="metaedu",
    )
    op.create_index(
        "ix_tenant_scoped_config_tenant_id",
        "tenant_scoped_config",
        ["tenant_id"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_scoped_config_tenant_id",
        table_name="tenant_scoped_config",
        schema="metaedu",
    )
    op.drop_table("tenant_scoped_config", schema="metaedu")