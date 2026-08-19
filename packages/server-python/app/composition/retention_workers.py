"""R1-S6 S6-I1: retention workers——``run_event_retention`` + ``run_audit_retention``。

契约：Plan §R1-S6-2/3（冻结，经 PR #581 并入 main ``01524667``）。两个 worker 均
为 ``execution.core.v1`` **N 类写者**（S6-4 登记）：非正文 tombstone/删除维护路径，
自管短事务分批（默认 100 行/批）、tenant 谓词、幂等（谓词 + 行锁）、DB clock
（``clock_timestamp()``）裁决。锁序复制 S6-2.4/S6-3.3（裁决三）：**Run 行 FOR
UPDATE**，不取 Conversation 行锁、不取 owner advisory、不取 fence——hold 检查 =
语句级无锁 EXISTS（避免持 Run 锁等 Conversation 的 AB-BA）。

S6-I1 不启用任何生产 wiring（无 scheduler tick、无 HTTP/CLI/API、不触碰 S5
production erase 组合根）；本模块为独立可调用函数，测试直接经
``async_sessionmaker`` 调用。日志/指标只允许计数与 time（R1-AC10 / S4-F F-3
sentinel 判别），不记录 payload 正文、event ref、Runtime session ref 或自由文本
reason。
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# 冻结时间基线（S6-1 item 2，Spec §3）：RunEvent 热重放 90 天（``persisted_at``
# 起算）；AgentRun 终态/审计 envelope 365 天（``ended_at`` 起算）。当前无 tenant
# policy 表，worker 侧策略 = 冻结默认基线，hardcode（S6-7 裁决六）。
_EVENT_RETENTION_DAYS = 90
_AUDIT_RETENTION_DAYS = 365

_TERMINAL_RUN_STATUSES = ("completed", "failed", "cancelled", "expired")

# 事件类型判别（S6-3 item 1 blocked 清单）。
_EVENT_TOOL_OUTCOME_UNKNOWN = "tool.outcome_unknown"
_EVENT_TOOL_RESOLVE = ("tool.started", "tool.completed", "tool.failed")
_EVENT_APPROVAL_REQUESTED = "approval.requested"
_EVENT_APPROVAL_RESOLVE = ("approval.resolved", "approval.expired")

# outbox 非终态（ck_agent_exec_outbox_status 终态 = published/cancelled/suppressed）。
_OUTBOX_NON_TERMINAL = ("pending", "claimed", "dead_letter")


@dataclass(frozen=True, slots=True)
class EventRetentionResult:
    """run_event_retention 的可观察计数（R1-AC10：只含计数，不含正文/ref）。

    - ``payloads_expired``：payload expiry 行数（inline 清除 + external 仅 state）。
    - ``envelopes_pruned``：连续前缀删除的 envelope 行数。
    - ``first_available_event_seq_advanced``：推进了 ``first_available_event_seq``
      的 run 数（同事务置 ``event_log_complete=False``）。
    - ``runs_processed``：本批实际处理（锁内重读命中）的 run 数。
    - ``runs_skipped_hold``：因 Conversation 存在 active hold 而跳过的 run 数。
    """

    payloads_expired: int = 0
    envelopes_pruned: int = 0
    first_available_event_seq_advanced: int = 0
    runs_processed: int = 0
    runs_skipped_hold: int = 0


@dataclass(frozen=True, slots=True)
class AuditRetentionResult:
    """run_audit_retention 的可观察计数。

    ``blocked_reasons`` 只含结构化 reason code（S6-3 item 5 / R1-AC10），非自由文本。
    """

    runs_pruned: int = 0
    runs_blocked: int = 0
    blocked_reasons: Counter[str] = field(default_factory=Counter)
    runs_skipped_hold: int = 0


async def _db_now(session: AsyncSession) -> datetime:
    result = await session.scalar(text("SELECT clock_timestamp()"))
    assert result is not None, "clock_timestamp() must return a value"
    return result


async def _effective_now(session: AsyncSession, now: datetime | None) -> datetime:
    """DB clock 优先；``now`` 仅允许测试注入（S6-1 item 1）。"""
    if now is not None:
        return now
    return await _db_now(session)


async def _has_active_hold_stmt(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    now: datetime,
) -> bool:
    """语句级无锁 EXISTS（S6-2.4/S6-3.3 裁决三）：hold active = state='active'
    且未过期（``expires_at NULL OR > now``，S6-1 裁决一读侧语义）。不取
    Conversation 行锁。"""
    result = await session.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM "
            "metaedu.agent_conversation_legal_holds "
            "WHERE tenant_id = :tid AND conversation_id = :cid "
            "AND state = 'active' "
            "AND (expires_at IS NULL OR expires_at > :now))"
        ),
        {"tid": tenant_id, "cid": conversation_id, "now": now},
    )
    return bool(result.scalar_one())


async def _lock_run_row(
    session: AsyncSession, *, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> dict | None:
    row = await session.execute(
        text(
            "SELECT id, tenant_id, conversation_id, first_available_event_seq, "
            "next_event_seq, event_log_complete "
            "FROM metaedu.agent_runs "
            "WHERE tenant_id = :tid AND id = :rid FOR UPDATE"
        ),
        {"tid": tenant_id, "rid": run_id},
    )
    mapping = row.mappings().first()
    return dict(mapping) if mapping is not None else None


# ---------------------------------------------------------------------------
# run_event_retention
# ---------------------------------------------------------------------------


async def run_event_retention(
    session_factory: async_sessionmaker,
    *,
    batch_size: int = 100,
    now: datetime | None = None,
) -> EventRetentionResult:
    """RunEvent payload expiry + 连续 envelope prune + ``first_available_event_seq``
    推进（S6-2 冻结；锁域 S6-2.4）。

    每个短事务：取 DB clock（``now`` 缺省）→ 选候选 run（存在到期 event 行且
    Conversation 无 active hold）→ 逐 run 锁 Run 行 FOR UPDATE → 锁内重读谓词 +
    语句级 hold 重验 → payload expiry → 连续前缀 prune + 同事务推进
    ``first_available_event_seq`` + 置 ``event_log_complete=False`` → commit。

    幂等：已处理行不命中谓词；多实例并发由 Run 行锁串行（S6-2.4）。
    ``batch_size`` 为该批最多处理的 run 数（自管短事务边界；每 run 的 event 行数
    由其 envelope 大小界定——低频全表扫描可承受，量级评估登记见契约 S6-2.4）。

    hold-skip 的 run 在本轮 invocation 内保持 held（候选查询已排除持锁 run，
    锁内重验跳过只在候选↔锁的竞态窗口出现），用 ``_seen_hold_skipped`` 排除后续
    批次候选，避免「候选仍匹配 + 锁内重验持续跳过 → 死循环」。
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    total = EventRetentionResult()
    seen_hold_skipped: set[tuple[uuid.UUID, uuid.UUID]] = set()
    while True:
        async with session_factory() as session, session.begin():
            effective_now = await _effective_now(session, now)
            candidates = [
                (tid, rid, cid)
                for (tid, rid, cid) in await _event_retention_candidates(
                    session, effective_now, limit=batch_size
                )
                if (tid, rid) not in seen_hold_skipped
            ]
            if not candidates:
                break
            for tenant_id, run_id, conversation_id in candidates:
                run_row = await _lock_run_row(
                    session, tenant_id=tenant_id, run_id=run_id
                )
                if run_row is None:
                    continue
                if await _has_active_hold_stmt(
                    session,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    now=effective_now,
                ):
                    seen_hold_skipped.add((tenant_id, run_id))
                    total = replace(total, runs_skipped_hold=total.runs_skipped_hold + 1)
                    continue
                run_now = await _effective_now(session, now)
                expired = await _expire_expired_payloads(
                    session, tenant_id=tenant_id, run_id=run_id, now=run_now
                )
                pruned, advanced = await _prune_expired_prefix(
                    session,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    now=run_now,
                    first_available_event_seq=run_row["first_available_event_seq"],
                )
                total = replace(
                    total,
                    payloads_expired=total.payloads_expired + expired,
                    envelopes_pruned=total.envelopes_pruned + pruned,
                    first_available_event_seq_advanced=(
                        total.first_available_event_seq_advanced + advanced
                    ),
                    runs_processed=total.runs_processed + 1,
                )
    return total


