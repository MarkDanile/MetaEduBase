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


# --- 第二轮独立复核回归测试（#2 ref_value / #3 多表重扫 / #4 冲突 / #5 投影 / #6 mismatch）-


async def _make_ws_outbox_null_scope(connection, tenant_id, message_id) -> uuid.UUID:
    """造一条 NULL-scope 的 ws outbox（aggregate_id=message_id，待 backfill 回填）。"""
    oid = uuid.uuid4()
    await connection.execute(
        "INSERT INTO metaedu.agent_workspace_outbox ("
        "  id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
        "  payload_inline, payload_ref, payload_digest, correlation_id, status, "
        "  attempt_count, next_attempt_at, created_at"
        ") VALUES ($1,$2,'turn.requested.v1',1,$3,'workspace.message',"
        "  '{}'::jsonb,NULL,$4,$5,'pending',0,clock_timestamp(),clock_timestamp())",
        oid,
        tenant_id,
        message_id,
        "a" * 64,
        uuid.uuid4(),
    )
    return oid


async def _make_ws_outbox_mismatch_type(
    connection, tenant_id, *, payload_ref=None
) -> uuid.UUID:
    """造一条 (event_type, aggregate_type) 不在 B2 矩阵的 ws outbox（复核 #6）。

    event_type='future.event.v1'、aggregate_type='future.aggregate'，aggregate_id 随机。
    B2 无此类型映射，backfill 须路由到 ambiguous（不盲 join aggregate_id）。
    """
    oid = uuid.uuid4()
    inline = None if payload_ref else "{}"
    await connection.execute(
        "INSERT INTO metaedu.agent_workspace_outbox ("
        "  id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
        "  payload_inline, payload_ref, payload_digest, correlation_id, status, "
        "  attempt_count, next_attempt_at, created_at"
        ") VALUES ($1,$2,'future.event.v1',1,$3,'future.aggregate',"
        "  $4::jsonb,$5,$6,$7,'pending',0,clock_timestamp(),clock_timestamp())",
        oid,
        tenant_id,
        uuid.uuid4(),  # aggregate_id 随机（不指向真实 Message）
        inline,
        payload_ref,
        "a" * 64,
        uuid.uuid4(),
    )
    return oid


async def test_p2_ref_value_mismatch_reregisters():
    """复核 #2：external ref 按 (source_row, ref_value) 唯一，旧 ref_value 不算数。

    反例：旧 NOT EXISTS 只匹配 (source_row_id)，source_row 上有任意 ref_value 登记即跳过
    -> payload_ref 对应的新 ref 静默漏登记，verify 也误报 ok。新实现：NOT EXISTS 额外匹配
    ``er.ref_value = t.payload_ref``，当前 ref 须登记。
    """
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        msg = await _make_message(connection, tenant, conv)
        oid = await _make_ws_outbox_with_scope_and_ref(
            connection, tenant, msg, conv, payload_ref="ref-A"
        )
        # 手工塞一条**不同 ref_value** 的 external ledger 行（模拟旧 ref 残留）。
        await connection.execute(
            "INSERT INTO metaedu.agent_external_object_refs ("
            "  id, tenant_id, conversation_id, owner_key, ref_scheme, ref_value, "
            "  source_table, source_row_id, erase_state, blocked_reason, "
            "  created_at, updated_at"
            ") VALUES ($1,$2,$3,'external.payload.v1','unknown','stale-ref-X',"
            "  'agent_workspace_outbox',$4,'blocked','unknown_scheme',"
            "  clock_timestamp(),clock_timestamp())",
            uuid.uuid4(),
            tenant,
            conv,
            oid,
        )
    finally:
        await connection.close()

    engine, factory = _factory()
    report = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert report.ok, f"{report.failures} / {report.verify_detail}"

    connection = await _connect()
    try:
        n = await connection.fetchval(
            "SELECT count(*) FROM metaedu.agent_external_object_refs "
            "WHERE source_row_id=$1 AND ref_value='ref-A'",
            oid,
        )
        assert n == 1, "payload_ref='ref-A' 须按当前 ref_value 登记一条"
        # 旧 ref_value 不被删除（expand-only，仅补登新 ref）。
        stale = await connection.fetchval(
            "SELECT count(*) FROM metaedu.agent_external_object_refs "
            "WHERE source_row_id=$1 AND ref_value='stale-ref-X'",
            oid,
        )
        assert stale == 1, "旧 ref_value 不被删除（仅补登新 ref）"
    finally:
        await connection.close()


