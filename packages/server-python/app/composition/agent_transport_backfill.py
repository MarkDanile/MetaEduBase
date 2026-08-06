"""R1-S4-B transport/external scope backfill（可恢复、分批、tenant 限流、幂等）。

按 Plan §R1-S4 B2/B3/B4/B5/B7 落地：为 4 张既有 inbox/outbox 与 RunEvent 回填
结构化 owner scope（``conversation_id``）、登记三态 reconcile issue、登记
external ref ledger，并做五维度最终 verify（scope/epoch/external-ref/投影一致性/scope-vs-来源）。

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

**三态 reconcile（B4）**：scope 已知但冲突（A≠B：行内与来源 conversation 不同，
或来源跨 tenant）-> ``tenant_scope``（**不带** conversation_id，阻断该 tenant
scheduler-enable；第三轮复核 #3 推翻 conversation_scope 降级决策——不猜、不 gate
单一 Conversation）；scope 未知（源缺失/歧义）-> ``tenant_scope``；Conversation 已
物理删除 -> ``orphan``（不猜 UUID）。gate 一律 ``state <> 'resolved'`` fail closed。
集合级并发用事务级 advisory lock（``acquire_transport_aggregate_lock``，不依赖源行存在）。

**external ref（B5）**：所有 ref-bearing source（RunEvent + 两张 outbox 的非空
``payload_ref``）登记 ledger；无可证明 DB-local 格式 -> ``ref_scheme='unknown'``
且 ``erase_state='blocked'``（``blocked_reason='unknown_scheme'``）。run_events
恒有 scope（``conversation_id`` NOT NULL、无 scope 列），故不参与 scope 回填 /
reconcile / epoch verify，只对非空 ``payload_ref`` 行做 external ref 登记（独立
批次，``SELECT ... FOR UPDATE SKIP LOCKED`` 原子 claim，多并发不重复处理）。

**并发新写（B7）**：S4-C 前旧 writer 仍可能产生 scope NULL 新行 -> backfill 与
部分唯一索引均以 ``IS NOT NULL`` 为作用域，NULL 行不阻塞新写、不被误回填。
**verify（B7，五维 fail closed，互不豁免）**：scope 维（``conversation_id IS NULL`` ->
具名 scope 类 issue）、epoch 维（``producer_purge_revision IS NULL`` ->
``epoch_unresolvable``）、external-ref 维（``payload_ref IS NOT NULL`` -> external ledger
登记）、投影一致性维（行内 ``scope_reconcile_state`` 与 ledger issue 集重算一致）、
scope-vs-来源矩阵维（scope-set 行的 conversation_id 与来源 Message/Run/源 outbox 一致，
覆盖不进扫描的冲突行）。
"""

from __future__ import annotations

import asyncio
import math
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

# B2 来源矩阵的 event_type/aggregate_type 约束（复核 #6）：backfill 只对受支持的
# (event_type, aggregate_type) 做来源映射（盲 join 会被禁）。未知类型的行**不跳过**--
# 它们被扫描后路由到 ``resolution='ambiguous'``（不盲 join aggregate_id），登记
# ``tenant_scope``/``ambiguous_mapping`` + ``epoch_unresolvable``，使 B7:817/B3:778
# 「每行必登记」无类型豁免（verify 不加 type_filter）。inbox 无 aggregate_type 列，
# 其类型约束由源 outbox 的行级判定传递。
_SOURCE_TYPE_BY_TABLE: dict[str, tuple[str, str]] = {
    "agent_workspace_outbox": ("turn.requested.v1", "workspace.message"),
    "agent_execution_outbox": ("assistant_message.publish_requested.v1", "execution.run"),
}


