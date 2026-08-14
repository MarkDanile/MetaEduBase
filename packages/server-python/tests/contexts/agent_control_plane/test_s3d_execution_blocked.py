"""R1-S3-D：execution.core.v1 blocked 前置检查（Spec §9.2 / §7.2）。

blocked 作为正常返回提交（不抛异常致回滚），fence 保持 active（不清除正文），
operation/checkpoint 记 blocked + reason_code，可重试。

变异验证（逐项删除 blocker 均应被击杀）：
- 删非终态 Run blocker -> 非终态 Run 进入清除 -> assert blocked 失败。
- 删 external payload_ref blocker -> external ref 进入清除（payload_ref 不归
  execution owner 清）-> assert blocked 失败。
- 删 runtime binding ref blocker -> runtime-bound Run 进入清除（runtime ref 不归
  execution owner 清）-> assert blocked 失败。
- 删 legal hold 检查 -> hold conversation 进入清除 -> assert blocked 失败。
"""

from __future__ import annotations

import uuid

import pytest

from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
    REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
    REASON_PURGE_BLOCKED_BY_UNRESOLVED_ACTION,
    REASON_PURGE_OWNER_UNAVAILABLE,
)
from app.contexts.agent_execution.infrastructure.models import (
    RuntimeSessionBindingModel,
)
from app.contexts.agent_workspace.domain import ErasureFenceState, PurgeOwnerState
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from tests.contexts.agent_control_plane import s3d_helpers as h

pytestmark = pytest.mark.asyncio


async def _erase(db_session, ctx):
    return await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )


async def test_nonterminal_run_blocks(db_session):
    """非终态 Run（running）-> purge_blocked_by_unresolved_action，正文不动。

    变异杀手：删非终态 blocker -> running Run 进入清除 -> assert blocked 失败。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    # 追加一个 running Run（completed Run 仍在，但非终态优先 block）。
    await h.seed_nonterminal_run(
        db_session,
        conversation_id=ctx["conversation_id"],
        identity=ctx["identity"],
        queue_seq=2,
        status="running",
    )
    await db_session.commit()

    outcome = await _erase(db_session, ctx)
    await db_session.commit()

    assert outcome.blocked
    assert outcome.block_reason == REASON_PURGE_BLOCKED_BY_UNRESOLVED_ACTION
    assert outcome.ack_digest is None
    fence = await h.fence_model(db_session, ctx["conversation_id"])
    assert fence.state == ErasureFenceState.ACTIVE.value  # 未推进 erasing
    op = await h.operation_model(db_session, ctx["operation_id"])
    assert op.state == "blocked"
    assert op.failure_code == REASON_PURGE_BLOCKED_BY_UNRESOLVED_ACTION
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == PurgeOwnerState.BLOCKED.value
    # completed Run 的正文未被动（terminal_output_ref 仍在）。
    completed = await h.run_model(db_session, ctx["run_id"])
    assert completed.terminal_output_ref is not None


async def test_external_payload_ref_blocks(db_session):
    """RunEvent payload_ref 存在（external.payload.v1 S4 未安装）->
    purge_owner_unavailable，不清 inline（不假 ACK）。

    变异杀手：删 external_ref blocker -> external ref 进入清除路径（payload_ref
    不被清）-> scan 非零 -> blocked（但 reason 错），且 fence 推进 erasing。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    run = await h.run_model(db_session, ctx["run_id"])
    # 追加一个 external payload_ref 事件。
    await h.seed_run_event(
        db_session,
        run=run,
        seq=2,
        payload_inline=None,
        payload_ref="obj://external/payload",
        payload_state="external",
    )
    await db_session.commit()

    outcome = await _erase(db_session, ctx)
    await db_session.commit()

    assert outcome.blocked
    assert outcome.block_reason == REASON_PURGE_OWNER_UNAVAILABLE
    assert outcome.ack_digest is None
    fence = await h.fence_model(db_session, ctx["conversation_id"])
    assert fence.state == ErasureFenceState.ACTIVE.value  # 未推进 erasing
    op = await h.operation_model(db_session, ctx["operation_id"])
    assert op.state == "blocked"
    assert op.failure_code == REASON_PURGE_OWNER_UNAVAILABLE


