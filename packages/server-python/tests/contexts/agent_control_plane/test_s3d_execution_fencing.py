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
    不重写，operation 保持 running。

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
    assert op.state == "running"  # 未被改回
    assert op.failure_code is None


async def test_erased_repairs_pending_checkpoint(db_session):
    """fence erased 但 checkpoint pending（ACK 丢失）+ operation scheduled ->
    幂等重放修复 checkpoint 到 acked、operation 到 running；purged_at 不阻断恢复。"""
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
    assert op.state == "running"  # scheduled -> running 修复
    assert op.failure_code is None


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

    with pytest.raises(ValueError, match="purge operation cancelled"):
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
    修复到 running/acked/running（三方一致）。"""
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
    assert op.state == "running"
    assert op.failure_code is None
    conv = await db_session.get(h.ConversationModel, ctx["conversation_id"])
    assert conv.purge_state == "running"
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == PurgeOwnerState.ACKED.value
    assert cp.ack_digest == fence_ack


async def test_erased_acked_checkpoint_blocked_operation_repaired(db_session):
    """erased 重放时 checkpoint=acked（digest 一致）+ operation=blocked -> checkpoint
    no-op（不重写），fall through 修 operation 到 running（round-5 P1-1：ACKed 分支
    不得早 return）。"""
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
    assert op.state == "running"
    assert op.failure_code is None
    cp = await h.checkpoint_model(db_session, ctx["operation_id"])
    assert cp.state == PurgeOwnerState.ACKED.value
    assert cp.ack_digest == fence_ack  # 未重写
