"""R1-S5 SCH-B Owner Execution Orchestrator 真实 PG 验收（B/C/D stack root）。

契约：Plan §R1-S5-D S5-SCH-1.3/1.3b/1.4/2 + SCH-B 范围（S5-SCH-3）。

反例映射（每项具名 mutation，随实现 kill）：
- SCH-4 预算耗尽写 failed + reason 保留（M-SCH-B-4：failed 丢 reason）
- SCH-5 循环中途崩溃 takeover 后按 checkpoint 恢复、acked 不重跑（M：重跑 acked）
- SCH-6/7 跨 tenant 与旧 token 零写（M：裸 id 谓词 / 旧 token 仍写）
- owner 顺序（M：未按字典序）
- 每 owner 后 coordinator（M：漏聚合）
- erasing 只调 settlement port（M：erasing 直接 entry）
- blocked 白名单 vs 拒绝域（M：拒绝域仍 entry）
- pre-window 不耗预算（M：pre-window 计入预算）
- 周期 tick 全量重算（M：tick 漏候选）

边界：owner participant 经显式 port 注入；SCH-B 不直接写 fence（erasing 收口
与 failed-fence 收敛由窄 settlement port 承担）；不建生产组合根。
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from app.composition.agent_erasure_registry import registry_snapshot
from app.composition.conversation_purge_scheduler import (
    ConversationPurgeScheduler,
)
from app.composition.owner_execution_orchestrator import (
    OwnerEntryOutcome,
    OwnerEntryRequest,
    OwnerExecutionOrchestrator,
    SettlementPort,
)
from app.composition.transactional_projection_coordinator import (
    build_scan_providers,
)
from app.shared.schemas.canonical_json import canonical_digest

_OWNER_KEYS = [str(o["owner_key"]) for o in registry_snapshot()]
assert sorted(_OWNER_KEYS) == _OWNER_KEYS

_REASON_ERASE_TIMEOUT = "purge_blocked_by_external_erase_timeout"
_REASON_OUTCOME_UNKNOWN = "purge_blocked_by_external_outcome_unknown"
_REASON_LEGAL_HOLD = "purge_blocked_by_legal_hold"


# ---------------------------------------------------------------------------
# 种子 helpers
# ---------------------------------------------------------------------------


async def _seed_conversation(
    session, *, tenant_id: uuid.UUID | None = None, actor_state: str = "redacted"
) -> tuple[uuid.UUID, uuid.UUID]:
    tid = tenant_id or uuid.uuid4()
    cid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, "
            "creator_identity_digest, title, title_source, state, purge_after, "
            "purge_state, purge_revision, hold_revision, revision, created_at, "
            "updated_at) "
            "VALUES (:id, :tid, NULL, 'redacted', :digest, :identity, 't', "
            "'none', 'deleted', now() - interval '1 day', 'scheduled', 1, 0, "
            "1, now(), now())"
        ),
        {"id": cid, "tid": tid, "digest": "c" * 64, "identity": "d" * 64},
    )
    return tid, cid


async def _claim(session, tid, cid):
    return await ConversationPurgeScheduler(session).claim(
        tenant_id=tid,
        conversation_id=cid,
        retention_policy_snapshot={"conversation_recovery_days": 30},
    )


async def _cp(session, op_id, owner_key, col="state"):
    return (
        await session.execute(
            text(
                f"SELECT {col} FROM metaedu.agent_conversation_purge_owners "
                "WHERE purge_operation_id = :op AND owner_key = :k"
            ),
            {"op": op_id, "k": owner_key},
        )
    ).scalar_one_or_none()


async def _set_cp(session, op_id, owner_key, *, state, reason=None, attempt=None):
    sets = ["state = :state"]
    params = {"op": op_id, "k": owner_key, "state": state}
    if state == "acked":
        # ck_agent_purge_owner_ack：acked 必须携带 64 位 ack_digest。
        sets.append("ack_digest = :ack, checkpoint_digest = :ack")
        params["ack"] = "e" * 64
        sets.append("reason_code = NULL")
    elif reason is not None:
        sets.append("reason_code = :reason")
        params["reason"] = reason
    else:
        sets.append("reason_code = NULL")
    if attempt is not None:
        sets.append("attempt = :attempt")
        params["attempt"] = attempt
    await session.execute(
        text(
            "UPDATE metaedu.agent_conversation_purge_owners SET "
            + ", ".join(sets)
            + " WHERE purge_operation_id = :op AND owner_key = :k"
        ),
        params,
    )


class _RecordingSettlement(SettlementPort):
    def __init__(self) -> None:
        self.closeout: list[str] = []
        self.converge: list[str] = []

    async def closeout_erasing(
        self, *, tenant_id, conversation_id, purge_operation_id, owner_key
    ) -> None:
        self.closeout.append(owner_key)

    async def converge_failed_fence(
        self, *, tenant_id, conversation_id, purge_operation_id, owner_key
    ) -> None:
        self.converge.append(owner_key)


def _entry(behavior: str, calls: list[str]):
    """entry fake：record call + 返回规范化 outcome。

    behavior: 'ack' | 'block'（带 reason）| 'raise'（drift）。
    """

    async def fn(request: OwnerEntryRequest) -> OwnerEntryOutcome:
        calls.append(request.owner_key)
        if behavior == "ack":
            return OwnerEntryOutcome(acked=True, blocked_reason=None)
        if behavior == "raise":
            raise ValueError("drift: hold_revision mismatch")
        raise AssertionError(f"unknown behavior {behavior}")

    return fn


def _blocking_entry(reason: str, calls: list[str]):
    async def fn(request: OwnerEntryRequest) -> OwnerEntryOutcome:
        calls.append(request.owner_key)
        return OwnerEntryOutcome(acked=False, blocked_reason=reason)

    return fn


def _ack_with_db_write(calls: list[str]):
    """entry fake：自记 acked checkpoint + erased fence（镜像真实 participant
    的 DB 效果），供 coordinator 聚合收敛为 completed。"""

    async def fn(request: OwnerEntryRequest) -> OwnerEntryOutcome:
        calls.append(request.owner_key)
        await request.session.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners SET "
                "state='acked', ack_digest=:a, checkpoint_digest=:a, "
                "reason_code=NULL WHERE purge_operation_id=:op AND owner_key=:k"
            ),
            {"a": "e" * 64, "op": request.purge_operation_id, "k": request.owner_key},
        )
        ic = {"schema_version": 1, "sources": {}}
        await request.session.execute(
            text(
                "INSERT INTO metaedu.agent_erasure_fences "
                "(tenant_id, conversation_id, owner_key, owner_version, state, "
                "purge_revision, hold_revision, ingress_checkpoint, "
                "ingress_digest, ack_digest, acked_at, revision, created_at, "
                "updated_at) VALUES (:tid, :cid, :o, 1, 'erased', 1, 0, :ic, "
                ":ing, :ack, now(), 1, now(), now())"
            ),
            {
                "tid": request.tenant_id,
                "cid": request.conversation_id,
                "o": request.owner_key,
                "ic": json.dumps(ic, sort_keys=True),
                "ing": canonical_digest(ic),
                "ack": "e" * 64,
            },
        )
        return OwnerEntryOutcome(acked=True, blocked_reason=None)

    return fn


def _orchestrator(session_factory, *, entries, settlement=None):
    return OwnerExecutionOrchestrator(
        session_factory,
        owner_entries=entries,
        settlement_port=settlement or _RecordingSettlement(),
        scan_providers=build_scan_providers,
    )


# ---------------------------------------------------------------------------
# 核心测试
# ---------------------------------------------------------------------------


async def test_owner_lexicographic_order_and_per_owner_coordinator(
    db_session, session_factory
):
    """owner 字典序循环 + 每 owner 后 coordinator（真实聚合效果）：
    - 全 pending → 依字典序逐 owner entry；
    - 每个 entry 后 coordinator 聚合——全 owner acked + erased fence 后
      operation 收敛为 completed（漏聚合则仍 scheduled → mutation 判别点）。
    """
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id

    calls: list[str] = []
    orch = _orchestrator(
        session_factory,
        entries={k: _ack_with_db_write(calls) for k in _OWNER_KEYS},
    )
    result = await orch.run_cycle(
        tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
    )
    assert calls == _OWNER_KEYS, "owner 字典序循环"
    assert result.aggregation_count == len(_OWNER_KEYS), "每 owner 后 coordinator"

    async with session_factory() as verify:
        state = (
            await verify.execute(
                text(
                    "SELECT state FROM metaedu.agent_conversation_purges "
                    "WHERE id = :op"
                ),
                {"op": op_id},
            )
        ).scalar_one()
        assert state == "completed", "每 owner 后 coordinator 收敛为 completed"


async def test_skips_acked_and_failed(db_session, session_factory):
    """checkpoint 重读：acked/failed 跳过，仅 pending 入 entry。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    await _set_cp(db_session, op_id, _OWNER_KEYS[0], state="acked")
    await _set_cp(db_session, op_id, _OWNER_KEYS[1], state="failed")
    await db_session.commit()

    calls: list[str] = []
    orch = _orchestrator(
        session_factory, entries={k: _entry("ack", calls) for k in _OWNER_KEYS}
    )
    await orch.run_cycle(tenant_id=tid, conversation_id=cid, purge_operation_id=op_id)
    assert calls == _OWNER_KEYS[2:], "acked/failed 跳过"