async def test_runtime_binding_ref_blocks(db_session):
    """非 compatibility Run 存在 runtime binding（runtime_session_ref 非空）->
    purge_owner_unavailable（runtime.private.v1 S4 未安装）。

    变异杀手：删 runtime_ref blocker -> runtime-bound Run 进入清除（runtime ref
    不被清）-> assert blocked 失败。
    """
    conversation_id, identity, purge_revision = await h.seed_purgeable(db_session)
    profile_id, binding_id = await h.seed_native_binding(
        db_session, conversation_id=conversation_id
    )
    run = await h.seed_completed_run(
        db_session,
        conversation_id=conversation_id,
        identity=identity,
        queue_seq=1,
        runtime_binding_id=binding_id,
        runtime_profile_id=profile_id,
    )
    await db_session.commit()
    operation_id, op_revision = await h.make_purge_operation(
        db_session, conversation_id, purge_revision
    )
    ctx = {
        "conversation_id": conversation_id,
        "identity": identity,
        "purge_revision": purge_revision,
        "operation_id": operation_id,
        "op_revision": op_revision,
        "run_id": run.id,
    }

    outcome = await _erase(db_session, ctx)
    await db_session.commit()

    assert outcome.blocked
    assert outcome.block_reason == REASON_PURGE_OWNER_UNAVAILABLE
    assert outcome.ack_digest is None
    fence = await h.fence_model(db_session, conversation_id)
    assert fence.state == ErasureFenceState.ACTIVE.value
    op = await h.operation_model(db_session, operation_id)
    assert op.state == "blocked"
    assert op.failure_code == REASON_PURGE_OWNER_UNAVAILABLE


async def test_legal_hold_blocks(db_session):
    """active legal hold -> purge_blocked_by_legal_hold，正文不动，fence active。

    变异杀手：删 legal hold 检查 -> hold conversation 进入清除 -> assert blocked 失败。

    I1 语义更新：create_legal_hold 推进 Conversation.hold_revision，operation
    必须以 hold 后的 revision 为 snapshot（hold 先行 + snapshot=1），否则按
    G2 drift 拒绝（先 operation 后 hold 的旧序列不再是合法 blocked 基线）。
    """
    conversation_id, identity, purge_revision = await h.seed_purgeable(db_session)
    run = await h.seed_completed_run(
        db_session, conversation_id=conversation_id, identity=identity
    )
    await h.seed_run_event(db_session, run=run)
    await h.seed_compatibility_output(db_session, run=run)
    await h.seed_turn_input(db_session, run=run)
    await AgentErasureRepository(db_session).create_legal_hold(
        tenant_id=h.TENANT_ID,
        conversation_id=conversation_id,
        reason_code="litigation",
        purpose="ongoing case",
        actor_id=h.ACTOR_ID,
    )
    await db_session.commit()
    operation_id, op_revision = await h.make_purge_operation(
        db_session, conversation_id, purge_revision, hold_revision_snapshot=1
    )
    ctx = {
        "conversation_id": conversation_id,
        "identity": identity,
        "purge_revision": purge_revision,
        "operation_id": operation_id,
        "op_revision": op_revision,
        "run_id": run.id,
    }

    outcome = await _erase(db_session, ctx)
    await db_session.commit()

    assert outcome.blocked
    assert outcome.block_reason == REASON_PURGE_BLOCKED_BY_LEGAL_HOLD
    assert outcome.ack_digest is None
    fence = await h.fence_model(db_session, ctx["conversation_id"])
    assert fence.state == ErasureFenceState.ACTIVE.value
    op = await h.operation_model(db_session, ctx["operation_id"])
    assert op.state == "blocked"
    assert op.failure_code == REASON_PURGE_BLOCKED_BY_LEGAL_HOLD
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == PurgeOwnerState.BLOCKED.value
    assert cp.reason_code == REASON_PURGE_BLOCKED_BY_LEGAL_HOLD