async def _event_retention_candidates(
    session: AsyncSession, now: datetime, *, limit: int
) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    """候选 run：存在（a）到期 payload（inline/external，expires_at 或 persisted_at
    到期）或（b）**头行**（``seq = first_available_event_seq``）已 tombstone +
    envelope 到期（只有头行可删时前缀才可能推进——前缀从 ``first_available`` 起，
    头行不可删则没有任何行可删，避免「live 头行 + 尾部 tombstone 行」死循环
    候选）。且 Conversation 无 active hold（hold EXISTS 并入，避免浪费 Run 锁；
    锁内仍重验）。"""
    payload_cutoff = now - timedelta(days=_EVENT_RETENTION_DAYS)
    rows = await session.execute(
        text(
            "SELECT r.tenant_id AS tid, r.id AS rid, r.conversation_id AS cid "
            "FROM metaedu.agent_runs r "
            "WHERE EXISTS ("
            "  SELECT 1 FROM metaedu.agent_run_events e "
            "  WHERE e.tenant_id = r.tenant_id AND e.run_id = r.id AND ("
            "    (e.payload_state IN ('inline', 'external') "
            "     AND ((e.expires_at IS NOT NULL AND e.expires_at <= :now) "
            "          OR (e.expires_at IS NULL AND e.persisted_at <= :cutoff))) "
            "    OR (e.payload_state IN ('redacted', 'expired', 'archived') "
            "        AND e.payload_inline IS NULL AND e.payload_ref IS NULL "
            "        AND e.persisted_at <= :cutoff "
            "        AND e.seq = r.first_available_event_seq)"
            "  )"
            ") "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM metaedu.agent_conversation_legal_holds h "
            "  WHERE h.tenant_id = r.tenant_id "
            "    AND h.conversation_id = r.conversation_id "
            "    AND h.state = 'active' "
            "    AND (h.expires_at IS NULL OR h.expires_at > :now)"
            ") "
            "ORDER BY r.id LIMIT :limit"
        ),
        {"now": now, "cutoff": payload_cutoff, "limit": limit},
    )
    return [(row.tid, row.rid, row.cid) for row in rows.mappings()]


