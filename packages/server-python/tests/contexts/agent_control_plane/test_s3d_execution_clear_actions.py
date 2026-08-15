"""R1-S3-D：execution.core.v1 正文清除动作 + final body scan + ACK（主路径）。

Spec §5.2/§7.2（plan §R1-S3「S3-D 契约注记」）。

变异验证（逐项删除清除动作均应被击杀）：
- 删 ``_clear_terminal_outputs`` -> terminal_output_ref 残留 -> scan 非零 -> blocked。
- 删 terminal code/reason 裁剪（第二循环）-> terminal_code 不在白名单 -> scan 非零 -> blocked。
- 删 ``_clear_context_snapshots`` -> context_snapshot_ref 残留 -> scan 非零 -> blocked。
- 删 ``_clear_compatibility_outputs`` -> CompatibilityOutput payload_state=present
  -> scan 非零 -> blocked。
- 删 ``_clear_event_payloads`` -> payload_inline 残留 -> scan 非零 -> blocked。
- 删 ``_anonymize_actors`` -> created_by 残留 -> scan 非零 -> blocked。
- 删 scan 的 ``payload_ref`` 分支（只查 inline）-> erased 后注入 payload_ref 事件 ->
  scan 漏报 -> erased+非零 fail closed 不触发（本测试击杀该变异）。

envelope/digest 保留（Spec §7.2 tombstone）：terminal_result_digest/
terminal_output_digest/terminal_output_size、CompatibilityOutput output_digest/
response_digest、RunEvent payload_digest/payload_size/seq 全部保留。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.composition.agent_actor_digest import actor_audit_digest
from app.composition.agent_suppression_reasons import SUPPRESSION_REASON_CODES
from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
    REASON_EXECUTION_BODY_SCAN_NONZERO,
)
from app.contexts.agent_execution.infrastructure.models import (
    CompatibilityOutputModel,
    RunEventModel,
    TurnInputModel,
)
from app.contexts.agent_workspace.domain import ErasureFenceState, PurgeOwnerState
from tests.contexts.agent_control_plane import s3d_helpers as h

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 主路径：清除全部正文 + envelope 保留 + scan 零 + ACK
# ---------------------------------------------------------------------------


async def test_erase_clears_all_body_and_acks(db_session):
    """主路径：completed Run（terminal output + context snapshot + event payload +
    compatibility output + actor）清除后 scan 为零、fence erased + ack_digest、
    checkpoint acked；R1-S5-I2：operation/Conversation 聚合投影归 coordinator，
    participant 零共享写（保持 scheduled/running 生命周期值）。

    逐项变异杀手：删任一清除动作 -> scan 非零 -> blocked（非 erased）。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    outcome = await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )
    await db_session.commit()

    assert outcome.erased
    assert outcome.blocked is False
    assert outcome.ack_digest is not None
    assert len(outcome.ack_digest) == 64
    assert outcome.fence.state is ErasureFenceState.ERASED
    assert outcome.fence.ack_digest == outcome.ack_digest
    assert outcome.body_scan.total == 0

    # checkpoint acked（owner 事实）；operation/Conversation 投影归 coordinator。
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == PurgeOwnerState.ACKED.value
    assert cp.ack_digest == outcome.ack_digest
    assert cp.checkpoint_digest is not None
    assert cp.checkpoint_digest != cp.ack_digest
    assert cp.reason_code is None
    op = await h.operation_model(db_session, ctx["operation_id"])
    assert op.state == "scheduled"  # R1-S5-I2
    assert op.failure_code is None
    conv = await db_session.get(
        h.ConversationModel, ctx["conversation_id"]
    )
    assert conv.purge_state == "scheduled"