async def test_erasing_delegates_to_settlement_port(db_session, session_factory):
    """checkpoint erasing → 交 settlement port，不 entry。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    await _set_cp(db_session, op_id, _OWNER_KEYS[0], state="erasing")
    await db_session.commit()

    calls: list[str] = []
    settlement = _RecordingSettlement()
    orch = _orchestrator(
        session_factory,
        entries={k: _entry("ack", calls) for k in _OWNER_KEYS},
        settlement=settlement,
    )
    await orch.run_cycle(tenant_id=tid, conversation_id=cid, purge_operation_id=op_id)
    assert _OWNER_KEYS[0] not in calls, "erasing 不得 entry"
    assert settlement.closeout == [_OWNER_KEYS[0]]
    assert _OWNER_KEYS[1] in calls


async def test_blocked_whitelist_vs_reject(db_session, session_factory):
    """blocked 白名单可重试；拒绝域跳过（不 entry）。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    await _set_cp(
        db_session, op_id, _OWNER_KEYS[0], state="blocked",
        reason=_REASON_ERASE_TIMEOUT,
    )
    await _set_cp(
        db_session, op_id, _OWNER_KEYS[1], state="blocked",
        reason=_REASON_OUTCOME_UNKNOWN,
    )
    await db_session.commit()

    calls: list[str] = []
    orch = _orchestrator(
        session_factory, entries={k: _entry("ack", calls) for k in _OWNER_KEYS}
    )
    await orch.run_cycle(tenant_id=tid, conversation_id=cid, purge_operation_id=op_id)
    assert _OWNER_KEYS[0] in calls, "白名单可重试"
    assert _OWNER_KEYS[1] not in calls, "拒绝域跳过"
    assert _OWNER_KEYS[2] in calls