async def _expire_expired_payloads(
    session: AsyncSession, *, tenant_id: uuid.UUID, run_id: uuid.UUID, now: datetime
) -> int:
    """payload expiry（S6-2.2）：inline 行清 payload_inline + 转 ``expired``；
    external 行仅 state 转 ``expired``（payload_ref 保留——ref 清除唯一者 =
    external.payload.v1）。两写均须经 migration 043 guard 白名单放行（043(a)
    分支 1/2）。保留 seq/type/digest/size/media_type/classification/provenance/
    runtime 八元。"""
    payload_cutoff = now - timedelta(days=_EVENT_RETENTION_DAYS)
    inline_result = await session.execute(
        text(
            "UPDATE metaedu.agent_run_events "
            "SET payload_inline = NULL, payload_state = 'expired' "
            "WHERE tenant_id = :tid AND run_id = :rid "
            "AND payload_state = 'inline' "
            "AND ((expires_at IS NOT NULL AND expires_at <= :now) "
            "     OR (expires_at IS NULL AND persisted_at <= :cutoff))"
        ),
        {"tid": tenant_id, "rid": run_id, "now": now, "cutoff": payload_cutoff},
    )
    external_result = await session.execute(
        text(
            "UPDATE metaedu.agent_run_events "
            "SET payload_state = 'expired' "
            "WHERE tenant_id = :tid AND run_id = :rid "
            "AND payload_state = 'external' "
            "AND ((expires_at IS NOT NULL AND expires_at <= :now) "
            "     OR (expires_at IS NULL AND persisted_at <= :cutoff))"
        ),
        {"tid": tenant_id, "rid": run_id, "now": now, "cutoff": payload_cutoff},
    )
    if not isinstance(inline_result, CursorResult) or not isinstance(
        external_result, CursorResult
    ):
        raise RuntimeError("event retention UPDATE must return CursorResult")
    return int(inline_result.rowcount) + int(external_result.rowcount)