async def test_terminal_output_suppressed_and_envelope_preserved(db_session):
    """terminal output suppress：output_publish_state->suppressed + 清
    ref/media_type/classification/message_id，保留 result_digest/output_digest/size。

    变异杀手：删 ``_clear_terminal_outputs`` -> terminal_output_ref 残留 +
    output_publish_state != suppressed -> scan 非零 -> blocked（assert erased 失败）。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )
    await db_session.commit()

    run = await h.run_model(db_session, ctx["run_id"])
    assert run.output_publish_state == "suppressed"
    assert run.terminal_output_ref is None
    assert run.terminal_output_media_type is None
    assert run.terminal_output_classification is None
    assert run.terminal_message_id is None
    # envelope 保留（tombstone 审计）。
    assert run.terminal_result_digest == h._DIGEST
    assert run.terminal_output_digest == h._DIGEST
    assert run.terminal_output_size == 42
    assert run.status == "completed"  # terminal status 不改写


async def test_terminal_code_reason_trimmed_to_whitelist(db_session):
    """terminal_code/reason 裁剪为受控 suppression_reason_code（白名单）。

    变异杀手：删 terminal code/reason 裁剪 -> terminal_code='completed' 不在白名单
    -> scan.unredacted_terminal_codes != 0 -> blocked（assert erased 失败）。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )
    await db_session.commit()

    run = await h.run_model(db_session, ctx["run_id"])
    assert run.terminal_code in SUPPRESSION_REASON_CODES
    assert run.terminal_reason in SUPPRESSION_REASON_CODES
    # 默认 _ERASURE_REDACTED_REASON='retention_expired' -> 归一后仍在白名单。
    assert run.terminal_code == "retention_expired"
    assert run.terminal_reason == "retention_expired"


async def test_context_snapshot_cleared(db_session):
    """context_snapshot_ref/digest/classification -> NULL。

    变异杀手：删 ``_clear_context_snapshots`` -> context_snapshot_ref 残留 ->
    scan.uncleared_context_snapshots != 0 -> blocked。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )
    await db_session.commit()

    run = await h.run_model(db_session, ctx["run_id"])
    assert run.context_snapshot_ref is None
    assert run.context_snapshot_digest is None
    assert run.context_snapshot_classification is None


async def test_compatibility_output_redacted_and_digests_preserved(db_session):
    """CompatibilityOutput reply_text/response_envelope -> NULL + payload_state=redacted，
    保留 output_digest/response_digest。

    变异杀手：删 ``_clear_compatibility_outputs`` -> payload_state=present 残留 ->
    scan.unredacted_compatibility_outputs != 0 -> blocked。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )
    await db_session.commit()

    compat = (
        (
            await db_session.execute(
                select(CompatibilityOutputModel).where(
                    CompatibilityOutputModel.run_id == ctx["run_id"]
                )
            )
        )
        .scalars()
        .one()
    )
    assert compat.payload_state == "redacted"
    assert compat.reply_text is None
    assert compat.response_envelope is None
    # digest 保留。
    assert compat.output_digest == h._DIGEST
    assert compat.response_digest == h._DIGEST


