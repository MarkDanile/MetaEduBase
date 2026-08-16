"""R1-S3-D：execution.core.v1 fencing CAS 反例 + erased fence 幂等重放/修复。

Spec §5.2/§6.1/§9.2（plan §R1-S3「S3-D 契约注记」+「round-3/4/5 复审修订」）。

fencing 反例（表驱动，任一不符 fail closed，ValueError/OwnerRegistryChangedError）：
- operation 身份：跨 Conversation / purge_revision / lease_epoch / hold_revision /
  operation revision CAS。
- checkpoint owner capability CAS：owner_version / capability_digest。
- registry drift（operation registry_digest != 已安装 registry）。

erased fence 幂等重放（ACK 丢失恢复 + 三方一致）：
- 幂等重放：第二次 erase no-op，ack_digest 不变（修复前的 bug：已 acked checkpoint
  直接 raise，破坏幂等）。
- erased + pending checkpoint + scheduled operation -> 修复 acked/running。
- erased + 非零 scan -> fail closed（正文泄漏，不在泄漏正文上补 ACK）。
- erased + cancelled operation -> fail closed（不在已取消 operation 上补 ACK）。
- erased + acked checkpoint digest 不一致 -> fail closed（矛盾 ACK 事实）。
- erased + blocked operation -> 修复 running（三方一致）。
- erased + acked checkpoint + blocked operation -> fall through 修 operation。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.composition.agent_erasure_registry import (
    OwnerRegistryChangedError,
    registry_digest,
)
from app.contexts.agent_workspace.domain import (
    PurgeOperationState,
    PurgeOwnerState,
)
from tests.contexts.agent_control_plane import s3d_helpers as h

pytestmark = pytest.mark.asyncio


async def _erase(db_session, ctx, **overrides):
    return await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        **overrides,
    )


# ---------------------------------------------------------------------------
# fencing CAS 反例（表驱动）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario, expected_match",
    [
        ("cross_conversation", "conversation mismatch"),
        ("purge_revision_mismatch", "purge_revision mismatch"),
        ("stale_lease_epoch", "lease_epoch mismatch"),
        ("hold_revision_drift", "hold_revision_snapshot mismatch"),
        ("stale_operation_revision", "revision CAS mismatch"),
        ("checkpoint_owner_version", "checkpoint owner_version"),
        ("checkpoint_capability_digest", "capability_digest"),
    ],
)
async def test_operation_fencing_counterexamples(
    db_session, scenario, expected_match
):
    """operation 身份 / lease / hold / revision / owner capability 任一不符 ->
    fail closed。表驱动反例。

    变异杀手：删任一 CAS 检查 -> 对应反例不再 raise -> assert raises 失败。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    # 强制带 expected_operation_revision=CAS（helper 不传，由 caller 决定）。
    call_kwargs: dict = {"expected_operation_revision": ctx["op_revision"]}
    # capability_digest 不匹配 -> OwnerRegistryChangedError（registry drift 语义）；
    # 其余 fencing 反例 -> ValueError。
    expected_exc = (
        OwnerRegistryChangedError if scenario == "checkpoint_capability_digest"
        else ValueError
    )

    if scenario == "cross_conversation":
        other_conv_id, other_identity, other_rev = await h.seed_purgeable(
            db_session, title="other conv"
        )
        other_op_id, other_op_rev = await h.make_purge_operation(
            db_session, other_conv_id, other_rev
        )
        ctx["operation_id"] = other_op_id
        ctx["op_revision"] = other_op_rev
        ctx["purge_revision"] = other_rev  # helper 也读 ctx，以 ctx 为准
    elif scenario == "purge_revision_mismatch":
        ctx["purge_revision"] = 999  # 改 ctx（helper 读 ctx），避免与 call_kwargs 重名
    elif scenario == "stale_lease_epoch":
        call_kwargs["expected_lease_epoch"] = 5
    elif scenario == "hold_revision_drift":
        conv = await db_session.get(h.ConversationModel, ctx["conversation_id"])
        conv.hold_revision = 1
        await db_session.commit()
    elif scenario == "stale_operation_revision":
        call_kwargs["expected_operation_revision"] = ctx["op_revision"] + 5
    elif scenario == "checkpoint_owner_version":
        cp = await h.checkpoint_model(db_session, ctx["operation_id"])
        cp.owner_version = 2  # fence owner_version=1
        await db_session.commit()
    elif scenario == "checkpoint_capability_digest":
        cp = await h.checkpoint_model(db_session, ctx["operation_id"])
        cp.capability_digest = "0" * 64
        await db_session.commit()

    with pytest.raises(expected_exc, match=expected_match):
        await _erase(db_session, ctx, **call_kwargs)


