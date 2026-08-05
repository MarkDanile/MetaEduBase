"""R1-S4-B M4：并发集合锁 / 中断恢复 / execution outbox via Run / 全 ref-bearing source。

覆盖（Plan §R1-S4 B2/B4/B5/B7）：
- 并发集合锁：同一源行并发 backfill 不产生重复 issue（advisory lock 串行化 +
  ON CONFLICT 兜底）。
- execution outbox 经 Run 回填 conversation_id（aggregate_id=runs.id ->
  run.conversation_id）。
- RunEvent 全 ref-bearing source：非空 payload_ref 登记 external ledger
  unknown+blocked；payload_ref 为 NULL 的行不登记。
- 中断恢复：max_rows 截断后从 tenant 起点幂等重跑收敛（不丢行）。
- 重复执行幂等（并发 + 串行重跑均不产生重复）。

边界（S4-B）：erase_available 保持 False；不接线 writer/claim/participant。
"""

from __future__ import annotations

import asyncio
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


def _factory():
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _make_tenant(connection) -> uuid.UUID:
    tid = uuid.uuid4()
    await connection.execute(
        "INSERT INTO metaedu.tenants (id, name, school_name, created_at, updated_at) "
        "VALUES ($1, $2, $3, clock_timestamp(), clock_timestamp())",
        tid,
        f"tenant-{tid.hex[:12]}",
        "m4 school",
    )
    return tid


async def _make_conversation(connection, tenant_id) -> uuid.UUID:
    cid = uuid.uuid4()
    await connection.execute(
        "INSERT INTO metaedu.agent_conversations (id, tenant_id, creation_digest, created_by) "
        "VALUES ($1, $2, $3, $4)",
        cid,
        tenant_id,
        "d" * 64,
        uuid.uuid4(),
    )
    return cid


async def _make_run(connection, tenant_id, conversation_id, *, queue_seq=1) -> uuid.UUID:
    """最小 Run。默认 status='queued'/output_publish_state='not_required' 走
    ck_agent_run_terminal_output 第三分支（terminal 全 NULL）；默认
    actor_state='present' 走 ck_agent_runs_actor 第一分支（created_by 非空）。
    replica 角色绕 FK。uq_agent_run_queue_seq 唯一 (tenant, conversation,
    queue_seq)，同 conv 多 run 需递增 queue_seq。"""
    rid = uuid.uuid4()
    async with connection.transaction():
        await connection.execute("SET LOCAL session_replication_role = replica")
        await connection.execute(
            "INSERT INTO metaedu.agent_runs ("
            "  id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
            "  agent_definition_version_id, runtime_profile_id, creation_digest, "
            "  correlation_id, runtime_capability_snapshot, run_config_snapshot, "
            "  budget_snapshot, usage_summary, created_by"
            ") VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'{}'::jsonb,'{}'::jsonb,'{}'::jsonb,"
            "  '{}'::jsonb,$10)",
            rid,
            tenant_id,
            conversation_id,
            queue_seq,
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            "c" * 64,
            uuid.uuid4(),
            uuid.uuid4(),  # created_by（ck_agent_runs_actor present 分支）
        )
    return rid


async def _make_exec_outbox(
    connection, tenant_id, run_id, *, payload_ref=None
) -> uuid.UUID:
    oid = uuid.uuid4()
    inline = None if payload_ref else "{}"
    await connection.execute(
        "INSERT INTO metaedu.agent_execution_outbox ("
        "  id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
        "  payload_inline, payload_ref, payload_digest, correlation_id, status, "
        "  attempt_count, next_attempt_at, created_at"
        ") VALUES ($1,$2,'assistant_message.publish_requested.v1',1,$3,'execution.run',"
        "  $4::jsonb,$5,$6,$7,'pending',0,clock_timestamp(),clock_timestamp())",
        oid,
        tenant_id,
        run_id,
        inline,
        payload_ref,
        "a" * 64,
        uuid.uuid4(),
    )
    return oid


