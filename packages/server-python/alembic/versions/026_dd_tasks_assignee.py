"""add assignee_id to dd_tasks

REQ-058 Slice 2: 任务可分配给同 tenant 其他用户（spec D-3）。
可见性策略 = 本人 + 分配对象 + 高权角色。

Revision ID: 026_dd_tasks_assignee
Revises: 025_tenant_scoped_config
Create Date: 2026-07-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "026_dd_tasks_assignee"
down_revision: Union[str, None] = "025_tenant_scoped_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dd_tasks",
        sa.Column("assignee_id", UUID(as_uuid=True), nullable=True),
        schema="metaedu",
    )
    op.create_index(
        "ix_dd_tasks_assignee_id",
        "dd_tasks",
        ["assignee_id"],
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dd_tasks_assignee_id",
        table_name="dd_tasks",
        schema="metaedu",
    )
    op.drop_column("dd_tasks", "assignee_id", schema="metaedu")