async def test_registry_drift_fail_closed(db_session, monkeypatch):
    """operation registry_digest 与已安装 registry 不匹配（drift）-> fail closed
    （OwnerRegistryChangedError）。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    monkeypatch.setattr(
        "app.contexts.agent_execution.infrastructure.execution_erasure_participant."
        "registry_digest",
        lambda: "0" * 64,
    )
    with pytest.raises(OwnerRegistryChangedError):
        await _erase(db_session, ctx, expected_operation_revision=ctx["op_revision"])
    assert registry_digest() != "0" * 64  # monkeypatch 已还原


# ---------------------------------------------------------------------------
# erased fence 幂等重放 + 修复
# ---------------------------------------------------------------------------


async def test_idempotent_replay_no_op(db_session):
    """已 erased 后再次 erase 幂等 no-op：ack_digest 不变，checkpoint 已 acked
    不重写；R1-S5-I2：operation 聚合投影归 coordinator（保持 scheduled）。

    修复前的 bug：``_repair_checkpoint_if_pending`` 直接调 ``_ack_owner_checkpoint``，
    在 ACKED checkpoint 上 raise ``checkpoint not ackable`` -> 幂等重放失败。本测试
    击杀该回归。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    first = await _erase(db_session, ctx, expected_operation_revision=ctx["op_revision"])
    await db_session.commit()
    assert first.erased
    first_ack = first.ack_digest
    op_revision_after = await h.op_revision(db_session, ctx["operation_id"])

    second = await _erase(db_session, ctx, expected_operation_revision=op_revision_after)
    await db_session.commit()
    assert second.erased
    assert second.ack_digest == first_ack  # 不变

    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == PurgeOwnerState.ACKED.value
    assert cp.ack_digest == first_ack
    op = await h.operation_model(db_session, ctx["operation_id"])
    assert op.state == "scheduled"  # R1-S5-I2：未被 participant 改
    assert op.failure_code is None


async def test_erased_repairs_pending_checkpoint(db_session):
    """fence erased 但 checkpoint pending（ACK 丢失）+ operation scheduled ->
    幂等重放修复 checkpoint 到 acked（R1-S5-I2：operation 投影归 coordinator，
    零共享写）；purged_at 不阻断恢复。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    first = await _erase(db_session, ctx, expected_operation_revision=ctx["op_revision"])
    await db_session.commit()
    assert first.erased
    fence_ack = first.ack_digest
    op_revision_after = await h.op_revision(db_session, ctx["operation_id"])

    # 模拟 ACK 丢失：checkpoint 回退 pending、operation 回退 scheduled、purged_at 置位。
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    cp.state = PurgeOwnerState.PENDING.value
    cp.ack_digest = None
    cp.checkpoint_digest = None
    op = await h.operation_model(db_session, ctx["operation_id"])
    op.state = PurgeOperationState.SCHEDULED.value
    op.failure_code = "stale"
    op.started_at = None
    op.revision = op_revision_after + 1
    conv = await db_session.get(h.ConversationModel, ctx["conversation_id"])
    conv.purged_at = datetime.now(UTC)
    await db_session.commit()

    outcome = await _erase(
        db_session, ctx, expected_operation_revision=op_revision_after + 1
    )
    await db_session.commit()
    assert outcome.erased
    assert outcome.ack_digest == fence_ack

    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == PurgeOwnerState.ACKED.value
    assert cp.ack_digest == fence_ack
    op = await h.operation_model(db_session, ctx["operation_id"])
    assert op.state == "scheduled"  # R1-S5-I2：participant 零共享写
    assert op.failure_code == "stale"


async def test_erased_nonzero_scan_fail_closed(db_session):
    """erased fence + 非零 scan（正文泄漏）-> fail closed，不在泄漏正文上补 ACK。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    first = await _erase(db_session, ctx, expected_operation_revision=ctx["op_revision"])
    await db_session.commit()
    assert first.erased
    op_revision_after = await h.op_revision(db_session, ctx["operation_id"])

    # 注入残留 present 正文（模拟 body 泄漏）。
    run = await h.run_model(db_session, ctx["run_id"])
    await h.seed_run_event(db_session, run=run, seq=99)
    await db_session.commit()

    with pytest.raises(ValueError, match="body scan non-zero"):
        await _erase(db_session, ctx, expected_operation_revision=op_revision_after)


