"""add ai_context column to templates table

Revision ID: 9466ea6e5d33
Revises: 006_create_templates
Create Date: 2026-06-01 20:28:04.247348

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '9466ea6e5d33'
down_revision: Union[str, None] = '006_create_templates'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('templates', sa.Column('ai_context', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('templates', 'ai_context')
