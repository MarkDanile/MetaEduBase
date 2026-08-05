"""R1-S4-B migration 040 schema 真实 PostgreSQL 验证（M1）。

覆盖（Plan §R1-S4 B1/B8）：
- 040 upgrade 落地：4 张 inbox/outbox 新增 scope 列（conversation_id /
  producer_purge_revision / scope_reconcile_state）、2 张 inbox 增 receipt_tombstone_*、
  4 个部分唯一索引（WHERE conversation_id IS NOT NULL）、4 个条件复合 FK
  （ON DELETE RESTRICT）、2 张新 ledger 表与其 CHECK/唯一键/索引。
- CHECK 反例（真实 PG IntegrityError）：负 producer_purge_revision、越界
  scope_reconcile_state、非 hex tombstone digest、tombstone 单边（state/digest 不
  同生同灭）、reconcile resolution_evidence、class_scope、external erase_evidence。
- 条件 FK 反例：conversation_id 指向不存在的 (tenant, id) -> IntegrityError；
  conversation_id NULL 行（orphan/未知）天然放行。
- downgrade/upgrade 往返：空证据时 downgrade 还原全部新增对象；已有非空
  scope/tombstone 数据或非空 ledger 时 downgrade fail closed（raise），不丢证据。

边界（S4-B）：erase_available 保持 False；不接线 writer/claim/participant/scheduler。
"""

from __future__ import annotations

import asyncio
import os
import uuid
import warnings
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config

from alembic import command
from app.config import settings

SERVER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEST_DB_URL = "postgresql://metaedu:dev_only_123@localhost:5432/metaedu_test"

_SCOPE_TABLES = (
    "agent_workspace_outbox",
    "agent_workspace_inbox",
    "agent_execution_outbox",
    "agent_execution_inbox",
)
_INBOX_TABLES = ("agent_workspace_inbox", "agent_execution_inbox")
_LEDGER_TABLES = ("agent_transport_scope_reconcile", "agent_external_object_refs")
_SCOPE_INDEXES = (
    "uq_agent_ws_outbox_scope",
    "uq_agent_exec_outbox_scope",
    "uq_agent_ws_inbox_scope",
    "uq_agent_exec_inbox_scope",
)
_SCOPE_FKS = (
    "fk_agent_ws_outbox_scope_conv",
    "fk_agent_exec_outbox_scope_conv",
    "fk_agent_ws_inbox_scope_conv",
    "fk_agent_exec_inbox_scope_conv",
)


def _db_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


def _sqlalchemy_url() -> str:
    return _db_url().replace("postgresql://", "postgresql+asyncpg://", 1)


def _run_alembic(direction: str, revision: str) -> None:
    original_url = settings.database_url
    settings.database_url = _sqlalchemy_url()
    try:
        config = Config(str(SERVER_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(SERVER_ROOT / "alembic"))
        fn = command.upgrade if direction == "upgrade" else command.downgrade
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            fn(config, revision)
    finally:
        settings.database_url = original_url


async def _connect():
    return await asyncpg.connect(_db_url())


async def _columns(table: str) -> set[str]:
    connection = await _connect()
    try:
        rows = await connection.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='metaedu' AND table_name=$1",
            table,
        )
        return {row["column_name"] for row in rows}
    finally:
        await connection.close()


async def _clear_040_evidence() -> None:
    """清空 040 全部证据（scope 列置 NULL + 两 ledger 清空 + inbox tombstone 置 NULL）。

    供 sync 的 downgrade round-trip 测试前置调用，确保「空证据」前提，避免单步
    downgrade fail-closed 在全量回归残留证据下误触发。仅清数据，不动 schema。
    """
    connection = await _connect()
    try:
        for table in _LEDGER_TABLES:
            await connection.execute(f"TRUNCATE TABLE metaedu.{table}")
        for table in _SCOPE_TABLES:
            await connection.execute(
                f"UPDATE metaedu.{table} SET conversation_id = NULL, "
                f"producer_purge_revision = NULL, scope_reconcile_state = NULL"
            )
        for table in _INBOX_TABLES:
            await connection.execute(
                f"UPDATE metaedu.{table} SET receipt_tombstone_state = NULL, "
                f"receipt_tombstone_digest = NULL"
            )
    finally:
        await connection.close()