async def test_erased_cancelled_operation_fail_closed(db_session):
    """erased 重放时 operation 已 cancelled -> fail closed，不在已取消 operation
    上补 ACK。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    first = await _erase(db_session, ctx, expected_operation_revision=ctx["op_revision"])
    await db_session.commit()
    assert first.erased
    op_revision_after = await h.op_revision(db_session, ctx["operation_id"])

    op = await h.operation_model(db_session, ctx["operation_id"])
    op.state = PurgeOperationState.CANCELLED.value
    op.revision = op_revision_after + 1
    await db_session.commit()

    with pytest.raises(ValueError, match="operation not in runnable state: 'cancelled'"):
        await _erase(
            db_session, ctx, expected_operation_revision=op_revision_after + 1
        )


async def test_erased_acked_digest_mismatch_fail_closed(db_session):
    """erased 重放时 checkpoint 已 acked 但 ack_digest 与 fence 不一致（矛盾事实）
    -> fail closed，不接受孤立 ACK。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    first = await _erase(db_session, ctx, expected_operation_revision=ctx["op_revision"])
    await db_session.commit()
    assert first.erased
    op_revision_after = await h.op_revision(db_session, ctx["operation_id"])

    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    cp.ack_digest = "0" * 64  # 篡改，与 fence.ack_digest 不一致
    await db_session.commit()

    with pytest.raises(ValueError, match="contradictory ACK fact"):
        await _erase(db_session, ctx, expected_operation_revision=op_revision_after)