async def test_compatibility_run_without_binding_acks(db_session):
    """compatibility Run（runtime_binding_id=NULL）不触发 runtime blocker -> 可 ACK。

    即使会话有 native binding，只要 Run 本身是 compatibility（binding_id NULL），
    execution owner 仍可清除（runtime ref 不归 execution owner 管）。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    # seed_purgeable_with_run 的 Run 是 compatibility（binding_id NULL）。
    outcome = await _erase(db_session, ctx)
    await db_session.commit()
    assert outcome.erased


async def test_blocked_body_untouched(db_session):
    """blocked 时正文未被清除（terminal_output_ref / event payload_inline 仍在）。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    await h.seed_nonterminal_run(
        db_session,
        conversation_id=ctx["conversation_id"],
        identity=ctx["identity"],
        queue_seq=2,
        status="running",
    )
    await db_session.commit()

    outcome = await _erase(db_session, ctx)
    await db_session.commit()
    assert outcome.blocked

    completed = await h.run_model(db_session, ctx["run_id"])
    assert completed.terminal_output_ref is not None  # 未清
    assert completed.output_publish_state == "published"  # 未 suppress
    assert completed.created_by == h.ACTOR_ID  # 未匿名化


# ---------------------------------------------------------------------------
# round-1 复审返修反例（P1-1/3/5/6）
# ---------------------------------------------------------------------------


async def test_round1_p1_3_binding_without_run_blocks(db_session):
    """P1-3：RuntimeSessionBinding 不被任何 Run 引用也须 blocked（直查 binding 表）。

    旧实现从 AgentRunModel join binding，只看被 Run 引用的 binding；存在
    ``runtime_session_ref`` 活跃但无 Run 引用时，execution 会错误 ACK。本测试
    不建任何 Run，仅建 binding -- 旧实现会被此场景放行。
    变异杀手：把 blocker 改回 ``AgentRunModel JOIN RuntimeSessionBindingModel`` ->
    binding_count=0（因为无 Run 引用）-> 进入清除路径（runtime ref 不被清）-> blocked 断言失败。
    """
    conversation_id, identity, purge_revision = await h.seed_purgeable(db_session)
    profile_id, binding_id = await h.seed_native_binding(
        db_session, conversation_id=conversation_id
    )
    await db_session.commit()  # 注意：未建任何 AgentRun，binding 是孤儿
    operation_id, op_revision = await h.make_purge_operation(
        db_session, conversation_id, purge_revision
    )
    ctx = {
        "conversation_id": conversation_id,
        "identity": identity,
        "purge_revision": purge_revision,
        "operation_id": operation_id,
        "op_revision": op_revision,
        "run_id": uuid.uuid4(),  # placeholder
    }
    outcome = await _erase(db_session, ctx)
    await db_session.commit()
    assert outcome.blocked
    assert outcome.block_reason == REASON_PURGE_OWNER_UNAVAILABLE
    op = await h.operation_model(db_session, operation_id)
    assert op.state == "blocked"
    # 验证 binding 仍在（execution 不清 binding）
    binding = await db_session.get(
        RuntimeSessionBindingModel, binding_id
    )
    assert binding is not None
    assert binding.runtime_session_ref is not None


