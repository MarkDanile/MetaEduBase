"""add REQ-047 B1 integration payload contracts

Revision ID: 031_agent_control_plane_bridge
Revises: 030_agent_execution_durable_core
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "031_agent_control_plane_bridge"
down_revision: str | None = "030_agent_execution_durable_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_payload_inline(table: str, constraint: str) -> None:
    op.add_column(
        table,
        sa.Column("payload_inline", JSONB(), nullable=True),
        schema="metaedu",
    )
    op.create_check_constraint(
        constraint,
        table,
        "(payload_inline IS NOT NULL AND payload_ref IS NULL "
        "AND pg_column_size(payload_inline) <= 32768) OR "
        "(payload_inline IS NULL AND payload_ref IS NOT NULL)",
        schema="metaedu",
    )


def upgrade() -> None:
    _add_payload_inline("agent_workspace_outbox", "ck_agent_ws_outbox_payload")
    _add_payload_inline("agent_execution_outbox", "ck_agent_exec_outbox_payload")
    op.add_column(
        "agent_execution_outbox",
        sa.Column("decision_actor_id", sa.UUID(), nullable=True),
        schema="metaedu",
    )
    op.add_column(
        "agent_execution_outbox",
        sa.Column("decision_reason", sa.String(500), nullable=True),
        schema="metaedu",
    )
    op.add_column(
        "agent_execution_outbox",
        sa.Column("decision_digest", sa.String(64), nullable=True),
        schema="metaedu",
    )
    op.add_column(
        "agent_execution_outbox",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        schema="metaedu",
    )
    op.create_check_constraint(
        "ck_agent_exec_outbox_decision",
        "agent_execution_outbox",
        "(decision_actor_id IS NULL AND decision_reason IS NULL "
        "AND decision_digest IS NULL AND decided_at IS NULL) OR "
        "(decision_actor_id IS NOT NULL AND decision_reason IS NOT NULL "
        "AND char_length(decision_digest) = 64 AND decided_at IS NOT NULL)",
        schema="metaedu",
    )
    op.create_index(
        "uq_agent_ws_outbox_turn",
        "agent_workspace_outbox",
        ["tenant_id", "aggregate_id"],
        unique=True,
        schema="metaedu",
        postgresql_where=sa.text("event_type = 'turn.requested.v1'"),
    )
    op.create_index(
        "uq_agent_exec_outbox_publish",
        "agent_execution_outbox",
        ["tenant_id", "aggregate_id"],
        unique=True,
        schema="metaedu",
        postgresql_where=sa.text(
            "event_type = 'assistant_message.publish_requested.v1'"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    durable_payloads = bind.execute(
        sa.text(
            "SELECT "
            "(SELECT count(*) FROM metaedu.agent_workspace_outbox "
            "WHERE payload_inline IS NOT NULL) + "
            "(SELECT count(*) FROM metaedu.agent_execution_outbox "
            "WHERE payload_inline IS NOT NULL)"
        )
    ).scalar_one()
    if durable_payloads:
        raise RuntimeError(
            "cannot downgrade 031 while durable inline integration payloads exist"
        )
    op.drop_index(
        "uq_agent_exec_outbox_publish",
        table_name="agent_execution_outbox",
        schema="metaedu",
    )
    op.drop_constraint(
        "ck_agent_exec_outbox_decision",
        "agent_execution_outbox",
        schema="metaedu",
        type_="check",
    )
    op.drop_column("agent_execution_outbox", "decided_at", schema="metaedu")
    op.drop_column("agent_execution_outbox", "decision_digest", schema="metaedu")
    op.drop_column("agent_execution_outbox", "decision_reason", schema="metaedu")
    op.drop_column("agent_execution_outbox", "decision_actor_id", schema="metaedu")
    op.drop_index(
        "uq_agent_ws_outbox_turn",
        table_name="agent_workspace_outbox",
        schema="metaedu",
    )
    op.drop_constraint(
        "ck_agent_exec_outbox_payload",
        "agent_execution_outbox",
        schema="metaedu",
        type_="check",
    )
    op.drop_column("agent_execution_outbox", "payload_inline", schema="metaedu")
    op.drop_constraint(
        "ck_agent_ws_outbox_payload",
        "agent_workspace_outbox",
        schema="metaedu",
        type_="check",
    )
    op.drop_column("agent_workspace_outbox", "payload_inline", schema="metaedu")