async def test_erased_blocked_operation_repaired_to_running(db_session):
    """erased 重放时 operation=blocked + checkpoint=pending + purge_state=blocked ->
    checkpoint 修复 acked（R1-S5-I2：operation/purge_state 投影归 coordinator，
    participant 零共享写——原「修复三方一致」语义由 coordinator 从 facts 重算替代）。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    first = await _erase(db_session, ctx, expected_operation_revision=ctx["op_revision"])
    await db_session.commit()
    assert first.erased
    fence_ack = first.ack_digest
    op_revision_after = await h.op_revision(db_session, ctx["operation_id"])

    op = await h.operation_model(db_session, ctx["operation_id"])
    op.state = PurgeOperationState.BLOCKED.value
    op.failure_code = "stale"
    op.revision = op_revision_after + 1
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    cp.state = PurgeOwnerState.PENDING.value
    cp.ack_digest = None
    cp.checkpoint_digest = None
    conv = await db_session.get(h.ConversationModel, ctx["conversation_id"])
    conv.purge_state = "blocked"
    await db_session.commit()

    outcome = await _erase(
        db_session, ctx, expected_operation_revision=op_revision_after + 1
    )
    await db_session.commit()
    assert outcome.erased

    op = await h.operation_model(db_session, ctx["operation_id"])
    assert op.state == "blocked"  # R1-S5-I2：projection 归 coordinator
    assert op.failure_code == "stale"
    conv = await db_session.get(h.ConversationModel, ctx["conversation_id"])
    assert conv.purge_state == "blocked"
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == PurgeOwnerState.ACKED.value
    assert cp.ack_digest == fence_ack


async def test_erased_acked_checkpoint_blocked_operation_repaired(db_session):
    """erased 重放时 checkpoint=acked（digest 一致）+ operation=blocked -> checkpoint
    no-op（不重写）；R1-S5-I2：operation 投影归 coordinator，participant 零共享写
    （原「fall through 修 operation 到 running」语义由 coordinator 从 facts 重算
    替代）。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    first = await _erase(db_session, ctx, expected_operation_revision=ctx["op_revision"])
    await db_session.commit()
    assert first.erased
    fence_ack = first.ack_digest
    op_revision_after = await h.op_revision(db_session, ctx["operation_id"])

    # 关键：不回退 checkpoint（保留 acked + 正确 digest），只破坏 operation。
    op = await h.operation_model(db_session, ctx["operation_id"])
    op.state = PurgeOperationState.BLOCKED.value
    op.failure_code = "stale"
    op.revision = op_revision_after + 1
    await db_session.commit()

    outcome = await _erase(
        db_session, ctx, expected_operation_revision=op_revision_after + 1
    )
    await db_session.commit()
    assert outcome.erased

    op = await h.operation_model(db_session, ctx["operation_id"])
    assert op.state == "blocked"  # R1-S5-I2：projection 归 coordinator
    assert op.failure_code == "stale"
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == PurgeOwnerState.ACKED.value
    assert cp.ack_digest == fence_ack  # 未重写


# ---------------------------------------------------------------------------
# round-1 复审返修反例（P1-4 failed operation / P1-6 真实清除计数）
# ---------------------------------------------------------------------------


