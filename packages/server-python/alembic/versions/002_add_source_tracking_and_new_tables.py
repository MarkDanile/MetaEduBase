"""add source tracking to knowledge_nodes + new tables

Revision ID: 002_source_tracking
Revises: 001_baseline
Create Date: 2026-05-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision: str = "002_source_tracking"
down_revision: Union[str, None] = "001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add source tracking columns to knowledge_nodes
    op.add_column("knowledge_nodes", sa.Column("source_chunk_id", UUID(as_uuid=True), nullable=True), schema="metaedu")
    op.add_column("knowledge_nodes", sa.Column("source_file_id", UUID(as_uuid=True), nullable=True), schema="metaedu")
    op.add_column("knowledge_nodes", sa.Column("source_dataset_id", UUID(as_uuid=True), nullable=True), schema="metaedu")
    op.add_column("knowledge_nodes", sa.Column("source_row_id", UUID(as_uuid=True), nullable=True), schema="metaedu")

    # Add indexes for source tracking
    op.create_index("ix_kn_source_file_id", "knowledge_nodes", ["tenant_id", "source_file_id"], schema="metaedu")
    op.create_index("ix_kn_source_chunk_id", "knowledge_nodes", ["tenant_id", "source_chunk_id"], schema="metaedu")
    op.create_index("ix_kn_source_dataset_id", "knowledge_nodes", ["tenant_id", "source_dataset_id"], schema="metaedu")
    op.create_index("ix_kn_source_row_id", "knowledge_nodes", ["tenant_id", "source_row_id"], schema="metaedu")

    # Add indexes for knowledge_edges
    op.create_index("ix_ke_source_rel", "knowledge_edges", ["tenant_id", "source_id", "relation_type"], schema="metaedu")
    op.create_index("ix_ke_target_rel", "knowledge_edges", ["tenant_id", "target_id", "relation_type"], schema="metaedu")
    op.create_index("ix_ke_relation_type", "knowledge_edges", ["tenant_id", "relation_type"], schema="metaedu")

    # Create document context tables
    op.create_table(
        "folders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        schema="metaedu",
    )

    op.create_table(
        "files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("folder_id", UUID(as_uuid=True), nullable=True),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("doc_type", sa.String(50), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("tags", ARRAY(sa.String()), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploaded"),
        sa.Column("structured_data", JSONB, nullable=True),
        sa.Column("uploaded_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        schema="metaedu",
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("section_title", sa.String(200), nullable=True),
        sa.Column("section_path", sa.String(100), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        schema="metaedu",
    )

    op.create_table(
        "document_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", UUID(as_uuid=True), nullable=True),
        sa.Column("dataset_id", UUID(as_uuid=True), nullable=True),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        schema="metaedu",
    )

    # Create structured_data context tables
    op.create_table(
        "datasets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("column_names", JSONB, nullable=True),
        sa.Column("column_types", JSONB, nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_file", sa.String(300), nullable=True),
        sa.Column("tags", ARRAY(sa.String()), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploaded"),
        sa.Column("kg_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        schema="metaedu",
    )

    op.create_table(
        "dataset_rows",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", UUID(as_uuid=True), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_table("dataset_rows", schema="metaedu")
    op.drop_table("datasets", schema="metaedu")
    op.drop_table("document_tasks", schema="metaedu")
    op.drop_table("document_chunks", schema="metaedu")
    op.drop_table("files", schema="metaedu")
    op.drop_table("folders", schema="metaedu")

    op.drop_index("ix_ke_relation_type", "knowledge_edges", schema="metaedu")
    op.drop_index("ix_ke_target_rel", "knowledge_edges", schema="metaedu")
    op.drop_index("ix_ke_source_rel", "knowledge_edges", schema="metaedu")
    op.drop_index("ix_kn_source_row_id", "knowledge_nodes", schema="metaedu")
    op.drop_index("ix_kn_source_dataset_id", "knowledge_nodes", schema="metaedu")
    op.drop_index("ix_kn_source_chunk_id", "knowledge_nodes", schema="metaedu")
    op.drop_index("ix_kn_source_file_id", "knowledge_nodes", schema="metaedu")

    op.drop_column("knowledge_nodes", "source_row_id", schema="metaedu")
    op.drop_column("knowledge_nodes", "source_dataset_id", schema="metaedu")
    op.drop_column("knowledge_nodes", "source_file_id", schema="metaedu")
    op.drop_column("knowledge_nodes", "source_chunk_id", schema="metaedu")
