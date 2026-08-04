"""R1-S3-E round-1 复审反例（P1 already-suppressed / P2 claim CAS）。

- **P1**：S3-D eraser 先把 completed Run 翻 ``output_publish_state='suppressed'``
  并保留 execution outbox 给 S4；此后迟到的 ``dispatch_output`` 在 workspace fence
  抛 ``LateBodyWriteRejectedError``，deterministic terminalize 必须**幂等接受**
  already-suppressed Run，仍把 outbox 置 ``cancelled``、不重回可重试集。首实现复用
  人工 ``suppress_output_projection``（只接受 pending/dead_letter），遇 already-
  suppressed Run 抛冲突 -> outbox 卡 claimed 继续重试（本测试变异可检出）。
- **P2**：deterministic terminalize 必须绑定当前 delivery claim（payload_digest +
  status=claimed + attempt_count + claimed_by CAS），过期 worker 不得覆盖后来
  worker 的 claim；同一 deterministic 终态已落（status 已非 claimed）时幂等 no-op。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.composition.agent_control_plane import AgentBridgeDispatcher
from app.contexts.agent_execution.domain import (
    OutputPublishState,
)
from app.contexts.agent_execution.domain.errors import (
    ExecutionIntegrationConflictError,
)
from app.contexts.agent_execution.infrastructure.bridge_repository import (
    ExecutionBridgeRepository,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    ExecutionOutboxModel,
)
from app.contexts.agent_workspace.domain.errors import LateBodyWriteRejectedError
from tests.contexts.agent_control_plane import s3d_helpers as h
from tests.contexts.agent_control_plane.helpers import TENANT_ID, StaticOutputReader
from tests.contexts.agent_control_plane.test_s3e_dispatch_output_late_write import (
    _completed_run_with_pending_outbox,
    _flip_workspace_fence_to_erased,
)

pytestmark = pytest.mark.asyncio

_EXECUTION_OWNER = h.EXECUTION_CORE_OWNER


async def _read_outbox(session_factory, outbox_id) -> ExecutionOutboxModel:
    async with session_factory() as session:
        row = await session.get(ExecutionOutboxModel, outbox_id)
        assert row is not None
        return row


async def test_late_write_after_s3d_erasure_terminalizes_idempotently(
    db_session, session_factory
):
    """P1 反例：S3-D 先行把 Run 翻 ``suppressed``（保留 outbox 给 S4），迟到的
    ``dispatch_output`` 仍须 deterministic terminalize（outbox cancelled、不重回可
    重试集）。

    首实现复用人工 ``suppress_output_projection``，它只接受 Run
    ``output_publish_state ∈ {pending, dead_letter}``，遇 already-suppressed Run 抛
    ``ExecutionIntegrationConflictError`` -> deterministic 落库失败、outbox 卡
    ``claimed`` 继续重试（变异可检出）。专用 ``terminalize_output_late_write``
    幂等接受 already-suppressed Run。

    round-2 P2：本测试**跑真实** ``ExecutionErasureParticipant.erase_execution_body``
    （completed Run + pending outbox -> erase -> Run suppressed + outbox 保留），
    而非手工造状态——真实 eraser 在同一 UPDATE 原子设置 suppressed 并清 terminal
    字段，**不触发** ``ck_agent_run_terminal_output`` 冲突（round-1 的错误假设已
    从 plan/工作台删除）。
    """
    conversation_id, run, outbox = await _completed_run_with_pending_outbox(
        db_session, session_factory, content=b"# erased answer"
    )
    payload_before = outbox.payload_inline
    await db_session.commit()

    # 真实 S3-D eraser 前置：Conversation deleted + purge_after 已过（Spec §3）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversations SET state = 'deleted', "
            "purge_after = clock_timestamp() - interval '1 second' "
            "WHERE tenant_id = :t AND id = :c"
        ),
        {"t": TENANT_ID, "c": conversation_id},
    )
    await db_session.commit()
    # 真实 participant erase：completed Run（output_publish_state=pending）原子
    # suppressed + 清 terminal 字段；execution outbox 保留给 S4（不清 transport）。
    op_id, op_rev = await h.make_purge_operation(db_session, conversation_id, 1)
    outcome = await h.participant(db_session).erase_execution_body(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=1,
        purge_operation_id=op_id,
        expected_operation_revision=op_rev,
    )
    assert outcome.erased
    await db_session.commit()

    # erase 后：Run suppressed、outbox 仍 pending（S3-D 不清 transport owner）。
    erased_run = await db_session.get(AgentRunModel, run.id)
    assert erased_run is not None
    await db_session.refresh(erased_run)
    assert erased_run.output_publish_state == OutputPublishState.SUPPRESSED.value
    persisted = await _read_outbox(session_factory, outbox.id)
    assert persisted.status == "pending", "S3-D 保留 outbox 给 S4"

    # workspace fence erased -> 迟到的 dispatch_output 抛 LateBodyWriteRejectedError，
    # deterministic terminalize 幂等接受 already-suppressed Run。
    await _flip_workspace_fence_to_erased(
        db_session, tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    await db_session.commit()
    dispatcher = AgentBridgeDispatcher(
        session_factory,
        worker_id="s3e-round1",
        output_reader=StaticOutputReader(b"# erased answer"),
    )
    with pytest.raises(LateBodyWriteRejectedError):
        await dispatcher.dispatch_output(event_id=outbox.id)

    final = await _read_outbox(session_factory, outbox.id)
    assert final.status == "cancelled", "already-suppressed Run 也应 terminalize"
    assert final.decision_reason == "late_body_write_rejected"
    assert final.decision_digest is not None
    assert final.claimed_by is None and final.claimed_at is None
    # S4 边界：payload 原样保留。
    assert final.payload_inline == payload_before
    final_run = await db_session.get(AgentRunModel, run.id)
    assert final_run is not None
    await db_session.refresh(final_run)
    assert final_run.output_publish_state == OutputPublishState.SUPPRESSED.value

    # 不重回可重试集：再 dispatch 无事件可 claim。
    again = AgentBridgeDispatcher(
        session_factory,
        worker_id="s3e-round1-retry",
        output_reader=StaticOutputReader(b"# erased answer"),
    )
    assert await again.dispatch_output(event_id=outbox.id) is False


async def test_late_write_terminalize_rejects_stale_claim(db_session, session_factory):
    """P2 反例：attempt N 的过期 worker terminalize 不得覆盖 attempt N+1 的新 claim。

    worker2 把 outbox 从 pending claim 到 attempt 1；worker1（过期，仍持 attempt 0 +
    自己的 claimant）调 terminalize -> CAS 失败 fail closed，outbox 仍归 worker2。
    """
    _, run, outbox = await _completed_run_with_pending_outbox(
        db_session, session_factory, content=b"stale claim output"
    )
    await db_session.commit()

    # worker2 接管当前 claim（pending[attempt 0] -> claimed[attempt 1]）。
    async with session_factory() as session, session.begin():
        repo = ExecutionBridgeRepository(session)
        claimed = await repo.claim_output_outbox(
            worker_id="worker-2",
            now=await session.scalar(text("SELECT clock_timestamp()")),
            stale_before=await session.scalar(
                text("SELECT clock_timestamp() - interval '60 seconds'")
            ),
            event_id=outbox.id,
        )
        assert claimed is not None
        _, event = claimed
    current = await _read_outbox(session_factory, outbox.id)
    assert current.status == "claimed"
    assert current.attempt_count == 1
    assert current.claimed_by == "worker-2"

    # 过期 worker1（attempt 0，claimant worker-1）terminalize -> CAS 拒。
    async with session_factory() as session, session.begin():
        repo = ExecutionBridgeRepository(session)
        with pytest.raises(ExecutionIntegrationConflictError):
            await repo.terminalize_output_late_write(
                tenant_id=TENANT_ID,
                event_id=outbox.id,
                payload_digest=current.payload_digest,
                expected_attempt=0,  # 过期 attempt（当前已是 1）
                claimant_id="worker-1",  # 过期 claimant（当前已是 worker-2）
                decided_at=await session.scalar(text("SELECT clock_timestamp()")),
            )

    # outbox 仍归 worker2，未被覆盖。
    after = await _read_outbox(session_factory, outbox.id)
    assert after.status == "claimed"
    assert after.attempt_count == 1
    assert after.claimed_by == "worker-2"
    assert after.decision_reason is None


async def test_late_write_terminalize_fails_closed_when_takeover_returns_to_pending(
    db_session, session_factory
):
    """round-2 P1 反例：``claim N -> takeover N+1 -> transient 回 pending -> stale
    terminalize（attempt N）`` 必须 fail closed，事件仍 ``pending``（继续重试集）。

    round-1 实现对所有 ``status != 'claimed'`` 直接 return（幂等 no-op），导致
    takeover 后回 pending 的事件被 stale worker 误判「已 terminalize」而放任重试
    （事件仍 pending、decision_reason=None）。修订后仅完整匹配的既有 late-write
    终态 no-op，pending 一律 fail closed。变异：恢复「非 claimed 即 return」->
    本测试转红。
    """
    _, run, outbox = await _completed_run_with_pending_outbox(
        db_session, session_factory, content=b"takeover pending output"
    )
    await db_session.commit()
    base = await _read_outbox(session_factory, outbox.id)
    digest = base.payload_digest

    # worker1 claim（pending[0] -> claimed[1]）。
    async with session_factory() as session, session.begin():
        repo = ExecutionBridgeRepository(session)
        now = await session.scalar(text("SELECT clock_timestamp()"))
        stale = await session.scalar(
            text("SELECT clock_timestamp() - interval '60 seconds'")
        )
        assert (
            await repo.claim_output_outbox(
                worker_id="worker-1", now=now, stale_before=stale, event_id=outbox.id
            )
            is not None
        )
    # worker1 transient 失败 -> 回 pending（attempt 1, next_attempt 未来）。
    async with session_factory() as session, session.begin():
        repo = ExecutionBridgeRepository(session)
        now = await session.scalar(text("SELECT clock_timestamp()"))
        await repo.record_output_delivery_failure(
            tenant_id=TENANT_ID,
            event_id=outbox.id,
            payload_digest=digest,
            error_code="RuntimeError",
            next_attempt_at=now,
            max_attempts=5,
            expected_attempt=1,
            claimant_id="worker-1",
        )
    # worker2 接管（pending[1] -> claimed[2]）再 transient 回 pending。
    async with session_factory() as session, session.begin():
        repo = ExecutionBridgeRepository(session)
        now = await session.scalar(text("SELECT clock_timestamp()"))
        stale = await session.scalar(
            text("SELECT clock_timestamp() - interval '60 seconds'")
        )
        assert (
            await repo.claim_output_outbox(
                worker_id="worker-2", now=now, stale_before=stale, event_id=outbox.id
            )
            is not None
        )
        await repo.record_output_delivery_failure(
            tenant_id=TENANT_ID,
            event_id=outbox.id,
            payload_digest=digest,
            error_code="RuntimeError",
            next_attempt_at=now,
            max_attempts=5,
            expected_attempt=2,
            claimant_id="worker-2",
        )
    current = await _read_outbox(session_factory, outbox.id)
    assert current.status == "pending"
    assert current.attempt_count == 2

    # 过期 worker1（仍持 attempt 1 + 自己 claimant）terminalize -> fail closed。
    async with session_factory() as session, session.begin():
        repo = ExecutionBridgeRepository(session)
        with pytest.raises(ExecutionIntegrationConflictError):
            await repo.terminalize_output_late_write(
                tenant_id=TENANT_ID,
                event_id=outbox.id,
                payload_digest=digest,
                expected_attempt=1,
                claimant_id="worker-1",
                decided_at=await session.scalar(text("SELECT clock_timestamp()")),
            )

    # 事件仍 pending（可重试集），未被 stale worker 静默吞掉。
    after = await _read_outbox(session_factory, outbox.id)
    assert after.status == "pending"
    assert after.decision_reason is None


async def test_late_write_terminalize_idempotent_when_already_terminal(
    db_session, session_factory
):
    """P2 幂等：outbox 已被 terminalize（status 非 claimed）时，同一 deterministic
    结论下不覆盖他人终态，直接 no-op（不抛错、不改写 digest）。"""
    _, run, outbox = await _completed_run_with_pending_outbox(
        db_session, session_factory, content=b"idempotent terminal"
    )
    await db_session.commit()

    # 第一次 terminalize（真实 claim 后）。
    async with session_factory() as session, session.begin():
        repo = ExecutionBridgeRepository(session)
        now = await session.scalar(text("SELECT clock_timestamp()"))
        claimed = await repo.claim_output_outbox(
            worker_id="worker-1",
            now=now,
            stale_before=await session.scalar(
                text("SELECT clock_timestamp() - interval '60 seconds'")
            ),
            event_id=outbox.id,
        )
        assert claimed is not None
        row_now = await session.get(ExecutionOutboxModel, outbox.id)
        await repo.terminalize_output_late_write(
            tenant_id=TENANT_ID,
            event_id=outbox.id,
            payload_digest=row_now.payload_digest,
            expected_attempt=row_now.attempt_count,
            claimant_id="worker-1",
            decided_at=now,
        )
    first = await _read_outbox(session_factory, outbox.id)
    assert first.status == "cancelled"
    first_digest = first.decision_digest

    # 第二次（重复 terminalize，status 已非 claimed）-> 幂等 no-op。
    async with session_factory() as session, session.begin():
        repo = ExecutionBridgeRepository(session)
        await repo.terminalize_output_late_write(
            tenant_id=TENANT_ID,
            event_id=outbox.id,
            payload_digest=first.payload_digest,
            expected_attempt=first.attempt_count,
            claimant_id="worker-1",
            decided_at=await session.scalar(text("SELECT clock_timestamp()")),
        )
    second = await _read_outbox(session_factory, outbox.id)
    assert second.status == "cancelled"
    assert second.decision_digest == first_digest, "幂等 no-op 不改写已落终态"
