"""012 semantic models for REQ-052.

REQ-052 Task 1: Semantic layer schema baseline. Defines the ``semantic_models``
table that maps raw dataset columns / external data sources to business entities
and metrics consumed by the intelligent data query pipeline.

Revision ID: 012_semantic_models
Revises: 030_embedding_vector_4096
Create Date: 2026-07-06
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "012_semantic_models"
down_revision: str | None = "030_embedding_vector_4096"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semantic_models",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "dataset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("metaedu.datasets.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_name", sa.String(100), nullable=False),
        sa.Column(
            "data_source_config",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("column_mapping", JSONB, nullable=False),
        sa.Column(
            "metric_definitions",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("version", sa.String(20), nullable=False, server_default=sa.text("'v1'")),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "tenant_id",
            "entity_type",
            "data_source_config",
            name="uq_semantic_models_tenant_entity_datasource",
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_semantic_models_dataset",
        "semantic_models",
        ["dataset_id"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_semantic_models_dataset",
        table_name="semantic_models",
        schema="metaedu",
    )
    op.drop_table("semantic_models", schema="metaedu")