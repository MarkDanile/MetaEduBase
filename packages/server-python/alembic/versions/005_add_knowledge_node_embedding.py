"""add embedding column to knowledge_nodes + enable pgvector

Revision ID: 005_add_kn_embedding
Revises: 004_add_chunk_vectors
Create Date: 2026-05-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_add_kn_embedding"
down_revision: Union[str, None] = "004_add_chunk_vectors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "knowledge_nodes",
        sa.Column("embedding", sa.Text(), nullable=True),
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_column("knowledge_nodes", "embedding", schema="metaedu")
