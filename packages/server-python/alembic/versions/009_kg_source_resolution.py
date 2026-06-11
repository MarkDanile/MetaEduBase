"""add knowledge_nodes.node_source_resolution

REQ-010 Slice 5 — KG 抽取按 chunk 切片。

Adds `node_source_resolution` column to mark how a knowledge_node's source
chunk linkage was resolved:
- 'chunk_resolved': LLM extraction pinned the entity to a specific chunk
- 'file_only': only source_file_id could be determined; chunk undecided
- (NULL): legacy node extracted before Slice 5; resolution status unknown

Note: `source_chunk_id` and `source_file_id` columns already exist (added
in migration 002 — see `add_source_tracking_and_new_tables`). This
migration only adds the resolution status column.

Revision ID: 009_kg_source_resolution
Revises: 008_template_schema_version
Create Date: 2026-06-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009_kg_source_resolution"
down_revision: Union[str, None] = "008_template_schema_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_nodes",
        sa.Column("node_source_resolution", sa.String(20), nullable=True),
        schema="metaedu",
    )
    # Partial index for backfill queries filtering by resolution status
    op.create_index(
        "ix_kn_node_source_resolution",
        "knowledge_nodes",
        ["tenant_id", "node_source_resolution"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_kn_node_source_resolution",
        "knowledge_nodes",
        schema="metaedu",
    )
    op.drop_column("knowledge_nodes", "node_source_resolution", schema="metaedu")
