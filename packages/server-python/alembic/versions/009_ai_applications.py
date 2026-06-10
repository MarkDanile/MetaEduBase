"""add ai_applications table

Revision ID: 009_ai_applications
Revises: 008_template_schema_version
Create Date: 2026-06-11

REQ-011: AI 应用广场与应用注册中心 - Slice 1 数据模型
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "009_ai_applications"
down_revision: Union[str, None] = "008_template_schema_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_applications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("icon", sa.String(500), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="Draft",
        ),
        sa.Column(
            "visibility",
            sa.String(20),
            nullable=False,
            server_default="internal",
        ),
        sa.Column(
            "entry_type",
            sa.String(20),
            nullable=False,
            server_default="internal_route",
        ),
        sa.Column("route_path", sa.String(200), nullable=True),
        sa.Column("external_url", sa.String(500), nullable=True),
        sa.Column("config_schema", JSONB(), nullable=True),
        sa.Column("required_capabilities", JSONB(), nullable=True),
        sa.Column("owner", sa.String(200), nullable=True),
        sa.Column("version", sa.String(20), nullable=False, server_default="1.0.0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("share_token", sa.String(100), nullable=True, unique=True),
        sa.Column("api_token", sa.String(100), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["metaedu.tenants.id"]),
    )
    op.create_index("ix_ai_applications_status", "ai_applications", ["status"])
    op.create_index("ix_ai_applications_tenant_id", "ai_applications", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_applications_tenant_id", table_name="ai_applications")
    op.drop_index("ix_ai_applications_status", table_name="ai_applications")
    op.drop_table("ai_applications")
