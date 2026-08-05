"""S4-B: transport/external owner scope 列 + reconcile/external ledger + inbox tombstone。

Revision ID: 040_transport_external_scope
Revises: 039_run_event_tombstone_guard
Create Date: 2026-08-04

R1-S4-B（Plan §R1-S4 B1）：为 transport/external payload 与迟到写治理补结构化
owner scope 与 reconcile/external 证据基座。本迁移只做 expand：

*(a)* 4 张既有 inbox/outbox 各增 ``conversation_id`` / ``producer_purge_revision`` /
``scope_reconcile_state``（全部 nullable，无默认值——回填前保持 NULL，见 backfill）；
*(b)* 4 个**部分**唯一索引（``WHERE conversation_id IS NOT NULL``，防 backfill/新写
并发产生重复 scope 行；新写未接线前仍可 NULL，不参与唯一约束）；
*(c)* 4 个**条件**复合外键 ``(tenant_id, conversation_id) ->
agent_conversations(tenant_id, id) ON DELETE RESTRICT``（PostgreSQL 复合 FK 对含
NULL 的行不检查，orphan/未知行天然放行；Conversation 物理删除前须先处理引用，
配合 D3 orphan 路径）；
*(d)* 新表 ``agent_transport_scope_reconcile``（D3 三态 reconcile ledger：唯一事实源，
``revision`` 乐观锁 + 多 CHECK + 五元组唯一键）；
*(e)* 新表 ``agent_external_object_refs``（D5 external ref ledger：来源唯一 +
erase receipt 状态机 + 跨列防伪）；
*(f)* 2 张 inbox 各增 ``receipt_tombstone_state`` / ``receipt_tombstone_digest``
（D4 tombstone marker + digest，跨列同生同灭）。

不收紧任何既有约束；``erase_available`` 保持 False（本迁移不接线 writer/claim，
不启用 purge/scheduler）。

**downgrade 边界**（B8 复核 #5 + 第二轮独立复核 #1，生产 fail-closed 语义）：
040 ``downgrade()`` **无论单步（目标 = ``down_revision`` = 039）还是 alembic 全链降级**
（目标早于 040，如预存迁移测试 downgrade 到更低版本再 upgrade head）一律 fail
closed：先校验所有新增列全为 NULL **且**两 ledger 全为空，否则 **raise**（拒绝降级，
要求 forward-fix），**不得删列/删表丢失 reconcile/external receipt/tombstone 证据**。
测试库的全链往返须在**测试准备阶段**清空 040 证据（见 ``_clear_040_evidence``），
生产 migration 不按目标版本放行数据删除。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "040_transport_external_scope"
down_revision: str | None = "039_run_event_tombstone_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "metaedu"

# 4 张 integration 表与各自部分唯一索引/条件 FK 名（命名沿 ck_/uq_/ix_/fk_ 约定）。
_OUTBOX_INBOX_TABLES = (
    "agent_workspace_outbox",
    "agent_workspace_inbox",
    "agent_execution_outbox",
    "agent_execution_inbox",
)

# (table, scope 唯一索引名, 唯一索引列, 条件 FK 名)
_SCOPE_INDEXES = (
    (
        "agent_workspace_outbox",
        "uq_agent_ws_outbox_scope",
        ("tenant_id", "conversation_id", "event_type", "aggregate_id"),
        "fk_agent_ws_outbox_scope_conv",
    ),
    (
        "agent_execution_outbox",
        "uq_agent_exec_outbox_scope",
        ("tenant_id", "conversation_id", "event_type", "aggregate_id"),
        "fk_agent_exec_outbox_scope_conv",
    ),
    (
        "agent_workspace_inbox",
        "uq_agent_ws_inbox_scope",
        ("tenant_id", "conversation_id", "consumer_name", "event_id"),
        "fk_agent_ws_inbox_scope_conv",
    ),
    (
        "agent_execution_inbox",
        "uq_agent_exec_inbox_scope",
        ("tenant_id", "conversation_id", "consumer_name", "event_id"),
        "fk_agent_exec_inbox_scope_conv",
    ),
)

_INBOX_TABLES = ("agent_workspace_inbox", "agent_execution_inbox")


def _add_scope_columns(table: str) -> None:
    op.add_column(
        table,
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        table,
        sa.Column("producer_purge_revision", sa.BigInteger(), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        table,
        sa.Column("scope_reconcile_state", sa.String(20), nullable=True),
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        f"ck_{table}_producer_purge_revision",
        table,
        "producer_purge_revision IS NULL OR producer_purge_revision >= 0",
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        f"ck_{table}_scope_reconcile_state",
        table,
        "scope_reconcile_state IS NULL OR scope_reconcile_state IN "
        "('pending','reconciled','orphan')",
        schema=_SCHEMA,
    )


def _add_inbox_tombstone_columns(table: str) -> None:
    op.add_column(
        table,
        sa.Column("receipt_tombstone_state", sa.String(16), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        table,
        sa.Column("receipt_tombstone_digest", sa.String(64), nullable=True),
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        f"ck_{table}_receipt_tombstone_state",
        table,
        "receipt_tombstone_state IS NULL OR receipt_tombstone_state IN ('redacted')",
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        f"ck_{table}_receipt_tombstone_digest",
        table,
        "receipt_tombstone_digest IS NULL OR "
        "receipt_tombstone_digest ~ '^[0-9a-f]{64}$'",
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        f"ck_{table}_receipt_tombstone",
        table,
        "(receipt_tombstone_state IS NULL) = (receipt_tombstone_digest IS NULL)",
        schema=_SCHEMA,
    )


def _create_reconcile_ledger() -> None:
    op.create_table(
        "agent_transport_scope_reconcile",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("owner_key", sa.String(40), nullable=False),
        sa.Column("source_table", sa.String(40), nullable=False),
        sa.Column("source_row_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("reconcile_class", sa.String(20), nullable=False),
        sa.Column("issue_code", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="open"),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("resolution_digest", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{_SCHEMA}.tenants.id"],
            name="fk_agent_transport_reconcile_tenant",
        ),
        sa.CheckConstraint(
            "owner_key IN ('workspace.transport.v1','execution.transport.v1',"
            "'external.payload.v1')",
            name="ck_agent_transport_reconcile_owner_key",
        ),
        sa.CheckConstraint(
            "source_table IN ('agent_workspace_outbox','agent_workspace_inbox',"
            "'agent_execution_outbox','agent_execution_inbox','agent_run_events')",
            name="ck_agent_transport_reconcile_source_table",
        ),
        sa.CheckConstraint(
            "reconcile_class IN ('conversation_scope','tenant_scope','orphan')",
            name="ck_agent_transport_reconcile_class",
        ),
        sa.CheckConstraint(
            "issue_code IN ('source_message_missing','source_run_missing',"
            "'source_outbox_missing','cross_tenant_mismatch','ambiguous_mapping',"
            "'conversation_deleted_orphan','epoch_unresolvable')",
            name="ck_agent_transport_reconcile_issue_code",
        ),
        sa.CheckConstraint(
            "state IN ('open','acknowledged','resolved')",
            name="ck_agent_transport_reconcile_state",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="ck_agent_transport_reconcile_revision",
        ),
        sa.CheckConstraint(
            "resolution_digest IS NULL OR resolution_digest ~ '^[0-9a-f]{64}$'",
            name="ck_agent_transport_reconcile_resolution_digest",
        ),
        sa.CheckConstraint(
            "((state = 'resolved') AND resolution_digest IS NOT NULL "
            "AND resolved_at IS NOT NULL) "
            "OR (state <> 'resolved' AND resolution_digest IS NULL "
            "AND resolved_at IS NULL)",
            name="ck_agent_transport_reconcile_resolution_evidence",
        ),
        sa.CheckConstraint(
            "(reconcile_class = 'conversation_scope') = (conversation_id IS NOT NULL)",
            name="ck_agent_transport_reconcile_class_scope",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "owner_key",
            "source_table",
            "source_row_id",
            "issue_code",
            name="uq_agent_transport_reconcile_issue",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_agent_transport_reconcile_tenant_state",
        "agent_transport_scope_reconcile",
        ["tenant_id", "state"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_agent_transport_reconcile_conv",
        "agent_transport_scope_reconcile",
        ["tenant_id", "conversation_id"],
        schema=_SCHEMA,
        postgresql_where=sa.text("conversation_id IS NOT NULL"),
    )


def _create_external_ref_ledger() -> None:
    op.create_table(
        "agent_external_object_refs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "owner_key",
            sa.String(40),
            nullable=False,
            server_default="external.payload.v1",
        ),
        sa.Column("ref_scheme", sa.String(40), nullable=False),
        sa.Column("ref_value", sa.String(500), nullable=False),
        sa.Column("source_table", sa.String(40), nullable=False),
        sa.Column("source_row_id", UUID(as_uuid=True), nullable=False),
        sa.Column("erase_state", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("receipt_digest", sa.String(64), nullable=True),
        sa.Column("blocked_reason", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{_SCHEMA}.tenants.id"],
            name="fk_agent_external_refs_tenant",
        ),
        sa.CheckConstraint(
            "ref_scheme IN ('db_local','unknown')",
            name="ck_agent_external_refs_ref_scheme",
        ),
        sa.CheckConstraint(
            "source_table IN ('agent_run_events','agent_workspace_outbox',"
            "'agent_execution_outbox')",
            name="ck_agent_external_refs_source_table",
        ),
        sa.CheckConstraint(
            "erase_state IN ('pending','registered','erased','blocked','unknown')",
            name="ck_agent_external_refs_erase_state",
        ),
        sa.CheckConstraint(
            "receipt_digest IS NULL OR receipt_digest ~ '^[0-9a-f]{64}$'",
            name="ck_agent_external_refs_receipt_digest",
        ),
        sa.CheckConstraint(
            "blocked_reason IS NULL OR blocked_reason IN ('unknown_scheme',"
            "'erase_timeout','digest_mismatch','outcome_unknown','adapter_unavailable')",
            name="ck_agent_external_refs_blocked_reason",
        ),
        sa.CheckConstraint(
            "((erase_state = 'erased') = (receipt_digest IS NOT NULL)) AND "
            "((erase_state IN ('blocked','unknown')) = (blocked_reason IS NOT NULL)) AND "
            "((erase_state IN ('pending','registered')) = "
            "(receipt_digest IS NULL AND blocked_reason IS NULL))",
            name="ck_agent_external_refs_erase_evidence",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_table",
            "source_row_id",
            "ref_value",
            name="uq_agent_external_ref_source",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_agent_external_refs_conv",
        "agent_external_object_refs",
        ["tenant_id", "conversation_id"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_agent_external_refs_state",
        "agent_external_object_refs",
        ["tenant_id", "erase_state"],
        schema=_SCHEMA,
    )


def upgrade() -> None:
    # (a) 4 表 scope 列 + CHECK。
    for table in _OUTBOX_INBOX_TABLES:
        _add_scope_columns(table)
    # (f) 2 张 inbox tombstone 列 + CHECK。
    for table in _INBOX_TABLES:
        _add_inbox_tombstone_columns(table)
    # (b) 部分唯一索引（WHERE conversation_id IS NOT NULL）。
    for table, index_name, columns, _fk in _SCOPE_INDEXES:
        op.create_index(
            index_name,
            table,
            list(columns),
            unique=True,
            schema=_SCHEMA,
            postgresql_where=sa.text("conversation_id IS NOT NULL"),
        )
    # (c) 条件复合 FK（含 NULL 行自动放行；ON DELETE RESTRICT）。
    for table, _index_name, _columns, fk_name in _SCOPE_INDEXES:
        op.create_foreign_key(
            fk_name,
            table,
            "agent_conversations",
            ["tenant_id", "conversation_id"],
            ["tenant_id", "id"],
            source_schema=_SCHEMA,
            referent_schema=_SCHEMA,
            ondelete="RESTRICT",
        )
    # (d)(e) 两张新 ledger 表。
    _create_reconcile_ledger()
    _create_external_ref_ledger()


def _has_non_null_scope_data() -> str | None:
    """返回首个含非空 scope/tombstone 数据的表名（downgrade fail-closed 证据）。"""
    bind = op.get_bind()
    for table in _OUTBOX_INBOX_TABLES:
        row = bind.execute(
            sa.text(
                f"SELECT EXISTS(SELECT 1 FROM {_SCHEMA}.{table} WHERE "
                f"conversation_id IS NOT NULL OR producer_purge_revision IS NOT NULL "
                f"OR scope_reconcile_state IS NOT NULL)"
            )
        )
        if bool(row.scalar()):
            return table
    for table in _INBOX_TABLES:
        row = bind.execute(
            sa.text(
                f"SELECT EXISTS(SELECT 1 FROM {_SCHEMA}.{table} WHERE "
                f"receipt_tombstone_state IS NOT NULL OR "
                f"receipt_tombstone_digest IS NOT NULL)"
            )
        )
        if bool(row.scalar()):
            return table
    return None


def _ledger_nonempty(table: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(sa.text(f"SELECT EXISTS(SELECT 1 FROM {_SCHEMA}.{table})"))
    return bool(row.scalar())


def _lock_tables_access_exclusive(bind) -> None:
    """按固定顺序对 040 涉及的全部表取 ACCESS EXCLUSIVE（第三轮复核 #4 TOCTOU 修复）。"""
    tables = [
        "agent_transport_scope_reconcile",
        "agent_external_object_refs",
        "agent_workspace_outbox",
        "agent_workspace_inbox",
        "agent_execution_outbox",
        "agent_execution_inbox",
    ]
    for tbl in tables:
        bind.execute(sa.text(f"LOCK TABLE {_SCHEMA}.{tbl} IN ACCESS EXCLUSIVE MODE"))


