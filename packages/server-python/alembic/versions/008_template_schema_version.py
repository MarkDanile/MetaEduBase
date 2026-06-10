"""add template schema_version + deprecation fields

REQ-002-4: schema_version 演进 + deprecated 标记。
- schema_version: int, NOT NULL, default 1
- is_deprecated: bool, NOT NULL, default false
- deprecated_at: datetime, nullable
- deprecated_reason: text, nullable

Revision ID: 008_template_schema_version
Revises: 007_template_versions
Create Date: 2026-06-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_template_schema_version"
down_revision: Union[str, None] = "007_template_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "templates",
        sa.Column(
            "is_deprecated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "templates",
        sa.Column(
            "deprecated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "templates",
        sa.Column(
            "deprecated_reason",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("templates", "deprecated_reason")
    op.drop_column("templates", "deprecated_at")
    op.drop_column("templates", "is_deprecated")
    op.drop_column("templates", "schema_version")