async def test_round1_p1_4_failed_operation_fails_closed(db_session):
    """P1-4：operation=failed 不得进入清除与 ACK。

    旧实现 ``_load_verified_operation`` 只拒 cancelled/completed，failed operation
    会穿透 ``_mark_operation_running``（只处理 scheduled/blocked）继续清除并
    ACK，留下 ``operation=failed / checkpoint=acked / fence=erased`` 的矛盾。
    修订后：可运行状态白名单 ``{scheduled, running, blocked}``，failed 必拒。
    变异杀手：删 ``_RUNNABLE_OPERATION_STATES`` 谓词或放宽为允许 failed ->
    异常不抛，进入清除路径，本测试变红。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    op = await h.operation_model(db_session, ctx["operation_id"])
    op.state = PurgeOperationState.FAILED.value
    op.revision = ctx["op_revision"] + 1
    await db_session.commit()
    expected_revision = op.revision

    with pytest.raises(
        ValueError, match="operation not in runnable state: 'failed'"
    ):
        await _erase(
            db_session, ctx, expected_operation_revision=expected_revision
        )
    await db_session.rollback()

    # 验证零状态变更：operation=failed 仍在，checkpoint=pending，正文未清
    op_after = await h.operation_model(db_session, ctx["operation_id"])
    assert op_after.state == "failed", "operation state must not change"
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == "pending", "checkpoint must remain pending"
    completed = await h.run_model(db_session, ctx["run_id"])
    assert completed.terminal_output_ref is not None, (
        "body must not be cleared when operation is in non-runnable state"
    )


async def test_round1_p1_4_operation_locked_for_update(
    db_session, session_factory
):
    """P1-4：_load_verified_operation 必须真发 ``FOR UPDATE``，锁住 operation 行
    直到事务结束——否则并发 scheduler 可与 revision 裁决竞态。

    **真变异杀手（codex P2-3 修订）**：主会话先对 operation 行持 ``FOR UPDATE``
    锁且不提交；随后**真实 participant** 在**第二会话**上 erase 同一 operation。
    主会话用 ``FOR KEY SHARE`` 持锁。锁强度矩阵（PG 行级锁冲突表）：

    - ``FOR KEY SHARE`` 与 participant 的 operation ``FOR UPDATE``
      （``_load_verified_operation``）**互斥** -> 保留 ``.with_for_update()`` 时
      participant 卡在 FOR UPDATE -> 超时窗口内无法完成 -> 断言 blocking 成立。
    - ``FOR KEY SHARE`` 与 participant 投影的 ``UPDATE state/started_at``
      （``_mark_operation_running``，隐式 ``FOR NO KEY UPDATE`` 强度）**不互斥**，
      且主会话是 reader 不进入 updater 的 xid-wait 路径 -> 删除 ``.with_for_update()``
      后 participant 直通、清除并投影、erase 在超时窗口内**完成** -> 断言失败（转红）。

    不用 ``FOR SHARE``/``FOR NO KEY UPDATE``：前者经 ORM versioning 调
    ``pg_current_xact_id_if_assigned`` 置 xmax，把 participant 的 UPDATE 卡在主会话
    xmin；后者本身就是 updater 锁，updater-vs-updater 进入 xid-wait。两者都让
    变异（无 FOR UPDATE）仍因投影 UPDATE 阻塞而假绿。``FOR KEY SHARE`` 是纯 reader
    锁，不触发这些路径，成败只由 ``.with_for_update()`` 决定。
    """
    import asyncio

    from sqlalchemy import text

    ctx = await h.seed_purgeable_with_run(db_session)
    op_id = ctx["operation_id"]
    op_rev = ctx["op_revision"]

    # 主会话对 operation 行持 FOR KEY SHARE 锁（不提交）。
    _ = (
        await db_session.execute(
            text(
                "SELECT id FROM metaedu.agent_conversation_purges "
                "WHERE id = :oid FOR KEY SHARE"
            ),
            {"oid": op_id},
        )
    ).one()

    async def run_real_participant():
        """在第二会话上跑**真实 participant** 的 erase（含 operation FOR UPDATE）。"""
        async with session_factory() as session:
            outcome = await h.participant(session).erase_execution_body(
                tenant_id=h.TENANT_ID,
                conversation_id=ctx["conversation_id"],
                purge_revision=ctx["purge_revision"],
                purge_operation_id=op_id,
                expected_operation_revision=op_rev,
            )
            await session.commit()
            return outcome

    # 主会话持锁期间，participant 的 operation FOR UPDATE 必然等待 -> 无法完成。
    participant_task = asyncio.create_task(run_real_participant())
    try:
        completed = await asyncio.wait_for(
            asyncio.shield(participant_task), timeout=1.0
        )
        # 能走到这说明 participant 在持锁窗口内完成了 erase -> operation 读取未被
        # 行锁阻塞 -> .with_for_update() 缺失（变异存活）。本测试应变红。
        raise AssertionError(
            f"participant completed erase while operation row lock was held "
            f"(outcome={completed!r}) -- _load_verified_operation is not holding "
            f"FOR UPDATE (mutation: delete .with_for_update() survives)"
        )
    except TimeoutError:
        pass  # 期望：participant 被 operation FOR UPDATE 行锁阻塞，超时未完成。

    # 释放主会话行锁后，被阻塞的 participant 继续推进并完成 erase。
    await db_session.rollback()
    outcome = await asyncio.wait_for(participant_task, timeout=10)
    assert outcome.erased


async def test_round1_p1_6_real_clear_counts_drive_ack_digest(db_session):
    """P1-6：ACK digest 必须随真实清除计数变化（旧实现从必为零的 final scan
    取值，digest 不表达清除事实）。

    删除 1 个 event vs 删除 2 个 event -> 不同 digest。
    变异杀手：把 ``summary.ack_digest`` 改回取自 final scan（恒零）-> 两组
    digest 相同，本测试变红。
    """
    # 第一次 erase：标准 1 event
    ctx1 = await h.seed_purgeable_with_run(db_session, title="clear 1 event")
    out1 = await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx1["conversation_id"],
        purge_revision=ctx1["purge_revision"],
        purge_operation_id=ctx1["operation_id"],
        expected_operation_revision=ctx1["op_revision"],
    )
    await db_session.commit()
    assert out1.erased
    digest_1 = out1.ack_digest

    # 第二次 erase：同 conversation_id 再插一个 event，期望 digest 不同
    ctx2 = await h.seed_purgeable_with_run(db_session, title="clear 2 events")
    conversation_id = ctx2["conversation_id"]
    # 在已 seed 的 run 上加一个 inline event
    run = await h.run_model(db_session, ctx2["run_id"])
    await h.seed_run_event(db_session, run=run, seq=2)
    await db_session.commit()
    out2 = await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=ctx2["purge_revision"],
        purge_operation_id=ctx2["operation_id"],
        expected_operation_revision=ctx2["op_revision"],
    )
    await db_session.commit()
    assert out2.erased
    digest_2 = out2.ack_digest

    assert digest_1 != digest_2, (
        "ack_digest must reflect real clear counts: 1 event vs 2 events "
        "should differ (P1-6: ack digest is not zero)"
    )


# ---------------------------------------------------------------------------
# codex round-1 复审返修反例（P1-1 failed checkpoint / P2-2 repair 完整性）
# ---------------------------------------------------------------------------


async def test_codex_p1_1_failed_checkpoint_fails_closed_on_blocked(
    db_session, session_factory
):
    """codex P1-1：failed checkpoint 不得被 _record_blocked 复活为 blocked。

    旧实现 ``_record_blocked`` 对 checkpoint 无白名单，任意非 blocked 状态
    （含 failed）都会被改为 blocked，failed -> blocked -> acked 是可能的复活链。

    **round-3 P1（codex）**：``ValueError`` 不会使 SQLAlchemy 事务失效——若
    ``_record_blocked`` 先改 operation（state/revision/failure_code）再校验
    checkpoint 并 raise，调用方捕获异常后**提交**，部分复活（operation 已
    blocked、revision 已 bump、checkpoint 仍 failed）就会落库。故修复后必须先
    完成 checkpoint 白名单裁决、再改任何实体。本测试**捕获异常后主动 commit**，
    并用**新 session** 读回验证 operation/checkpoint/conversation 三方零变更——
    不再靠 rollback 掩盖部分提交路径。

    变异杀手：把 checkpoint 白名单判定移回 operation 赋值之后 -> commit 后
    operation 已变 blocked、revision 已 +1 -> 新 session 读回发现变更 -> 变红。
    """
    from app.contexts.agent_workspace.infrastructure.models import (
        ConversationModel,
    )

    ctx = await h.seed_purgeable_with_run(db_session)
    op_id = ctx["operation_id"]
    conv_id = ctx["conversation_id"]
    cp = await h.checkpoint_model(db_session, op_id)
    op = await h.operation_model(db_session, op_id)
    conv = await db_session.get(ConversationModel, conv_id)
    # 人为制造 failed checkpoint（绕过正常状态机，只验证白名单语义）
    cp.state = PurgeOwnerState.FAILED.value
    await db_session.commit()
    op_rev_before = op.revision
    op_state_before = op.state
    conv_purge_state_before = conv.purge_state

    # 直接调用 participant._record_blocked（带 failed checkpoint），应 raise。
    from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
        ExecutionBodyScan,
    )
    scan = ExecutionBodyScan(
        unredacted_terminal_outputs=1,
        uncleared_context_snapshots=1,
        unredacted_compatibility_outputs=1,
        unredacted_event_payloads=1,
        unredacted_terminal_codes=1,
        unanonymized_run_actors=1,
        unanonymized_turn_input_actors=1,
    )
    participant = h.participant(db_session)
    with pytest.raises(
        ValueError, match="checkpoint not blockable from state"
    ):
        await participant._record_blocked(
            operation=op,
            checkpoint=cp,
            conversation=conv,
            scan=scan,
            reason_code="execution_body_scan_nonzero",
            now=datetime.now(UTC),
        )
    # round-3 P1：捕获异常后**提交**（不 rollback）——若 _record_blocked 在裁决前
    # 已改 operation，此次提交会把部分复活落库。
    await db_session.commit()

    # 用**新 session** 读回（绕过当前 session identity map），验证三方零变更。
    async with session_factory() as fresh:
        op_after = await h.operation_model(fresh, op_id)
        cp_after = await h.checkpoint_model(fresh, op_id)
        conv_after = await fresh.get(ConversationModel, conv_id)
    assert cp_after.state == "failed", (
        f"checkpoint must remain failed, got {cp_after.state!r}"
    )
    assert op_after.state == op_state_before, (
        f"operation state must not change (partial resurrection), "
        f"{op_state_before!r} -> {op_after.state!r}"
    )
    assert op_after.revision == op_rev_before, (
        f"operation revision must not bump (partial resurrection), "
        f"{op_rev_before} -> {op_after.revision}"
    )
    assert op_after.failure_code is None, (
        f"operation failure_code must not be set, got {op_after.failure_code!r}"
    )
    assert conv_after.purge_state == conv_purge_state_before, (
        f"conversation purge_state must not change, "
        f"{conv_purge_state_before!r} -> {conv_after.purge_state!r}"
    )


async def test_codex_p1_1_erased_replay_rejects_failed_checkpoint(db_session):
    """codex P1-1：erased fence 重放时 failed checkpoint 不得被复活为 acked。

    变异杀手：删 ``checkpoint.state not in (PENDING/ERASING/BLOCKED)`` raise ->
    本测试变红。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    first = await _erase(db_session, ctx, expected_operation_revision=ctx["op_revision"])
    await db_session.commit()
    assert first.erased
    op_revision_after = await h.op_revision(db_session, ctx["operation_id"])

    # 把 checkpoint 回退到 failed（绕过正常状态机）
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    cp.state = PurgeOwnerState.FAILED.value
    cp.ack_digest = None
    cp.checkpoint_digest = None
    op = await h.operation_model(db_session, ctx["operation_id"])
    op.state = PurgeOperationState.SCHEDULED.value
    op.revision = op_revision_after + 1
    await db_session.commit()

    with pytest.raises(
        ValueError, match="checkpoint not repairable from state"
    ):
        await _erase(
            db_session, ctx, expected_operation_revision=op_revision_after + 1
        )