async def test_budget_exhaustion_writes_failed(db_session, session_factory):
    """SCH-4：白名单 owner 连续 blocked 达预算（attempt>=3）→ failed + reason
    保留 + next_retry_at 清 + fence 收敛经 port。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id

    calls: list[str] = []
    settlement = _RecordingSettlement()
    entries = {
        k: _blocking_entry(_REASON_ERASE_TIMEOUT, calls)
        if k == _OWNER_KEYS[0]
        else _entry("ack", calls)
        for k in _OWNER_KEYS
    }
    orch = _orchestrator(
        session_factory, entries=entries, settlement=settlement
    )
    # 模拟 participant 已把 attempt 推进到 3（Tx1 语义），orchestrator 重读后
    # 判预算耗尽。先跑一轮 entry（blocked），再由测试把 attempt 置 3，再跑一轮
    # 触发 failed。
    await orch.run_cycle(tenant_id=tid, conversation_id=cid, purge_operation_id=op_id)
    async with session_factory() as s:
        await _set_cp(s, op_id, _OWNER_KEYS[0], state="blocked",
                      reason=_REASON_ERASE_TIMEOUT, attempt=3)
        await s.commit()

    await orch.run_cycle(tenant_id=tid, conversation_id=cid, purge_operation_id=op_id)

    async with session_factory() as verify:
        assert await _cp(verify, op_id, _OWNER_KEYS[0], "state") == "failed"
        assert (
            await _cp(verify, op_id, _OWNER_KEYS[0], "reason_code")
            == _REASON_ERASE_TIMEOUT
        ), "failed 保留最后 blocked reason"
        # SCH-4：预算耗尽后无 blocked owner 剩余 → next_retry_at 清 NULL。
        next_retry_at = (
            await verify.execute(
                text(
                    "SELECT next_retry_at FROM metaedu.agent_conversation_purges "
                    "WHERE id = :op"
                ),
                {"op": op_id},
            )
        ).scalar_one_or_none()
        assert next_retry_at is None, "failed 后 next_retry_at 清"
    assert settlement.converge == [_OWNER_KEYS[0]]


async def test_pre_window_gate_exempts_budget(db_session, session_factory):
    """pre-window gate（legal_hold）不耗预算：attempt=3 仍不落 failed。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    async with session_factory() as s:
        await _set_cp(s, op_id, _OWNER_KEYS[0], state="blocked",
                      reason=_REASON_LEGAL_HOLD, attempt=3)
        await s.commit()

    calls: list[str] = []
    settlement = _RecordingSettlement()
    orch = _orchestrator(
        session_factory,
        entries={k: _blocking_entry(_REASON_LEGAL_HOLD, calls) for k in _OWNER_KEYS},
        settlement=settlement,
    )
    await orch.run_cycle(tenant_id=tid, conversation_id=cid, purge_operation_id=op_id)

    async with session_factory() as verify:
        assert await _cp(verify, op_id, _OWNER_KEYS[0], "state") == "blocked"
    assert settlement.converge == [], "pre-window 不写 failed"