async def _make_run_event(
    connection, tenant_id, conversation_id, run_id, *, seq, payload_ref=None
) -> uuid.UUID:
    """RunEvent：payload_ref 非空 -> 'external'；为 NULL -> 'redacted'（inline 均 NULL）。"""
    eid = uuid.uuid4()
    state = "external" if payload_ref else "redacted"
    async with connection.transaction():
        await connection.execute("SET LOCAL session_replication_role = replica")
        await connection.execute(
            "INSERT INTO metaedu.agent_run_events ("
            "  id, tenant_id, conversation_id, run_id, seq, event_type, schema_version, "
            "  occurred_at, persisted_at, visibility, classification, payload_inline, "
            "  payload_ref, payload_state, payload_digest, payload_size, media_type, "
            "  correlation_id"
            ") VALUES ($1,$2,$3,$4,$5,'run.step',1,clock_timestamp(),clock_timestamp(),"
            "  'internal','internal',NULL,$6,$7,$8,0,'application/json',$9)",
            eid,
            tenant_id,
            conversation_id,
            run_id,
            seq,
            payload_ref,
            state,
            "f" * 64,
            uuid.uuid4(),
        )
    return eid


# --- execution outbox via Run + RunEvent 全 ref-bearing source ----------------


async def test_backfill_exec_outbox_via_run_and_run_event_ref():
    """execution outbox 经 Run 回填 scope；RunEvent 非空 payload_ref 登记 external ledger。"""
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        run = await _make_run(connection, tenant, conv)
        exec_outbox = await _make_exec_outbox(connection, tenant, run)
        event_with_ref = await _make_run_event(
            connection, tenant, conv, run, seq=1, payload_ref="opaque-event-ref"
        )
        event_no_ref = await _make_run_event(connection, tenant, conv, run, seq=2)
    finally:
        await connection.close()

    engine, factory = _factory()
    report = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert report.ok, f"{report.failures} / {report.verify_detail}"

    connection = await _connect()
    try:
        # execution outbox 经 Run 回填 conversation_id。
        row = await connection.fetchrow(
            "SELECT conversation_id FROM metaedu.agent_execution_outbox WHERE id=$1",
            exec_outbox,
        )
        assert row["conversation_id"] == conv, "exec outbox 应经 Run 回填 scope"
        # RunEvent 带 ref -> external ledger unknown+blocked。
        ref = await connection.fetchrow(
            "SELECT ref_scheme, erase_state, blocked_reason, source_table FROM "
            "metaedu.agent_external_object_refs WHERE source_row_id=$1",
            event_with_ref,
        )
        assert ref is not None, "RunEvent 非空 payload_ref 须登记 external ledger"
        assert ref["ref_scheme"] == "unknown"
        assert ref["erase_state"] == "blocked"
        assert ref["blocked_reason"] == "unknown_scheme"
        assert ref["source_table"] == "agent_run_events"
        # RunEvent 无 ref -> 不登记。
        no_ref = await connection.fetchval(
            "SELECT count(*) FROM metaedu.agent_external_object_refs WHERE source_row_id=$1",
            event_no_ref,
        )
        assert no_ref == 0, "payload_ref 为 NULL 的 RunEvent 不得登记 external ledger"
    finally:
        await connection.close()


# --- 并发集合锁（同一源行并发 backfill 不产生重复 issue）----------------------


