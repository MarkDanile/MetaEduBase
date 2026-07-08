"""017 add catalog_id FK to datasets / semantic_models / knowledge_nodes / query_audit_log.

REQ-054 Task 1: Adds ``catalog_id`` nullable FK column to the four REQ-052
tables so that existing rows can be backfilled in migration 018 before the
column is made NOT NULL. Also replaces the ``semantic_models`` unique
constraint to include ``catalog_id`` — the same (tenant, entity_type,
data_source_config) triple can now coexist under different catalogs.

Revision ID: 017_add_catalog_id_fk
Revises: 016_data_catalogs
Create Date: 2026-07-07
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "017_add_catalog_id_fk"
down_revision: str | None = "016_data_catalogs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # datasets.catalog_id (nullable now, NOT NULL after 018 backfill)
    op.add_column(
        "datasets",
        sa.Column("catalog_id", UUID(as_uuid=True), nullable=True),
        schema="metaedu",
    )
    op.create_foreign_key(
        "fk_datasets_catalog_id",
        "datasets",
        "data_catalogs",
        ["catalog_id"],
        ["id"],
        source_schema="metaedu",
        referent_schema="metaedu",
    )

    # semantic_models.catalog_id
    op.add_column(
        "semantic_models",
        sa.Column("catalog_id", UUID(as_uuid=True), nullable=True),
        schema="metaedu",
    )
    op.create_foreign_key(
        "fk_semantic_models_catalog_id",
        "semantic_models",
        "data_catalogs",
        ["catalog_id"],
        ["id"],
        source_schema="metaedu",
        referent_schema="metaedu",
    )
    # Replace unique constraint: add catalog_id to the key
    op.drop_constraint(
        "uq_semantic_models_tenant_entity_datasource",
        "semantic_models",
        schema="metaedu",
    )
    op.create_unique_constraint(
        "uq_semantic_models_tenant_catalog_entity_datasource",
        "semantic_models",
        ["tenant_id", "catalog_id", "entity_type", "data_source_config"],
        schema="metaedu",
    )

    # knowledge_nodes.catalog_id (nullable tag, V1)
    op.add_column(
        "knowledge_nodes",
        sa.Column("catalog_id", UUID(as_uuid=True), nullable=True),
        schema="metaedu",
    )
    op.create_foreign_key(
        "fk_knowledge_nodes_catalog_id",
        "knowledge_nodes",
        "data_catalogs",
        ["catalog_id"],
        ["id"],
        source_schema="metaedu",
        referent_schema="metaedu",
    )

    # query_audit_log.catalog_id (nullable, filled at query time)
    op.add_column(
        "query_audit_log",
        sa.Column("catalog_id", UUID(as_uuid=True), nullable=True),
        schema="metaedu",
    )
    op.create_foreign_key(
        "fk_query_audit_log_catalog_id",
        "query_audit_log",
        "data_catalogs",
        ["catalog_id"],
        ["id"],
        source_schema="metaedu",
        referent_schema="metaedu",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_query_audit_log_catalog_id", "query_audit_log", schema="metaedu"
    )
    op.drop_column("query_audit_log", "catalog_id", schema="metaedu")

    op.drop_constraint(
        "fk_knowledge_nodes_catalog_id", "knowledge_nodes", schema="metaedu"
    )
    op.drop_column("knowledge_nodes", "catalog_id", schema="metaedu")

    op.drop_constraint(
        "uq_semantic_models_tenant_catalog_entity_datasource",
        "semantic_models",
        schema="metaedu",
    )
    op.create_unique_constraint(
        "uq_semantic_models_tenant_entity_datasource",
        "semantic_models",
        ["tenant_id", "entity_type", "data_source_config"],
        schema="metaedu",
    )
    op.drop_constraint(
        "fk_semantic_models_catalog_id", "semantic_models", schema="metaedu"
    )
    op.drop_column("semantic_models", "catalog_id", schema="metaedu")

    op.drop_constraint("fk_datasets_catalog_id", "datasets", schema="metaedu")
    op.drop_column("datasets", "catalog_id", schema="metaedu")