async def test_codex_p2_2_repair_sets_started_at_and_clears_failure_code(db_session):
    """codex P2-2（R1-S5-I2 迁移）：erased replay 只修 owner checkpoint；
    operation 投影（含 started_at/failure_code）归 coordinator，participant
    零共享写——原「修复 operation 到 running 同时设 started_at + 清 failure_code」
    的变异杀手随写权移除由六 owner 零写守卫（test_s5i2_six_owner_*）承接。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    first = await _erase(db_session, ctx, expected_operation_revision=ctx["op_revision"])
    await db_session.commit()
    assert first.erased
    op_revision_after = await h.op_revision(db_session, ctx["operation_id"])

    # 模拟 ACK 丢失：checkpoint 回退 pending，operation 回退 scheduled
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    cp.state = PurgeOwnerState.PENDING.value
    cp.ack_digest = None
    cp.checkpoint_digest = None
    op = await h.operation_model(db_session, ctx["operation_id"])
    op.state = PurgeOperationState.SCHEDULED.value
    op.failure_code = "stale_error"
    op.started_at = None  # 模拟从未启动
    op.revision = op_revision_after + 1
    conv = await db_session.get(h.ConversationModel, ctx["conversation_id"])
    conv.purged_at = datetime.now(UTC)
    await db_session.commit()

    outcome = await _erase(
        db_session, ctx, expected_operation_revision=op_revision_after + 1
    )
    await db_session.commit()
    assert outcome.erased

    op_after = await h.operation_model(db_session, ctx["operation_id"])
    assert op_after.state == "scheduled", (
        "R1-S5-I2: operation projection is coordinator-owned; participant "
        "must not repair it"
    )
    assert op_after.started_at is None
    assert op_after.failure_code == "stale_error"
    cp_after = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp_after.state == PurgeOwnerState.ACKED.value
