"""R1-S4-B transport/external scope backfill（可恢复、分批、tenant 限流、幂等）。

按 Plan §R1-S4 B2/B3/B4/B5/B7 落地：为 4 张既有 inbox/outbox 与 RunEvent 回填
结构化 owner scope（``conversation_id``）、登记三态 reconcile issue、登记
external ref ledger，并做 scope/epoch 双维度最终 verify。

**回填顺序（B2）**：先两张 outbox（直接经 Message/Run），再两张 inbox（经已回填
的源 outbox）。所有 UPDATE 带 ``tenant_id`` 谓词 + 源行 tenant 一致性校验（跨
tenant 不映射，记 reconcile）。

**来源矩阵（B2）**：

| 表 | 源 | scope 映射 |
|----|----|-----------|
| ``agent_workspace_outbox`` | ``aggregate_id=messages.id`` | ``= message.conversation_id`` |
| ``agent_execution_outbox`` | ``aggregate_id=runs.id`` | ``= run.conversation_id`` |
| ``agent_workspace_inbox`` | ``event_id=execution_outbox.id`` | ``= exec_outbox.conversation_id`` |
| ``agent_execution_inbox`` | ``event_id=workspace_outbox.id`` | ``= ws_outbox.conversation_id`` |

**epoch（B3）**：backfill 只回填 ``conversation_id``；``producer_purge_revision``
对历史行保持 NULL（未知），且**每个 NULL 行登记一条 ``epoch_unresolvable``
reconcile issue**——不得拿当前 ``Conversation.purge_revision`` 伪造历史 epoch。

**三态 reconcile（B4）**：scope 已知但冲突 -> ``conversation_scope``（带
conversation_id，阻塞该 Conversation purge）；scope 未知（源缺失/歧义）->
``tenant_scope``（阻断该 tenant scheduler-enable）；Conversation 已物理删除 ->
``orphan``（不猜 UUID）。gate 一律 ``state <> 'resolved'`` fail closed。集合级并发
用事务级 advisory lock（``acquire_transport_aggregate_lock``，不依赖源行存在）。

**external ref（B5）**：所有 ref-bearing source（RunEvent + 两张 outbox 的非空
``payload_ref``）登记 ledger；无可证明 DB-local 格式 -> ``ref_scheme='unknown'``
且 ``erase_state='blocked'``（``blocked_reason='unknown_scheme'``）。run_events
恒有 scope（``conversation_id`` NOT NULL、无 scope 列），故不参与 scope 回填 /
reconcile / epoch verify，只对非空 ``payload_ref`` 行做 external ref 登记（独立
批次，``SELECT ... FOR UPDATE SKIP LOCKED`` 原子 claim，多并发不重复处理）。

**并发新写（B7）**：S4-C 前旧 writer 仍可能产生 scope NULL 新行 -> backfill 与
部分唯一索引均以 ``IS NOT NULL`` 为作用域，NULL 行不阻塞新写、不被误回填。
**verify（B7）**：scope 维（``conversation_id IS NULL`` -> 具名 scope 类 issue）与
epoch 维（``producer_purge_revision IS NULL`` -> ``epoch_unresolvable``）各自独立
fail closed，互不豁免。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import cast

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_locks import acquire_transport_aggregate_lock

# 失败样本上限（内存有界，系统性失败时不 O(N) 增长）。
_MAX_FAILURE_SAMPLES = 16

# D3/D5 受控枚举（与 migration 040 CHECK 一致）。
OWNER_BY_TABLE = {
    "agent_workspace_outbox": "workspace.transport.v1",
    "agent_workspace_inbox": "workspace.transport.v1",
    "agent_execution_outbox": "execution.transport.v1",
    "agent_execution_inbox": "execution.transport.v1",
}
_EXTERNAL_OWNER = "external.payload.v1"

# scope 类 issue（B4，epoch_unresolvable 属 epoch 类，单独处理）。
_SOURCE_MISSING_ISSUE: dict[str, str] = {
    "agent_workspace_outbox": "source_message_missing",
    "agent_execution_outbox": "source_run_missing",
    "agent_workspace_inbox": "source_outbox_missing",
    "agent_execution_inbox": "source_outbox_missing",
}


@dataclass(frozen=True, slots=True)
class ScopeBackfillFailure:
    """单行回填失败的稳定诊断（不持久化正文）。"""

    source_table: str
    source_row_id: uuid.UUID
    reason_code: str
    error_type: str


@dataclass(slots=True)
class ScopeBackfillReport:
    tenant_id: uuid.UUID | None = None
    rows_scanned: int = 0
    scope_backfilled: int = 0
    scope_already_present: int = 0
    reconcile_issues_registered: int = 0
    external_refs_registered: int = 0
    failures: list[ScopeBackfillFailure] = field(default_factory=list)
    failure_count: int = 0
    next_after_id: uuid.UUID | None = None
    completed: bool = False
    # verify 结果（scope/epoch 双维）。verify_failed=True 表示存在未登记 NULL 行。
    verify_failed: bool = False
    verify_detail: str = ""

    @property
    def ok(self) -> bool:
        return self.failure_count == 0 and not self.verify_failed


# ---------------------------------------------------------------------------
# 源行扫描（keyset 分页，仅取 scope 未决行）。
# ---------------------------------------------------------------------------


async def _select_null_scope_batch(
    session: AsyncSession,
    *,
    table: str,
    tenant_id: uuid.UUID,
    after_id: uuid.UUID | None,
    batch_size: int,
) -> list[tuple[uuid.UUID, uuid.UUID, str | None]]:
    """取一批 ``conversation_id IS NULL`` 的 4 张 transport 源行 (id, join_key, ref)。

    返回 (source_row_id, join_key, payload_ref)。join_key 对 outbox 是
    aggregate_id、对 inbox 是 event_id。payload_ref 仅 outbox 用于 external
    ledger 登记。run_events 不经此函数（它无 scope 列，恒有 conversation_id，
    只做 external ref 登记，见 ``_select_ref_event_batch``）。
    """
    if table in ("agent_workspace_outbox", "agent_execution_outbox"):
        join_col, ref_col = "aggregate_id", "payload_ref"
    else:  # agent_workspace_inbox / agent_execution_inbox
        join_col, ref_col = "event_id", "NULL"
    sql = (
        f"SELECT id, {join_col} AS join_key, {ref_col} AS payload_ref "
        f"FROM metaedu.{table} "
        f"WHERE tenant_id = :t AND conversation_id IS NULL"
    )
    if after_id is not None:
        sql += " AND id > :after"
    sql += " ORDER BY id LIMIT :lim"
    params = {"t": tenant_id, "lim": batch_size}
    if after_id is not None:
        params["after"] = after_id
    result = await session.execute(text(sql), params)
    return [(row[0], row[1], row[2]) for row in result.all()]


async def _select_ref_event_batch(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    after_id: uuid.UUID | None,
    batch_size: int,
) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, str]]:
    """取一批带非空 ``payload_ref`` 的 RunEvent (id, conversation_id, run_id, ref)。

    用 ``FOR UPDATE ... SKIP LOCKED`` 对 ``uq_agent_run_event_tenant_id
    (tenant_id, id)`` 命中的行做原子 claim，多并发 backfill 不重复处理同一行；
    行锁随事务提交释放，不长期持有。run_events 恒有 scope（conversation_id NOT
    NULL），故只登记 external ref、不参与 reconcile/scope 回填。
    """
    sql = (
        "SELECT id, conversation_id, run_id, payload_ref FROM metaedu.agent_run_events "
        "WHERE tenant_id = :t AND payload_ref IS NOT NULL"
    )
    if after_id is not None:
        sql += " AND id > :after"
    sql += " ORDER BY id LIMIT :lim FOR UPDATE SKIP LOCKED"
    params = {"t": tenant_id, "lim": batch_size}
    if after_id is not None:
        params["after"] = after_id
    result = await session.execute(text(sql), params)
    return [(row[0], row[1], row[2], row[3]) for row in result.all()]


# ---------------------------------------------------------------------------
# 源 scope 解析（经 Message/Run/源 outbox；跨 tenant 校验；orphan 判定）。
# ---------------------------------------------------------------------------


async def _resolve_source_conversation(
    session: AsyncSession,
    *,
    table: str,
    tenant_id: uuid.UUID,
    join_key: uuid.UUID,
) -> tuple[str, uuid.UUID | None]:
    """解析源行 Conversation。返回 (resolution, conversation_id)。

    resolution ∈ {resolved, source_missing, cross_tenant, orphan}：
    - resolved：唯一映射到现存 Conversation（跨 tenant 校验通过）。
    - source_missing：源 Message/Run/源 outbox 不存在 -> scope 未知。
    - cross_tenant：源行 tenant 与本行 tenant 不一致 -> 跨 tenant，不映射。
    - orphan：Conversation 已物理删除（agent_conversations 无对应）。
    """
    if table == "agent_workspace_outbox":
        src = "agent_messages"
    elif table == "agent_execution_outbox":
        src = "agent_runs"
    elif table == "agent_workspace_inbox":
        src = "agent_execution_outbox"
    else:  # agent_execution_inbox
        src = "agent_workspace_outbox"
    row = (
        await session.execute(
            text(
                f"SELECT tenant_id, conversation_id FROM metaedu.{src} WHERE id = :k"
            ),
            {"k": join_key},
        )
    ).first()
    if row is None:
        return "source_missing", None
    src_tenant: uuid.UUID = row[0]
    conversation_id: uuid.UUID | None = row[1]
    if src_tenant != tenant_id:
        return "cross_tenant", None
    if conversation_id is None:
        # inbox 的源 outbox 尚未回填（先 outbox 后 inbox 顺序下不应出现；兜底未知）。
        return "source_missing", None
    # orphan 判定：Conversation 是否仍在。
    conv_exists = (
        await session.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM metaedu.agent_conversations "
                "WHERE tenant_id = :t AND id = :c)"
            ),
            {"t": tenant_id, "c": conversation_id},
        )
    ).scalar()
    if not conv_exists:
        return "orphan", None
    return "resolved", conversation_id


async def _register_issue(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    owner_key: str,
    table: str,
    source_row_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    reconcile_class: str,
    issue_code: str,
) -> bool:
    """幂等登记一条 reconcile issue（唯一键 ON CONFLICT DO NOTHING）。返回是否新建。"""
    result = cast(
        CursorResult,
        await session.execute(
            text(
                "INSERT INTO metaedu.agent_transport_scope_reconcile ("
                "  id, tenant_id, owner_key, source_table, source_row_id, "
                "  conversation_id, reconcile_class, issue_code, state, revision, created_at"
                ") VALUES (:id, :t, :o, :st, :sr, :c, :rc, :ic, 'open', 1, clock_timestamp()) "
                "ON CONFLICT ON CONSTRAINT uq_agent_transport_reconcile_issue DO NOTHING"
            ),
            {
                "id": uuid.uuid4(),
                "t": tenant_id,
                "o": owner_key,
                "st": table,
                "sr": source_row_id,
                "c": conversation_id,
                "rc": reconcile_class,
                "ic": issue_code,
            },
        ),
    )
    return result.rowcount > 0


async def _register_external_ref(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    table: str,
    source_row_id: uuid.UUID,
    ref_value: str,
) -> bool:
    """幂等登记 external ref（无可证明 DB-local 格式 -> unknown + blocked）。"""
    result = cast(
        CursorResult,
        await session.execute(
            text(
                "INSERT INTO metaedu.agent_external_object_refs ("
                "  id, tenant_id, conversation_id, owner_key, ref_scheme, ref_value, "
                "  source_table, source_row_id, erase_state, blocked_reason, "
                "  created_at, updated_at"
                ") VALUES (:id, :t, :c, :o, 'unknown', :rv, :st, :sr, 'blocked', "
                "  'unknown_scheme', clock_timestamp(), clock_timestamp()) "
                "ON CONFLICT ON CONSTRAINT uq_agent_external_ref_source DO NOTHING"
            ),
            {
                "id": uuid.uuid4(),
                "t": tenant_id,
                "c": conversation_id,
                "o": _EXTERNAL_OWNER,
                "rv": ref_value,
                "st": table,
                "sr": source_row_id,
            },
        ),
    )
    return result.rowcount > 0


async def _recompute_projection(
    session: AsyncSession,
    *,
    table: str,
    tenant_id: uuid.UUID,
    source_row_id: uuid.UUID,
) -> None:
    """按 ledger 当前 issue 集重算行内 ``scope_reconcile_state`` 投影（同事务）。

    规则（B4）：orphan 类 issue 存在 -> 'orphan'（最高优先级）；任一 issue
    state<>'resolved' -> 'pending'；全部 resolved -> 'reconciled'。源行已回填
    scope（conversation_id 非 NULL）时同样按 issue 集投影（无 issue 即 NULL=已带
    scope，不参与 reconcile）。
    """
    state = (
        await session.execute(
            text(
                "SELECT CASE "
                "  WHEN bool_or(reconcile_class = 'orphan') THEN 'orphan' "
                "  WHEN bool_or(state <> 'resolved') THEN 'pending' "
                "  ELSE 'reconciled' END "
                "FROM metaedu.agent_transport_scope_reconcile "
                "WHERE tenant_id = :t AND source_table = :st AND source_row_id = :sr"
            ),
            {"t": tenant_id, "st": table, "sr": source_row_id},
        )
    ).scalar()
    if state is None:
        return  # 无 issue 行：投影保持 NULL（已带 scope / 无需 reconcile）
    await session.execute(
        text(
            f"UPDATE metaedu.{table} SET scope_reconcile_state = :s "
            f"WHERE tenant_id = :t AND id = :sr"
        ),
        {"s": state, "t": tenant_id, "sr": source_row_id},
    )


async def _backfill_source_row(
    session: AsyncSession,
    *,
    table: str,
    tenant_id: uuid.UUID,
    source_row_id: uuid.UUID,
    join_key: uuid.UUID,
    payload_ref: str | None,
    report: ScopeBackfillReport,
) -> None:
    """单行回填（调用方在独立短事务内调用；同事务取集合 advisory lock）。

    流程（D8 锁序：纯 backfill 路径只取集合锁）：集合 advisory lock -> 解析源
    scope -> 回填 conversation_id 或登记 reconcile -> 登记 epoch_unresolvable ->
    登记 external ref -> 重算投影。
    """
    owner_key = OWNER_BY_TABLE.get(table, _EXTERNAL_OWNER)
    # 集合级并发锁（不依赖源行存在，覆盖空集合/源行已删/新增成员）。
    await acquire_transport_aggregate_lock(
        session,
        tenant_id=tenant_id,
        owner_key=owner_key,
        source_table=table,
        source_row_id=source_row_id,
    )
    resolution, conversation_id = await _resolve_source_conversation(
        session, table=table, tenant_id=tenant_id, join_key=join_key
    )
    if resolution == "resolved":
        # 回填 scope（幂等：仅命中仍 NULL 的行）。
        result = cast(
            CursorResult,
            await session.execute(
                text(
                    f"UPDATE metaedu.{table} SET conversation_id = :c "
                    f"WHERE tenant_id = :t AND id = :sr AND conversation_id IS NULL"
                ),
                {"c": conversation_id, "t": tenant_id, "sr": source_row_id},
            ),
        )
        if result.rowcount > 0:
            report.scope_backfilled += 1
        else:
            report.scope_already_present += 1
    else:
        # scope 未知/orphan/跨 tenant：登记 scope 类 issue。
        if resolution == "orphan":
            reconcile_class = "orphan"
            issue_code = "conversation_deleted_orphan"
            issue_conv = None
        elif resolution == "cross_tenant":
            reconcile_class = "tenant_scope"
            issue_code = "cross_tenant_mismatch"
            issue_conv = None
        else:  # source_missing
            reconcile_class = "tenant_scope"
            issue_code = _SOURCE_MISSING_ISSUE[table]
            issue_conv = None
        if await _register_issue(
            session,
            tenant_id=tenant_id,
            owner_key=owner_key,
            table=table,
            source_row_id=source_row_id,
            conversation_id=issue_conv,
            reconcile_class=reconcile_class,
            issue_code=issue_code,
        ):
            report.reconcile_issues_registered += 1
    # epoch（B3）：历史行 producer_purge_revision 保持 NULL，登记 epoch_unresolvable。
    # epoch 类按 scope 状态归 class（B4 复核）：resolved->conversation_scope（带
    # conversation_id）；orphan->orphan；其余->tenant_scope。
    if resolution == "resolved":
        epoch_class, epoch_conv = "conversation_scope", conversation_id
    elif resolution == "orphan":
        epoch_class, epoch_conv = "orphan", None
    else:
        epoch_class, epoch_conv = "tenant_scope", None
    if await _register_issue(
        session,
        tenant_id=tenant_id,
        owner_key=owner_key,
        table=table,
        source_row_id=source_row_id,
        conversation_id=epoch_conv,
        reconcile_class=epoch_class,
        issue_code="epoch_unresolvable",
    ):
        report.reconcile_issues_registered += 1
    # external ref（B5）：仅 outbox 的非空 payload_ref（run_events 走独立路径）。
    if payload_ref is not None and await _register_external_ref(
        session,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        table=table,
        source_row_id=source_row_id,
        ref_value=payload_ref,
    ):
        report.external_refs_registered += 1
    # 重算行内投影（同事务，仅对有 issue 的源行）。
    await _recompute_projection(
        session, table=table, tenant_id=tenant_id, source_row_id=source_row_id
    )


async def _register_run_event_ref(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_row_id: uuid.UUID,
    conversation_id: uuid.UUID,
    ref_value: str,
    report: ScopeBackfillReport,
) -> None:
    """登记单条 RunEvent 的 external ref（调用方在独立短事务内调用）。

    run_events 恒有 scope（conversation_id NOT NULL），不做 scope 回填/epoch
    登记/投影；唯一职责是把非空 ``payload_ref`` 登记进 external ledger
    （unknown+blocked）。同事务取集合 advisory lock 与 4 张 transport 表保持
    一致的串行化边界；行已由 SELECT FOR UPDATE SKIP LOCKED claim。
    """
    await acquire_transport_aggregate_lock(
        session,
        tenant_id=tenant_id,
        owner_key=_EXTERNAL_OWNER,
        source_table="agent_run_events",
        source_row_id=source_row_id,
    )
    if await _register_external_ref(
        session,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        table="agent_run_events",
        source_row_id=source_row_id,
        ref_value=ref_value,
    ):
        report.external_refs_registered += 1


async def _verify_scope_epoch(
    session_factory, *, tenant_id: uuid.UUID
) -> tuple[bool, str]:
    """scope/epoch 双维最终 verify（fail closed，互不豁免）。

    scope 维：4 张 transport 表凡 ``conversation_id IS NULL`` 的行必须有对应
    scope 类 issue；epoch 维：凡 ``producer_purge_revision IS NULL`` 的行必须有
    ``epoch_unresolvable`` issue。run_events 不参与——它恒有 scope
    （conversation_id NOT NULL，无 NULL-scope 行），且无
    ``producer_purge_revision`` 列。
    """
    problems: list[str] = []
    scope_tables = [
        "agent_workspace_outbox",
        "agent_execution_outbox",
        "agent_workspace_inbox",
        "agent_execution_inbox",
    ]
    async with session_factory() as session, session.begin():
        for table in scope_tables:
            # scope 维：未填 scope 且无 scope 类 issue 的行数。
            scope_missing = (
                await session.execute(
                    text(
                        f"SELECT count(*) FROM metaedu.{table} t "
                        f"WHERE t.tenant_id = :t AND t.conversation_id IS NULL "
                        f"AND NOT EXISTS ("
                        f"  SELECT 1 FROM metaedu.agent_transport_scope_reconcile r "
                        f"  WHERE r.tenant_id = t.tenant_id AND r.source_table = :st "
                        f"  AND r.source_row_id = t.id AND r.issue_code IN ("
                        f"    'source_message_missing','source_run_missing',"
                        f"    'source_outbox_missing','cross_tenant_mismatch',"
                        f"    'ambiguous_mapping','conversation_deleted_orphan'))"
                    ),
                    {"t": tenant_id, "st": table},
                )
            ).scalar()
            if scope_missing:
                problems.append(f"{table}: {scope_missing} NULL-scope 行无 scope 类 issue")
        # epoch 维（仅 4 张 transport 表有 producer_purge_revision 列）。
        for table in scope_tables:
            epoch_missing = (
                await session.execute(
                    text(
                        f"SELECT count(*) FROM metaedu.{table} t "
                        f"WHERE t.tenant_id = :t AND t.producer_purge_revision IS NULL "
                        f"AND NOT EXISTS ("
                        f"  SELECT 1 FROM metaedu.agent_transport_scope_reconcile r "
                        f"  WHERE r.tenant_id = t.tenant_id AND r.source_table = :st "
                        f"  AND r.source_row_id = t.id "
                        f"  AND r.issue_code = 'epoch_unresolvable')"
                    ),
                    {"t": tenant_id, "st": table},
                )
            ).scalar()
            if epoch_missing:
                problems.append(
                    f"{table}: {epoch_missing} NULL-epoch 行无 epoch_unresolvable issue"
                )
    return (not problems), "; ".join(problems)


async def backfill_transport_scope(
    session_factory,
    *,
    tenant_id: uuid.UUID,
    batch_size: int = 100,
    max_rows: int | None = None,
    after_id: uuid.UUID | None = None,
) -> ScopeBackfillReport:
    """为指定 tenant 回填 transport/external scope（可恢复、分批、幂等）。

    每行在独立短事务处理（取集合 advisory lock）；任一行失败计入 failures 并
    继续（fail closed 由 report.ok 体现）。游标 keyset 仅用于分批/断点续跑，
    **不作为完备性证明**（S1 已记录随机 UUID 主键 point-in-time 缺陷）；失败恢复
    唯一可靠路径是从 tenant 起点（不带 after_id）幂等重跑。
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    if max_rows is not None and max_rows < 1:
        raise ValueError(f"max_rows must be None or >= 1, got {max_rows}")

    report = ScopeBackfillReport(tenant_id=tenant_id)
    # 先 outbox（经 Message/Run），再 inbox（经已回填源 outbox）。run_events 无
    # scope 列（恒有 conversation_id），不走 NULL-scope 扫描，单独做 ref 登记。
    tables = [
        "agent_workspace_outbox",
        "agent_execution_outbox",
        "agent_workspace_inbox",
        "agent_execution_inbox",
    ]
    processed = 0
    exhausted = True
    for table in tables:
        cursor = after_id
        while True:
            async with session_factory() as session, session.begin():
                batch = await _select_null_scope_batch(
                    session,
                    table=table,
                    tenant_id=tenant_id,
                    after_id=cursor,
                    batch_size=batch_size,
                )
            if not batch:
                break
            for source_row_id, join_key, payload_ref in batch:
                if max_rows is not None and processed >= max_rows:
                    exhausted = False
                    break
                try:
                    async with session_factory() as session, session.begin():
                        await _backfill_source_row(
                            session,
                            table=table,
                            tenant_id=tenant_id,
                            source_row_id=source_row_id,
                            join_key=join_key,
                            payload_ref=payload_ref,
                            report=report,
                        )
                    report.rows_scanned += 1
                except Exception as exc:  # noqa: BLE001 - fail closed 计入 failures
                    report.failure_count += 1
                    if len(report.failures) < _MAX_FAILURE_SAMPLES:
                        report.failures.append(
                            ScopeBackfillFailure(
                                source_table=table,
                                source_row_id=source_row_id,
                                reason_code="scope_backfill_failed",
                                error_type=type(exc).__name__,
                            )
                        )
                processed += 1
                cursor = source_row_id
                report.next_after_id = cursor
            if max_rows is not None and processed >= max_rows:
                break
            if len(batch) < batch_size:
                break
        if max_rows is not None and processed >= max_rows:
            break
    # run_events external ref 登记（独立批次：SELECT FOR UPDATE SKIP LOCKED claim
    # 带非空 payload_ref 的行，登记 external ledger unknown+blocked）。幂等：
    # ledger 唯一键 ON CONFLICT 兜底，重跑不重复。
    cursor = after_id
    while not (max_rows is not None and processed >= max_rows):
        async with session_factory() as session, session.begin():
            batch = await _select_ref_event_batch(
                session,
                tenant_id=tenant_id,
                after_id=cursor,
                batch_size=batch_size,
            )
        if not batch:
            break
        for source_row_id, conversation_id, _run_id, ref_value in batch:
            if max_rows is not None and processed >= max_rows:
                exhausted = False
                break
            try:
                async with session_factory() as session, session.begin():
                    await _register_run_event_ref(
                        session,
                        tenant_id=tenant_id,
                        source_row_id=source_row_id,
                        conversation_id=conversation_id,
                        ref_value=ref_value,
                        report=report,
                    )
                report.rows_scanned += 1
            except Exception as exc:  # noqa: BLE001 - fail closed 计入 failures
                report.failure_count += 1
                if len(report.failures) < _MAX_FAILURE_SAMPLES:
                    report.failures.append(
                        ScopeBackfillFailure(
                            source_table="agent_run_events",
                            source_row_id=source_row_id,
                            reason_code="external_ref_register_failed",
                            error_type=type(exc).__name__,
                        )
                    )
            processed += 1
            cursor = source_row_id
            report.next_after_id = cursor
        if len(batch) < batch_size:
            break
    report.completed = exhausted
    # 最终 verify（scope/epoch 双维 fail closed）。
    verify_ok, detail = await _verify_scope_epoch(session_factory, tenant_id=tenant_id)
    report.verify_failed = not verify_ok
    report.verify_detail = detail
    return report