async def test_drift_fails_closed_zero_entry(db_session, session_factory):
    """周期级 token 重验：hold drift → fail closed（raise），零 entry。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    # 推进 conversation.hold_revision，operation.hold_revision_snapshot 仍 0 → drift。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversations SET hold_revision = 1 "
            "WHERE id = :cid"
        ),
        {"cid": cid},
    )
    await db_session.commit()

    calls: list[str] = []
    orch = _orchestrator(
        session_factory, entries={k: _entry("ack", calls) for k in _OWNER_KEYS}
    )
    with pytest.raises(ValueError):
        await orch.run_cycle(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
        )
    assert calls == [], "drift 零 entry"


async def test_expired_lease_fails_closed(db_session, session_factory):
    """cycle 开始时租约已过期 → fail closed（重入 claim），零 entry。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges SET "
                "lease_expires_at = clock_timestamp() - interval '1 second' "
                "WHERE id = :op"
            ),
            {"op": op_id},
        )
        await s.commit()

    calls: list[str] = []
    orch = _orchestrator(
        session_factory, entries={k: _entry("ack", calls) for k in _OWNER_KEYS}
    )
    with pytest.raises(ValueError, match="lease expired"):
        await orch.run_cycle(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
        )
    assert calls == []


async def test_tick_forces_aggregation(db_session, session_factory):
    """tick() 对候选集（非终态 + 在租）全量聚合：quiescent 全 acked → completed。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges SET next_retry_at = NULL "
                "WHERE id = :op"
            ),
            {"op": op_id},
        )
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purge_owners SET "
                "state='acked', ack_digest=:a, checkpoint_digest=:a, "
                "reason_code=NULL WHERE purge_operation_id=:op"
            ),
            {"a": "e" * 64, "op": op_id},
        )
        ic = {"schema_version": 1, "sources": {}}
        for o in registry_snapshot():
            await s.execute(
                text(
                    "INSERT INTO metaedu.agent_erasure_fences "
                    "(tenant_id, conversation_id, owner_key, owner_version, "
                    "state, purge_revision, hold_revision, ingress_checkpoint, "
                    "ingress_digest, ack_digest, acked_at, revision, created_at, "
                    "updated_at) VALUES (:tid, :cid, :o, 1, 'erased', 1, 0, :ic, "
                    ":ing, :ack, now(), 1, now(), now())"
                ),
                {
                    "tid": tid, "cid": cid, "o": str(o["owner_key"]),
                    "ic": json.dumps(ic, sort_keys=True),
                    "ing": canonical_digest(ic), "ack": "e" * 64,
                },
            )
        await s.commit()

    orch = _orchestrator(session_factory, entries={})
    count = await orch.tick()
    assert count == 1

    async with session_factory() as verify:
        row = (
            await verify.execute(
                text(
                    "SELECT state FROM metaedu.agent_conversation_purges "
                    "WHERE id = :op"
                ),
                {"op": op_id},
            )
        ).scalar_one()
        assert row == "completed"


async def test_cross_tenant_zero_entry(db_session, session_factory):
    """SCH-6：run_cycle 错误 tenant → fail closed 零 entry。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id

    calls: list[str] = []
    orch = _orchestrator(
        session_factory, entries={k: _entry("ack", calls) for k in _OWNER_KEYS}
    )
    with pytest.raises(ValueError):
        await orch.run_cycle(
            tenant_id=uuid.uuid4(), conversation_id=cid,
            purge_operation_id=op_id,
        )
    assert calls == []