async def test_concurrent_backfill_same_tenant_no_duplicate_issues():
    """并发 backfill 同一 tenant：advisory lock 串行化 + ON CONFLICT 兜底，无重复 issue。"""
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        # 造多行混合场景（部分可回填、部分源缺失）。uq_agent_exec_outbox_publish
        # 唯一 (tenant_id, aggregate_id)，每 run 一条 outbox，故每行一个 run。
        conv = await _make_conversation(connection, tenant)
        outboxes = []
        for i in range(3):
            run = await _make_run(connection, tenant, conv, queue_seq=i + 1)
            outboxes.append(
                await _make_exec_outbox(
                    connection, tenant, run, payload_ref=f"concurrent-ref-{i}"
                )
            )
        # 源缺失行（指向不存在的 run）。
        phantom = await _make_exec_outbox(connection, tenant, uuid.uuid4())
    finally:
        await connection.close()

    engine, factory = _factory()
    # 两个并发 backfill 同一 tenant。
    r1, r2 = await asyncio.gather(
        backfill_transport_scope(factory, tenant_id=tenant),
        backfill_transport_scope(factory, tenant_id=tenant),
    )
    await engine.dispose()

    connection = await _connect()
    try:
        for oid in outboxes + [phantom]:
            n = await connection.fetchval(
                "SELECT count(*) FROM metaedu.agent_transport_scope_reconcile "
                "WHERE source_row_id=$1 AND issue_code='epoch_unresolvable'",
                oid,
            )
            assert n == 1, f"并发执行不得产生重复 epoch issue（{oid} 实际 {n}）"
        # 每个源行 scope 类 issue 至多一条。
        dup = await connection.fetchval(
            "SELECT count(*) FROM ("
            "  SELECT source_row_id, issue_code, count(*) c "
            "  FROM metaedu.agent_transport_scope_reconcile "
            "  WHERE tenant_id=$1 GROUP BY source_row_id, issue_code HAVING count(*)>1) x",
            tenant,
        )
        assert dup == 0, "并发执行不得产生重复 (source_row, issue_code)"
        # external ref 在并发下不重复（唯一键 + ON CONFLICT 兜底，与锁无关）。
        ref_dup = await connection.fetchval(
            "SELECT count(*) FROM ("
            "  SELECT source_table, source_row_id, ref_value, count(*) c "
            "  FROM metaedu.agent_external_object_refs "
            "  WHERE tenant_id=$1 GROUP BY source_table, source_row_id, ref_value "
            "  HAVING count(*)>1) x",
            tenant,
        )
        assert ref_dup == 0, "并发执行不得产生重复 external ref"
    finally:
        await connection.close()
    assert r1.ok or r2.ok, "至少一次并发 backfill 应完整成功"


# --- 中断恢复（max_rows 截断后从 tenant 起点幂等重跑收敛）---------------------


async def test_interrupted_backfill_resumes_idempotently():
    """max_rows 截断后，从 tenant 起点（不带游标）幂等重跑收敛全部行。"""
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        # uq_agent_exec_outbox_publish 唯一 (tenant_id, aggregate_id)，每 run 一条。
        outboxes = []
        for i in range(4):
            run = await _make_run(connection, tenant, conv, queue_seq=i + 1)
            outboxes.append(await _make_exec_outbox(connection, tenant, run))
    finally:
        await connection.close()

    engine, factory = _factory()
    # 第一次：max_rows=2 截断（模拟中断）。
    r1 = await backfill_transport_scope(factory, tenant_id=tenant, max_rows=2)
    assert not r1.completed, "截断后应未完成"
    # 从 tenant 起点幂等重跑（唯一可靠恢复路径，S1 契约）。
    r2 = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert r2.ok, f"{r2.failures} / {r2.verify_detail}"

    connection = await _connect()
    try:
        for oid in outboxes:
            row = await connection.fetchrow(
                "SELECT conversation_id FROM metaedu.agent_execution_outbox WHERE id=$1",
                oid,
            )
            assert row["conversation_id"] == conv, "重跑后全部行应回填 scope"
            n = await connection.fetchval(
                "SELECT count(*) FROM metaedu.agent_transport_scope_reconcile "
                "WHERE source_row_id=$1 AND issue_code='epoch_unresolvable'",
                oid,
            )
            assert n == 1, "重跑不得产生重复 epoch issue"
    finally:
        await connection.close()


# --- 复核修复回归测试（P1-1 / P1-2 / P2-2 / P2-3）----------------------------


async def _make_message(connection, tenant_id, conversation_id) -> uuid.UUID:
    """最小 agent_messages 行（ws outbox 的 scope 源：aggregate_id=messages.id）。

    仅填 NOT NULL 列（id/tenant/conversation/seq/message_kind/author_type/
    content_state/content_digest/body_state），replica 角色绕 FK。
    """
    mid = uuid.uuid4()
    async with connection.transaction():
        await connection.execute("SET LOCAL session_replication_role = replica")
        # message_kind='system_notice'（envelope 最简分支：origin_run_id/output_ordinal
        # 均 NULL）；content_state='visible' + body_state='present' 满足 content/body CHECK。
        await connection.execute(
            "INSERT INTO metaedu.agent_messages ("
            "  id, tenant_id, conversation_id, seq, message_kind, author_type, "
            "  content_state, content_digest, body_state, created_at"
            ") VALUES ($1,$2,$3,1,'system_notice','system',"
            "  'visible',$4,'present',clock_timestamp())",
            mid,
            tenant_id,
            conversation_id,
            "c" * 64,
        )
    return mid