async def _prune_expired_prefix(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    now: datetime,
    first_available_event_seq: int,
) -> tuple[int, int]:
    """连续 envelope prune（S6-2.3）：只删从 ``first_available_event_seq`` 起
    连续存在且全部满足「payload 已 tombstone + envelope 到期」的行；任何非连续/
    未到期/未 tombstone 行立即停止。删除后同事务推进
    ``first_available_event_seq``（单调，受 CHECK ``<= next_event_seq`` 约束）+
    置 ``event_log_complete=False``。返回 ``(envelopes_pruned, advanced)``：
    ``advanced`` 恒等于 prune 是否发生（1=推进，0=未推进）。"""
    envelope_cutoff = now - timedelta(days=_EVENT_RETENTION_DAYS)
    prefix_rows = await session.execute(
        text(
            "SELECT seq FROM metaedu.agent_run_events "
            "WHERE tenant_id = :tid AND run_id = :rid "
            "AND seq >= :first_available "
            "AND payload_state IN ('redacted', 'expired', 'archived') "
            "AND payload_inline IS NULL AND payload_ref IS NULL "
            "AND persisted_at <= :cutoff "
            "ORDER BY seq"
        ),
        {
            "tid": tenant_id,
            "rid": run_id,
            "first_available": first_available_event_seq,
            "cutoff": envelope_cutoff,
        },
    )
    seqs = [int(row.seq) for row in prefix_rows.mappings()]
    delete_seqs: list[int] = []
    expected = first_available_event_seq
    for seq in seqs:
        if seq != expected:
            break
        delete_seqs.append(seq)
        expected += 1
    if not delete_seqs:
        return 0, 0
    await session.execute(
        text(
            "DELETE FROM metaedu.agent_run_events "
            "WHERE tenant_id = :tid AND run_id = :rid AND seq = ANY(:seqs)"
        ),
        {"tid": tenant_id, "rid": run_id, "seqs": delete_seqs},
    )
    new_first_available = delete_seqs[-1] + 1
    await session.execute(
        text(
            "UPDATE metaedu.agent_runs "
            "SET first_available_event_seq = :first_available, "
            "event_log_complete = false "
            "WHERE tenant_id = :tid AND id = :rid "
            "AND first_available_event_seq = :old_first_available"
        ),
        {
            "first_available": new_first_available,
            "tid": tenant_id,
            "rid": run_id,
            "old_first_available": first_available_event_seq,
        },
    )
    return len(delete_seqs), 1


# ---------------------------------------------------------------------------
# run_audit_retention
# ---------------------------------------------------------------------------


