"""persist idempotent Agent Run cancel intent

Revision ID: 032_agent_run_cancel_intent
Revises: 031_agent_control_plane_bridge
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "032_agent_run_cancel_intent"
down_revision: str | None = "031_agent_control_plane_bridge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("cancel_requested_revision", sa.BigInteger(), nullable=True),
        schema="metaedu",
    )
    op.create_check_constraint(
        "ck_agent_run_cancel_revision",
        "agent_runs",
        "cancel_requested_revision IS NULL OR "
        "(cancel_requested_revision >= 1 "
        "AND cancel_requested_revision <= status_revision)",
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_run_cancel_revision",
        "agent_runs",
        schema="metaedu",
        type_="check",
    )
    op.drop_column(
        "agent_runs",
        "cancel_requested_revision",
        schema="metaedu",
    )