def downgrade() -> None:
    # B8 复核 #5 + 第二轮独立复核 #1（生产 fail-closed 语义）：downgrade **无论单步
    # 还是全链**，凡有证据（非空 scope/tombstone 数据或非空 ledger）一律 fail closed
    # raise，要求 forward-fix——**不得**按目标版本放行 TRUNCATE/清列，否则生产
    # `alembic downgrade <早期版本>` 会静默丢失 reconcile/external receipt/tombstone
    # 证据。测试库的全链往返须在**测试准备阶段**清空证据（B8：downgrade 永不删证据）。
    # 第三轮复核 #4（TOCTOU）：EXISTS 检查取 ACCESS SHARE，不挡并发 INSERT/UPDATE--
    # 并发写可在检查通过后、DROP 前提交证据，随后 DROP 取 ACCESS EXCLUSIVE 时证据已落盘
    # 并被删除。检查前按固定顺序 LOCK TABLE ... ACCESS EXCLUSIVE，使「检查 + DROP」在
    # 同一事务内对并发写原子：并发写者阻塞到 DROP 完成（表已删，写入失败）或检查 raise
    # （证据已提交则被检见 -> fail closed）。
    bind = op.get_bind()
    _lock_tables_access_exclusive(bind)
    evidence_table = _has_non_null_scope_data()
    if evidence_table is not None:
        raise RuntimeError(
            f"cannot downgrade 040_transport_external_scope: {evidence_table} has "
            f"non-null scope/tombstone data; dropping columns would lose reconcile/"
            f"tombstone evidence. forward-fix instead of downgrading"
        )
    for ledger in ("agent_transport_scope_reconcile", "agent_external_object_refs"):
        if _ledger_nonempty(ledger):
            raise RuntimeError(
                f"cannot downgrade 040_transport_external_scope: {ledger} is "
                f"non-empty; dropping it would lose reconcile/external receipt "
                f"evidence. forward-fix instead of downgrading"
            )
    # 无证据数据时安全还原：先撤新表，再撤 FK/索引/列。
    op.drop_table("agent_external_object_refs", schema=_SCHEMA)
    op.drop_table("agent_transport_scope_reconcile", schema=_SCHEMA)
    for table, index_name, _columns, fk_name in _SCOPE_INDEXES:
        op.drop_constraint(fk_name, table, schema=_SCHEMA, type_="foreignkey")
        op.drop_index(index_name, table_name=table, schema=_SCHEMA)
    for table in _INBOX_TABLES:
        op.drop_constraint(
            f"ck_{table}_receipt_tombstone", table, schema=_SCHEMA, type_="check"
        )
        op.drop_constraint(
            f"ck_{table}_receipt_tombstone_digest", table, schema=_SCHEMA, type_="check"
        )
        op.drop_constraint(
            f"ck_{table}_receipt_tombstone_state", table, schema=_SCHEMA, type_="check"
        )
        op.drop_column(table, "receipt_tombstone_digest", schema=_SCHEMA)
        op.drop_column(table, "receipt_tombstone_state", schema=_SCHEMA)
    for table in _OUTBOX_INBOX_TABLES:
        op.drop_constraint(
            f"ck_{table}_scope_reconcile_state", table, schema=_SCHEMA, type_="check"
        )
        op.drop_constraint(
            f"ck_{table}_producer_purge_revision", table, schema=_SCHEMA, type_="check"
        )
        op.drop_column(table, "scope_reconcile_state", schema=_SCHEMA)
        op.drop_column(table, "producer_purge_revision", schema=_SCHEMA)
        op.drop_column(table, "conversation_id", schema=_SCHEMA)
