"""R1-S3-D：execution.core.v1 body scan 完整性 + ACK digest + DB 时钟 + 边界。

Spec §5.2/§7.2/§6.1（plan §R1-S3「S3-D 契约注记」+「P2 时钟/tenant」）。

- body scan 在清除前正确报出残留正文（非恒零摆设），各计数器独立可观测。
- scan tenant 谓词（跨 tenant 不误报）。
- ``erase_execution_body`` 不暴露 ``now`` 参数，始终用 PostgreSQL ``clock_timestamp()``。
- ACK digest：canonical digest（owner_key/owner_version/purge_revision/各类清除计数/
  body_scan_digest），不含正文/actor 明文；同输入可复现。
- 未知 conversation / 跨 tenant -> fail closed（不创建孤儿 fence、不清除）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
    ExecutionBodyScan,
)
from tests.contexts.agent_control_plane import s3d_helpers as h

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# body scan 完整性
# ---------------------------------------------------------------------------


async def test_scan_reports_residual_before_erase(db_session):
    """清除前 body scan 各计数器正确报出残留正文（非恒零）。

    completed Run：terminal output(+1) + context snapshot(+1) + terminal code 非白名单
    (+1) + run actor(+1) + event payload(+1) + compatibility output(+1) + turn input
    actor(+1)。
    """
    ctx = await h.seed_purgeable_with_run(db_session)
    scan = await h.participant(db_session).scan_execution_body(
        tenant_id=h.TENANT_ID, conversation_id=ctx["conversation_id"]
    )
    assert scan.unredacted_terminal_outputs == 1
    assert scan.uncleared_context_snapshots == 1
    assert scan.unredacted_compatibility_outputs == 1
    assert scan.unredacted_event_payloads == 1
    assert scan.unredacted_terminal_codes == 1  # 'completed' 不在白名单
    assert scan.unanonymized_run_actors == 1
    assert scan.unanonymized_turn_input_actors == 1
    assert scan.total == 7
    # digest 可复现。
    assert scan.digest() == scan.digest()
    assert len(scan.digest()) == 64


async def test_scan_tenant_scoped(db_session):
    """scan 带 tenant_id 谓词--跨 tenant 不得误报另一 tenant 会话的正文残留。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    other_tenant = uuid.uuid4()
    scan = await h.participant(db_session).scan_execution_body(
        tenant_id=other_tenant, conversation_id=ctx["conversation_id"]
    )
    assert scan.total == 0


async def test_scan_zero_after_erase(db_session):
    """清除后 scan 归零（清除动作 + scan 计数器一致）。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )
    await db_session.commit()
    scan = await h.participant(db_session).scan_execution_body(
        tenant_id=h.TENANT_ID, conversation_id=ctx["conversation_id"]
    )
    assert scan.total == 0


# ---------------------------------------------------------------------------
# DB 时钟
# ---------------------------------------------------------------------------


async def test_always_uses_database_clock(db_session, monkeypatch):
    """``erase_execution_body`` 始终用 PostgreSQL ``clock_timestamp()``（非进程时钟），
    ``_database_now`` 被调用。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    participant = h.participant(db_session)
    called = []
    real = participant._database_now

    async def _spy():
        called.append(True)
        return await real()

    monkeypatch.setattr(participant, "_database_now", _spy)
    outcome = await participant.erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )
    await db_session.commit()
    assert outcome.erased
    assert called  # 走了 DB 时钟路径