async def _make_ws_outbox_with_scope_and_ref(
    connection, tenant_id, message_id, conversation_id, *, payload_ref
) -> uuid.UUID:
    """造一条**已带 scope**（conversation_id 非空）且带 payload_ref 的 ws outbox。

    P1-1 场景：旧 backfill 只扫 ``conversation_id IS NULL``，此类行从不被扫描，
    其 payload_ref 静默漏登记 external ledger。
    """
    oid = uuid.uuid4()
    await connection.execute(
        "INSERT INTO metaedu.agent_workspace_outbox ("
        "  id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
        "  payload_inline, payload_ref, payload_digest, correlation_id, status, "
        "  attempt_count, next_attempt_at, created_at, conversation_id"
        ") VALUES ($1,$2,'turn.requested.v1',1,$3,'workspace.message',"
        "  NULL::jsonb,$4,$5,$6,'pending',0,clock_timestamp(),clock_timestamp(),$7)",
        oid,
        tenant_id,
        message_id,
        payload_ref,
        "a" * 64,
        uuid.uuid4(),
        conversation_id,
    )
    return oid


async def test_p11_scoped_outbox_with_ref_registers_external_ref():
    """P1-1：已带 scope 的 ref-bearing outbox 行也须登记 external ledger（不漏）。"""
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        msg = await _make_message(connection, tenant, conv)
        scoped_ref_outbox = await _make_ws_outbox_with_scope_and_ref(
            connection, tenant, msg, conv, payload_ref="scoped-ref-1"
        )
    finally:
        await connection.close()

    engine, factory = _factory()
    report = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert report.ok, f"{report.failures} / {report.verify_detail}"

    connection = await _connect()
    try:
        ref = await connection.fetchrow(
            "SELECT ref_scheme, erase_state, source_table FROM "
            "metaedu.agent_external_object_refs WHERE source_row_id=$1",
            scoped_ref_outbox,
        )
        assert ref is not None, "已带 scope 的 ref-bearing outbox 须登记 external ledger"
        assert ref["source_table"] == "agent_workspace_outbox"
        assert ref["erase_state"] == "blocked"
        # 该行已带 scope，不得重复登记 epoch_unresolvable（epoch 已是历史 NULL 才登记；
        # 此处 producer_purge_revision 默认 NULL，会登记一条——但 scope 类 issue 不得有）。
        scope_issues = await connection.fetchval(
            "SELECT count(*) FROM metaedu.agent_transport_scope_reconcile "
            "WHERE source_row_id=$1 AND issue_code IN ("
            "  'source_message_missing','source_run_missing','source_outbox_missing',"
            "  'cross_tenant_mismatch','ambiguous_mapping','conversation_deleted_orphan')",
            scoped_ref_outbox,
        )
        assert scope_issues == 0, "已带 scope 行不得登记 scope 类 issue"
    finally:
        await connection.close()


async def test_p11_verify_catches_unregistered_run_event_ref():
    """P1-1 verify 第三维：ref-bearing 行漏登记 external ledger 时 verify_failed=True。"""
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        run = await _make_run(connection, tenant, conv)
        # 造一条 ref-bearing RunEvent，但**不**让 backfill 登记（直接 verify）。
        await _make_run_event(
            connection, tenant, conv, run, seq=1, payload_ref="unregistered-ref"
        )
    finally:
        await connection.close()

    # 直接调 verify（不跑 backfill）：ref 未登记 -> external 维 fail closed。
    engine, factory = _factory()
    from app.composition.agent_transport_backfill import _verify_scope_epoch

    verify_ok, detail = await _verify_scope_epoch(factory, tenant_id=tenant)
    await engine.dispose()
    assert not verify_ok, "ref-bearing RunEvent 漏登记 external ledger 时 verify 应 fail"
    assert "agent_run_events" in detail and "external ref" in detail


