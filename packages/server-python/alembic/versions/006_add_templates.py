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
    # `doc_types` is an ARRAY(String) — use the default `array_ops` operator
    # class for `gin`. The previous `postgresql_ops={"doc_types": "gin"}`
    # literally rendered `USING gin (doc_types gin)`, which references a
    # `gin` operator class that does not exist (PG exposes `array_ops` and
    # btree_gin's own classes, neither of which is named `gin`). On a fresh
    # database that never had a previous broken `ix_templates_doc_types`
    # installed, the migration raised
    # `UndefinedObjectError: operator class "gin" does not exist` and
    # `alembic upgrade head` could not proceed, which in turn blocked 003's
    # `updated_at` add_column and was the root cause of TD-036.
    op.create_index(
        "ix_templates_doc_types",
        "templates",
        ["doc_types"],
        postgresql_using="gin",
    )

def downgrade() -> None:
    op.drop_table("templates")