async def _objects_exist(kind: str, names: tuple[str, ...]) -> set[str]:
    """返回给定对象名中当前存在的集合。kind ∈ {index, table, fk}。"""
    connection = await _connect()
    try:
        if kind == "index":
            rows = await connection.fetch(
                "SELECT indexname AS n FROM pg_indexes "
                "WHERE schemaname='metaedu' AND indexname = ANY($1::text[])",
                list(names),
            )
        elif kind == "table":
            rows = await connection.fetch(
                "SELECT table_name AS n FROM information_schema.tables "
                "WHERE table_schema='metaedu' AND table_name = ANY($1::text[])",
                list(names),
            )
        else:  # fk
            rows = await connection.fetch(
                "SELECT conname AS n FROM pg_constraint "
                "WHERE contype='f' AND conname = ANY($1::text[])",
                list(names),
            )
        return {row["n"] for row in rows}
    finally:
        await connection.close()


async def _tenant_id() -> uuid.UUID:
    """取一个可用 tenant id；干净库无 tenant 时自建一个（测试隔离，不依赖前序用例残留）。

    composition 的 autouse clean 不清 ``tenants``，但干净 fresh 库（CI 容器）里
    ``tenants`` 为空；若直接 ``LIMIT 1`` 会拿到 None，使 NOT NULL ``tenant_id`` 在
    反例插入处误触发 NotNullViolation 而非预期的 CHECK/FK 违规。故此处自给自足。
    """
    connection = await _connect()
    try:
        existing = await connection.fetchval("SELECT id FROM metaedu.tenants LIMIT 1")
        if existing is not None:
            return existing
        new_id = uuid.uuid4()
        await connection.execute(
            "INSERT INTO metaedu.tenants (id, name, school_name, created_at, updated_at) "
            "VALUES ($1, $2, $2, clock_timestamp(), clock_timestamp()) "
            "ON CONFLICT (id) DO NOTHING",
            new_id,
            f"probe-{new_id.hex[:8]}",
        )
        return new_id
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_040_columns_indexes_fks_ledgers_present():
    """upgrade 后：4 表 scope 列、2 张 inbox tombstone 列、4 索引、4 FK、2 ledger。"""
    for table in _SCOPE_TABLES:
        cols = await _columns(table)
        assert {
            "conversation_id",
            "producer_purge_revision",
            "scope_reconcile_state",
        } <= cols, f"{table} 缺 scope 列"
    for table in _INBOX_TABLES:
        cols = await _columns(table)
        assert {"receipt_tombstone_state", "receipt_tombstone_digest"} <= cols
    assert await _objects_exist("index", _SCOPE_INDEXES) == set(_SCOPE_INDEXES)
    assert await _objects_exist("fk", _SCOPE_FKS) == set(_SCOPE_FKS)
    assert await _objects_exist("table", _LEDGER_TABLES) == set(_LEDGER_TABLES)
    # reconcile ledger 关键列。
    reconcile_cols = await _columns("agent_transport_scope_reconcile")
    assert {
        "tenant_id",
        "owner_key",
        "source_table",
        "source_row_id",
        "conversation_id",
        "reconcile_class",
        "issue_code",
        "state",
        "revision",
        "resolution_digest",
        "created_at",
        "resolved_at",
    } <= reconcile_cols
    external_cols = await _columns("agent_external_object_refs")
    assert {
        "tenant_id",
        "conversation_id",
        "owner_key",
        "ref_scheme",
        "ref_value",
        "source_table",
        "source_row_id",
        "erase_state",
        "receipt_digest",
        "blocked_reason",
    } <= external_cols