async def test_p3_multitable_rescan_converges():
    """复核 #3：max_rows 跨多表截断，从 tenant 起点重扫收敛 ws+exec outbox 全部行。

    反例：旧跨调用/跨表游标复用会跳过后续表的行。新实现：每表独立进程内游标，跨调用
    从 tenant 起点全量幂等重扫，已填行幂等跳过。
    """
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        msg = await _make_message(connection, tenant, conv)
        ws_oid = await _make_ws_outbox_null_scope(connection, tenant, msg)
        exec_oids = []
        for i in range(2):
            run = await _make_run(connection, tenant, conv, queue_seq=i + 1)
            exec_oids.append(await _make_exec_outbox(connection, tenant, run))
    finally:
        await connection.close()

    engine, factory = _factory()
    r1 = await backfill_transport_scope(factory, tenant_id=tenant, max_rows=1)
    assert not r1.completed, "max_rows=1 截断后应未完成"
    r2 = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert r2.ok, f"{r2.failures} / {r2.verify_detail}"

    connection = await _connect()
    try:
        ws_scope = await connection.fetchval(
            "SELECT conversation_id FROM metaedu.agent_workspace_outbox WHERE id=$1",
            ws_oid,
        )
        assert ws_scope == conv, "重扫后 ws outbox 应回填 scope"
        for oid in exec_oids:
            s = await connection.fetchval(
                "SELECT conversation_id FROM metaedu.agent_execution_outbox WHERE id=$1",
                oid,
            )
            assert s == conv, "重扫后 exec outbox 应回填 scope"
    finally:
        await connection.close()


async def test_p4_scope_conflict_registers_ambiguous_mapping():
    """复核 #4：行已带 scope=A、源解析值=B（A≠B）时登记 conversation_scope/ambiguous_mapping。

    反例：旧 UPDATE ... WHERE conversation_id IS NULL 命中 0 行 -> 计 scope_already_present，
    冲突静默接受。新实现：检测 A≠B，登记 ambiguous_mapping（带**解析值 B**--B 无物理 FK
    保护，ledger gate 须指向 B 才能在 purge B 前 fail closed），不覆盖行内 A。
    """
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv_a = await _make_conversation(connection, tenant)
        conv_b = await _make_conversation(connection, tenant)
        msg_b = await _make_message(connection, tenant, conv_b)
        # aggregate_id=msg_b（源解析->conv_b），行内 conversation_id=conv_a（A≠B）。
        oid = await _make_ws_outbox_with_scope_and_ref(
            connection, tenant, msg_b, conv_a, payload_ref="conflict-ref"
        )
    finally:
        await connection.close()

    engine, factory = _factory()
    report = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert report.ok, f"{report.failures} / {report.verify_detail}"

    connection = await _connect()
    try:
        issue = await connection.fetchrow(
            "SELECT reconcile_class, issue_code, conversation_id FROM "
            "metaedu.agent_transport_scope_reconcile "
            "WHERE source_row_id=$1 AND issue_code='ambiguous_mapping'",
            oid,
        )
        assert issue is not None, "A≠B 冲突须登记 ambiguous_mapping"
        assert issue["reconcile_class"] == "conversation_scope"
        assert issue["conversation_id"] == conv_b, (
            "ambiguous_mapping 须带解析值 B（B 无 FK 保护，ledger gate 须指向 B）"
        )
        scope = await connection.fetchval(
            "SELECT conversation_id FROM metaedu.agent_workspace_outbox WHERE id=$1",
            oid,
        )
        assert scope == conv_a, "冲突时不得覆盖行内既有 scope（fail closed，不猜）"
    finally:
        await connection.close()


async def test_p5_zero_issue_row_projection_stays_null():
    """复核 #5 连带：零 issue 的干净行投影保持 NULL（不误盖 'reconciled'）。

    反例：``_recompute_projection`` 与第四维 verify 的 ``CASE WHEN bool_or(...) ... ELSE
    'reconciled'`` 无 GROUP BY，空集 bool_or=NULL -> ELSE 'reconciled'，零 issue 行被误盖
    'reconciled'；第四维 verify 期望 NULL、行内 'reconciled' -> 漂移 fail。修复：加
    ``WHEN count(*) = 0 THEN NULL``。本测试造一条已带 scope+epoch（不扫描、零 issue）的干净
    行，verify 须通过（无漂移）。
    """
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        conv = await _make_conversation(connection, tenant)
        msg = await _make_message(connection, tenant, conv)
        oid = uuid.uuid4()
        # 已带 scope（conv）+ epoch（0），无 ref -> 不被扫描、零 issue 的干净行。
        await connection.execute(
            "INSERT INTO metaedu.agent_workspace_outbox ("
            "  id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
            "  payload_inline, payload_ref, payload_digest, correlation_id, status, "
            "  attempt_count, next_attempt_at, created_at, conversation_id, "
            "  producer_purge_revision"
            ") VALUES ($1,$2,'turn.requested.v1',1,$3,'workspace.message',"
            "  '{}'::jsonb,NULL,$4,$5,'pending',0,clock_timestamp(),clock_timestamp(),$6,0)",
            oid,
            tenant,
            msg,
            "a" * 64,
            uuid.uuid4(),
            conv,
        )
    finally:
        await connection.close()

    engine, factory = _factory()
    report = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    # 干净行零 issue：第四维 verify 期望投影 NULL、行内 NULL -> 不漂移 -> ok。
    # （未修空集 bug 时：期望 'reconciled'、行内 NULL -> 漂移 -> verify_failed=True。）
    assert report.ok, f"零 issue 干净行不应触发投影漂移：{report.verify_detail}"
    connection = await _connect()
    try:
        state = await connection.fetchval(
            "SELECT scope_reconcile_state FROM metaedu.agent_workspace_outbox WHERE id=$1",
            oid,
        )
        assert state is None, f"零 issue 干净行投影应保持 NULL（实际 {state}）"
    finally:
        await connection.close()


