"""initial baseline from create_all

Revision ID: 001_baseline
Revises:
Create Date: 2026-05-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision: str = "001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS metaedu")

    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("school_name", sa.String(300), nullable=False),
        sa.Column("isolation", sa.String(20), server_default="shared"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
        schema="metaedu",
    )

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("metaedu.tenants.id"), nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("email", sa.String(200)),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("role", sa.String(30), nullable=False, server_default="teacher"),
        sa.Column("domain", sa.String(100)),
        sa.Column("clearance_level", sa.Integer, server_default="0"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
        sa.Index("ix_users_tenant_username", "tenant_id", "username", unique=True),
        schema="metaedu",
    )

    op.create_table(
        "knowledge_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("metaedu.tenants.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("level", sa.String(30), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("metaedu.knowledge_nodes.id")),
        sa.Column("path", sa.String(500)),
        sa.Column("tags", JSONB, server_default="[]"),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("embedding_id", sa.String(100)),
        sa.Column("full_text", sa.Text),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
        sa.Index("ix_kn_tenant_domain", "tenant_id", "domain"),
        sa.Index("ix_kn_tenant_parent", "tenant_id", "parent_id"),
        sa.Index("ix_kn_tenant_level", "tenant_id", "level"),
        sa.Index("ix_kn_path", "path"),
        schema="metaedu",
    )

    op.create_table(
        "knowledge_edges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("metaedu.tenants.id"), nullable=False),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("metaedu.knowledge_nodes.id"), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), sa.ForeignKey("metaedu.knowledge_nodes.id"), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("weight", sa.Float, server_default="1.0"),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime),
        sa.Index("ix_ke_source", "source_id"),
        sa.Index("ix_ke_target", "target_id"),
        schema="metaedu",
    )

    op.create_table(
        "resources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("metaedu.tenants.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), server_default="raw"),
        sa.Column("domain", sa.String(50)),
        sa.Column("course_id", UUID(as_uuid=True)),
        sa.Column("knowledge_point_ids", ARRAY(UUID(as_uuid=True))),
        sa.Column("file_size", sa.Integer),
        sa.Column("file_type", sa.String(50)),
        sa.Column("storage_key", sa.String(500)),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("uploaded_by", UUID(as_uuid=True), sa.ForeignKey("metaedu.users.id"), nullable=False),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
        sa.Index("ix_res_tenant_type", "tenant_id", "resource_type"),
        sa.Index("ix_res_tenant_domain", "tenant_id", "domain"),
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_table("resources", schema="metaedu")
    op.drop_table("knowledge_edges", schema="metaedu")
    op.drop_table("knowledge_nodes", schema="metaedu")
    op.drop_table("users", schema="metaedu")
    op.drop_table("tenants", schema="metaedu")