async def test_p23_completed_false_at_exact_batch_boundary():
    """P2-3：max_rows 恰好等于待处理行数但仍有后续表/行时，completed 不得误报 True。"""
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        # 造 2 条 exec outbox（待回填 scope），加 1 条 ref-bearing RunEvent。
        for i in range(2):
            run = await _make_run(connection, tenant, conv, queue_seq=i + 1)
            await _make_exec_outbox(connection, tenant, run)
        await _make_run_event(
            connection, tenant, conv, run, seq=1, payload_ref="boundary-ref"
        )
    finally:
        await connection.close()

    engine, factory = _factory()
    # max_rows=2 恰好覆盖 2 条 outbox，但还剩 RunEvent 未处理 -> completed 必须 False。
    r = await backfill_transport_scope(factory, tenant_id=tenant, max_rows=2)
    await engine.dispose()
    assert not r.completed, (
        "max_rows 命中边界且仍有 RunEvent 未处理时 completed 不得误报 True"
    )


async def test_p22_projection_is_owner_scoped():
    """P2-2：投影按 owner 聚合——其它 owner 对同一 source row 的 issue 不影响本 owner 投影。"""
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        await _make_conversation(connection, tenant)
        # 一条源缺失的 exec outbox（run 指向不存在 -> source_run_missing issue，投影 pending）。
        orphan_outbox = await _make_exec_outbox(connection, tenant, uuid.uuid4())
    finally:
        await connection.close()

    engine, factory = _factory()
    report = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert report.ok, f"{report.failures} / {report.verify_detail}"

    connection = await _connect()
    try:
        # 本 owner（execution.transport.v1）有 source_run_missing + epoch issue -> 投影 pending。
        state = await connection.fetchval(
            "SELECT scope_reconcile_state FROM metaedu.agent_execution_outbox WHERE id=$1",
            orphan_outbox,
        )
        assert state == "pending", f"本 owner 有未决 issue 时投影应为 pending（实际 {state}）"
        # 手工把本 owner 的 issue 全标 resolved，再塞一条**其它 owner** 的 open issue，
        # 重算投影应得 'reconciled'（不被其它 owner 的 open issue 拉成 pending）。
        await connection.execute(
            "UPDATE metaedu.agent_transport_scope_reconcile SET state='resolved', "
            "resolution_digest=$2, resolved_at=clock_timestamp() "
            "WHERE source_row_id=$1 AND owner_key='execution.transport.v1'",
            orphan_outbox,
            "e" * 64,
        )
        await connection.execute(
            "INSERT INTO metaedu.agent_transport_scope_reconcile ("
            "  id, tenant_id, owner_key, source_table, source_row_id, "
            "  reconcile_class, issue_code, state, revision, created_at"
            ") VALUES ($1,$2,'external.payload.v1','agent_execution_outbox',$3,"
            "  'tenant_scope','ambiguous_mapping','open',1,clock_timestamp())",
            uuid.uuid4(),
            tenant,
            orphan_outbox,
        )
    finally:
        await connection.close()

    # 触发投影重算（本 owner 无 NULL-scope/epoch 行，但投影按本 owner issue 集）。
    engine, factory = _factory()
    from app.composition.agent_transport_backfill import _recompute_projection

    async with factory() as session, session.begin():
        await _recompute_projection(
            session,
            table="agent_execution_outbox",
            tenant_id=tenant,
            owner_key="execution.transport.v1",
            source_row_id=orphan_outbox,
        )
    await engine.dispose()

    connection = await _connect()
    try:
        state = await connection.fetchval(
            "SELECT scope_reconcile_state FROM metaedu.agent_execution_outbox WHERE id=$1",
            orphan_outbox,
        )
        assert state == "reconciled", (
            f"投影应按本 owner issue 集聚合（本 owner 全 resolved -> reconciled，"
            f"不受 external.payload.v1 的 open issue 影响），实际 {state}"
        )
    finally:
        await connection.close()
