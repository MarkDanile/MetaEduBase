"""R1-S4-B M3：transport/external scope backfill 真实 PostgreSQL 验证。

覆盖（Plan §R1-S4 B2/B3/B4/B5/B7）：
- 来源矩阵：workspace outbox 经 Message、execution outbox 经 Run、两 inbox 经源
  outbox 回填 ``conversation_id``（先 outbox 后 inbox 顺序）。
- epoch（B3）：历史行 ``producer_purge_revision`` 保持 NULL + 每行登记
  ``epoch_unresolvable``（不伪造 epoch）。
- 三态 reconcile（B4）：scope 未知（源缺失）-> tenant_scope + scope 类 issue；
  orphan（Conversation 已删）-> orphan + conversation_deleted_orphan；跨 tenant ->
  tenant_scope + cross_tenant_mismatch（不映射）。行内投影 orphan > pending >
  reconciled。
- external ledger（B5）：outbox/run_events 非空 ``payload_ref`` 登记
  unknown+blocked(unknown_scheme)。
- 幂等（重复执行不产生重复 issue/ref）；verify scope/epoch 双维 fail closed。
- 真实 PG：断言 reconcile/external 行、行内投影、conversation_id 回填值。

边界（S4-B）：erase_available 保持 False；不接线 writer/claim/participant。
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from app.composition.agent_transport_backfill import backfill_transport_scope
from tests.conftest import TEST_DB_URL

pytestmark = pytest.mark.asyncio


def _db_url() -> str:
    return TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _connect():
    return await asyncpg.connect(_db_url())


async def _make_tenant(connection) -> uuid.UUID:
    tid = uuid.uuid4()
    await connection.execute(
        "INSERT INTO metaedu.tenants (id, name, school_name, created_at, updated_at) "
        "VALUES ($1, $2, $3, clock_timestamp(), clock_timestamp()) "
        "ON CONFLICT (id) DO NOTHING",
        tid,
        f"tenant-{tid.hex[:12]}",
        "backfill test school",
    )
    return tid


async def _make_conversation(connection, tenant_id) -> uuid.UUID:
    cid = uuid.uuid4()
    # ck_agent_conv_actor：actor_state='present'（默认）要求 created_by 非空。
    await connection.execute(
        "INSERT INTO metaedu.agent_conversations (id, tenant_id, creation_digest, created_by) "
        "VALUES ($1, $2, $3, $4)",
        cid,
        tenant_id,
        "d" * 64,
        uuid.uuid4(),
    )
    return cid


async def _make_message(connection, tenant_id, conversation_id) -> uuid.UUID:
    mid = uuid.uuid4()
    # ck_agent_msg_envelope：用 system_notice 分支（client/requested/turn/origin/
    # output 全 NULL）满足 envelope 约束，避免 user_input 的完整 envelope 要求。
    await connection.execute(
        "INSERT INTO metaedu.agent_messages ("
        "  id, tenant_id, conversation_id, seq, message_kind, author_type, content_digest"
        ") VALUES ($1, $2, $3, 1, 'system_notice', 'system', $4)",
        mid,
        tenant_id,
        conversation_id,
        "e" * 64,
    )
    return mid


async def _make_ws_outbox(
    connection, tenant_id, aggregate_id, *, payload_ref=None
) -> uuid.UUID:
    oid = uuid.uuid4()
    inline = None if payload_ref else "{}"
    await connection.execute(
        "INSERT INTO metaedu.agent_workspace_outbox ("
        "  id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
        "  payload_inline, payload_ref, payload_digest, correlation_id, status, "
        "  attempt_count, next_attempt_at, created_at"
        ") VALUES ($1,$2,'turn.requested.v1',1,$3,'workspace.message',"
        "  $4::jsonb,$5,$6,$7,'pending',0,clock_timestamp(),clock_timestamp())",
        oid,
        tenant_id,
        aggregate_id,
        inline,
        payload_ref,
        "a" * 64,
        uuid.uuid4(),
    )
    return oid


async def _make_exec_inbox(connection, tenant_id, event_id) -> uuid.UUID:
    iid = uuid.uuid4()
    await connection.execute(
        "INSERT INTO metaedu.agent_execution_inbox ("
        "  id, tenant_id, consumer_name, event_id, event_type, schema_version, "
        "  payload_digest, correlation_id, status, created_at"
        ") VALUES ($1,$2,'turn_requested',$3,'turn.requested.v1',1,$4,$5,'consumed',"
        "  clock_timestamp())",
        iid,
        tenant_id,
        event_id,
        "b" * 64,
        uuid.uuid4(),
    )
    return iid


async def _fetch_one(connection, sql, *args):
    return await connection.fetchrow(sql, *args)


# --- 来源矩阵 + epoch + 幂等 -------------------------------------------------


async def test_backfill_ws_outbox_via_message_and_epoch():
    """workspace outbox 经 Message 回填 conversation_id + 登记 epoch_unresolvable。"""
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        msg = await _make_message(connection, tenant, conv)
        outbox = await _make_ws_outbox(connection, tenant, msg)
    finally:
        await connection.close()

    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    report = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()

    assert report.ok, f"backfill 失败: {report.failures} / verify: {report.verify_detail}"
    assert report.scope_backfilled >= 1

    connection = await _connect()
    try:
        row = await _fetch_one(
            connection,
            "SELECT conversation_id, producer_purge_revision FROM "
            "metaedu.agent_workspace_outbox WHERE id = $1",
            outbox,
        )
        assert row["conversation_id"] == conv, "应经 Message 回填 conversation_id"
        assert row["producer_purge_revision"] is None, "历史 epoch 保持 NULL（B3）"
        # epoch_unresolvable 已登记（conversation_scope 类，带 conversation_id）。
        epoch_issue = await _fetch_one(
            connection,
            "SELECT reconcile_class, conversation_id FROM "
            "metaedu.agent_transport_scope_reconcile "
            "WHERE source_table='agent_workspace_outbox' AND source_row_id=$1 "
            "AND issue_code='epoch_unresolvable'",
            outbox,
        )
        assert epoch_issue is not None, "每行须登记 epoch_unresolvable（B3）"
        assert epoch_issue["reconcile_class"] == "conversation_scope"
        assert epoch_issue["conversation_id"] == conv
    finally:
        await connection.close()


async def test_backfill_inbox_via_source_outbox():
    """execution inbox 经源 workspace outbox 回填（先 outbox 后 inbox 顺序）。"""
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        msg = await _make_message(connection, tenant, conv)
        ws_outbox = await _make_ws_outbox(connection, tenant, msg)
        inbox = await _make_exec_inbox(connection, tenant, ws_outbox)
    finally:
        await connection.close()

    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    report = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert report.ok, f"{report.failures} / {report.verify_detail}"

    connection = await _connect()
    try:
        row = await _fetch_one(
            connection,
            "SELECT conversation_id FROM metaedu.agent_execution_inbox WHERE id=$1",
            inbox,
        )
        assert row["conversation_id"] == conv, "inbox 应经源 outbox 回填 scope"
    finally:
        await connection.close()


async def test_backfill_idempotent_no_duplicate_issues():
    """重复执行幂等：不产生重复 reconcile issue / external ref。"""
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        msg = await _make_message(connection, tenant, conv)
        outbox = await _make_ws_outbox(connection, tenant, msg, payload_ref="opaque-1")
    finally:
        await connection.close()

    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    r1 = await backfill_transport_scope(factory, tenant_id=tenant)
    r2 = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert r1.ok and r2.ok

    connection = await _connect()
    try:
        issue_count = await connection.fetchval(
            "SELECT count(*) FROM metaedu.agent_transport_scope_reconcile "
            "WHERE source_row_id=$1 AND issue_code='epoch_unresolvable'",
            outbox,
        )
        assert issue_count == 1, "重跑不得产生重复 epoch_unresolvable"
        ref_count = await connection.fetchval(
            "SELECT count(*) FROM metaedu.agent_external_object_refs "
            "WHERE source_row_id=$1 AND ref_value='opaque-1'",
            outbox,
        )
        assert ref_count == 1, "重跑不得产生重复 external ref"
        # 第二次不应新建 issue（already_present）。
        assert r2.reconcile_issues_registered == 0
    finally:
        await connection.close()


# --- 三态 reconcile + 投影 ---------------------------------------------------


async def test_backfill_source_missing_tenant_scope():
    """源 Message 缺失 -> tenant_scope + source_message_missing，投影 pending。"""
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        phantom_msg = uuid.uuid4()  # 不存在的 Message
        outbox = await _make_ws_outbox(connection, tenant, phantom_msg)
    finally:
        await connection.close()

    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    report = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert report.ok, f"{report.failures} / {report.verify_detail}"

    connection = await _connect()
    try:
        issue = await _fetch_one(
            connection,
            "SELECT reconcile_class, issue_code, conversation_id FROM "
            "metaedu.agent_transport_scope_reconcile "
            "WHERE source_row_id=$1 AND issue_code='source_message_missing'",
            outbox,
        )
        assert issue is not None
        assert issue["reconcile_class"] == "tenant_scope", "scope 未知 -> tenant_scope"
        assert issue["conversation_id"] is None
        # 行内投影：有未 resolved issue -> pending。
        row = await _fetch_one(
            connection,
            "SELECT conversation_id, scope_reconcile_state FROM "
            "metaedu.agent_workspace_outbox WHERE id=$1",
            outbox,
        )
        assert row["conversation_id"] is None, "scope 未知不回填"
        assert row["scope_reconcile_state"] == "pending"
    finally:
        await connection.close()


async def test_backfill_orphan_conversation_deleted():
    """Conversation 已物理删除 -> orphan + conversation_deleted_orphan，投影 orphan。

    源 Message 仍存在（带 conversation_id），但该 Conversation 已不在
    agent_conversations。messages.conversation_id 有到 conversations 的 FK
    （NO ACTION），无法直接删「仍被 message 引用」的 conversation；故用
    ``session_replication_role = replica`` 在单事务内绕过触发器/FK 检查造出
    「message 指向已删 conversation」的孤儿形态（仅测试造数，不改生产路径）。
    """
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        orphan_conv = uuid.uuid4()
        # 单事务：replica 角色禁用 FK 触发器 -> 造 message 指向不存在 conversation。
        async with connection.transaction():
            await connection.execute("SET LOCAL session_replication_role = replica")
            msg = await _make_message(connection, tenant, orphan_conv)
        outbox = await _make_ws_outbox(connection, tenant, msg)
    finally:
        await connection.close()

    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    report = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert report.ok, f"{report.failures} / {report.verify_detail}"

    connection = await _connect()
    try:
        issue = await _fetch_one(
            connection,
            "SELECT reconcile_class, issue_code FROM "
            "metaedu.agent_transport_scope_reconcile "
            "WHERE source_row_id=$1 AND issue_code='conversation_deleted_orphan'",
            outbox,
        )
        assert issue is not None
        assert issue["reconcile_class"] == "orphan"
        row = await _fetch_one(
            connection,
            "SELECT scope_reconcile_state FROM metaedu.agent_workspace_outbox WHERE id=$1",
            outbox,
        )
        assert row["scope_reconcile_state"] == "orphan", "orphan 投影最高优先级"
        # 清理孤儿 message（避免污染后续测试，跨 tenant 隔离故影响有限）。
        await connection.execute(
            "DELETE FROM metaedu.agent_messages WHERE id = $1", msg
        )
    finally:
        await connection.close()


async def test_backfill_cross_tenant_not_mapped():
    """跨 tenant：源 Message 属另一 tenant -> cross_tenant_mismatch，不映射。"""
    connection = await _connect()
    try:
        tenant_a = await _make_tenant(connection)
        tenant_b = await _make_tenant(connection)
        conv_b = await _make_conversation(connection, tenant_b)
        msg_b = await _make_message(connection, tenant_b, conv_b)
        # tenant_a 的 outbox 引用 tenant_b 的 message。
        outbox = await _make_ws_outbox(connection, tenant_a, msg_b)
    finally:
        await connection.close()

    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    report = await backfill_transport_scope(factory, tenant_id=tenant_a)
    await engine.dispose()
    assert report.ok, f"{report.failures} / {report.verify_detail}"

    connection = await _connect()
    try:
        issue = await _fetch_one(
            connection,
            "SELECT reconcile_class, issue_code FROM "
            "metaedu.agent_transport_scope_reconcile "
            "WHERE source_row_id=$1 AND issue_code='cross_tenant_mismatch'",
            outbox,
        )
        assert issue is not None, "跨 tenant 须登记 cross_tenant_mismatch"
        assert issue["reconcile_class"] == "tenant_scope"
        row = await _fetch_one(
            connection,
            "SELECT conversation_id FROM metaedu.agent_workspace_outbox WHERE id=$1",
            outbox,
        )
        assert row["conversation_id"] is None, "跨 tenant 不映射 scope"
    finally:
        await connection.close()


# --- external ledger（B5）----------------------------------------------------


async def test_backfill_external_ref_unknown_blocked():
    """outbox 非空 payload_ref -> external ledger unknown + blocked(unknown_scheme)。"""
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        msg = await _make_message(connection, tenant, conv)
        outbox = await _make_ws_outbox(
            connection, tenant, msg, payload_ref="some-opaque-ref"
        )
    finally:
        await connection.close()

    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    report = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert report.ok, f"{report.failures} / {report.verify_detail}"
    assert report.external_refs_registered >= 1

    connection = await _connect()
    try:
        ref = await _fetch_one(
            connection,
            "SELECT ref_scheme, erase_state, blocked_reason, conversation_id FROM "
            "metaedu.agent_external_object_refs WHERE source_row_id=$1",
            outbox,
        )
        assert ref is not None
        assert ref["ref_scheme"] == "unknown", "无可证明 DB-local 格式 -> unknown"
        assert ref["erase_state"] == "blocked"
        assert ref["blocked_reason"] == "unknown_scheme"
        assert ref["conversation_id"] == conv, "溯源 conversation_id"
    finally:
        await connection.close()


# --- verify 双维 fail closed -------------------------------------------------


async def test_verify_fails_when_null_epoch_unregistered():
    """verify epoch 维 fail closed：删 epoch issue 后 verify 检出；point-in-time 重扫边界。

    backfill 只扫 ``conversation_id IS NULL`` 行；已回填 scope 的行不会被 point-in-time
    重扫补登 epoch issue（S1 已记录的随机 UUID point-in-time 局限，由 S4-C catch-up
    全量重扫补偿）。本测试直接验证 ``_verify_scope_epoch`` 对该缺陷 fail closed。
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    from app.composition.agent_transport_backfill import _verify_scope_epoch

    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        msg = await _make_message(connection, tenant, conv)
        outbox = await _make_ws_outbox(connection, tenant, msg)
    finally:
        await connection.close()

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    r1 = await backfill_transport_scope(factory, tenant_id=tenant)
    assert r1.ok, f"首轮 backfill 应 ok: {r1.failures} / {r1.verify_detail}"
    # 删除 epoch issue 制造「NULL-epoch 无登记」缺陷。
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "DELETE FROM metaedu.agent_transport_scope_reconcile "
                "WHERE source_row_id = :sr AND issue_code = 'epoch_unresolvable'"
            ),
            {"sr": outbox},
        )
    # verify 必须 fail closed（epoch 维检出）。
    verify_ok, detail = await _verify_scope_epoch(factory, tenant_id=tenant)
    await engine.dispose()
    assert not verify_ok, "NULL-epoch 无 epoch_unresolvable 时 verify 必须 fail closed"
    assert "epoch_unresolvable" in detail