@pytest.mark.asyncio
async def test_040_scope_index_is_partial():
    """scope 唯一索引是部分索引（WHERE conversation_id IS NOT NULL）。"""
    connection = await _connect()
    try:
        rows = await connection.fetch(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname='metaedu' AND indexname = ANY($1::text[])",
            list(_SCOPE_INDEXES),
        )
        defs = {row["indexname"]: row["indexdef"] for row in rows}
        for name in _SCOPE_INDEXES:
            assert "WHERE (conversation_id IS NOT NULL)" in defs[name], name
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_040_scope_fk_is_on_delete_restrict():
    connection = await _connect()
    try:
        rows = await connection.fetch(
            "SELECT conname, confdeltype FROM pg_constraint "
            "WHERE contype='f' AND conname = ANY($1::text[])",
            list(_SCOPE_FKS),
        )
        actions = {row["conname"]: row["confdeltype"] for row in rows}
        # 'r' = RESTRICT（asyncpg 以单字节 bytes 返回 "char" 类型）。
        for name in _SCOPE_FKS:
            assert actions[name] in (b"r", "r"), name
    finally:
        await connection.close()


# --- CHECK / FK 反例（真实 PG IntegrityError）------------------------------


async def _insert_outbox_scope(
    connection, *, conversation_id, producer_purge_revision, scope_state
) -> None:
    """直接以 SQL 在 agent_workspace_outbox 造一行最小合法 outbox + scope 列。"""
    tenant = await _tenant_id()
    await connection.execute(
        """
        INSERT INTO metaedu.agent_workspace_outbox (
            id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type,
            payload_inline, payload_ref, payload_digest, correlation_id, status,
            attempt_count, next_attempt_at, created_at,
            conversation_id, producer_purge_revision, scope_reconcile_state
        ) VALUES (
            $1, $2, 'turn.requested.v1', 1, $3, 'workspace.message',
            '{}'::jsonb, NULL, $4, $5, 'pending',
            0, clock_timestamp(), clock_timestamp(),
            $6, $7, $8
        )
        """,
        uuid.uuid4(),
        tenant,
        uuid.uuid4(),
        "a" * 64,
        uuid.uuid4(),
        conversation_id,
        producer_purge_revision,
        scope_state,
    )


@pytest.mark.asyncio
async def test_040_negative_producer_purge_revision_rejected():
    connection = await _connect()
    try:
        async with connection.transaction():
            with pytest.raises(asyncpg.CheckViolationError):
                await _insert_outbox_scope(
                    connection,
                    conversation_id=None,
                    producer_purge_revision=-1,
                    scope_state=None,
                )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_040_invalid_scope_reconcile_state_rejected():
    connection = await _connect()
    try:
        async with connection.transaction():
            with pytest.raises(asyncpg.CheckViolationError):
                await _insert_outbox_scope(
                    connection,
                    conversation_id=None,
                    producer_purge_revision=None,
                    scope_state="bogus",
                )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_040_scope_fk_rejects_unknown_conversation():
    """conversation_id 指向不存在的 (tenant, id) -> FK 违规。"""
    connection = await _connect()
    try:
        async with connection.transaction():
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await _insert_outbox_scope(
                    connection,
                    conversation_id=uuid.uuid4(),  # 不存在
                    producer_purge_revision=None,
                    scope_state=None,
                )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_040_null_scope_passes_fk():
    """orphan/未知（conversation_id NULL）行天然放行（复合 FK 跳过含 NULL 行）。"""
    connection = await _connect()
    try:
        async with connection.transaction():
            await _insert_outbox_scope(
                connection,
                conversation_id=None,
                producer_purge_revision=None,
                scope_state=None,
            )
            # 不抛即通过；回滚保持库干净。
            raise _RollbackError
    except _RollbackError:
        pass
    finally:
        await connection.close()


class _RollbackError(Exception):
    pass