async def test_unknown_exception_propagates_not_fake_blocked(
    db_session, session_factory
):
    """未知异常不得通过 catch-all 伪造 blocked：entry 抛非 drift 异常 → 编排
    方直接传播（fail closed），不写 checkpoint blocked。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id

    async def _boom(request: OwnerEntryRequest) -> OwnerEntryOutcome:
        raise RuntimeError("unexpected adapter crash")

    calls: list[str] = []
    entries = {
        _OWNER_KEYS[0]: _boom,
        **{k: _entry("ack", calls) for k in _OWNER_KEYS[1:]},
    }
    orch = _orchestrator(session_factory, entries=entries)
    with pytest.raises(RuntimeError):
        await orch.run_cycle(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
        )
    async with session_factory() as verify:
        assert await _cp(verify, op_id, _OWNER_KEYS[0], "state") == "pending", (
            "未知异常不得伪造 blocked"
        )


async def test_interop_real_workspace_participant(db_session, session_factory):
    """六 owner participant/coordinator 互操作回归（代表 owner = workspace 真
    实 participant）：orchestrator 驱动真实 `erase_conversation_body` →
    checkpoint acked + fence erased + coordinator 聚合。"""
    from app.contexts.agent_workspace.infrastructure.workspace_erasure_participant import (
        WorkspaceErasureParticipant,
    )

    tid, cid = await _seed_conversation(db_session)  # redacted + no body
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id

    async def _workspace_entry(request: OwnerEntryRequest) -> OwnerEntryOutcome:
        participant = WorkspaceErasureParticipant(
            request.session, audit_secret="test-audit-secret", audit_secret_version=1
        )
        outcome = await participant.erase_conversation_body(
            tenant_id=request.tenant_id,
            conversation_id=request.conversation_id,
            purge_revision=request.purge_revision,
            purge_operation_id=request.purge_operation_id,
            expected_operation_revision=request.expected_operation_revision,
            expected_lease_epoch=request.expected_lease_epoch,
        )
        return OwnerEntryOutcome(
            acked=outcome.erased, blocked_reason=outcome.block_reason
        )

    calls: list[str] = []
    entries = {
        "workspace.core.v1": _workspace_entry,
        **{k: _entry("ack", calls) for k in _OWNER_KEYS if k != "workspace.core.v1"},
    }
    orch = _orchestrator(session_factory, entries=entries)
    await orch.run_cycle(tenant_id=tid, conversation_id=cid, purge_operation_id=op_id)

    async with session_factory() as verify:
        assert await _cp(verify, op_id, "workspace.core.v1", "state") == "acked"
        fence_state = (
            await verify.execute(
                text(
                    "SELECT state FROM metaedu.agent_erasure_fences "
                    "WHERE conversation_id = :cid AND owner_key = 'workspace.core.v1'"
                ),
                {"cid": cid},
            )
        ).scalar_one()
        assert fence_state == "erased", "真实 participant 推进 fence 到 erased"


async def test_stale_purge_revision_fails_closed(db_session, session_factory):
    """SCH-7：旧 purge_revision（rebuild 后旧 operation）→ I2 gate fail closed，
    零 entry。mutation（M-SCH-B-stale-revision）：verify 去 purge_revision gate。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    # 模拟 rebuild 推进 conversation.purge_revision 到 2（operation 仍 1）。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversations SET purge_revision = 2 "
                "WHERE id = :cid"
            ),
            {"cid": cid},
        )
        await s.commit()

    calls: list[str] = []
    orch = _orchestrator(
        session_factory, entries={k: _entry("ack", calls) for k in _OWNER_KEYS}
    )
    with pytest.raises(ValueError):
        await orch.run_cycle(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
        )
    assert calls == [], "旧 purge_revision 零 entry"


async def test_failed_operation_stops_cycle_gracefully(
    db_session, session_factory
):
    """并发面 P1 反例：operation 已 failed（coordinator 优先级 5 收敛）后，
    run_cycle 必须优雅停止（verify 把 failed 纳入终态），不得再对 pending
    owner 调 entry 抛 participant 终态守卫异常循环。"""
    tid, cid = await _seed_conversation(db_session)
    out = await _claim(db_session, tid, cid)
    await db_session.commit()
    op_id = out.token.purge_operation_id
    # 模拟 coordinator 优先级 5 已把 operation 收敛为 failed。
    async with session_factory() as s:
        await s.execute(
            text(
                "UPDATE metaedu.agent_conversation_purges SET state = 'failed' "
                "WHERE id = :op"
            ),
            {"op": op_id},
        )
        await s.commit()

    calls: list[str] = []
    orch = _orchestrator(
        session_factory, entries={k: _entry("ack", calls) for k in _OWNER_KEYS}
    )
    with pytest.raises(ValueError, match="operation failed"):
        await orch.run_cycle(
            tenant_id=tid, conversation_id=cid, purge_operation_id=op_id
        )
    assert calls == [], "failed 后不得再调 entry（优雅停止）"
