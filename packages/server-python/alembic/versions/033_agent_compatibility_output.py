"""add durable Direct RAG compatibility output staging

Revision ID: 033_agent_compat_output
Revises: 032_agent_run_cancel_intent
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "033_agent_compat_output"
down_revision: str | None = "032_agent_run_cancel_intent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_compatibility_outputs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("output_ref", sa.String(length=500), nullable=False),
        sa.Column("output_digest", sa.String(length=64), nullable=False),
        sa.Column("response_digest", sa.String(length=64), nullable=False),
        sa.Column("reply_text", sa.Text(), nullable=False),
        sa.Column(
            "response_envelope", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("classification", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.CheckConstraint(
            "media_type = 'text/markdown' AND classification = 'internal'",
            name="ck_agent_compat_output_contract",
        ),
        sa.CheckConstraint(
            "char_length(output_digest) = 64 AND char_length(response_digest) = 64",
            name="ck_agent_compat_output_digests",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(response_envelope) = 'object' "
            "AND pg_column_size(response_envelope) <= 262144",
            name="ck_agent_compat_output_envelope_size",
        ),
        sa.CheckConstraint(
            "char_length(btrim(output_ref)) > 0 AND output_ref = btrim(output_ref)",
            name="ck_agent_compat_output_ref",
        ),
        sa.CheckConstraint(
            "octet_length(reply_text) <= 65536",
            name="ck_agent_compat_output_reply_size",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "conversation_id"],
            [
                "metaedu.agent_runs.tenant_id",
                "metaedu.agent_runs.id",
                "metaedu.agent_runs.conversation_id",
            ],
            name="fk_agent_compat_output_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "output_ref", name="uq_agent_compat_output_ref"
        ),
        sa.UniqueConstraint(
            "tenant_id", "run_id", name="uq_agent_compat_output_tenant_run"
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_compat_output_conversation",
        "agent_compatibility_outputs",
        ["tenant_id", "conversation_id", "created_at"],
        unique=False,
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_compat_output_conversation",
        table_name="agent_compatibility_outputs",
        schema="metaedu",
    )
    op.drop_table("agent_compatibility_outputs", schema="metaedu")
