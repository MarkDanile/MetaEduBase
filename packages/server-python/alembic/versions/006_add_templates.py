"""create templates table

Revision ID: 006_create_templates
Revises: 005_add_kn_embedding
Create Date: 2026-05-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision: str = "006_create_templates"
down_revision: str = "005_add_kn_embedding"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "templates",
        sa.Column("id", UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("doc_types", ARRAY(sa.String(length=50)), nullable=False),
        sa.Column("fields", JSONB(), nullable=False),
        sa.Column("ai_prompt", sa.Text(), nullable=True),
        sa.Column("source_file_id", UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_templates_tenant_name"),
    )
    op.create_index("ix_templates_tenant_id", "templates", ["tenant_id"])
    op.create_index("ix_templates_doc_types", "templates", ["doc_types"], postgresql_using="gin", postgresql_ops={"doc_types": "gin"})

def downgrade() -> None:
    op.drop_table("templates")