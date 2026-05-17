"""add updated_at to document_tasks

Revision ID: 003_add_updated_at
Revises: 002_source_tracking
Create Date: 2026-05-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_add_updated_at"
down_revision: Union[str, None] = "002_source_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_tasks",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_column("document_tasks", "updated_at", schema="metaedu")