async def test_round1_p1_5_blocked_projects_purge_state_and_scan_digest(
    db_session,
):
    """P1-5：blocked 路径必须同事务投影 ``Conversation.purge_state=blocked`` 并把
    ``scan.digest()`` 写入 ``checkpoint.checkpoint_digest``。

    旧实现 ``_record_blocked`` 不接 conversation/scan，blocked 后
    ``purge_state`` 仍为 running、``checkpoint_digest`` 为空。
    变异杀手：移除 ``conversation.purge_state = BLOCKED`` 赋值或
    ``checkpoint.checkpoint_digest = scan.digest()`` 赋值 -> 本测试变红。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    await h.seed_nonterminal_run(
        db_session,
        conversation_id=ctx["conversation_id"],
        identity=ctx["identity"],
        queue_seq=2,
        status="running",
    )
    await db_session.commit()
    outcome = await _erase(db_session, ctx)
    await db_session.commit()
    assert outcome.blocked

    from sqlalchemy import select

    from app.contexts.agent_workspace.infrastructure.models import (
        ConversationModel,
    )
    conv = (
        await db_session.execute(
            select(ConversationModel).where(
                ConversationModel.id == ctx["conversation_id"]
            )
        )
    ).scalar_one()
    assert conv.purge_state == "blocked", (
        "Conversation.purge_state must be blocked after blocked outcome "
        "(P1-5: blocked projection gap)"
    )
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == "blocked"
    assert cp.checkpoint_digest, (
        "checkpoint_digest must be populated with scan.digest() on blocked "
        "(P1-5: scan evidence missing)"
    )
    assert cp.checkpoint_digest == outcome.body_scan.digest()


async def test_round1_p1_1_suppressed_envelope_acked_zero_scan(db_session):
    """P1-1：已 suppressed 但保留完整 terminal envelope 的 Run 必须被清除并 ACK。

    旧实现清除与 scan 都按 ``output_publish_state != 'suppressed'`` 跳过这类行，
    故会保留 ``terminal_output_ref/media_type/classification/message_id`` 而
    body_scan 报告非零，blocked 而非 erased。``ck_agent_run_terminal_output`` 的
    第一分支明确允许 suppressed 保留完整 envelope（合法 B1 审计状态），所以旧
    实现把这种行留在 DB 头也不回地 ACKed。

    变异杀手：把清除谓词改回 ``output_publish_state != 'suppressed'`` 或
    把 scan 谓词改回 ``output_publish_state != 'suppressed' AND ...`` ->
    本测试变红。
    """
    from sqlalchemy import update as _sa_update  # noqa: F401  (unused, doc reference)
    ctx = await h.seed_purgeable_with_run(db_session)
    # 强制把该 Run 改为 suppressed+完整 envelope（合法 B1 状态）。
    from sqlalchemy import text
    await db_session.execute(text(
        "UPDATE metaedu.agent_runs SET output_publish_state='suppressed' "
        "WHERE id=:r"
    ), {"r": ctx["run_id"]})
    await db_session.commit()

    outcome = await _erase(db_session, ctx)
    await db_session.commit()
    # P1-1 修订后，suppressed+完整 envelope 的行也被清，scan 应为零，erased。
    assert outcome.erased, (
        f"expected erased (suppressed envelope should be cleared too), "
        f"got blocked={outcome.blocked} reason={outcome.block_reason}"
    )
    completed = await h.run_model(db_session, ctx["run_id"])
    assert completed.terminal_output_ref is None
    assert completed.terminal_output_media_type is None
    assert completed.terminal_output_classification is None
    assert completed.terminal_message_id is None


async def test_i1_hold_drift_rejects_execution_entry(db_session):
    """I1：hold create 推进 hold_revision 后，旧 snapshot 的 execution entry
    必须被拒绝（G2 drift），正文/fence/checkpoint/operation 零变化。

    与 workspace 侧 test_create_drift_rejects_participant_entry 同构——
    execution `_load_verified_operation` 独立实现同校验（hold_revision_snapshot
    != conversation.hold_revision），I1 后从 vacuous 变为 live，须有独立
    mutation kill（删该校验即本测试转红）。
    """
    conversation_id, identity, purge_revision = await h.seed_purgeable(db_session)
    run = await h.seed_completed_run(
        db_session, conversation_id=conversation_id, identity=identity
    )
    await h.seed_run_event(db_session, run=run)
    await h.seed_compatibility_output(db_session, run=run)
    await h.seed_turn_input(db_session, run=run)
    operation_id, op_revision = await h.make_purge_operation(
        db_session, conversation_id, purge_revision, hold_revision_snapshot=0
    )
    await AgentErasureRepository(db_session).create_legal_hold(
        tenant_id=h.TENANT_ID,
        conversation_id=conversation_id,
        reason_code="litigation",
        purpose="drift case",
        actor_id=h.ACTOR_ID,
    )
    await db_session.commit()
    ctx = {
        "conversation_id": conversation_id,
        "identity": identity,
        "purge_revision": purge_revision,
        "operation_id": operation_id,
        "op_revision": op_revision,
        "run_id": run.id,
    }

    with pytest.raises(ValueError, match="hold_revision_snapshot"):
        await _erase(db_session, ctx)
    await db_session.rollback()

    completed = await h.run_model(db_session, ctx["run_id"])
    assert completed.terminal_output_ref is not None  # 正文未被清除
    # 零写断言含 fence：entry 在同事务内惰性建 fence 后才在 hold 分支 raise
    # drift；显式 rollback 后 fence 零行（整个失败 entry 的事务写全部归零）。
    fence = await h.fence_model_or_none(db_session, ctx["conversation_id"])
    assert fence is None
    op = await h.operation_model(db_session, ctx["operation_id"])
    assert op.state == "scheduled"
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == PurgeOwnerState.PENDING.value
