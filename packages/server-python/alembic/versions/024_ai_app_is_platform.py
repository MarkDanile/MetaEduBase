"""add is_platform to ai_applications

BUG-018 Slice 2: 平台应用跨租户可见但只能 super_admin 写；公开广场仅展示
is_platform=True + status=Published + visibility=public 的应用。普通应用
保持 tenant 隔离（仅本 tenant 可见 + 所有 HIGH_PRIVILEGE_ROLES 可管理）。

Revision ID: 024_ai_app_is_platform
Revises: 023_dd_workbench
Create Date: 2026-07-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "024_ai_app_is_platform"
down_revision: Union[str, None] = "023_dd_workbench"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_applications",
        sa.Column(
            "is_platform",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_ai_applications_is_platform",
        "ai_applications",
        ["is_platform"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_applications_is_platform", table_name="ai_applications")
    op.drop_column("ai_applications", "is_platform")