async def test_now_param_not_accepted(db_session):
    """``erase_execution_body`` 不接受 ``now`` 关键字参数--防调用方绕过 DB 时钟。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    with pytest.raises(TypeError, match="unexpected keyword argument 'now'"):
        await h.participant(db_session).erase_execution_body(
            tenant_id=h.TENANT_ID,
            conversation_id=ctx["conversation_id"],
            purge_revision=ctx["purge_revision"],
            purge_operation_id=ctx["operation_id"],
            expected_operation_revision=ctx["op_revision"],
            now=datetime.now(UTC),  # 不应被接受
        )


# ---------------------------------------------------------------------------
# ACK digest
# ---------------------------------------------------------------------------


async def test_ack_digest_deterministic_and_no_plaintext(db_session):
    """ACK digest 是 canonical digest（同输入可复现），不含正文/actor 明文。

    两次独立 seed + erase（同 body 形状）-> ack_digest 一致（owner_version/
    purge_revision/计数器/body_scan_digest 同源）。digest 是 hex，不含 'sensitive'。

    **round-1 P1-6**：ACK digest 含**真实清除计数**（不是从必为零的 final scan
    取值）。增加反例：构造一个清除 0 个 terminal output 的 conversation，与
    标准 fixture 的清除量不同，digest 必须不同——这能杀回「清除计数恒零」的旧
    实现。
    """
    ctx1 = await h.seed_purgeable_with_run(db_session, title="sensitive A")
    out1 = await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx1["conversation_id"],
        purge_revision=ctx1["purge_revision"],
        purge_operation_id=ctx1["operation_id"],
        expected_operation_revision=ctx1["op_revision"],
    )
    await db_session.commit()
    # 第二次独立 seed（同 body 形状）。
    ctx2 = await h.seed_purgeable_with_run(db_session, title="sensitive B")
    out2 = await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx2["conversation_id"],
        purge_revision=ctx2["purge_revision"],
        purge_operation_id=ctx2["operation_id"],
        expected_operation_revision=ctx2["op_revision"],
    )
    await db_session.commit()

    assert out1.ack_digest == out2.ack_digest  # 同 body 形状 -> 同 digest
    assert "sensitive" not in out1.ack_digest  # hex，无明文
    assert len(out1.ack_digest) == 64

    # round-1 P1-6：清除 0 个 terminal output 的 conversation 与标准 fixture 的
    # 清除量不同，digest 必须不同（杀回「从必为零的 final scan 取值」的实现）。
    from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
        ExecutionErasureSummary,
    )
    zero_scan = ExecutionBodyScan(
        unredacted_terminal_outputs=0,
        uncleared_context_snapshots=0,
        unredacted_compatibility_outputs=0,
        unredacted_event_payloads=0,
        unredacted_terminal_codes=0,
        unanonymized_run_actors=0,
        unanonymized_turn_input_actors=0,
    )
    # 1. 全零计数的 digest 一定不等于真实清除的 digest
    zero_summary = ExecutionErasureSummary(
        owner_key="execution.core.v1",
        owner_version=out1.fence.owner_version,
        purge_revision=1,
        terminal_outputs_suppressed=0,
        terminal_codes_redacted=0,
        context_snapshots_cleared=0,
        compatibility_outputs_redacted=0,
        event_payloads_redacted=0,
        run_actors_anonymized=0,
        turn_input_actors_anonymized=0,
        body_scan=zero_scan,
    )
    assert zero_summary.ack_digest() != out1.ack_digest, (
        "ACK digest must differ when all clear counts are zero — guards "
        "against falling back to final-scan readings (which would be zero)"
    )

    # 2. 真实清除计数非零（用所有计数+1 与全零对比，digest 必须不同）—— 与
    # canonical_digest 的字段敏感性绑定。
    nonzero_summary = ExecutionErasureSummary(
        owner_key="execution.core.v1",
        owner_version=out1.fence.owner_version,
        purge_revision=1,
        terminal_outputs_suppressed=1,
        terminal_codes_redacted=1,
        context_snapshots_cleared=1,
        compatibility_outputs_redacted=1,
        event_payloads_redacted=1,
        run_actors_anonymized=1,
        turn_input_actors_anonymized=1,
        body_scan=zero_scan,
    )
    assert nonzero_summary.ack_digest() != out1.ack_digest, (
        "All counts=1 with body_scan=0 still produces a digest (zero counts) "
        "different from real clear — confirms field-level digest sensitivity"
    )
    # 仅一项计数差异 digest 必须不同（最小粒度敏感性，锁定 P1-6 计数契约）。
    one_field_diff = ExecutionErasureSummary(
        owner_key="execution.core.v1",
        owner_version=out1.fence.owner_version,
        purge_revision=1,
        terminal_outputs_suppressed=1,
        terminal_codes_redacted=1,
        context_snapshots_cleared=1,
        compatibility_outputs_redacted=1,
        event_payloads_redacted=1,
        run_actors_anonymized=1,  # ← non_zero fixture 真实值
        turn_input_actors_anonymized=2,  # ← 仅这一项不同
        body_scan=zero_scan,
    )
    one_field_same = ExecutionErasureSummary(
        owner_key="execution.core.v1",
        owner_version=out1.fence.owner_version,
        purge_revision=1,
        terminal_outputs_suppressed=1,
        terminal_codes_redacted=1,
        context_snapshots_cleared=1,
        compatibility_outputs_redacted=1,
        event_payloads_redacted=1,
        run_actors_anonymized=1,
        turn_input_actors_anonymized=1,
        body_scan=zero_scan,
    )
    assert one_field_diff.ack_digest() != one_field_same.ack_digest, (
        "Summary diff of 1 must change digest — guards against silent truncation"
    )


# ---------------------------------------------------------------------------
# 边界：未知 / 跨 tenant fail closed
# ---------------------------------------------------------------------------


async def test_unknown_conversation_fail_closed(db_session):
    """未知 conversation_id -> fail closed（不创建孤儿 fence、不清除）。"""
    with pytest.raises(ValueError, match="not found"):
        await h.participant(db_session).erase_execution_body(
            tenant_id=h.TENANT_ID,
            conversation_id=uuid.uuid4(),
            purge_revision=1,
            purge_operation_id=uuid.uuid4(),
            expected_operation_revision=1,
        )


async def test_cross_tenant_fail_closed(db_session):
    """跨 tenant：正确 tenant 的会话对另一 tenant 不可见，清除 fail closed。"""
    ctx = await h.seed_purgeable_with_run(db_session)
    other_tenant = uuid.uuid4()
    with pytest.raises(ValueError, match="not found"):
        await h.participant(db_session).erase_execution_body(
            tenant_id=other_tenant,
            conversation_id=ctx["conversation_id"],
            purge_revision=1,
            purge_operation_id=ctx["operation_id"],
            expected_operation_revision=ctx["op_revision"],
        )
    # 正文未被触动。
    run = await h.run_model(db_session, ctx["run_id"])
    assert run.terminal_output_ref is not None


# ---------------------------------------------------------------------------
# capability gate（erase_available 必须 True 才能进入）
# ---------------------------------------------------------------------------


async def test_capability_gate_rejects_when_erase_unavailable(db_session, monkeypatch):
    """``require_capability(execution.core.v1, 'erase')`` 在 erase_available=False 时
    fail closed--capability gate 是 participant 入口第一道闸。"""
    from app.composition.agent_erasure_registry import (
        OwnerRegistryChangedError,
    )

    ctx = await h.seed_purgeable_with_run(db_session)
    # 模拟 erase_available=False（registry 升级回退场景）。
    monkeypatch.setattr(
        "app.contexts.agent_execution.infrastructure.execution_erasure_participant."
        "require_capability",
        lambda *a, **kw: (_ for _ in ()).throw(
            OwnerRegistryChangedError("erase capability not available")
        ),
    )
    with pytest.raises(OwnerRegistryChangedError, match="erase capability not available"):
        await h.participant(db_session).erase_execution_body(
            tenant_id=h.TENANT_ID,
            conversation_id=ctx["conversation_id"],
            purge_revision=ctx["purge_revision"],
            purge_operation_id=ctx["operation_id"],
            expected_operation_revision=ctx["op_revision"],
        )