@pytest.mark.asyncio
async def test_040_inbox_tombstone_single_sided_rejected():
    """tombstone marker 与 digest 必须同生同灭：只填 digest 不填 state -> CHECK。"""
    tenant = await _tenant_id()
    connection = await _connect()
    try:
        async with connection.transaction():
            with pytest.raises(asyncpg.CheckViolationError):
                await connection.execute(
                    """
                    INSERT INTO metaedu.agent_workspace_inbox (
                        id, tenant_id, consumer_name, event_id, event_type,
                        schema_version, payload_digest, correlation_id, status,
                        created_at, receipt_tombstone_state, receipt_tombstone_digest
                    ) VALUES (
                        $1, $2, 'assistant_publish', $3, 'assistant_message.publish_requested.v1',
                        1, $4, $5, 'consumed',
                        clock_timestamp(), NULL, $6
                    )
                    """,
                    uuid.uuid4(),
                    tenant,
                    uuid.uuid4(),
                    "b" * 64,
                    uuid.uuid4(),
                    "c" * 64,
                )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_040_reconcile_resolution_evidence_rejected():
    """state='resolved' 但缺 resolution_digest/resolved_at -> CHECK 违规。"""
    tenant = await _tenant_id()
    connection = await _connect()
    try:
        async with connection.transaction():
            with pytest.raises(asyncpg.CheckViolationError):
                await connection.execute(
                    """
                    INSERT INTO metaedu.agent_transport_scope_reconcile (
                        id, tenant_id, owner_key, source_table, source_row_id,
                        reconcile_class, issue_code, state, revision,
                        resolution_digest, created_at, resolved_at
                    ) VALUES (
                        $1, $2, 'workspace.transport.v1', 'agent_workspace_outbox', $3,
                        'tenant_scope', 'source_message_missing', 'resolved', 1,
                        NULL, clock_timestamp(), NULL
                    )
                    """,
                    uuid.uuid4(),
                    tenant,
                    uuid.uuid4(),
                )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_040_reconcile_class_scope_binding_rejected():
    """conversation_scope 必须带 conversation_id（ck_..._class_scope）。"""
    tenant = await _tenant_id()
    connection = await _connect()
    try:
        async with connection.transaction():
            with pytest.raises(asyncpg.CheckViolationError):
                await connection.execute(
                    """
                    INSERT INTO metaedu.agent_transport_scope_reconcile (
                        id, tenant_id, owner_key, source_table, source_row_id,
                        conversation_id, reconcile_class, issue_code, state, revision,
                        created_at
                    ) VALUES (
                        $1, $2, 'workspace.transport.v1', 'agent_workspace_outbox', $3,
                        NULL, 'conversation_scope', 'ambiguous_mapping', 'open', 1,
                        clock_timestamp()
                    )
                    """,
                    uuid.uuid4(),
                    tenant,
                    uuid.uuid4(),
                )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_040_external_erase_evidence_rejected():
    """erase_state='erased' 但缺 receipt_digest -> CHECK 违规（防伪）。"""
    tenant = await _tenant_id()
    connection = await _connect()
    try:
        async with connection.transaction():
            with pytest.raises(asyncpg.CheckViolationError):
                await connection.execute(
                    """
                    INSERT INTO metaedu.agent_external_object_refs (
                        id, tenant_id, owner_key, ref_scheme, ref_value,
                        source_table, source_row_id, erase_state, receipt_digest,
                        blocked_reason, created_at, updated_at
                    ) VALUES (
                        $1, $2, 'external.payload.v1', 'unknown', 'opaque-1',
                        'agent_run_events', $3, 'erased', NULL,
                        NULL, clock_timestamp(), clock_timestamp()
                    )
                    """,
                    uuid.uuid4(),
                    tenant,
                    uuid.uuid4(),
                )
    finally:
        await connection.close()


# --- downgrade / upgrade 往返与 fail-closed ---------------------------------


def test_040_downgrade_upgrade_round_trip_empty():
    """空证据时 downgrade 完整还原全部新增对象，upgrade 可重入。

    前置显式清空 040 证据：本测试是 sync（无 autouse async clean fixture），全量
    回归中可能排在写了 scope/reconcile 证据的测试之后，库残留证据会让单步
    downgrade fail-closed raise（B8 #5 语义），进而 finally 的 upgrade head 撞
    「列已存在」把库卡在不一致态。先清空证据确保「empty」前提，与测试名一致。
    """
    asyncio.run(_clear_040_evidence())
    try:
        _run_alembic("downgrade", "039_run_event_tombstone_guard")
        assert asyncio.run(_objects_exist("table", _LEDGER_TABLES)) == set()
        assert asyncio.run(_objects_exist("index", _SCOPE_INDEXES)) == set()
        assert asyncio.run(_objects_exist("fk", _SCOPE_FKS)) == set()
        cols = asyncio.run(_columns("agent_workspace_outbox"))
        assert "conversation_id" not in cols
        assert "producer_purge_revision" not in cols
        assert "scope_reconcile_state" not in cols
    finally:
        _run_alembic("upgrade", "head")
    assert asyncio.run(_objects_exist("table", _LEDGER_TABLES)) == set(_LEDGER_TABLES)


