"""add embedding and tsvector columns to document_chunks

Revision ID: 004_add_chunk_vectors
Revises: 003_add_updated_at
Create Date: 2026-05-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, TEXT, TIMESTAMP, INTEGER

revision: str = "004_add_chunk_vectors"
down_revision: Union[str, None] = "003_add_updated_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("embedding", TEXT(), nullable=True),
        schema="metaedu",
    )
    op.add_column(
        "document_chunks",
        sa.Column("content_tsvector", TEXT(), nullable=True),
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "content_tsvector", schema="metaedu")
    op.drop_column("document_chunks", "embedding", schema="metaedu")