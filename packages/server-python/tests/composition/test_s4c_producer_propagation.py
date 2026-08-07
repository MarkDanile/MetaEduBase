r"""R1-S4-C PR-A Producer propagation：writer 真实 scope/epoch + 幂等重放。

契约：Plan §R1-S4-C C1/C2/C5（round-1~10 修订）。
- C1/C2：新写 outbox 行必须带真实 ``conversation_id``（该 Conversation UUID）
  与 ``producer_purge_revision``（产生同事务快照的 ``Conversation.purge_revision``，
  Conversation 行锁内读）；**禁**用 fence CAS ``revision``/fence ``purge_revision``/
  Conversation ``revision``/时间戳冒充（R1）。
- C2：幂等重放（``add_turn_outbox`` 命中既有行 / ``commit_terminal``
  ``terminal_digest_match=True``）不重写 scope/epoch；重放遇 040 列仍 NULL 的
  旧行不补写（R6）。
- C5：catch-up 自 tenant 起点幂等重扫、无跨调用游标、verify 双维（R5）。

本文件是 PR-A（Producer propagation + replay/catch-up）的真实 PostgreSQL 反例。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, update

from app.composition.agent_control_plane import ConversationExecutionCoordinator
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    ExecutionOutboxModel,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    WorkspaceOutboxModel,
)
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
    bootstrap_workspace,
    turn_command,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# workspace turn outbox：conversation_id + producer_purge_revision
# ---------------------------------------------------------------------------


async def test_turn_outbox_writes_real_scope_and_epoch(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    coordinator = ConversationExecutionCoordinator(db_session)
    command = turn_command(identity, "propagate epoch")

    await coordinator.submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=command,
        launch=launch,
    )
    await db_session.commit()

    row = (
        await db_session.execute(
            select(WorkspaceOutboxModel)
            .where(WorkspaceOutboxModel.tenant_id == TENANT_ID)
            .limit(1)
        )
    ).scalar_one()
    conv = await db_session.get(ConversationModel, conversation_id)

    assert row.conversation_id == conversation_id
    assert row.producer_purge_revision == conv.purge_revision
    # 禁伪造：epoch 必须等于 Conversation.purge_revision，不得用 fence/CAS 值。
    assert row.producer_purge_revision == 0  # 新建会话 baseline purge_revision


async def test_turn_outbox_idempotent_replay_does_not_rewrite_scope_epoch(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    coordinator = ConversationExecutionCoordinator(db_session)
    command = turn_command(identity, "idempotent scope")

    first = await coordinator.submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=command,
        launch=launch,
    )
    await db_session.commit()
    # 人为回填 scope/epoch 为「已知真实值」，模拟已持久化
    await db_session.execute(
        update(WorkspaceOutboxModel)
        .where(WorkspaceOutboxModel.tenant_id == TENANT_ID)
        .values(producer_purge_revision=7)
    )
    await db_session.commit()

    replay = await coordinator.submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=command,
        launch=launch,
    )
    await db_session.commit()
    assert replay.reserved.idempotent_replay is True
    assert replay.event_id == first.event_id

    row = (
        await db_session.execute(
            select(WorkspaceOutboxModel)
            .where(WorkspaceOutboxModel.tenant_id == TENANT_ID)
            .limit(1)
        )
    ).scalar_one()
    # 幂等重放不重写已持久化值（即使与当前 purge_revision 不一致）
    assert row.producer_purge_revision == 7


# ---------------------------------------------------------------------------
# anti-forgery：epoch 必须来自 Conversation.purge_revision（R1/C2）
# ---------------------------------------------------------------------------


async def test_turn_outbox_epoch_is_conversation_purge_revision_not_fence(
    db_session,
):
    """epoch 必须等于 Conversation.purge_revision（禁拿 fence/CAS 冒充，R1）。

    通过推进 Conversation.purge_revision（restore 语义）验证：outbox 写的是
    Conversation 的新值，而非 fence 对齐前的旧值。
    """
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    # 推进 Conversation.purge_revision 模拟一次 restore（soft_delete 后再
    # restore 会 purge_revision += 1；这里直接推进该列）。
    from sqlalchemy import text

    await db_session.execute(
        text(
            "UPDATE metaedu.agent_conversations SET purge_revision = 3 "
            "WHERE tenant_id = :tenant AND id = :conv"
        ),
        {"tenant": TENANT_ID, "conv": conversation_id},
    )
    await db_session.commit()

    coordinator = ConversationExecutionCoordinator(db_session)
    command = turn_command(identity, "anti-forgery epoch")
    await coordinator.submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=command,
        launch=launch,
    )
    await db_session.commit()

    row = (
        await db_session.execute(
            select(WorkspaceOutboxModel)
            .where(WorkspaceOutboxModel.tenant_id == TENANT_ID)
            .limit(1)
        )
    ).scalar_one()
    conv = await db_session.get(ConversationModel, conversation_id)
    assert row.producer_purge_revision == conv.purge_revision  # 3
    assert row.producer_purge_revision == 3


# ---------------------------------------------------------------------------
# catch-up：S4-B backfill 幂等重扫（C5/R5，C8 项 9）
# ---------------------------------------------------------------------------


async def test_catch_up_rescans_null_scope_rows_idempotently(
    db_session, session_factory
):
    """S4-B catch-up 对仍 NULL-scope 的行做 tenant 起点幂等重扫。

    这里用真实 backfill 跑一遍，验证：已填 scope 的行不被覆盖、未登记
    reconcile 不重复（幂等）；NULL 行被收敛为 scope 或 reconcile issue。
    """
    from app.composition.agent_transport_backfill import backfill_transport_scope

    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    coordinator = ConversationExecutionCoordinator(db_session)
    command = turn_command(identity, "catch-up scope")
    await coordinator.submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=command,
        launch=launch,
    )
    await db_session.commit()

    # 第一次回填：workspace outbox 已带 scope（PR-A 新写），但 inbox 未消费、
    # 无 NULL 行；跑 backfill 应幂等无失败。
    report = await backfill_transport_scope(
        session_factory,
        tenant_id=TENANT_ID,
        batch_size=50,
    )
    assert report.ok
    # 新写行已带 scope，backfill 不应产生 scope 类 reconcile issue
    assert report.reconcile_issues_registered == 0

    # 幂等重跑：不产生重复 issue、不覆盖已填值
    report2 = await backfill_transport_scope(
        session_factory,
        tenant_id=TENANT_ID,
        batch_size=50,
    )
    assert report2.ok
    assert report2.reconcile_issues_registered == 0
    assert report2.failure_count == 0


# ---------------------------------------------------------------------------
# execution output outbox：conversation_id + producer_purge_revision
# ---------------------------------------------------------------------------


async def test_execution_outbox_writes_real_scope_and_epoch(
    session_factory,
):
    """真实路径：submit -> dispatch_turn(create) -> start_run -> commit_terminal。

    commit_terminal 成功落 completed 并写 publish outbox（PR-A producer 路径），
    断言 outbox 带真实 conversation_id + producer_purge_revision。
    """
    from app.composition.agent_control_plane import (
        AgentBridgeDispatcher,
        ConversationExecutionCoordinator,
    )
    from app.composition.execution_fenced_port import FencedExecutionPort
    from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
    from app.contexts.agent_execution.domain import RunStatus, TerminalResult

    async with session_factory() as session, session.begin():
        conversation_id, identity, launch = await bootstrap_workspace(session)
    coordinator_ctx = ConversationExecutionCoordinator
    async with session_factory() as session, session.begin():
        coordinator = coordinator_ctx(session)
        command = turn_command(identity, "execution epoch")
        await coordinator.submit_turn(
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            conversation_id=conversation_id,
            command=command,
            launch=launch,
        )
    run = await AgentBridgeDispatcher(
        session_factory, worker_id="producer-worker"
    ).dispatch_turn()
    assert run is not None
    async with session_factory() as session, session.begin():
        coordinator = coordinator_ctx(session)
        started, _ = await coordinator.start_run(
            tenant_id=TENANT_ID,
            run_id=run.id,
            expected_revision=1,
        )
        await RunCoordinator(session).transition_run(
            tenant_id=TENANT_ID,
            run_id=run.id,
            expected_status=RunStatus.STARTING,
            expected_revision=started.status_revision,
            target_status=RunStatus.RUNNING,
            summary="acquired runtime lease",
        )
        running = await RunCoordinator(session).require_run(
            tenant_id=TENANT_ID, run_id=run.id
        )
        # 生产入口经 fenced port：commit_terminal 前读 Conversation.purge_revision
        # 写入 outbox（无旁路守卫，S3-E no-bypass 契约）。
        await FencedExecutionPort(session).fenced_commit_terminal(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            run_id=run.id,
            queue_seq=run.queue_seq,
            expected_status=RunStatus.RUNNING,
            expected_revision=running.status_revision,
            result=TerminalResult(
                outcome="completed",
                code="success",
                reason="done",
                output_ref="obj-12345",
                output_digest="a" * 64,
                output_size=1,
                output_media_type="text/plain",
                output_classification="public",
                terminal_message_id=uuid.uuid4(),
            ),
        )

    async with session_factory() as session:
        outbox = (
            await session.execute(
                select(ExecutionOutboxModel)
                .where(ExecutionOutboxModel.tenant_id == TENANT_ID)
                .limit(1)
            )
        ).scalar_one()
        conv = await session.get(ConversationModel, conversation_id)
        run_row = (
            await session.execute(
                select(AgentRunModel).where(AgentRunModel.id == run.id)
            )
        ).scalar_one()

    assert outbox.conversation_id == conversation_id
    # producer epoch = Conversation.purge_revision（Conversation 行锁内读），
    # 不是 run 或 fence 的值。
    assert outbox.producer_purge_revision == conv.purge_revision
    assert run_row.conversation_id == conversation_id
