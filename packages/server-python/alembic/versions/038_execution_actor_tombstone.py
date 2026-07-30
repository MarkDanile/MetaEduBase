"""S3-B: execution actor tombstone（agent_runs + agent_turn_inputs）。

Revision ID: 038_execution_actor_tombstone
Revises: 037_system_key_fingerprints
Create Date: 2026-07-30

R1-S3 契约注记 round-1 P1-2 / round-2 P1-4 + P2-3：Spec §7.1「Conversation.
created_by、Message.author_id **等**直接主体标识在 purge 时清除」覆盖 execution
表。``AgentRun.created_by`` / ``TurnInput.created_by`` 是直接主体标识，purge 时
必须清除并另存不可逆 tenant-scoped HMAC digest（与 workspace Conversation/Message
同模式，复用 composition shared ``actor_audit_digest``）。

本迁移为 ``agent_runs`` + ``agent_turn_inputs`` 增 ``actor_state``（present/redacted）
+ ``actor_identity_digest``（64-hex nullable），放宽 ``created_by`` 为 nullable +
CHECK（present 强制 created_by 非空 + digest NULL；redacted 强制 created_by NULL +
digest 64-hex）。expand-only。

**downgrade 边界**（round-2 P2-3）：downgrade **仅在无 redacted 行时可逆**（还原
NOT NULL + 删列）。已产生 redacted 行（anonymization 后）downgrade 必须 **fail
closed**--匿名化不可逆，回填伪造 UUID 会破坏审计真实性。downgrade 函数运行期检查
``actor_state='redacted'`` 行，存在即 raise。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "038_execution_actor_tombstone"
down_revision: str | None = "037_system_key_fingerprints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "metaedu"

# present/redacted actor tombstone CHECK（与 workspace ck_agent_conv_actor 同模式）。
_ACTOR_CHECK_SQL = (
    "(actor_state = 'present' AND created_by IS NOT NULL "
    "AND actor_identity_digest IS NULL) OR "
    "(actor_state = 'redacted' AND created_by IS NULL "
    "AND actor_identity_digest IS NOT NULL "
    "AND char_length(actor_identity_digest) = 64)"
)


def _upgrade_table(table: str) -> None:
    op.add_column(
        table,
        sa.Column("actor_state", sa.String(16), nullable=False, server_default="present"),
        schema=_SCHEMA,
    )
    op.add_column(
        table,
        sa.Column("actor_identity_digest", sa.String(64), nullable=True),
        schema=_SCHEMA,
    )
    op.alter_column(
        table,
        "created_by",
        existing_type=sa.UUID(as_uuid=True),
        nullable=True,
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        f"ck_{table}_actor",
        table,
        _ACTOR_CHECK_SQL,
        schema=_SCHEMA,
    )


def upgrade() -> None:
    for table in ("agent_runs", "agent_turn_inputs"):
        _upgrade_table(table)


def _has_redacted_rows(table: str) -> bool:
    """运行期检查是否存在 actor_state='redacted' 行（anonymization 后不可逆）。"""
    bind = op.get_bind()
    result = bind.execute(
        sa.text(f"SELECT EXISTS(SELECT 1 FROM {_SCHEMA}.{table} WHERE actor_state = 'redacted')")
    )
    return bool(result.scalar())


def _downgrade_table(table: str) -> None:
    op.drop_constraint(f"ck_{table}_actor", table, schema=_SCHEMA, type_="check")
    op.alter_column(
        table,
        "created_by",
        existing_type=sa.UUID(as_uuid=True),
        nullable=False,
        schema=_SCHEMA,
    )
    op.drop_column(table, "actor_identity_digest", schema=_SCHEMA)
    op.drop_column(table, "actor_state", schema=_SCHEMA)


def downgrade() -> None:
    # round-2 P2-3：anonymization 不可逆。若已有 redacted 行，downgrade 必须 fail
    # closed（不伪造 UUID 回填 created_by）。无 redacted 行时才安全还原 schema。
    for table in ("agent_runs", "agent_turn_inputs"):
        if _has_redacted_rows(table):
            raise RuntimeError(
                f"cannot downgrade {table}: actor anonymization has produced "
                f"redacted rows (irreversible); forward-fix instead of fabricating "
                f"UUIDs into created_by"
            )
    for table in ("agent_runs", "agent_turn_inputs"):
        _downgrade_table(table)
