r"""R1-S4-C PR-B 批次3：stale/unknown epoch 的双事务协议（Tx1/Tx2 + 重放三分支）。

契约：Plan §R1-S4-C C3/R4（round-4/5/6/7/8 状态表，冻结）。

- **Tx1（消费事务，正常提交不 raise）**：inbox receipt ``status='rejected'`` +
  ``last_error_code=<具名 code>``（unknown→``epoch_unknown_rejected`` /
  stale→``epoch_stale_rejected``）+ ``receipt_tombstone_state='redacted'`` +
  ``receipt_tombstone_digest=<64-hex>``（B1f，同事务）；**仅 unknown** 在集合锁
  临界区内登记 ``epoch_unresolvable`` ledger（scope 已知 ``conversation_scope``）。
- **Tx2（第二独立事务，claim CAS）**：
  - workspace turn outbox：``status='cancelled'`` + 清 claim +
    ``last_error_code=<具名 code>`` + 同事务 Message
    ``turn_dispatch_state='abandoned'`` + ``turn_dispatch_error_code=<同一 code>``。
  - execution output outbox：``status='cancelled'`` + 清 claim + decision 四元
    （``decision_actor_id=UUID(0)`` + ``decision_reason=<具名 code>`` +
    ``decision_digest=snapshot_digest(envelope)`` + ``decided_at``）+ Run
    ``output_publish_state='suppressed'``。
- **Tx2 后重放（round-6/7 三分支）**：锁后检查 outbox 精确终态——(a) 已精确终态
  no-op；(b) ``claimed`` 且 claim 匹配续做；(c) 其余 fail closed
  （``*IntegrationConflictError``）。
- **data_anomaly**（producer epoch > 当前）：fail closed 不消费、不登记、不写
  inbox（R1，C7 不变），消息留在 outbox。
- **stale 可达性（round-5 P1-1 修订）**：epoch 分类在 ``require_active_fence``
  **之前**（非抛 ``read_fence_state``），fence erasing/erased 时 stale 走
  Tx1/Tx2 而非 raise。

变异验证：把 classify 移回 ``require_active_fence`` 之后（stale 被 raise 吞掉）
-> stale 测试转红；把 Tx1 的 ledger 登记删除 -> unknown ledger 断言转红；把
Tx2 三分支改两分支（任意 cancelled 即 no-op）-> 错误 digest 的 cancelled 测试
转红。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.composition.agent_control_plane import (
    AgentBridgeDispatcher,
    ConversationExecutionCoordinator,
    EpochRejectedError,
)
from app.contexts.agent_execution.domain import (
    OutputPublishState,
    RunStatus,
    SnapshotClassification,
    TerminalResult,
    snapshot_digest,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    ExecutionInboxModel,
    ExecutionOutboxModel,
)
from app.contexts.agent_workspace.application.bridge import (
    AgentWorkspaceBridgeService,
    PoisonedWorkspaceEvent,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    MessageModel,
    WorkspaceInboxModel,
    WorkspaceOutboxModel,
)
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
    bootstrap_workspace,
    turn_command,
)

pytestmark = pytest.mark.asyncio

_EXECUTION_OWNER = "execution.core.v1"
_WORKSPACE_OWNER = "workspace.core.v1"
_EPOCH_UNKNOWN = "epoch_unknown_rejected"
_EPOCH_STALE = "epoch_stale_rejected"


# ---------------------------------------------------------------------------
# 基建：造 turn/run + 推进 purge token / 翻 fence
# ---------------------------------------------------------------------------


async def _advance_conversation_purge(
    db_session, *, conversation_id: uuid.UUID, new_revision: int
) -> None:
    """直接推进 Conversation.purge_revision（模拟 purge 推进 epoch）。"""
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversations SET purge_revision = :r "
            "WHERE tenant_id = :t AND id = :c"
        ),
        {"r": new_revision, "t": TENANT_ID, "c": conversation_id},
    )
    await db_session.flush()


async def _force_fence_state(
    db_session, *, conversation_id: uuid.UUID, owner: str, state: str
) -> None:
    """直接把 fence 翻到指定 state（模拟 purge 推进后的 fence 状态）。"""
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET state = :state "
            "WHERE tenant_id = :t AND conversation_id = :c AND owner_key = :o"
        ),
        {"state": state, "t": TENANT_ID, "c": conversation_id, "o": owner},
    )
    await db_session.flush()


async def _seed_turn_outbox(
    db_session, session_factory, *, text_content: str = "batch3 turn"
):
    """bootstrap + submit_turn -> 一条 pending turn outbox 事件。返回
    (conversation_id, outbox_row, event_id)。"""
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, text_content),
        launch=launch,
    )
    await db_session.commit()
    return conversation_id, receipt


async def _seed_run_with_pending_output(db_session, session_factory, *, content: bytes):
    """真实 dispatch_turn + start + transition + commit_terminal -> completed Run +
    一条 pending 的 assistant publish outbox 事件。返回 (conversation_id, outbox_row)。"""
    from app.contexts.agent_execution.application.run_coordinator import RunCoordinator

    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "complete output"),
        launch=launch,
    )
    await db_session.commit()
    run = await AgentBridgeDispatcher(
        session_factory, worker_id="b3-setup"
    ).dispatch_turn(event_id=receipt.event_id)
    assert run is not None
    async with session_factory() as session, session.begin():
        started, _ = await ConversationExecutionCoordinator(session).start_run(
            tenant_id=TENANT_ID,
            run_id=run.id,
            expected_revision=1,
        )
        running, _ = await RunCoordinator(session).transition_run(
            tenant_id=TENANT_ID,
            run_id=run.id,
            expected_status=RunStatus.STARTING,
            expected_revision=started.status_revision,
            target_status=RunStatus.RUNNING,
            summary="Runtime started",
        )
        await RunCoordinator(session).commit_terminal(
            tenant_id=TENANT_ID,
            run_id=run.id,
            expected_status=RunStatus.RUNNING,
            expected_revision=running.status_revision,
            result=TerminalResult(
                outcome="completed",
                code="ok",
                reason="answer ready",
                output_ref=f"terminal-output-{run.id}",
                output_digest=hashlib_hex(content),
                output_size=len(content),
                output_media_type="text/markdown",
                output_classification=SnapshotClassification.INTERNAL,
                terminal_message_id=uuid.uuid4(),
            ),
            producer_purge_revision=(
                await session.scalar(
                    select(ConversationModel.purge_revision).where(
                        ConversationModel.tenant_id == TENANT_ID,
                        ConversationModel.id == conversation_id,
                    )
                )
            ),
        )
    outbox = await db_session.scalar(
        select(ExecutionOutboxModel).where(
            ExecutionOutboxModel.aggregate_id == run.id
        )
    )
    assert outbox is not None and outbox.status == "pending"
    return conversation_id, outbox


def hashlib_hex(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


async def _claim_turn(db_session, *, worker_id: str = "b3-worker"):
    """claim 一条 turn outbox 事件（独立短事务），返回 ClaimedWorkspaceEvent。"""
    from sqlalchemy import func

    async with db_session.begin() as tx:
        now = await tx.session.scalar(select(func.clock_timestamp()))
        claimed = await AgentWorkspaceBridgeService(tx.session).claim_turn_event(
            worker_id=worker_id,
            now=now,
            stale_before=now - timedelta(minutes=1),
        )
    return claimed


# ---------------------------------------------------------------------------
# turn 路径：stale -> Tx1/Tx2
# ---------------------------------------------------------------------------


async def test_turn_stale_epoch_tx1_tx2(db_session, session_factory):
    """stale：producer epoch < 当前 且 fence erasing -> Tx1（inbox rejected +
    tombstone，不登记 ledger）+ Tx2（outbox cancelled + Message abandoned）。"""
    from tests.contexts.agent_control_plane.helpers import create_baseline_fences

    conversation_id, receipt = await _seed_turn_outbox(db_session, session_factory)
    # 建 baseline fence（submit 不 dispatch，execution fence 未惰性创建），再翻
    # execution fence erasing -> stale 可达。
    await create_baseline_fences(
        db_session, tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    # 推进 Conversation purge_revision + 翻 execution fence erasing -> stale。
    await _advance_conversation_purge(
        db_session, conversation_id=conversation_id, new_revision=7
    )
    await _force_fence_state(
        db_session, conversation_id=conversation_id, owner=_EXECUTION_OWNER, state="erasing"
    )
    await db_session.commit()

    dispatcher = AgentBridgeDispatcher(session_factory, worker_id="b3-stale")
    # Tx1 + Tx2 全部在 dispatcher 内完成，正常返回（不 raise）。
    run = await dispatcher.dispatch_turn(event_id=receipt.event_id)
    assert run is None, "stale 不应产生 Run"

    async with session_factory() as check:
        # Tx1：execution inbox rejected + tombstone 证据（不登记 ledger）。
        inbox = (
            await check.execute(
                select(ExecutionInboxModel).where(
                    ExecutionInboxModel.tenant_id == TENANT_ID,
                    ExecutionInboxModel.event_id == receipt.event_id,
                )
            )
        ).scalar_one()
        assert inbox.status == "rejected"
        assert inbox.last_error_code == _EPOCH_STALE
        assert inbox.receipt_tombstone_state == "redacted"
        assert inbox.receipt_tombstone_digest is not None
        # C1 第 4 跳：inbox scope/epoch = claim envelope 值（stale 写原 producer
        # epoch——迟到写证据，不得读当前 revision 伪造）。
        assert inbox.conversation_id == conversation_id
        assert inbox.producer_purge_revision is not None
        assert inbox.producer_purge_revision < 7  # 原 producer epoch（旧值）
        ledger = (
            await check.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_transport_scope_reconcile "
                    "WHERE tenant_id = :t AND source_table = 'agent_execution_inbox' "
                    "AND source_row_id = :rid"
                ),
                {"t": TENANT_ID, "rid": inbox.id},
            )
        ).scalar()
        assert ledger == 0, "stale 不登记 epoch_unresolvable（P1-b）"

        # Tx2：workspace turn outbox cancelled + 清 claim + 具名 code。
        outbox = (
            await check.execute(
                select(WorkspaceOutboxModel).where(
                    WorkspaceOutboxModel.tenant_id == TENANT_ID,
                    WorkspaceOutboxModel.id == receipt.event_id,
                )
            )
        ).scalar_one()
        assert outbox.status == "cancelled"
        assert outbox.claimed_by is None and outbox.claimed_at is None
        assert outbox.last_error_code == _EPOCH_STALE
        # Message abandoned + 同一 code。
        message = await check.get(MessageModel, outbox.aggregate_id)
        assert message is not None
        assert message.turn_dispatch_state == "abandoned"
        assert message.turn_dispatch_error_code == _EPOCH_STALE


async def test_turn_unknown_epoch_registers_ledger_conversation_scope(
    db_session, session_factory
):
    """unknown：producer epoch NULL -> Tx1 登记 epoch_unresolvable
    （conversation_scope，scope 已知）+ Tx2 终态化。"""
    conversation_id, receipt = await _seed_turn_outbox(db_session, session_factory)
    # 人为把 outbox 的 producer_purge_revision 置 NULL（历史/backfill 期行）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_workspace_outbox "
            "SET producer_purge_revision = NULL "
            "WHERE tenant_id = :t AND id = :id"
        ),
        {"t": TENANT_ID, "id": receipt.event_id},
    )
    await db_session.commit()

    dispatcher = AgentBridgeDispatcher(session_factory, worker_id="b3-unknown")
    run = await dispatcher.dispatch_turn(event_id=receipt.event_id)
    assert run is None

    async with session_factory() as check:
        inbox = (
            await check.execute(
                select(ExecutionInboxModel).where(
                    ExecutionInboxModel.tenant_id == TENANT_ID,
                    ExecutionInboxModel.event_id == receipt.event_id,
                )
            )
        ).scalar_one()
        assert inbox.status == "rejected"
        assert inbox.last_error_code == _EPOCH_UNKNOWN
        # C1 第 4 跳：unknown 写 scope（envelope conversation_id）、epoch 保持
        # NULL（NULL-epoch 行由 backfill 收敛，不得伪造当前 revision）。
        assert inbox.conversation_id == conversation_id
        assert inbox.producer_purge_revision is None
        # ledger：conversation_scope（scope 已知，带 conversation_id）+ owner_key
        # 必须是 transport owner（R3，变异击杀：错 owner 全绿）。
        issue = (
            await check.execute(
                text(
                    "SELECT reconcile_class, issue_code, conversation_id, owner_key "
                    "FROM metaedu.agent_transport_scope_reconcile "
                    "WHERE tenant_id = :t AND source_table = 'agent_execution_inbox' "
                    "AND source_row_id = :rid"
                ),
                {"t": TENANT_ID, "rid": inbox.id},
            )
        ).first()
        assert issue is not None
        assert issue[0] == "conversation_scope"
        assert issue[1] == "epoch_unresolvable"
        assert issue[2] == conversation_id
        assert issue[3] == "execution.transport.v1"

        # Tx2 终态。
        outbox = (
            await check.execute(
                select(WorkspaceOutboxModel).where(
                    WorkspaceOutboxModel.tenant_id == TENANT_ID,
                    WorkspaceOutboxModel.id == receipt.event_id,
                )
            )
        ).scalar_one()
        assert outbox.status == "cancelled"
        assert outbox.last_error_code == _EPOCH_UNKNOWN
        # C1 第 4 跳幂等：重放不重写——inbox 的 scope/epoch 保持首次 Tx1 写入值
        # （unknown 保持 NULL），不得因 Conversation 已推进到 9 而改写。
        inbox = (
            await check.execute(
                select(ExecutionInboxModel).where(
                    ExecutionInboxModel.tenant_id == TENANT_ID,
                    ExecutionInboxModel.event_id == receipt.event_id,
                )
            )
        ).scalar_one()
        assert inbox.conversation_id == conversation_id
        assert inbox.producer_purge_revision is None  # 未被重写为 9
        assert inbox.last_error_code == _EPOCH_UNKNOWN
        message = await check.get(MessageModel, outbox.aggregate_id)
        assert message.turn_dispatch_state == "abandoned"
        assert message.turn_dispatch_error_code == _EPOCH_UNKNOWN


# ---------------------------------------------------------------------------
# Tx2 后重放：三分支（round-6/7）
# ---------------------------------------------------------------------------


async def test_tx2_replay_after_tx1_only_continues(db_session, session_factory):
    """Tx1 已提交、Tx2 未跑（模拟 Tx2 前崩溃）：claim 租约过期后重 claim ->
    Tx1 幂等（inbox rejected + tombstone 已存在，不重复写）+ 续做 Tx2。"""
    from datetime import timedelta

    conversation_id, receipt = await _seed_turn_outbox(db_session, session_factory)
    # 制造 unknown：epoch 置 NULL。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_workspace_outbox "
            "SET producer_purge_revision = NULL "
            "WHERE tenant_id = :t AND id = :id"
        ),
        {"t": TENANT_ID, "id": receipt.event_id},
    )
    await db_session.commit()

    # 手动执行 Tx1（claim + consume_turn_event -> outcome），但**不执行 Tx2**
    # （模拟 Tx2 前崩溃/进程退出，Tx1 已提交）。
    claimed = await _claim_turn(db_session, worker_id="b3-replay")
    assert claimed is not None and not isinstance(claimed, PoisonedWorkspaceEvent)
    async with session_factory() as session, session.begin():
        outcome = await ConversationExecutionCoordinator(session).consume_turn_event(
            claimed, consumed_at=datetime.now(UTC)
        )
        assert outcome.__class__.__name__ == "ConsumeEpochOutcome"
    # 此处事务已提交，Tx2 未执行 -> outbox 仍 claimed。

    # 让 claim 租约过期（claimed_at 推到 stale_before 之前），dispatcher 重 claim
    # 同事件（attempt+1）-> Tx1 幂等续做 -> Tx2 补终态化。
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE metaedu.agent_workspace_outbox SET claimed_at = :old "
                "WHERE tenant_id = :t AND id = :id"
            ),
            {
                "old": datetime.now(UTC) - timedelta(minutes=10),
                "t": TENANT_ID,
                "id": receipt.event_id,
            },
        )
        # 重放前再推进 Conversation purge_revision（模拟重放期间 purge 继续推进）——
        # C1 第 4 跳幂等：inbox 已写 scope/epoch 即保留，重放不得读当前 revision
        # 重写旧值（变异：推进 revision 后重放重写 -> 本断言转红）。同 session
        # 内执行（避免跨 session 行锁竞争）。
        await session.execute(
            text(
                "UPDATE metaedu.agent_conversations SET purge_revision = 9 "
                "WHERE tenant_id = :t AND id = :c"
            ),
            {"t": TENANT_ID, "c": conversation_id},
        )

    dispatcher = AgentBridgeDispatcher(session_factory, worker_id="b3-replay2")
    run = await dispatcher.dispatch_turn(event_id=receipt.event_id)
    assert run is None

    async with session_factory() as check:
        outbox = (
            await check.execute(
                select(WorkspaceOutboxModel).where(
                    WorkspaceOutboxModel.tenant_id == TENANT_ID,
                    WorkspaceOutboxModel.id == receipt.event_id,
                )
            )
        ).scalar_one()
        assert outbox.status == "cancelled"
        assert outbox.last_error_code == _EPOCH_UNKNOWN
        message = await check.get(MessageModel, outbox.aggregate_id)
        assert message.turn_dispatch_state == "abandoned"


async def test_tx2_replay_when_outbox_already_terminal_is_noop(
    db_session, session_factory
):
    """Tx1 + Tx2 都完成（精确终态）：重放 -> no-op（不重复写、不 raise）。"""
    conversation_id, receipt = await _seed_turn_outbox(db_session, session_factory)
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_workspace_outbox "
            "SET producer_purge_revision = NULL "
            "WHERE tenant_id = :t AND id = :id"
        ),
        {"t": TENANT_ID, "id": receipt.event_id},
    )
    await db_session.commit()

    # 第一次完整跑（Tx1 + Tx2）。
    dispatcher = AgentBridgeDispatcher(session_factory, worker_id="b3-nop-1")
    assert await dispatcher.dispatch_turn(event_id=receipt.event_id) is None

    # 第二次重放：已精确终态 -> no-op，不 raise。
    dispatcher2 = AgentBridgeDispatcher(session_factory, worker_id="b3-nop-2")
    assert await dispatcher2.dispatch_turn(event_id=receipt.event_id) is None

    async with session_factory() as check:
        outbox = (
            await check.execute(
                select(WorkspaceOutboxModel).where(
                    WorkspaceOutboxModel.tenant_id == TENANT_ID,
                    WorkspaceOutboxModel.id == receipt.event_id,
                )
            )
        ).scalar_one()
        assert outbox.status == "cancelled"
        assert outbox.last_error_code == _EPOCH_UNKNOWN


async def test_tx2_replay_other_cancelled_fails_closed_not_noop(
    db_session, session_factory
):
    """精确终态负例（round-7，变异 (f) 击杀）：outbox 已 cancelled 但**非**本次
    精确终态（错 code / Message 未 abandoned）——重放必须 fail closed
    （WorkspaceIntegrationConflictError），不得当 no-op 吞掉。

    退化实现（任意 cancelled+清 claim 即 no-op）在此转红。
    """
    from app.contexts.agent_workspace.domain import WorkspaceIntegrationConflictError

    conversation_id, receipt = await _seed_turn_outbox(db_session, session_factory)
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_workspace_outbox "
            "SET producer_purge_revision = NULL "
            "WHERE tenant_id = :t AND id = :id"
        ),
        {"t": TENANT_ID, "id": receipt.event_id},
    )
    await db_session.commit()

    # Tx1：claim + consume（提交 rejected receipt）。Tx2 不执行。
    claimed = await _claim_turn(db_session, worker_id="b3-neg-1")
    assert claimed is not None and not isinstance(claimed, PoisonedWorkspaceEvent)
    async with session_factory() as session, session.begin():
        await ConversationExecutionCoordinator(session).consume_turn_event(
            claimed, consumed_at=datetime.now(UTC)
        )

    # 人为把 outbox 置「其他原因 cancelled」：错误 code（非具名 code）、Message
    # 未 abandoned——精确终态谓词不成立。
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE metaedu.agent_workspace_outbox "
                "SET status='cancelled', claimed_by=NULL, claimed_at=NULL, "
                "last_error_code='operator_suppressed' "
                "WHERE tenant_id = :t AND id = :id"
            ),
            {"t": TENANT_ID, "id": receipt.event_id},
        )

    # 旧 worker 重放 Tx2（outbox 非精确终态）-> fail closed：status 非 claimed
    # 且非精确终态（错 code）-> WorkspaceIntegrationConflictError。独立新
    # session 内调 terminalize（cancelled 行不可再 claim，行锁可正常取得）。
    async with session_factory() as session, session.begin():
        with pytest.raises(WorkspaceIntegrationConflictError):
            await AgentWorkspaceBridgeService(
                session
            ).terminalize_turn_epoch_rejected(
                tenant_id=TENANT_ID,
                event_id=receipt.event_id,
                payload_digest=claimed.payload_digest,
                expected_attempt=claimed.attempt_count,
                claimant_id=claimed.claimant_id,
                reason=_EPOCH_UNKNOWN,
                decided_at=datetime.now(UTC),
            )


async def test_tx2_replay_claim_mismatch_fails_closed(db_session, session_factory):
    """Tx1 已提交、outbox 仍 claimed：claim 被新 worker 接管（attempt+1，claimant
    变 B）后，旧 worker A 的 Tx2 claim CAS 不匹配 -> fail closed
    （WorkspaceIntegrationConflictError，不静默吞掉）。

    直接调 ``terminalize_turn_epoch_rejected``（确定性构造 CAS 拒绝）——经
    dispatcher 重放会先成功重 claim，claim 必匹配，CAS 拒绝分支只能确定性直测。
    """
    conversation_id, receipt = await _seed_turn_outbox(db_session, session_factory)
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_workspace_outbox "
            "SET producer_purge_revision = NULL "
            "WHERE tenant_id = :t AND id = :id"
        ),
        {"t": TENANT_ID, "id": receipt.event_id},
    )
    await db_session.commit()

    # Tx1：claim + consume（提交）。Tx2 不执行。
    claimed = await _claim_turn(db_session, worker_id="b3-owner-a")
    assert claimed is not None and not isinstance(claimed, PoisonedWorkspaceEvent)
    async with session_factory() as session, session.begin():
        await ConversationExecutionCoordinator(session).consume_turn_event(
            claimed, consumed_at=datetime.now(UTC)
        )

    # 模拟 claim 租约过期 + 新 worker B 接管（attempt+1，claimant 变 B）。
    from datetime import timedelta

    from sqlalchemy import func

    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE metaedu.agent_workspace_outbox SET claimed_at = :old "
                "WHERE tenant_id = :t AND id = :id"
            ),
            {
                "old": datetime.now(UTC) - timedelta(minutes=10),
                "t": TENANT_ID,
                "id": receipt.event_id,
            },
        )
        now = await session.scalar(select(func.clock_timestamp()))
        await AgentWorkspaceBridgeService(session).claim_turn_event(
            worker_id="b3-owner-b",
            now=now,
            stale_before=now - timedelta(minutes=1),
        )

    # 旧 worker A 携旧 claim（attempt N，claimant A）-> Tx2 CAS 不匹配 fail closed。
    from app.contexts.agent_workspace.domain import WorkspaceIntegrationConflictError

    async with session_factory() as session, session.begin():
        with pytest.raises(WorkspaceIntegrationConflictError):
            await AgentWorkspaceBridgeService(
                session
            ).terminalize_turn_epoch_rejected(
                tenant_id=TENANT_ID,
                event_id=receipt.event_id,
                payload_digest=claimed.payload_digest,
                expected_attempt=claimed.attempt_count,
                claimant_id=claimed.claimant_id,
                reason=_EPOCH_UNKNOWN,
                decided_at=datetime.now(UTC),
            )

    # fail closed：outbox 仍由 B 持有（attempt N+1，claimant B），未被 A 覆盖。
    async with session_factory() as check:
        outbox = (
            await check.execute(
                select(WorkspaceOutboxModel).where(
                    WorkspaceOutboxModel.tenant_id == TENANT_ID,
                    WorkspaceOutboxModel.id == receipt.event_id,
                )
            )
        ).scalar_one()
        assert outbox.status == "claimed"
        assert outbox.claimed_by == "b3-owner-b"
        assert outbox.attempt_count == claimed.attempt_count + 1


# ---------------------------------------------------------------------------
# output 路径：stale/unknown -> Tx1（workspace inbox rejected）+ Tx2（execution
# outbox decision 四元 + Run suppressed）
# ---------------------------------------------------------------------------


async def test_output_stale_epoch_tx1_tx2(db_session, session_factory):
    """output stale：producer epoch < 当前 且 execution fence erasing -> Tx1
    （workspace inbox rejected + tombstone，不登记 ledger）+ Tx2（execution outbox
    decision 四元 + Run suppressed）。"""
    from tests.contexts.agent_control_plane.helpers import StaticOutputReader

    content = b"# stale output"
    conversation_id, outbox = await _seed_run_with_pending_output(
        db_session, session_factory, content=content
    )
    # 推进 Conversation purge_revision + 翻 execution fence erasing -> stale。
    await _advance_conversation_purge(
        db_session, conversation_id=conversation_id, new_revision=7
    )
    await _force_fence_state(
        db_session, conversation_id=conversation_id, owner=_EXECUTION_OWNER, state="erasing"
    )
    await db_session.commit()

    dispatcher = AgentBridgeDispatcher(
        session_factory,
        worker_id="b3-out-stale",
        output_reader=StaticOutputReader(content),
    )
    # Tx1 + Tx2 全在 dispatcher 内完成，正常返回。
    assert await dispatcher.dispatch_output(event_id=outbox.id) is True

    async with session_factory() as check:
        # Tx1：workspace inbox rejected + tombstone（不登记 ledger）。
        inbox = (
            await check.execute(
                select(WorkspaceInboxModel).where(
                    WorkspaceInboxModel.tenant_id == TENANT_ID,
                    WorkspaceInboxModel.event_id == outbox.id,
                )
            )
        ).scalar_one()
        assert inbox.status == "rejected"
        assert inbox.last_error_code == _EPOCH_STALE
        assert inbox.receipt_tombstone_state == "redacted"
        assert inbox.receipt_tombstone_digest is not None
        # C1 第 4 跳：inbox scope/epoch = claim envelope 值（stale 写原 producer
        # epoch——迟到写证据，不得读当前 revision 伪造）。
        assert inbox.conversation_id == conversation_id
        assert inbox.producer_purge_revision is not None
        assert inbox.producer_purge_revision < 7  # 原 producer epoch（旧值）
        ledger = (
            await check.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_transport_scope_reconcile "
                    "WHERE tenant_id = :t AND source_table = 'agent_workspace_inbox' "
                    "AND source_row_id = :rid"
                ),
                {"t": TENANT_ID, "rid": inbox.id},
            )
        ).scalar()
        assert ledger == 0, "stale 不登记 epoch_unresolvable（P1-b）"

        # Tx2：execution outbox cancelled + 清 claim + decision 四元 + Run suppressed。
        persisted = await check.get(ExecutionOutboxModel, outbox.id)
        assert persisted is not None
        assert persisted.status == "cancelled"
        assert persisted.claimed_by is None and persisted.claimed_at is None
        assert persisted.decision_actor_id == uuid.UUID(int=0)
        assert persisted.decision_reason == _EPOCH_STALE
        assert persisted.decision_digest is not None and persisted.decided_at is not None
        persisted_run = await check.get(AgentRunModel, outbox.aggregate_id)
        assert persisted_run is not None
        assert (
            persisted_run.output_publish_state == OutputPublishState.SUPPRESSED.value
        )


async def test_output_unknown_epoch_registers_ledger_and_decision(
    db_session, session_factory
):
    """output unknown：producer epoch NULL -> Tx1 登记 epoch_unresolvable
    （conversation_scope）+ Tx2 decision 四元 digest envelope + Run suppressed。"""
    from tests.contexts.agent_control_plane.helpers import StaticOutputReader

    content = b"# unknown output"
    conversation_id, outbox = await _seed_run_with_pending_output(
        db_session, session_factory, content=content
    )
    # 人为把 execution outbox 的 producer_purge_revision 置 NULL（历史/backfill 期行）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_execution_outbox "
            "SET producer_purge_revision = NULL "
            "WHERE tenant_id = :t AND id = :id"
        ),
        {"t": TENANT_ID, "id": outbox.id},
    )
    await db_session.commit()

    dispatcher = AgentBridgeDispatcher(
        session_factory,
        worker_id="b3-out-unknown",
        output_reader=StaticOutputReader(content),
    )
    assert await dispatcher.dispatch_output(event_id=outbox.id) is True

    async with session_factory() as check:
        inbox = (
            await check.execute(
                select(WorkspaceInboxModel).where(
                    WorkspaceInboxModel.tenant_id == TENANT_ID,
                    WorkspaceInboxModel.event_id == outbox.id,
                )
            )
        ).scalar_one()
        assert inbox.status == "rejected"
        assert inbox.last_error_code == _EPOCH_UNKNOWN
        # C1 第 4 跳：unknown 写 scope（envelope conversation_id）、epoch 保持
        # NULL（NULL-epoch 行由 backfill 收敛，不得伪造当前 revision）。
        assert inbox.conversation_id == conversation_id
        assert inbox.producer_purge_revision is None
        # ledger：conversation_scope（scope 已知，带 conversation_id）+ owner_key
        # 必须是 transport owner（R3，变异击杀：错 owner 全绿）。
        issue = (
            await check.execute(
                text(
                    "SELECT reconcile_class, issue_code, conversation_id, owner_key "
                    "FROM metaedu.agent_transport_scope_reconcile "
                    "WHERE tenant_id = :t AND source_table = 'agent_workspace_inbox' "
                    "AND source_row_id = :rid"
                ),
                {"t": TENANT_ID, "rid": inbox.id},
            )
        ).first()
        assert issue is not None
        assert issue[0] == "conversation_scope"
        assert issue[1] == "epoch_unresolvable"
        assert issue[2] == conversation_id
        assert issue[3] == "workspace.transport.v1"

        # Tx2：decision 四元 + digest envelope（round-8 冻结键名）。
        persisted = await check.get(ExecutionOutboxModel, outbox.id)
        assert persisted is not None
        assert persisted.status == "cancelled"
        assert persisted.decision_actor_id == uuid.UUID(int=0)
        assert persisted.decision_reason == _EPOCH_UNKNOWN
        assert persisted.decided_at is not None
        expected_digest = snapshot_digest(
            {
                "schema_version": 1,
                "actor_id": str(uuid.UUID(int=0)),
                "reason": _EPOCH_UNKNOWN,
                "event_id": str(outbox.id),
                "receipt_tombstone_digest": inbox.receipt_tombstone_digest,
            }
        )
        assert persisted.decision_digest == expected_digest
        persisted_run = await check.get(AgentRunModel, outbox.aggregate_id)
        assert persisted_run is not None
        assert (
            persisted_run.output_publish_state == OutputPublishState.SUPPRESSED.value
        )


async def test_output_tx2_claim_cas_rejection_fails_closed(
    db_session, session_factory
):
    """output 侧 Tx2 claim CAS 拒绝（变异 (d)-output 击杀）：outbox claim 被新
    worker 接管后，旧 worker 的 ``terminalize_output_epoch_rejected`` 必须 raise
    （ExecutionIntegrationConflictError）且 **零变更**（B 的 claim、decision 列、
    Run 状态全不被覆盖）。

    退化实现（跳过 claim CAS 直接终态化）在此转红。
    """
    from app.contexts.agent_execution.domain import ExecutionIntegrationConflictError

    content = b"# output takeover"
    conversation_id, outbox = await _seed_run_with_pending_output(
        db_session, session_factory, content=content
    )
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_execution_outbox "
            "SET producer_purge_revision = NULL "
            "WHERE tenant_id = :t AND id = :id"
        ),
        {"t": TENANT_ID, "id": outbox.id},
    )
    await db_session.commit()

    # A 执行 Tx1（claim + consume，提交 rejected receipt）。Tx2 不执行。
    from sqlalchemy import func

    from app.contexts.agent_execution.application.bridge import (
        AgentExecutionBridgeService,
    )

    async with session_factory() as session, session.begin():
        now = await session.scalar(select(func.clock_timestamp()))
        claimed = await AgentExecutionBridgeService(session).claim_output_event(
            worker_id="b3-out-a",
            now=now,
            stale_before=now - timedelta(minutes=1),
        )
        assert claimed is not None and not isinstance(
            claimed, PoisonedWorkspaceEvent
        )
        await ConversationExecutionCoordinator(session).consume_output_event(
            claimed, consumed_at=datetime.now(UTC)
        )

    # 模拟 claim 租约过期 + B 接管（attempt+1，claimant 变 B）。
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE metaedu.agent_execution_outbox SET claimed_at = :old "
                "WHERE tenant_id = :t AND id = :id"
            ),
            {
                "old": datetime.now(UTC) - timedelta(minutes=10),
                "t": TENANT_ID,
                "id": outbox.id,
            },
        )
        now = await session.scalar(select(func.clock_timestamp()))
        await AgentExecutionBridgeService(session).claim_output_event(
            worker_id="b3-out-b",
            now=now,
            stale_before=now - timedelta(minutes=1),
        )

    # 旧 worker A 携旧 claim -> Tx2 CAS 不匹配 fail closed + 零变更。
    async with session_factory() as session, session.begin():
        with pytest.raises(ExecutionIntegrationConflictError):
            await AgentExecutionBridgeService(
                session
            ).terminalize_output_epoch_rejected(
                tenant_id=TENANT_ID,
                event_id=outbox.id,
                payload_digest=claimed.payload_digest,
                expected_attempt=claimed.attempt_count,
                claimant_id=claimed.claimant_id,
                reason=_EPOCH_UNKNOWN,
                receipt_tombstone_digest="0" * 64,
                decided_at=datetime.now(UTC),
            )

    async with session_factory() as check:
        persisted = await check.get(ExecutionOutboxModel, outbox.id)
        assert persisted is not None
        # 零变更：B 的 claim 保持、attempt 未回退、decision 列未写。
        assert persisted.status == "claimed"
        assert persisted.claimed_by == "b3-out-b"
        assert persisted.attempt_count == claimed.attempt_count + 1
        assert persisted.decision_actor_id is None
        assert persisted.decision_reason is None
        persisted_run = await check.get(AgentRunModel, outbox.aggregate_id)
        assert persisted_run is not None
        assert (
            persisted_run.output_publish_state
            != OutputPublishState.SUPPRESSED.value
        )


# ---------------------------------------------------------------------------
# data_anomaly：fail closed 不消费不登记
# ---------------------------------------------------------------------------


async def test_turn_data_anomaly_fails_closed_no_consume_no_ledger(
    db_session, session_factory
):
    """data_anomaly（producer epoch > 当前）：raise EpochRejectedError，不消费、
    不写 inbox、不登记 ledger、**不记 delivery failure**（不 retry-forever→
    dead_letter，R1/C7 不变），事件留在 outbox。"""
    conversation_id, receipt = await _seed_turn_outbox(db_session, session_factory)
    # producer epoch（outbox 写入值）> 当前 Conversation purge_revision。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_workspace_outbox SET producer_purge_revision = 99 "
            "WHERE tenant_id = :t AND id = :id"
        ),
        {"t": TENANT_ID, "id": receipt.event_id},
    )
    await db_session.commit()

    dispatcher = AgentBridgeDispatcher(session_factory, worker_id="b3-anomaly")
    with pytest.raises(EpochRejectedError):
        await dispatcher.dispatch_turn(event_id=receipt.event_id)

    async with session_factory() as check:
        # 不写 inbox（无 receipt 行）。
        inbox_count = (
            await check.execute(
                select(ExecutionInboxModel).where(
                    ExecutionInboxModel.tenant_id == TENANT_ID,
                    ExecutionInboxModel.event_id == receipt.event_id,
                )
            )
        ).scalar()
        assert inbox_count is None or inbox_count.id is None
        # 不登记 ledger。
        ledger_count = (
            await check.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_transport_scope_reconcile "
                    "WHERE tenant_id = :t AND source_table = 'agent_execution_inbox'"
                ),
                {"t": TENANT_ID},
            )
        ).scalar()
        assert ledger_count == 0
        # 不记 delivery failure：outbox 仍 claimed（本次 dispatch 已 claim，租约
        # 到期后可再 claim）或 pending，**last_error_code 未写**（未记 failure、
        # 不进 dead_letter），未消费未终态。
        outbox = (
            await check.execute(
                select(WorkspaceOutboxModel).where(
                    WorkspaceOutboxModel.tenant_id == TENANT_ID,
                    WorkspaceOutboxModel.id == receipt.event_id,
                )
            )
        ).scalar_one()
        assert outbox.status in ("pending", "claimed")
        assert outbox.last_error_code is None