async def test_event_payload_tombstoned_and_envelope_preserved(db_session):
    """RunEvent payload_inline -> NULL + payload_state=redacted，seq 不变，
    payload_digest/payload_size 保留。

    变异杀手：删 ``_clear_event_payloads`` -> payload_inline 残留 ->
    scan.unredacted_event_payloads != 0 -> blocked。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )
    await db_session.commit()

    event = (
        (
            await db_session.execute(
                select(RunEventModel).where(
                    RunEventModel.run_id == ctx["run_id"]
                )
            )
        )
        .scalars()
        .one()
    )
    assert event.payload_state == "redacted"
    assert event.payload_inline is None
    assert event.payload_ref is None  # 本就无 external ref
    assert event.seq == 1  # seq 不改写
    assert event.payload_digest == h._DIGEST
    assert event.payload_size is not None  # envelope 保留


async def test_actors_anonymized_with_hmac_digest(db_session):
    """AgentRun + TurnInput created_by -> NULL + actor_state=redacted + HMAC
    actor_identity_digest（共享版本化 helper，非普通 SHA-256）。

    变异杀手：删 ``_anonymize_actors`` -> created_by 残留 + actor_state=present ->
    scan.unanonymized_run_actors + turn_input_actors != 0 -> blocked。
    """
    import hashlib

    ctx = await h.seed_purgeable_with_run(db_session)
    await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )
    await db_session.commit()

    expected_digest = actor_audit_digest(
        secret=h.AUDIT_SECRET,
        secret_version=h.AUDIT_SECRET_VERSION,
        tenant_id=h.TENANT_ID,
        actor_id=h.ACTOR_ID,
    )
    plain = hashlib.sha256(h.TENANT_ID.bytes + h.ACTOR_ID.bytes).hexdigest()

    run = await h.run_model(db_session, ctx["run_id"])
    assert run.created_by is None
    assert run.actor_state == "redacted"
    assert run.actor_identity_digest == expected_digest
    assert len(run.actor_identity_digest) == 64
    assert run.actor_identity_digest != plain  # HMAC，非普通 SHA-256

    turn = (
        (
            await db_session.execute(
                select(TurnInputModel).where(TurnInputModel.run_id == ctx["run_id"])
            )
        )
        .scalars()
        .one()
    )
    assert turn.created_by is None
    assert turn.actor_state == "redacted"
    assert turn.actor_identity_digest == expected_digest
    assert len(turn.actor_identity_digest) == 64


# ---------------------------------------------------------------------------
# scan 的 payload_ref 分支变异杀手 + scan 非零禁止 ACK
# ---------------------------------------------------------------------------


async def test_scan_counts_payload_ref_not_just_inline(db_session):
    """scan 的 RunEvent 计数必须覆盖 ``payload_ref IS NOT NULL``（不只 inline）。

    变异杀手：把 scan 的 ``or_(inline, ref)`` 改成只 ``inline IS NOT NULL`` ->
    erased 后注入 payload_ref-only 事件 -> scan 漏报 total=0 -> 不 raise
    ``body scan non-zero``（本测试 assert raise -> 击杀变异）。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    first = await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )
    await db_session.commit()
    assert first.erased
    op_revision_after = await h.op_revision(db_session, ctx["operation_id"])

    # 注入 payload_ref-only 事件（payload_inline=NULL, payload_state=external）。
    run = await h.run_model(db_session, ctx["run_id"])
    await h.seed_run_event(
        db_session,
        run=run,
        seq=2,
        payload_inline=None,
        payload_ref="obj://external/payload",
        payload_state="external",
    )
    await db_session.commit()

    # erased + 非零 scan -> fail closed（不接受孤立 ACK）。
    with pytest.raises(ValueError, match="body scan non-zero"):
        await h.participant(db_session).erase_execution_body(
            tenant_id=h.TENANT_ID,
            conversation_id=ctx["conversation_id"],
            purge_revision=ctx["purge_revision"],
            purge_operation_id=ctx["operation_id"],
            expected_operation_revision=op_revision_after,
        )


async def test_scan_nonzero_blocks_ack(db_session, monkeypatch):
    """scan 非零 -> 不得 ACK，fence erasing->blocked + operation/checkpoint 记 blocked，
    正常返回（不抛异常致回滚）。重试 scan 归零 -> ACK。

    变异杀手：删 scan 非零分支 -> 清除不完整仍 ACK -> assert blocked 失败。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    participant = h.participant(db_session)
    real_scan = participant.scan_execution_body

    async def _nonzero_scan(*, tenant_id, conversation_id):
        real = await real_scan(tenant_id=tenant_id, conversation_id=conversation_id)
        return type(real)(
            unredacted_terminal_outputs=real.unredacted_terminal_outputs,
            uncleared_context_snapshots=real.uncleared_context_snapshots,
            unredacted_compatibility_outputs=real.unredacted_compatibility_outputs,
            unredacted_event_payloads=real.unredacted_event_payloads,
            unredacted_terminal_codes=real.unredacted_terminal_codes + 1,
            unanonymized_run_actors=real.unanonymized_run_actors,
            unanonymized_turn_input_actors=real.unanonymized_turn_input_actors,
        )

    monkeypatch.setattr(participant, "scan_execution_body", _nonzero_scan)
    blocked = await participant.erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )
    await db_session.commit()

    assert blocked.blocked
    assert blocked.block_reason == REASON_EXECUTION_BODY_SCAN_NONZERO
    assert blocked.ack_digest is None
    assert not blocked.erased
    fence = await h.fence_model(db_session, ctx["conversation_id"])
    assert fence.state == ErasureFenceState.BLOCKED.value
    op = await h.operation_model(db_session, ctx["operation_id"])
    assert op.state == "scheduled"  # R1-S5-I2：投影归 coordinator
    assert op.failure_code is None
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == PurgeOwnerState.BLOCKED.value
    op_revision_after = op.revision

    # 重试 scan 归零 -> ACK（清除幂等）。
    outcome = await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=op_revision_after,
    )
    await db_session.commit()
    assert outcome.erased
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == PurgeOwnerState.ACKED.value