# 第三轮复核 #1 discovery：scope-set 行 mismatch 检测的来源表 + join 列。
# outbox 来源是 Message/Run（aggregate_id）；inbox 来源是对端 outbox（event_id）。
_MISMATCH_SOURCE_BY_TABLE: dict[str, tuple[str, str]] = {
    "agent_workspace_outbox": ("agent_messages", "aggregate_id"),
    "agent_execution_outbox": ("agent_runs", "aggregate_id"),
    "agent_workspace_inbox": ("agent_execution_outbox", "event_id"),
    "agent_execution_inbox": ("agent_workspace_outbox", "event_id"),
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
    rows_attempted: int = 0
    scope_backfilled: int = 0
    scope_already_present: int = 0
    reconcile_issues_registered: int = 0
    external_refs_registered: int = 0
    failures: list[ScopeBackfillFailure] = field(default_factory=list)
    failure_count: int = 0
    completed: bool = False
    # verify 结果（scope/epoch/external-ref/投影一致性/scope-vs-来源 五维）。
    verify_failed: bool = False
    verify_detail: str = ""

    @property
    def ok(self) -> bool:
        return self.failure_count == 0 and not self.verify_failed


# ---------------------------------------------------------------------------
# 源行扫描（keyset 分页，仅取 scope 未决行）。
# ---------------------------------------------------------------------------


async def _select_actionable_batch(
    session: AsyncSession,
    *,
    table: str,
    tenant_id: uuid.UUID,
    after_id: uuid.UUID | None,
    batch_size: int,
) -> list[tuple[uuid.UUID, uuid.UUID, str | None]]:
    """取一批待处理的 4 张 transport 源行 (id, join_key, ref)。

    返回 (source_row_id, join_key, payload_ref)。join_key 对 outbox 是 aggregate_id、
    对 inbox 是 event_id。

    **选取范围（第三轮复核 #1 discovery + P1-1/#2/#6 + 第八轮复核 #1）**：
    - NULL-scope 未处理行（``conversation_id IS NULL AND scope_reconcile_state IS NULL``）：
      回填 scope 或登记 scope 类 issue。
    - outbox ref 未登记行（``payload_ref IS NOT NULL AND NOT EXISTS(external ledger
      ref_value 匹配)``）：
      补登 external ref（复核 #2：按 ref_value 匹配）。
    - scope-set mismatch 行（``conversation_id IS NOT NULL AND
      scope_reconcile_state IS NULL
      AND <来源 conversation_id 不一致或跨 tenant>``）：第三轮复核 #1 discovery--登记
      tenant_scope/ambiguous_mapping 或 cross_tenant_mismatch，形成可处理 reconcile 闭环
      （verify 第五维只读验证 issue 已存在）。无来源且 scope 已填的行不在 mismatch 范围
      （scope 仍有效、FK 保护），不登记。已登记 issue 的行（``scope_reconcile_state IS NOT NULL``）
      退出扫描，不饥饿（#1）。run_events 不经此函数（见 ``_select_ref_event_batch``）。
    - **epoch-only 行（第八轮复核 #1）**：``conversation_id IS NOT NULL AND
      producer_purge_revision IS NULL AND scope_reconcile_state IS NULL AND 无 mismatch``
      ——已带 scope 但 epoch 未知的行须被选中补登 ``epoch_unresolvable``（否则 verify
      epoch 维永久 fail、无法收敛）。
    """
    src_table, join_col = _MISMATCH_SOURCE_BY_TABLE[table]
    is_outbox = table in _SOURCE_TYPE_BY_TABLE
    ref_select = "payload_ref" if is_outbox else "NULL"
    # mismatch EXISTS（第八轮复核 #4：含源 conversation_id IS NULL——inbox 的源 outbox
    # scope 未知时，inbox 的 scope-set 行也是未知派生的，须登记 issue 而非假绿）：
    # 来源同 tenant 但 conversation_id 不同（A≠B）、来源 conversation_id 为 NULL
    # （源 scope 未知）、或来源跨 tenant。
    # outbox 源 Message/Run conversation_id NOT NULL，NULL 分支对 outbox 无害。
    mismatch = (
        f"(EXISTS(SELECT 1 FROM metaedu.{src_table} s WHERE s.id = t.{join_col} "
        f"AND s.tenant_id = t.tenant_id AND s.conversation_id IS NOT NULL "
        f"AND s.conversation_id <> t.conversation_id)"
        f" OR EXISTS(SELECT 1 FROM metaedu.{src_table} s WHERE s.id = t.{join_col} "
        f"AND s.tenant_id = t.tenant_id AND s.conversation_id IS NULL)"
        f" OR EXISTS(SELECT 1 FROM metaedu.{src_table} s WHERE s.id = t.{join_col} "
        f"AND s.tenant_id <> t.tenant_id))"
    )
    if is_outbox:
        ref_branch = (
            " OR (t.payload_ref IS NOT NULL AND NOT EXISTS ("
            "  SELECT 1 FROM metaedu.agent_external_object_refs er "
            "  WHERE er.tenant_id = t.tenant_id AND er.source_table = '" + table + "'"
            " AND er.source_row_id = t.id AND er.ref_value = t.payload_ref))"
            # 第十轮复核 #2（outbox 同缺口）：已登记但绑定不一致的 blocked 记录进入
            # 修复路径（_register_external_ref DO UPDATE 修正），否则永不重扫。
            " OR (t.payload_ref IS NOT NULL AND EXISTS ("
            "  SELECT 1 FROM metaedu.agent_external_object_refs er3 "
            "  WHERE er3.tenant_id = t.tenant_id AND er3.source_table = '" + table + "'"
            " AND er3.source_row_id = t.id AND er3.ref_value = t.payload_ref "
            " AND er3.erase_state = 'blocked' AND er3.blocked_reason = 'unknown_scheme'"
            " AND er3.conversation_id IS DISTINCT FROM ("
            "  SELECT CASE WHEN s.id IS NOT NULL AND s.tenant_id = t.tenant_id "
            "    AND s.conversation_id IS NOT NULL"
            "    AND s.conversation_id = t.conversation_id"
            "    AND EXISTS(SELECT 1 FROM metaedu.agent_conversations c "
            "      WHERE c.tenant_id = t.tenant_id AND c.id = s.conversation_id)"
            "    THEN s.conversation_id ELSE NULL END"
            "  FROM metaedu." + src_table + " s WHERE s.id = t." + join_col + " "
            "  LIMIT 1)))"
        )
    else:
        ref_branch = ""
    predicate = (
        "((t.conversation_id IS NULL AND t.scope_reconcile_state IS NULL)"
        + ref_branch
        + f" OR (t.conversation_id IS NOT NULL AND t.scope_reconcile_state IS NULL"
        f" AND {mismatch})"
        # 第八轮复核 #1：scope 已填但 epoch 未知的行补登 epoch_unresolvable（收敛）。
        f" OR (t.conversation_id IS NOT NULL AND t.producer_purge_revision IS NULL"
        f" AND t.scope_reconcile_state IS NULL AND NOT ({mismatch})))"
    )
    sql = (
        f"SELECT t.id, t.{join_col} AS join_key, {ref_select} AS payload_ref "
        f"FROM metaedu.{table} t "
        f"WHERE t.tenant_id = :t AND ({predicate})"
    )
    if after_id is not None:
        sql += " AND t.id > :after"
    sql += " ORDER BY t.id LIMIT :lim"
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
    """取一批带非空 ``payload_ref`` 且**尚未登记或绑定错误**的 RunEvent。

    返回 (id, conversation_id, run_id, payload_ref)。扫描谓词 = ``payload_ref IS
    NOT NULL AND (NOT EXISTS(external ledger 登记) OR EXISTS(blocked 记录绑定不一致))``
    （P1-1 + 第十轮复核 #2：错误绑定进入修复路径——`_register_external_ref` 的
    DO UPDATE 对 blocked/unknown_scheme 记录修正 conversation_id；verify 同判据
    保证闭环）。被并发 ``SKIP LOCKED`` 跳过而漏登记的行下次重跑会被重新选中补登，
    自愈；``FOR UPDATE SKIP LOCKED`` 仅作并发去重优化，不再是完备性依赖。
    run_events 恒有 scope（conversation_id NOT NULL），故只登记 external ref、不
    参与 reconcile/scope 回填。
    """
    sql = (
        "SELECT id, conversation_id, run_id, payload_ref FROM metaedu.agent_run_events "
        "WHERE tenant_id = :t AND payload_ref IS NOT NULL AND ("
        "  NOT EXISTS ("
        "    SELECT 1 FROM metaedu.agent_external_object_refs er "
        "    WHERE er.tenant_id = metaedu.agent_run_events.tenant_id "
        "    AND er.source_table = 'agent_run_events' "
        "    AND er.source_row_id = metaedu.agent_run_events.id "
        "    AND er.ref_value = metaedu.agent_run_events.payload_ref)"
        "  OR EXISTS ("
        "    SELECT 1 FROM metaedu.agent_external_object_refs er2 "
        "    WHERE er2.tenant_id = metaedu.agent_run_events.tenant_id "
        "    AND er2.source_table = 'agent_run_events' "
        "    AND er2.source_row_id = metaedu.agent_run_events.id "
        "    AND er2.ref_value = metaedu.agent_run_events.payload_ref "
        "    AND er2.conversation_id IS DISTINCT FROM "
        "      metaedu.agent_run_events.conversation_id))"
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
    """幂等登记 external ref（无可证明 DB-local 格式 -> unknown + blocked）。

    **第九轮复核 #2（可收敛）**：ON CONFLICT 不再 DO NOTHING——已存在但**仍处
    blocked/unknown_scheme** 的记录（旧版本/中断恢复留下的错误绑定）安全 UPDATE 修正
    ``conversation_id`` 为当前解析值（erase 尚未推进，仅 blocked 态可修正；已
    registered/erased 的记录不覆盖，由 verify fail closed 暴露）。返回是否新建。
    """
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
                "ON CONFLICT ON CONSTRAINT uq_agent_external_ref_source DO UPDATE SET "
                "  conversation_id = EXCLUDED.conversation_id, "
                "  updated_at = clock_timestamp() "
                "WHERE agent_external_object_refs.erase_state = 'blocked' "
                "  AND agent_external_object_refs.blocked_reason = 'unknown_scheme' "
                "  AND agent_external_object_refs.conversation_id IS DISTINCT FROM "
                "    EXCLUDED.conversation_id"
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
    owner_key: str,
    source_row_id: uuid.UUID,
) -> None:
    """按 ledger 当前 issue 集重算行内 ``scope_reconcile_state`` 投影（同事务）。

    规则（B4）：orphan 类 issue 存在 -> 'orphan'（最高优先级）；任一 issue
    state<>'resolved' -> 'pending'；全部 resolved -> 'reconciled'。源行已回填
    scope（conversation_id 非 NULL）时同样按 issue 集投影（无 issue 即 NULL=已带
    scope，不参与 reconcile）。

    **owner 维度（P2-2）**：ledger 唯一键含 ``owner_key``、集合锁按 owner 派生，
    故投影聚合必须限定同一 owner——否则后续不同 owner 对同一 source row 写入的
    issue 集会被错误聚合。
    """
    state = (
        await session.execute(
            text(
                "SELECT CASE "
                "  WHEN count(*) = 0 THEN NULL "
                "  WHEN bool_or(reconcile_class = 'orphan') THEN 'orphan' "
                "  WHEN bool_or(state <> 'resolved') THEN 'pending' "
                "  ELSE 'reconciled' END "
                "FROM metaedu.agent_transport_scope_reconcile "
                "WHERE tenant_id = :t AND owner_key = :o "
                "AND source_table = :st AND source_row_id = :sr"
            ),
            {"t": tenant_id, "o": owner_key, "st": table, "sr": source_row_id},
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
    # 先查行当前 scope/epoch 状态（P1-1：outbox 已带 scope 的 ref-bearing 行只做
    # ref 补登，不重复 epoch_unresolvable；epoch issue 只对 producer_purge_revision
    # 仍为 NULL 的 history 行登记一次）。outbox 额外取 (event_type, aggregate_type)
    # 用于 B2 类型约束判定（复核 #6）；inbox 无此列。
    type_cols = (
        ", event_type, aggregate_type" if table in _SOURCE_TYPE_BY_TABLE else ""
    )
    current = (
        await session.execute(
            text(
                f"SELECT conversation_id, producer_purge_revision{type_cols} "
                f"FROM metaedu.{table} WHERE tenant_id = :t AND id = :sr"
            ),
            {"t": tenant_id, "sr": source_row_id},
        )
    ).first()
    if current is None:
        return  # 行已被并发删除：集合锁边界内安全跳过（下一跑若重现再处理）。
    had_scope = current[0] is not None
    epoch_is_null = current[1] is None
    # B2 类型约束（复核 #6）：outbox 行 (event_type, aggregate_type) 须命中 B2 矩阵，
    # 否则**不盲 join** aggregate_id（future 类型行 aggregate_id 碰巧指向 Message/Run 会
    # 错配 scope），直接判 ambiguous（scope 真正未知、无候选 Conversation）-> 由下方
    # ``not had_scope`` 分支登记 tenant_scope/ambiguous_mapping（conversation_id=NULL，
    # ck_..._class_scope 强制）。inbox 无 aggregate_type，类型约束由源 outbox 行级判定
    # 传递，故 inbox 不在此判定。
    expected_type = _SOURCE_TYPE_BY_TABLE.get(table)
    if expected_type is not None and (current[2], current[3]) != expected_type:
        resolution, conversation_id = "ambiguous", None
    else:
        resolution, conversation_id = await _resolve_source_conversation(
            session, table=table, tenant_id=tenant_id, join_key=join_key
        )
    # 第三轮复核 #3：A≠B 冲突（行内 scope=A、源解析值=B）降级 tenant_scope/
    # ambiguous_mapping（**不带** conversation_id）。唯一键 (…,issue_code) 无法表示 A/B
    # 双候选，且只 gate B 会让 A 的 ledger purge gate 漏掉（FK 仅挡物理删除）；tenant_scope
    # 阻断该 tenant scheduler-enable 直到运维 resolved，保守且不声称 gate 单一 Conversation。
    # 不覆盖行内 A（fail closed，不猜）；external ref / epoch 同降 tenant_scope（见下）。
    conflict = resolution == "resolved" and had_scope and current[0] != conversation_id
    if conflict:
        if await _register_issue(
            session,
            tenant_id=tenant_id,
            owner_key=owner_key,
            table=table,
            source_row_id=source_row_id,
            conversation_id=None,
            reconcile_class="tenant_scope",
            issue_code="ambiguous_mapping",
        ):
            report.reconcile_issues_registered += 1
    elif resolution == "resolved":
        # 回填 scope（幂等：仅命中仍 NULL 的行；已有且一致 -> scope_already_present）。
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
    elif had_scope and resolution == "cross_tenant":
        # 第三轮复核 #1 discovery：scope 已填但来源跨 tenant（数据腐败）--登记
        # tenant_scope/cross_tenant_mismatch（不带 conversation_id），形成可处理 reconcile
        # 闭环；不覆盖行内 scope（fail closed，不猜）。由 discovery 扫描 mismatch 分支选中。
        if await _register_issue(
            session,
            tenant_id=tenant_id,
            owner_key=owner_key,
            table=table,
            source_row_id=source_row_id,
            conversation_id=None,
            reconcile_class="tenant_scope",
            issue_code="cross_tenant_mismatch",
        ):
            report.reconcile_issues_registered += 1
    elif had_scope and resolution == "source_missing":
        # 第八轮复核 #4：scope 已填但**源 scope 未知**（inbox 的源 outbox scope 为
        # NULL——源解析返回 source_missing）-> 行内 scope 是未知派生的，登记
        # tenant_scope/ambiguous_mapping（不带 conversation_id），形成可处理闭环；
        # 不覆盖行内 scope（fail closed，不猜）。
        if await _register_issue(
            session,
            tenant_id=tenant_id,
            owner_key=owner_key,
            table=table,
            source_row_id=source_row_id,
            conversation_id=None,
            reconcile_class="tenant_scope",
            issue_code="ambiguous_mapping",
        ):
            report.reconcile_issues_registered += 1
    elif not had_scope:
        # scope 未知/orphan/跨 tenant 且本行确无 scope：登记 scope 类 issue。
        # （已带 scope 的 ref-bearing 行跳过 scope issue——它不属于 scope 维问题。）
        if resolution == "orphan":
            reconcile_class = "orphan"
            issue_code = "conversation_deleted_orphan"
            issue_conv = None
        elif resolution == "cross_tenant":
            reconcile_class = "tenant_scope"
            issue_code = "cross_tenant_mismatch"
            issue_conv = None
        elif resolution == "ambiguous":
            # B2 类型不匹配（复核 #6）：scope 真正未知、无候选 Conversation，登记
            # tenant_scope/ambiguous_mapping（不带 conversation_id，ck_..._class_scope
            # 强制），阻断该 tenant scheduler-enable 直到 S4-C 接线后 resolved。
            reconcile_class = "tenant_scope"
            issue_code = "ambiguous_mapping"
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
    # epoch（B3）：仅当 producer_purge_revision 仍为 NULL 时登记 epoch_unresolvable
    # （幂等唯一键兜底，且已带 epoch 的行——如 S4-C 后新写入——不再补 issue）。
    # epoch 类按 scope 状态归 class（B4 复核）：resolved->conversation_scope（带
    # conversation_id）；orphan->orphan；其余->tenant_scope。
    if epoch_is_null:
        if conflict:
            # 冲突行 scope 争议 -> epoch 同降 tenant_scope（不带 conversation_id）。
            epoch_class, epoch_conv = "tenant_scope", None
        elif resolution == "resolved":
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
    # conversation_id（第八轮复核 #3）：仅 resolved（或 conflict——含 A≠B 且不猜）时
    # bind Conversation；**非 resolved（cross-tenant / source_missing / orphan /
    # ambiguous）一律 NULL**——不继承行内旧 scope（跨 tenant 不映射、不 gate 单一
    # Conversation；B4/B5 tenant/orphan 语义）。ref 与 scope 解耦：即使行内 scope
    # 已知，external ref 仍可登记（erase 按行独立推进）。
    if payload_ref is not None and await _register_external_ref(
        session,
        tenant_id=tenant_id,
        conversation_id=(
            None
            if resolution != "resolved"
            else (None if conflict else conversation_id)
        ),
        table=table,
        source_row_id=source_row_id,
        ref_value=payload_ref,
    ):
        report.external_refs_registered += 1
    # 重算行内投影（同事务，仅对有 issue 的源行；owner 维度绑定见 _recompute_projection）。
    await _recompute_projection(
        session,
        table=table,
        tenant_id=tenant_id,
        owner_key=owner_key,
        source_row_id=source_row_id,
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
    """scope/epoch/external-ref/投影一致性/scope-vs-来源 五维最终 verify（fail closed，互不豁免）。

    scope 维：4 张 transport 表凡 ``conversation_id IS NULL`` 的行必须有对应
    scope 类 issue；epoch 维：凡 ``producer_purge_revision IS NULL`` 的行必须有
    ``epoch_unresolvable`` issue。两维的 issue 匹配均限定 ``owner_key``（P2-2：
    ledger 唯一键含 owner_key，verify 不绑定 owner 会让跨 owner 的 issue 错误满足
    本 owner 的 verify）。**无类型豁免**（复核 #6 / B7:817 / B3:778）：mismatch 类型
    行经 ``_backfill_source_row`` 路由到 ``ambiguous`` 已登记 scope/epoch issue，
    故 verify 覆盖全部行、不加 ``type_filter``。

    external ref 维（P1-1）：两张 outbox + RunEvent 凡 ``payload_ref IS NOT NULL``
    的行必须在 external ledger 有登记（owner=external.payload.v1，B5:800 无类型豁免）。
    否则 SKIP LOCKED 跳过 / 已带 scope 的 ref-bearing 行会静默漏登记而 verify 误报 ok。

    投影一致性维（复核 #5 / B4 复核 #8）：行内 ``scope_reconcile_state`` 是派生只读
    投影，必须与该 owner 的完整 issue 集重算结果一致，任何漂移即数据异常 fail closed。

    run_events 不参与 scope/epoch 维--它恒有 scope（conversation_id NOT NULL，
    无 NULL-scope 行），且无 ``producer_purge_revision`` 列。
    """
    problems: list[str] = []
    # 第五轮复核 #1：与 migration 锁序一致的依赖顺序（exec_inbox 先于其源 ws_outbox、
    # ws_inbox 先于其源 exec_outbox），避免 verify 读序与 downgrade 锁序 AB-BA。
    scope_tables = [
        "agent_execution_inbox",
        "agent_workspace_outbox",
        "agent_workspace_inbox",
        "agent_execution_outbox",
    ]
    ref_tables = ["agent_workspace_outbox", "agent_execution_outbox", "agent_run_events"]
    async with session_factory() as session, session.begin():
        for table in scope_tables:
            owner = OWNER_BY_TABLE[table]
            # scope 维：未填 scope 且无 scope 类 issue 的行数（owner 绑定）。B7:817「每行
            # 必登记」无类型豁免（复核 #6）：mismatch 行经 _backfill_source_row 路由到
            # ambiguous 已登记 ambiguous_mapping，故 verify 覆盖全部 NULL-scope 行。
            # 第七轮复核 #1：issue_code 与 reconcile_class 须同时精确匹配（防错 class
            # 冒充——DB CHECK 只能挡新写，存量/绕过 CHECK 的错 class 行须由 verify 检出）。
            # 第八轮复核 #2：issue_code 还须**按来源表**精确匹配——每表只接受自己的
            # source-missing code（_SOURCE_MISSING_ISSUE[table]）+ 通用 mismatch/ambiguous/
            # orphan code；错表 code（如 ws outbox 塞 source_run_missing）不得满足。
            scope_issue_codes = (
                "'" + _SOURCE_MISSING_ISSUE[table] + "','cross_tenant_mismatch',"
                "'ambiguous_mapping','conversation_deleted_orphan'"
            )
            scope_missing = (
                await session.execute(
                    text(
                        f"SELECT count(*) FROM metaedu.{table} t "
                        f"WHERE t.tenant_id = :t AND t.conversation_id IS NULL "
                        f"AND NOT EXISTS ("
                        f"  SELECT 1 FROM metaedu.agent_transport_scope_reconcile r "
                        f"  WHERE r.tenant_id = t.tenant_id AND r.owner_key = :o "
                        f"  AND r.source_table = :st "
                        f"  AND r.source_row_id = t.id AND r.issue_code IN ("
                        f"    {scope_issue_codes})"
                        f"  AND r.reconcile_class = CASE "
                        f"    WHEN r.issue_code = 'conversation_deleted_orphan' "
                        f"    THEN 'orphan' ELSE 'tenant_scope' END)"
                    ),
                    {"t": tenant_id, "o": owner, "st": table},
                )
            ).scalar()
            if scope_missing:
                problems.append(f"{table}: {scope_missing} NULL-scope 行无 scope 类 issue")
        # epoch 维（仅 4 张 transport 表有 producer_purge_revision 列；owner 绑定；
        # B3:778「每行必登记」无类型豁免，mismatch 行经 ambiguous 路径已登记
        # epoch_unresolvable）。第七轮复核 #1 + 第八轮复核 #5 + 第九轮复核 #1：
        # epoch_unresolvable 的 class 须与行状态**精确**一一对应，且 orphan 判据
        # **独立于 ledger**（不得由 conversation_deleted_orphan issue 自证——DB CHECK
        # 只约束 code/class 组合、无法验证来源已删；伪 orphan issue 会让 live
        # Conversation 的未知 epoch 不触发 purge gate）。每行按来源矩阵独立解析
        # resolution（resolved / orphan / unknown），再要求对应 class：
        # resolved（来源存在且同 tenant 且 Conversation 存在且无冲突）->
        # conversation_scope；orphan（来源解析的 Conversation 已物理删除）-> orphan；
        # 其余（源缺失 / 跨 tenant / ambiguous / 冲突）-> tenant_scope。
        for table in scope_tables:
            owner = OWNER_BY_TABLE[table]
            src_table_s, join_col_s = _MISMATCH_SOURCE_BY_TABLE[table]
            # LATERAL 按来源矩阵独立解析 expected class（不读 ledger 自证）。
            # 注意：f-string 隐式拼接无换行，SQL 内不得使用 -- 注释（会吞掉后续语句）。
            expected_class = (
                f"LATERAL (SELECT CASE "
                f"  WHEN NOT EXISTS(SELECT 1 FROM metaedu.{src_table_s} s "
                f"    WHERE s.id = t.{join_col_s} AND s.tenant_id = t.tenant_id) "
                f"    THEN 'tenant_scope' "
                f"  WHEN EXISTS(SELECT 1 FROM metaedu.{src_table_s} s "
                f"    WHERE s.id = t.{join_col_s} AND s.tenant_id = t.tenant_id "
                f"    AND s.conversation_id IS NULL) THEN 'tenant_scope' "
                f"  WHEN EXISTS(SELECT 1 FROM metaedu.{src_table_s} s "
                f"    WHERE s.id = t.{join_col_s} AND s.tenant_id = t.tenant_id "
                f"    AND s.conversation_id IS NOT NULL "
                f"    AND NOT EXISTS(SELECT 1 FROM metaedu.agent_conversations c "
                f"      WHERE c.tenant_id = t.tenant_id AND c.id = s.conversation_id)) "
                f"    THEN 'orphan' "
                f"  WHEN EXISTS(SELECT 1 FROM metaedu.agent_transport_scope_reconcile rc "
                f"    WHERE rc.tenant_id = t.tenant_id AND rc.owner_key = :o "
                f"    AND rc.source_table = :st AND rc.source_row_id = t.id "
                f"    AND rc.issue_code IN ('ambiguous_mapping','cross_tenant_mismatch')) "
                f"    THEN 'tenant_scope' "
                f"  ELSE 'conversation_scope' END AS cls "
                f"  FROM metaedu.{src_table_s} s WHERE s.id = t.{join_col_s} "
                f"  AND s.tenant_id = t.tenant_id "
                f"  LIMIT 1) exp ON true "
            )
            epoch_missing = (
                await session.execute(
                    text(
                        f"SELECT count(*) FROM metaedu.{table} t "
                        f"LEFT JOIN {expected_class}"
                        f"WHERE t.tenant_id = :t AND t.producer_purge_revision IS NULL "
                        f"AND NOT EXISTS ("
                        f"  SELECT 1 FROM metaedu.agent_transport_scope_reconcile r "
                        f"  WHERE r.tenant_id = t.tenant_id AND r.owner_key = :o "
                        f"  AND r.source_table = :st "
                        f"  AND r.source_row_id = t.id "
                        f"  AND r.issue_code = 'epoch_unresolvable'"
                        f"  AND r.reconcile_class = COALESCE(exp.cls, 'tenant_scope'))"
                    ),
                    {"t": tenant_id, "o": owner, "st": table},
                )
            ).scalar()
            if epoch_missing:
                problems.append(
                    f"{table}: {epoch_missing} NULL-epoch 行无 epoch_unresolvable issue"
                )
        # external ref 维：ref-bearing 行的**当前 ref_value**须在 external ledger 登记
        # （P1-1 + 复核 #2：匹配 er.ref_value = t.payload_ref，ref 改写后旧登记不算数）。
        # B5:800「每个 ref-bearing source 行的每个非空 ref 恰好一条」无类型豁免：mismatch
        # 行带 ref 亦由 _backfill_source_row 登记，verify 覆盖全部 ref-bearing 行。
        for table in ref_tables:
            ref_missing = (
                await session.execute(
                    text(
                        f"SELECT count(*) FROM metaedu.{table} t "
                        f"WHERE t.tenant_id = :t AND t.payload_ref IS NOT NULL "
                        f"AND NOT EXISTS ("
                        f"  SELECT 1 FROM metaedu.agent_external_object_refs er "
                        f"  WHERE er.tenant_id = t.tenant_id AND er.owner_key = :o "
                        f"  AND er.source_table = :st AND er.source_row_id = t.id "
                        f"  AND er.ref_value = t.payload_ref)"
                    ),
                    {"t": tenant_id, "o": _EXTERNAL_OWNER, "st": table},
                )
            ).scalar()
            if ref_missing:
                problems.append(
                    f"{table}: {ref_missing} ref-bearing 行未登记 external ref"
                )
            # 第九轮复核 #2 + 第十轮复核 #1：绑定一致性——已登记 ref 的
            # conversation_id 须与**完整来源解析**的 expected 绑定一致。expected 按
            # LATERAL CASE：仅 resolved && !conflict 取源 Conversation，其余（orphan /
            # 跨 tenant / 源缺失 / ambiguous / 冲突）一律 NULL——与生产登记路径
            # （_backfill_source_row）完全一致，杜绝 orphan+ref 合法行误报。
            if table != "agent_run_events":
                src_table_r, join_col_r = _MISMATCH_SOURCE_BY_TABLE[table]
                ref_binding = (
                    await session.execute(
                        text(
                            f"SELECT count(*) FROM metaedu.{table} t "
                            f"LEFT JOIN LATERAL ("
                            f"  SELECT CASE "
                            f"    WHEN NOT EXISTS(SELECT 1 FROM metaedu.{src_table_r} s "
                            f"      WHERE s.id = t.{join_col_r} "
                            f"      AND s.tenant_id = t.tenant_id) THEN NULL "
                            f"    WHEN EXISTS(SELECT 1 FROM metaedu.{src_table_r} s "
                            f"      WHERE s.id = t.{join_col_r} "
                            f"      AND s.tenant_id = t.tenant_id "
                            f"      AND (s.conversation_id IS NULL"
                            f"        OR s.conversation_id <> t.conversation_id"
                            f"        OR NOT EXISTS(SELECT 1 FROM "
                            f"          metaedu.agent_conversations c "
                            f"          WHERE c.tenant_id = t.tenant_id "
                            f"          AND c.id = s.conversation_id))) THEN NULL "
                            f"    ELSE (SELECT s.conversation_id FROM "
                            f"      metaedu.{src_table_r} s WHERE s.id = t.{join_col_r} "
                            f"      AND s.tenant_id = t.tenant_id LIMIT 1) END AS exp "
                            f"  FROM metaedu.{src_table_r} s WHERE s.id = t.{join_col_r} "
                            f"  AND s.tenant_id = t.tenant_id LIMIT 1) exp ON true "
                            f"WHERE t.tenant_id = :t AND t.payload_ref IS NOT NULL "
                            f"AND EXISTS ("
                            f"  SELECT 1 FROM metaedu.agent_external_object_refs er "
                            f"  WHERE er.tenant_id = t.tenant_id AND er.owner_key = :o "
                            f"  AND er.source_table = :st AND er.source_row_id = t.id "
                            f"  AND er.ref_value = t.payload_ref "
                            f"  AND er.conversation_id IS DISTINCT FROM exp.exp)"
                        ),
                        {"t": tenant_id, "o": _EXTERNAL_OWNER, "st": table},
                    )
                ).scalar()
                if ref_binding:
                    problems.append(
                        f"{table}: {ref_binding} ref 绑定 conversation_id 与来源解析不一致"
                    )
            else:
                # 第十轮复核 #2：run_events expected = 行内 conversation_id（恒有
                # scope），错误绑定须被 verify 检出（fail closed）。
                ref_binding = (
                    await session.execute(
                        text(
                            f"SELECT count(*) FROM metaedu.{table} t "
                            f"WHERE t.tenant_id = :t AND t.payload_ref IS NOT NULL "
                            f"AND EXISTS ("
                            f"  SELECT 1 FROM metaedu.agent_external_object_refs er "
                            f"  WHERE er.tenant_id = t.tenant_id AND er.owner_key = :o "
                            f"  AND er.source_table = :st AND er.source_row_id = t.id "
                            f"  AND er.ref_value = t.payload_ref "
                            f"  AND er.conversation_id IS DISTINCT FROM t.conversation_id)"
                        ),
                        {"t": tenant_id, "o": _EXTERNAL_OWNER, "st": table},
                    )
                ).scalar()
                if ref_binding:
                    problems.append(
                        f"{table}: {ref_binding} ref 绑定 conversation_id 与行内不一致"
                    )
        # scope vs 来源矩阵一致性维（第三轮复核 #1/#2 + 第五轮复核 #3，read-only）：
        # discovery pass 已在集合锁下为 scope-set mismatch 行登记 tenant_scope issue；verify
        # 只读验证「每个 mismatch 行都有**精确**对应 issue」--按 mismatch 分支要求准确的
        # issue_code + owner_key 绑定 + reconcile_class='tenant_scope' + conversation_id
        # IS NULL（防错 owner / ambiguous_mapping 与 cross_tenant_mismatch 相互冒充假绿）。
        # mismatch 定义与 _select_actionable_batch discovery 分支完全一致。
        for table, src_table, join_col in [
            ("agent_execution_inbox", "agent_workspace_outbox", "event_id"),
            ("agent_workspace_outbox", "agent_messages", "aggregate_id"),
            ("agent_workspace_inbox", "agent_execution_outbox", "event_id"),
            ("agent_execution_outbox", "agent_runs", "aggregate_id"),
        ]:
            owner = OWNER_BY_TABLE[table]
            # A≠B/未知分支（第八轮复核 #4 含源 scope NULL）：来源同 tenant 但
            # conversation_id 不同，或来源 conversation_id 为 NULL（源 scope 未知）-> 须有
            # ambiguous_mapping。mismatch 定义与 _select_actionable_batch discovery 一致。
            same_tenant_diff = (
                f"(EXISTS(SELECT 1 FROM metaedu.{src_table} s WHERE s.id = t.{join_col} "
                f"AND s.tenant_id = t.tenant_id AND s.conversation_id IS NOT NULL "
                f"AND s.conversation_id <> t.conversation_id)"
                f" OR EXISTS(SELECT 1 FROM metaedu.{src_table} s WHERE s.id = t.{join_col} "
                f"AND s.tenant_id = t.tenant_id AND s.conversation_id IS NULL))"
            )
            ab_missing = (
                await session.execute(
                    text(
                        f"SELECT count(*) FROM metaedu.{table} t "
                        f"WHERE t.tenant_id = :t AND t.conversation_id IS NOT NULL "
                        f"AND {same_tenant_diff}"
                        f" AND NOT EXISTS ("
                        f"  SELECT 1 FROM metaedu.agent_transport_scope_reconcile r "
                        f"  WHERE r.tenant_id = t.tenant_id AND r.owner_key = :o "
                        f"  AND r.source_table = :st AND r.source_row_id = t.id "
                        f"  AND r.issue_code = 'ambiguous_mapping' "
                        f"  AND r.reconcile_class = 'tenant_scope' "
                        f"  AND r.conversation_id IS NULL)"
                    ),
                    {"t": tenant_id, "o": owner, "st": table},
                )
            ).scalar()
            if ab_missing:
                problems.append(
                    f"{table}: {ab_missing} A≠B mismatch 行缺 owner 正确的 ambiguous_mapping"
                    f"（tenant_scope + conversation_id NULL）"
                )
            # 跨 tenant 分支：来源跨 tenant -> 须有 cross_tenant_mismatch（同精确绑定）。
            cross_tenant = (
                f"EXISTS(SELECT 1 FROM metaedu.{src_table} s WHERE s.id = t.{join_col} "
                f"AND s.tenant_id <> t.tenant_id)"
            )
            ct_missing = (
                await session.execute(
                    text(
                        f"SELECT count(*) FROM metaedu.{table} t "
                        f"WHERE t.tenant_id = :t AND t.conversation_id IS NOT NULL "
                        f"AND {cross_tenant}"
                        f" AND NOT EXISTS ("
                        f"  SELECT 1 FROM metaedu.agent_transport_scope_reconcile r "
                        f"  WHERE r.tenant_id = t.tenant_id AND r.owner_key = :o "
                        f"  AND r.source_table = :st AND r.source_row_id = t.id "
                        f"  AND r.issue_code = 'cross_tenant_mismatch' "
                        f"  AND r.reconcile_class = 'tenant_scope' "
                        f"  AND r.conversation_id IS NULL)"
                    ),
                    {"t": tenant_id, "o": owner, "st": table},
                )
            ).scalar()
            if ct_missing:
                problems.append(
                    f"{table}: {ct_missing} 跨 tenant mismatch 行缺 owner 正确的 "
                    f"cross_tenant_mismatch（tenant_scope + conversation_id NULL）"
                )
        # 投影↔ledger 一致性维（复核 #5 / B4 复核 #8）：行内 scope_reconcile_state 是
        # 派生只读投影，必须与该 owner 的完整 issue 集一致——「行内已 reconciled 但
        # ledger 无对应 resolved 行」或任何投影/ledger 漂移即数据异常，fail closed。
        # 聚合规则与 _recompute_projection 完全一致（orphan > pending > reconciled，
        # 无 issue -> 投影须为 NULL），owner 绑定（P2-2）。
        for table in scope_tables:
            owner = OWNER_BY_TABLE[table]
            drift = (
                await session.execute(
                    text(
                        f"SELECT count(*) FROM metaedu.{table} t "
                        f"LEFT JOIN LATERAL ("
                        f"  SELECT CASE "
                        f"    WHEN count(*) = 0 THEN NULL "
                        f"    WHEN bool_or(r.reconcile_class = 'orphan') THEN 'orphan' "
                        f"    WHEN bool_or(r.state <> 'resolved') THEN 'pending' "
                        f"    ELSE 'reconciled' END AS expected "
                        f"  FROM metaedu.agent_transport_scope_reconcile r "
                        f"  WHERE r.tenant_id = t.tenant_id AND r.owner_key = :o "
                        f"  AND r.source_table = :st AND r.source_row_id = t.id"
                        f") agg ON true "
                        f"WHERE t.tenant_id = :t "
                        f"  AND NOT (t.scope_reconcile_state IS NOT DISTINCT FROM agg.expected)"
                    ),
                    {"t": tenant_id, "o": owner, "st": table},
                )
            ).scalar()
            if drift:
                problems.append(
                    f"{table}: {drift} 行行内投影与 ledger issue 集不一致"
                )
    return (not problems), "; ".join(problems)


def _validate_backfill_params(
    *, batch_size: int, max_rows: int | None, batch_interval_seconds: float
) -> None:
    """CLI / API 共用参数校验（第六轮复核 #2：CLI 在 tenant 循环前统一拒绝非法参数）。

    规则与 backfill_transport_scope 一致：batch_size>=1；max_rows 为 None 或 >=1；
    batch_interval_seconds 为非负有限数（NaN/负/Inf 拒绝）。放这里使 `_run_cli`
    在空 tenant 时也拒绝非法参数，而非静默返回 0。
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    if max_rows is not None and max_rows < 1:
        raise ValueError(f"max_rows must be None or >= 1, got {max_rows}")
    if not math.isfinite(batch_interval_seconds) or batch_interval_seconds < 0:
        raise ValueError(
            f"batch_interval_seconds must be a finite non-negative float, "
            f"got {batch_interval_seconds}"
        )


async def backfill_transport_scope(
    session_factory,
    *,
    tenant_id: uuid.UUID,
    batch_size: int = 100,
    max_rows: int | None = None,
    batch_interval_seconds: float = 0.0,
) -> ScopeBackfillReport:
    """为指定 tenant 回填 transport/external scope（可恢复、分批、幂等）。

    每行在独立短事务处理（取集合 advisory lock）；任一行失败计入 failures 并
    继续（fail closed 由 report.ok 体现）。``batch_interval_seconds`` 为每批之间
    的休眠（B7 tenant 限流：逐 tenant + 每批间隔，避免压库）。

    **恢复路径（复核 #3 / B7）**：不提供跨调用游标——随机 UUID 主键的 keyset 游标
    跨表复用会跳行、且 point-in-time 本就非完备性证明（B7）。中断/失败恢复一律
    从 tenant 起点（每次调用即全量幂等重扫，已填/已登记行幂等跳过）；``max_rows``
    仅用于限流分批，``completed`` 由截断标志判定。
    """
    _validate_backfill_params(
        batch_size=batch_size,
        max_rows=max_rows,
        batch_interval_seconds=batch_interval_seconds,
    )
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
    # 每张表用独立的进程内 keyset 游标（同表内单调推进、从 None=表起点开始），仅用于
    # 单次调用内的分批分页；不跨调用持久化、不跨表复用（复核 #3：跨调用/跨表游标跳行）。
    cursors: dict[str, uuid.UUID | None] = {t: None for t in tables}

    def _hit_cap() -> bool:
        return max_rows is not None and processed >= max_rows

    for table in tables:
        while not _hit_cap():
            cursor = cursors[table]
            async with session_factory() as session, session.begin():
                batch = await _select_actionable_batch(
                    session,
                    table=table,
                    tenant_id=tenant_id,
                    after_id=cursor,
                    batch_size=batch_size,
                )
            if not batch:
                break
            for source_row_id, join_key, payload_ref in batch:
                if _hit_cap():
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
                cursors[table] = source_row_id
            # 第五轮复核 #4：间隔在 break 之前--即使 partial batch（不足 batch_size）
            # 也休眠，避免大量小 tenant 连续执行无批间隔。
            if batch_interval_seconds > 0:
                await asyncio.sleep(batch_interval_seconds)
            if len(batch) < batch_size:
                break
        if _hit_cap():
            break
    # run_events external ref 登记（P1-1：扫描谓词 = payload_ref 非空且**未登记**，
    # 与 verify 的 external 维一致——被并发 SKIP LOCKED 跳过而漏登记的行下次重跑会
    # 被重新选中补登，自愈；SKIP LOCKED 仅并发去重优化，不再是完备性依赖）。幂等：
    # ledger 唯一键 ON CONFLICT 兜底，重跑不重复。进程内独立游标，不跨调用。
    run_event_cursor: uuid.UUID | None = None
    while not _hit_cap():
        async with session_factory() as session, session.begin():
            event_batch = await _select_ref_event_batch(
                session,
                tenant_id=tenant_id,
                after_id=run_event_cursor,
                batch_size=batch_size,
            )
        if not event_batch:
            break
        for source_row_id, conversation_id, _run_id, ref_value in event_batch:
            if _hit_cap():
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
            run_event_cursor = source_row_id
        if batch_interval_seconds > 0:
            await asyncio.sleep(batch_interval_seconds)
        if len(event_batch) < batch_size:
            break
    # P2-3：completed 仅当**没有因 max_rows 截断**且本次扫描已覆盖全部待处理行。
    # 判定依据是截断标志（一旦 _hit_cap() 中断任一循环即未完成），而非易错的
    # exhausted 标志（max_rows == batch_size 且恰好到边界时 exhausted 误判）。
    truncated = _hit_cap()
    report.completed = not truncated
    # 第五轮复核 #4：rows_attempted = processed（含失败行），供 CLI 按尝试数做全局预算
    # （rows_scanned 只计成功行，失败行会低估预算导致超发）。
    report.rows_attempted = processed
    # 最终 verify（scope/epoch/external-ref/投影一致性/scope-vs-来源 五维 fail closed）。
    verify_ok, detail = await _verify_scope_epoch(session_factory, tenant_id=tenant_id)
    report.verify_failed = not verify_ok
    report.verify_detail = detail
    return report


# ---------------------------------------------------------------------------
# 可执行入口（运维命令）：python -m app.composition.agent_transport_backfill
#
# 退出码契约（自动化调用）：
#   0 = 全部 tenant 完成、无失败、verify 全绿；
#   1 = 有失败（report.failures）或 verify_failed；
#   2 = 未完成（--max-rows 截断），须重跑（tenant 起点幂等重扫，无游标续跑）。
# ---------------------------------------------------------------------------


def _make_session_factory():
    """构造生产 session factory（独立可注入以便测试替换）。

    使用方负责在结束后 dispose 引擎；返回 (session_factory, engine)。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings

    engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


async def _list_tenant_ids(session_factory) -> list[uuid.UUID]:
    """取全部 tenant id（按 id 排序，逐 tenant 处理，B7）。"""
    async with session_factory() as session:
        rows = await session.execute(text("SELECT id FROM metaedu.tenants ORDER BY id"))
        return [row[0] for row in rows.all()]


async def _run_cli(args: object) -> int:
    factory, engine = _make_session_factory()
    try:
        # 第六轮复核 #2：CLI 参数在 tenant 枚举/循环前统一校验，空 tenant 也拒绝
        # 非法参数（此前只靠 backfill_transport_scope 间接触发，空 tenant 直接返回 0）。
        _validate_backfill_params(
            batch_size=args.batch_size,  # type: ignore[attr-defined]
            max_rows=args.max_rows,  # type: ignore[attr-defined]
            batch_interval_seconds=args.batch_interval_seconds,  # type: ignore[attr-defined]
        )
        if args.tenant_id:  # type: ignore[attr-defined]
            tenant_ids = [uuid.UUID(args.tenant_id)]  # type: ignore[attr-defined]
        else:
            tenant_ids = await _list_tenant_ids(factory)
        total_failures = 0
        total_attempted = 0
        any_incomplete = False
        completed_verify_failed = False
        for tid in tenant_ids:
            if args.max_rows is not None:  # type: ignore[attr-defined]
                # 第五轮复核 #4：按 rows_attempted（含失败行）扣全局预算，失败行不再漏算。
                remaining = args.max_rows - total_attempted  # type: ignore[attr-defined]
                if remaining <= 0:
                    any_incomplete = True
                    break
            else:
                remaining = None
            report = await backfill_transport_scope(
                factory,
                tenant_id=tid,
                batch_size=args.batch_size,  # type: ignore[attr-defined]
                max_rows=remaining,
                batch_interval_seconds=args.batch_interval_seconds,  # type: ignore[attr-defined]
            )
            total_attempted += report.rows_attempted
            total_failures += report.failure_count
            # 第五轮复核 #2：completed 的 verify_failed 是真实数据问题（非截断预期），
            # 优先级高于后续 tenant 的截断未完成（exit 1 而非 2）。
            if report.verify_failed and report.completed:
                completed_verify_failed = True
            print(  # noqa: T201
                f"tenant {tid}: attempted={report.rows_attempted} "
                f"scanned={report.rows_scanned} "
                f"scope_backfilled={report.scope_backfilled} "
                f"scope_already_present={report.scope_already_present} "
                f"issues={report.reconcile_issues_registered} "
                f"refs={report.external_refs_registered} "
                f"failed={report.failure_count} completed={report.completed} "
                f"verify_failed={report.verify_failed}"
            )
            for failure in report.failures:
                print(  # noqa: T201
                    f"  failed: table={failure.source_table} "
                    f"row={failure.source_row_id} reason={failure.reason_code} "
                    f"error={failure.error_type}"
                )
            if not report.completed:
                any_incomplete = True
                break  # --max-rows 截断：重跑续行（tenant 起点幂等重扫，无游标）
    finally:
        await engine.dispose()
    # 退出码优先级：1（失败 / completed 的 verify_failed）先于 2（--max-rows 截断未完成）。
    # 截断状态下的 verify_failed 是未处理行的预期结果，不按失败计（算子重跑续行即可）；
    # 但已 completed 的 tenant 的 verify_failed 是真实数据问题，优先级高于后续 tenant 的截断。
    if total_failures > 0 or completed_verify_failed:
        print(  # noqa: T201
            "failures/verify_failed present: rerun from tenant start (no cursor) "
            "to retry idempotently: python -m app.composition.agent_transport_backfill"
        )
        return 1
    if any_incomplete:
        print(  # noqa: T201
            "incomplete (--max-rows hit): rerun to continue (tenant-start rescan, idempotent)"
        )
        return 2
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m app.composition.agent_transport_backfill",
        description=(
            "为既有 transport/external 行幂等回填 owner scope + reconcile/external"
            " ledger（可恢复/分批/tenant 限流）。"
        ),
    )
    parser.add_argument(
        "--tenant-id",
        default=None,
        help="目标 tenant UUID；省略则逐 tenant 处理全部 tenant（B7）",
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="单次全局行数上限（across tenants）；达到后 exit 2，重跑续行（幂等）",
    )
    parser.add_argument(
        "--batch-interval-seconds",
        type=float,
        default=0.0,
        help="每批之间的休眠秒数（B7 tenant 限流，避免压库）",
    )
    return asyncio.run(_run_cli(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