async def test_p5_projection_ledger_drift_verify_fails():
    """复核 #5：行内 scope_reconcile_state 与 ledger issue 集漂移时 verify fail closed。

    反例：旧 verify 无投影一致性维，行内标 'reconciled' 但 ledger 有 open issue 静默通过。
    新实现：第四维 LATERAL 重算期望投影，与行内值不一致即 fail closed。
    """
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        # 源缺失 exec outbox -> backfill 登记 source_run_missing + epoch_unresolvable ->
        # 投影 'pending'。
        oid = await _make_exec_outbox(connection, tenant, uuid.uuid4())
    finally:
        await connection.close()

    engine, factory = _factory()
    await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()

    connection = await _connect()
    try:
        # 篡改行内投影为 'reconciled'（与 ledger open issue 集漂移）。
        await connection.execute(
            "UPDATE metaedu.agent_execution_outbox SET scope_reconcile_state='reconciled' "
            "WHERE id=$1",
            oid,
        )
    finally:
        await connection.close()

    engine, factory = _factory()
    from app.composition.agent_transport_backfill import _verify_scope_epoch

    verify_ok, detail = await _verify_scope_epoch(factory, tenant_id=tenant)
    await engine.dispose()
    assert not verify_ok, "投影与 ledger 漂移时 verify 应 fail closed"
    assert "agent_execution_outbox" in detail and "投影" in detail


async def test_p6_mismatch_type_row_routed_to_ambiguous():
    """复核 #6：非 B2 类型的 outbox 行路由到 ambiguous，登记 tenant_scope/ambiguous_mapping。

    反例：旧实现按表名盲 join aggregate_id->agent_messages，aggregate_id 碰巧指向某 Message
    会错配 scope；或被 type_filter 跳过 -> B7:817 NULL-scope 无 issue -> verify fail。新实现：
    不盲 join、登记 ambiguous_mapping（conversation_id=NULL，tenant_scope），verify 通过。
    """
    connection = await _connect()
    try:
        tenant = await _make_tenant(connection)
        await _make_conversation(connection, tenant)
        mismatch = await _make_ws_outbox_mismatch_type(connection, tenant)
    finally:
        await connection.close()

    engine, factory = _factory()
    report = await backfill_transport_scope(factory, tenant_id=tenant)
    await engine.dispose()
    assert report.ok, f"{report.failures} / {report.verify_detail}"

    connection = await _connect()
    try:
        scope = await connection.fetchval(
            "SELECT conversation_id FROM metaedu.agent_workspace_outbox WHERE id=$1",
            mismatch,
        )
        assert scope is None, "mismatch 类型行不得盲 join 回填 scope"
        issue = await connection.fetchrow(
            "SELECT reconcile_class, issue_code, conversation_id FROM "
            "metaedu.agent_transport_scope_reconcile WHERE source_row_id=$1",
            mismatch,
        )
        assert issue is not None, "mismatch 行须登记 scope 类 issue"
        assert issue["reconcile_class"] == "tenant_scope"
        assert issue["issue_code"] == "ambiguous_mapping"
        assert issue["conversation_id"] is None, (
            "无候选 Conversation 时 ambiguous_mapping 须 tenant_scope/不带 conversation_id"
        )
        epoch = await connection.fetchval(
            "SELECT count(*) FROM metaedu.agent_transport_scope_reconcile "
            "WHERE source_row_id=$1 AND issue_code='epoch_unresolvable'",
            mismatch,
        )
        assert epoch == 1, "mismatch 行 NULL-epoch 须登记 epoch_unresolvable"
    finally:
        await connection.close()