async def run_audit_retention(
    session_factory: async_sessionmaker,
    *,
    batch_size: int = 100,
    now: datetime | None = None,
) -> AuditRetentionResult:
    """AgentRun 终态/审计 envelope 365 天 prune（S6-3 冻结；锁域 S6-3.3）。

    每个短事务：取 DB clock → 选候选 run（终态 + ``ended_at`` 到期 + 无 active
    hold）→ 逐 run 锁 Run 行 FOR UPDATE → 锁内重验谓词 + 全部 blocked 前置
    （hold / events payload 未全 tombstone / outcome_unknown / 未解决审批 /
    projection reconcile 未完成 / 存活子 run）→ 通过则 children-first 同事务删除
    （turn_inputs → run_events → compat_outputs → run）→ commit。

    幂等：先查后删同事务，重入不命中已删行。与 ``run_event_retention`` 独立
    worker，二者对同一 run 的并发由 Run 行锁串行（S6-3.3）。

    blocked 的 run 在本轮 invocation 内保持 blocked（零写，无其他进程改状态），
    用 ``_seen_blocked`` 排除后续批次候选，避免「全部 blocked → 死循环」。
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    total = AuditRetentionResult()
    seen_blocked: set[tuple[uuid.UUID, uuid.UUID]] = set()
    while True:
        async with session_factory() as session, session.begin():
            effective_now = await _effective_now(session, now)
            candidates = [
                (tid, rid, cid)
                for (tid, rid, cid) in await _audit_retention_candidates(
                    session, effective_now, limit=batch_size
                )
                if (tid, rid) not in seen_blocked
            ]
            if not candidates:
                break
            for tenant_id, run_id, conversation_id in candidates:
                run_row = await _lock_run_row(
                    session, tenant_id=tenant_id, run_id=run_id
                )
                if run_row is None:
                    continue
                if await _has_active_hold_stmt(
                    session,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    now=effective_now,
                ):
                    total = replace(total, runs_skipped_hold=total.runs_skipped_hold + 1)
                    continue
                run_now = await _effective_now(session, now)
                reason = await _audit_blocked_reason(
                    session,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    conversation_id=conversation_id,
                    now=run_now,
                )
                if reason is not None:
                    seen_blocked.add((tenant_id, run_id))
                    total = replace(
                        total,
                        runs_blocked=total.runs_blocked + 1,
                        blocked_reasons=total.blocked_reasons
                        + Counter({reason: 1}),
                    )
                    continue
                await _delete_run_children_first(
                    session, tenant_id=tenant_id, run_id=run_id
                )
                total = replace(total, runs_pruned=total.runs_pruned + 1)
    return total


async def _audit_retention_candidates(
    session: AsyncSession, now: datetime, *, limit: int
) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    run_cutoff = now - timedelta(days=_AUDIT_RETENTION_DAYS)
    rows = await session.execute(
        text(
            "SELECT r.tenant_id AS tid, r.id AS rid, r.conversation_id AS cid "
            "FROM metaedu.agent_runs r "
            "WHERE r.status = ANY(:statuses) "
            "AND r.ended_at IS NOT NULL AND r.ended_at <= :cutoff "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM metaedu.agent_conversation_legal_holds h "
            "  WHERE h.tenant_id = r.tenant_id "
            "    AND h.conversation_id = r.conversation_id "
            "    AND h.state = 'active' "
            "    AND (h.expires_at IS NULL OR h.expires_at > :now)"
            ") "
            "ORDER BY r.id LIMIT :limit"
        ),
        {
            "statuses": list(_TERMINAL_RUN_STATUSES),
            "cutoff": run_cutoff,
            "now": now,
            "limit": limit,
        },
    )
    return [(row.tid, row.rid, row.cid) for row in rows.mappings()]


async def _audit_blocked_reason(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    conversation_id: uuid.UUID,
    now: datetime,
) -> str | None:
    """S6-3 item 1 blocked 前置（全真才可清理；任一命中 → 零写返回 reason code）。
    全部语句级重读，无附加行锁。"""
    if await _events_not_all_tombstoned(session, tenant_id=tenant_id, run_id=run_id):
        return "events_payload_not_tombstoned"
    if await _has_outcome_unknown_unresolved(
        session, tenant_id=tenant_id, run_id=run_id
    ):
        return "outcome_unknown"
    if await _has_unresolved_approval(session, tenant_id=tenant_id, run_id=run_id):
        return "unresolved_approval"
    if await _projection_reconcile_incomplete(
        session,
        tenant_id=tenant_id,
        run_id=run_id,
        conversation_id=conversation_id,
    ):
        return "projection_reconcile_incomplete"
    if await _has_surviving_child_run(session, tenant_id=tenant_id, run_id=run_id):
        return "surviving_child_run"
    return None


async def _events_not_all_tombstoned(
    session: AsyncSession, *, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> bool:
    result = await session.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM metaedu.agent_run_events "
            "  WHERE tenant_id = :tid AND run_id = :rid "
            "  AND NOT (payload_state IN ('redacted', 'expired', 'archived') "
            "           AND payload_inline IS NULL AND payload_ref IS NULL)"
            ")"
        ),
        {"tid": tenant_id, "rid": run_id},
    )
    return bool(result.scalar_one())


async def _has_outcome_unknown_unresolved(
    session: AsyncSession, *, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> bool:
    """``tool.outcome_unknown`` 无后续 resolve（seq 比较；S6-3 item 1）——resolve =
    后续任一 tool 生命周期 event（tool.started/completed/failed）。相关 envelope
    已随前缀剪除 → 判定基于现存 envelope，无法判定即 blocked（fail closed）。"""
    result = await session.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM metaedu.agent_run_events e1 "
            "  WHERE e1.tenant_id = :tid AND e1.run_id = :rid "
            "    AND e1.event_type = :unknown "
            "    AND NOT EXISTS ("
            "      SELECT 1 FROM metaedu.agent_run_events e2 "
            "      WHERE e2.tenant_id = e1.tenant_id AND e2.run_id = e1.run_id "
            "        AND e2.seq > e1.seq "
            "        AND e2.event_type = ANY(:resolves)"
            "    )"
            ")"
        ),
        {
            "tid": tenant_id,
            "rid": run_id,
            "unknown": _EVENT_TOOL_OUTCOME_UNKNOWN,
            "resolves": list(_EVENT_TOOL_RESOLVE),
        },
    )
    return bool(result.scalar_one())


async def _has_unresolved_approval(
    session: AsyncSession, *, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> bool:
    """``approval.requested`` 无对应 ``approval.resolved/expired``（seq 比较）。"""
    result = await session.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM metaedu.agent_run_events e1 "
            "  WHERE e1.tenant_id = :tid AND e1.run_id = :rid "
            "    AND e1.event_type = :requested "
            "    AND NOT EXISTS ("
            "      SELECT 1 FROM metaedu.agent_run_events e2 "
            "      WHERE e2.tenant_id = e1.tenant_id AND e2.run_id = e1.run_id "
            "        AND e2.seq > e1.seq "
            "        AND e2.event_type = ANY(:resolves)"
            "    )"
            ")"
        ),
        {
            "tid": tenant_id,
            "rid": run_id,
            "requested": _EVENT_APPROVAL_REQUESTED,
            "resolves": list(_EVENT_APPROVAL_RESOLVE),
        },
    )
    return bool(result.scalar_one())


async def _projection_reconcile_incomplete(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> bool:
    """run ``output_publish_state`` 非终态；或对应 outbox 非终态行；或 inbox
    非终态 receipt 行（``status='processing'``）。"""
    state_blocked = await session.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM metaedu.agent_runs "
            "  WHERE tenant_id = :tid AND id = :rid "
            "  AND output_publish_state IN ('pending', 'dead_letter')"
            ")"
        ),
        {"tid": tenant_id, "rid": run_id},
    )
    if bool(state_blocked.scalar_one()):
        return True
    outbox_blocked = await session.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM metaedu.agent_execution_outbox "
            "  WHERE tenant_id = :tid AND aggregate_id = :rid "
            "  AND status = ANY(:statuses)"
            ")"
        ),
        {"tid": tenant_id, "rid": run_id, "statuses": list(_OUTBOX_NON_TERMINAL)},
    )
    if bool(outbox_blocked.scalar_one()):
        return True
    inbox_blocked = await session.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM metaedu.agent_execution_inbox "
            "  WHERE tenant_id = :tid AND conversation_id = :cid "
            "  AND status = 'processing'"
            ")"
        ),
        {"tid": tenant_id, "cid": conversation_id},
    )
    return bool(inbox_blocked.scalar_one())


async def _has_surviving_child_run(
    session: AsyncSession, *, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> bool:
    result = await session.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM metaedu.agent_runs "
            "  WHERE tenant_id = :tid AND parent_run_id = :rid"
            ")"
        ),
        {"tid": tenant_id, "rid": run_id},
    )
    return bool(result.scalar_one())


async def _delete_run_children_first(
    session: AsyncSession, *, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> None:
    """children-first 显式删除顺序（S6-3.2 冻结）：``agent_turn_inputs`` →
    ``agent_run_events`` → ``agent_compatibility_outputs``（显式删，不依赖
    CASCADE 语义）→ ``agent_runs`` 行（最后）。``parent_run_id`` 自引用不在删除
    集合（父 run 仅当无存活子 run 时满足谓词）。``runtime_session_bindings`` /
    outbox/inbox 已终态行不随 run 删（S6-3.2 冻结边界）。"""
    await session.execute(
        text(
            "DELETE FROM metaedu.agent_turn_inputs "
            "WHERE tenant_id = :tid AND run_id = :rid"
        ),
        {"tid": tenant_id, "rid": run_id},
    )
    await session.execute(
        text(
            "DELETE FROM metaedu.agent_run_events "
            "WHERE tenant_id = :tid AND run_id = :rid"
        ),
        {"tid": tenant_id, "rid": run_id},
    )
    await session.execute(
        text(
            "DELETE FROM metaedu.agent_compatibility_outputs "
            "WHERE tenant_id = :tid AND run_id = :rid"
        ),
        {"tid": tenant_id, "rid": run_id},
    )
    await session.execute(
        text(
            "DELETE FROM metaedu.agent_runs "
            "WHERE tenant_id = :tid AND id = :rid"
        ),
        {"tid": tenant_id, "rid": run_id},
    )


__all__ = [
    "AuditRetentionResult",
    "EventRetentionResult",
    "run_audit_retention",
    "run_event_retention",
]