@pytest.mark.asyncio
async def test_040_downgrade_fail_closed_on_scope_data():
    """已有非空 scope 数据时 downgrade 必须 fail closed（不丢 reconcile/tombstone 证据）。"""
    connection = await _connect()
    try:
        # 造一行带非空 producer_purge_revision 的 outbox（触发 _has_non_null_scope_data）。
        await _insert_outbox_scope(
            connection,
            conversation_id=None,
            producer_purge_revision=0,
            scope_state=None,
        )
    finally:
        await connection.close()
    try:
        with pytest.raises(RuntimeError, match="cannot downgrade"):
            await asyncio.to_thread(
                _run_alembic, "downgrade", "039_run_event_tombstone_guard"
            )
    finally:
        # 清理证据行（downgrade 应在 raise 前回滚，保持 040 不降级）。
        connection = await _connect()
        try:
            await connection.execute(
                "DELETE FROM metaedu.agent_workspace_outbox "
                "WHERE producer_purge_revision IS NOT NULL"
            )
        finally:
            await connection.close()
        # 确认 head 仍是 040（downgrade 已 fail closed，未降级）。
        assert await _objects_exist("table", _LEDGER_TABLES) == set(_LEDGER_TABLES)


@pytest.mark.asyncio
async def test_040_full_chain_downgrade_clears_evidence_and_passes():
    """alembic 全链降级（目标 < 040）放行：清空证据后还原，不卡库，upgrade head 恢复。

    与单步降级（``test_040_downgrade_fail_closed_on_scope_data``，目标=039 时
    fail-closed）相对：全链降级（如预存迁移测试 downgrade 到 020 再 upgrade
    head）是测试库合法临时态，守卫不拦，先清空证据列/ledger 再还原，避免把库
    卡在中间版本。本测试造 ledger 证据（触发 ``_ledger_nonempty``）走全链路径。
    """
    connection = await _connect()
    try:
        # 造 ledger 证据（reconcile issue，触发 ledger 非空分支）。
        await _insert_outbox_scope(
            connection,
            conversation_id=None,
            producer_purge_revision=0,
            scope_state=None,
        )
        tenant = await _tenant_id()
        await connection.execute(
            "INSERT INTO metaedu.agent_transport_scope_reconcile ("
            "  id, tenant_id, owner_key, source_table, source_row_id, "
            "  reconcile_class, issue_code, state, revision, created_at"
            ") VALUES ($1, $2, 'workspace.transport.v1', 'agent_workspace_outbox', "
            "  $3, 'tenant_scope', 'source_message_missing', 'open', 1, clock_timestamp())",
            uuid.uuid4(),
            tenant,
            uuid.uuid4(),
        )
    finally:
        await connection.close()
    # 全链降级到 037（目标 < 040 的 down_revision=039）：040 走全链分支放行，
    # 清证据、还原、不 raise、不卡库。039 无守卫、038 守卫仅 actor tombstone 触发
    # （本测试数据无），链路可降到 037。
    await asyncio.to_thread(_run_alembic, "downgrade", "037_system_key_fingerprints")
    try:
        assert await _objects_exist("table", _LEDGER_TABLES) == set(), (
            "全链降级后 040 ledger 表应已删除"
        )
    finally:
        await asyncio.to_thread(_run_alembic, "upgrade", "head")
    # upgrade head 恢复全部对象；证据已被全链清空（升级后 ledger 为空）。
    assert await _objects_exist("table", _LEDGER_TABLES) == set(_LEDGER_TABLES)
    connection = await _connect()
    try:
        n = await connection.fetchval(
            "SELECT count(*) FROM metaedu.agent_transport_scope_reconcile"
        )
        assert n == 0, "全链降级应已清空 reconcile ledger 证据"
    finally:
        await connection.close()
