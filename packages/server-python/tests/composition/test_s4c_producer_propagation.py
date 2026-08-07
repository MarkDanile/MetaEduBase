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
from sqlalchemy import func, select, text, update

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

    构造部署窗口遗留 NULL-scope 行（PR-A writer 之前的旧行），验证 catch-up
    收敛为 scope 或 reconcile issue（C5 分支 1），且幂等重跑不重复登记。
    """
    from sqlalchemy import text

    from app.composition.agent_transport_backfill import backfill_transport_scope

    # backfill 写 reconcile ledger（fk_..._tenant -> tenants）需 tenant 行存在。
    await db_session.execute(
        text(
            "INSERT INTO metaedu.tenants (id, name, school_name, created_at, updated_at) "
            "VALUES (:id, :name, :school, clock_timestamp(), clock_timestamp()) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": TENANT_ID, "name": "s4c-tenant", "school": "s4c-test-school"},
    )
    await db_session.commit()

    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    # 构造部署窗口遗留 NULL-scope outbox 行：conversation_id IS NULL（旧 writer
    # 产出），source 指向真实 Message 以允许 backfill 解析 scope。
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
    # 人为把这条新写行打回「部署窗口遗留」形态：scope/epoch 置 NULL（模拟旧
    # writer 在 040 上线前产出的行，backfill 尚未回填）。
    await db_session.execute(
        text(
            "UPDATE metaedu.agent_workspace_outbox "
            "SET conversation_id = NULL, producer_purge_revision = NULL, "
            "scope_reconcile_state = NULL "
            "WHERE tenant_id = :tenant"
        ),
        {"tenant": TENANT_ID},
    )
    await db_session.commit()

    # 第一次回填：NULL-scope 行被收敛为 scope（经 Message 源解析）或 reconcile
    # issue；断言至少有 scope 被回填（该行 source 可解析）。
    report = await backfill_transport_scope(
        session_factory,
        tenant_id=TENANT_ID,
        batch_size=50,
    )
    assert report.ok
    assert report.scope_backfilled >= 1

    # 幂等重跑：不产生重复 issue、不覆盖已填值。
    report2 = await backfill_transport_scope(
        session_factory,
        tenant_id=TENANT_ID,
        batch_size=50,
    )
    assert report2.ok
    assert report2.reconcile_issues_registered == 0
    assert report2.failure_count == 0

    # 回填后行应带真实 conversation_id（收敛到源 Message 的会话）。
    row = (
        await db_session.execute(
            select(WorkspaceOutboxModel)
            .where(WorkspaceOutboxModel.tenant_id == TENANT_ID)
            .limit(1)
        )
    ).scalar_one()
    assert row.conversation_id == conversation_id


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


# ---------------------------------------------------------------------------
# execution anti-forgery：epoch 必须来自 Conversation.purge_revision（R1/C2）
# ---------------------------------------------------------------------------


async def test_execution_outbox_epoch_is_conversation_purge_revision_not_constant(
    session_factory,
):
    """execution outbox 的 epoch 必须等于推进后的 Conversation.purge_revision，
    不是常数 0、fence 对齐值或时间戳（R1）。"""
    from sqlalchemy import text

    from app.composition.agent_control_plane import (
        AgentBridgeDispatcher,
        ConversationExecutionCoordinator,
    )
    from app.composition.execution_fenced_port import FencedExecutionPort
    from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
    from app.contexts.agent_execution.domain import RunStatus, TerminalResult

    async with session_factory() as session, session.begin():
        conversation_id, identity, launch = await bootstrap_workspace(session)
        # 推进 Conversation.purge_revision 到非零值（模拟 restore/delete 后推进）。
        await session.execute(
            text(
                "UPDATE metaedu.agent_conversations SET purge_revision = 5 "
                "WHERE tenant_id = :tenant AND id = :conv"
            ),
            {"tenant": TENANT_ID, "conv": conversation_id},
        )
    async with session_factory() as session, session.begin():
        coordinator = ConversationExecutionCoordinator(session)
        command = turn_command(identity, "execution anti-forgery")
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
        coordinator = ConversationExecutionCoordinator(session)
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
    # epoch 必须是推进后的 Conversation 值（5），不是常数 0。
    assert outbox.producer_purge_revision == conv.purge_revision
    assert outbox.producer_purge_revision == 5


# ---------------------------------------------------------------------------
# execution idempotent replay：terminal_digest_match=True 不重写 scope/epoch（R6）
# ---------------------------------------------------------------------------


async def test_execution_outbox_idempotent_replay_does_not_rewrite_scope_epoch(
    session_factory,
):
    """execution idempotent replay（terminal digest 命中）不得重写 outbox
    scope/epoch（C2/R6）。"""
    from app.composition.agent_control_plane import (
        AgentBridgeDispatcher,
        ConversationExecutionCoordinator,
    )
    from app.composition.execution_fenced_port import FencedExecutionPort
    from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
    from app.contexts.agent_execution.domain import RunStatus, TerminalResult

    async with session_factory() as session, session.begin():
        conversation_id, identity, launch = await bootstrap_workspace(session)
    async with session_factory() as session, session.begin():
        coordinator = ConversationExecutionCoordinator(session)
        command = turn_command(identity, "execution replay scope")
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
    result = TerminalResult(
        outcome="completed",
        code="success",
        reason="done",
        output_ref="obj-12345",
        output_digest="a" * 64,
        output_size=1,
        output_media_type="text/plain",
        output_classification="public",
        terminal_message_id=uuid.uuid4(),
    )
    async with session_factory() as session, session.begin():
        coordinator = ConversationExecutionCoordinator(session)
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
        await FencedExecutionPort(session).fenced_commit_terminal(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            run_id=run.id,
            queue_seq=run.queue_seq,
            expected_status=RunStatus.RUNNING,
            expected_revision=running.status_revision,
            result=result,
        )
    # 第一次写入后，outbox 带真实 scope/epoch。
    async with session_factory() as session:
        outbox_before = (
            await session.execute(
                select(ExecutionOutboxModel)
                .where(ExecutionOutboxModel.tenant_id == TENANT_ID)
                .limit(1)
            )
        ).scalar_one()
        assert outbox_before.conversation_id == conversation_id
        assert outbox_before.producer_purge_revision is not None

    # round-2 P1：推进 Conversation.purge_revision（模拟 restore/delete），使
    # 「重放时重写当前值」的实现会产生不同 epoch——重放必须保持第一次写入的
    # 旧值（byte-identical），重写当前 5 会失败。
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE metaedu.agent_conversations SET purge_revision = 5 "
                "WHERE tenant_id = :tenant AND id = :conv"
            ),
            {"tenant": TENANT_ID, "conv": conversation_id},
        )

    # 幂等重放：同一 terminal digest 命中 -> terminal_digest_match=True，不重写。
    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        _run, _event, match = await port.fenced_commit_terminal(
            tenant_id=TENANT_ID,
            conversation_id=conversation_id,
            run_id=run.id,
            queue_seq=run.queue_seq,
            expected_status=RunStatus.RUNNING,
            expected_revision=run.status_revision,
            result=result,
        )
    assert match is True

    async with session_factory() as session:
        outbox_after = (
            await session.execute(
                select(ExecutionOutboxModel)
                .where(ExecutionOutboxModel.tenant_id == TENANT_ID)
                .limit(1)
            )
        ).scalar_one()
    # 幂等重放不重写 scope/epoch（byte-identical，即使 Conversation 已推进到 5）。
    assert outbox_after.conversation_id == outbox_before.conversation_id
    assert (
        outbox_after.producer_purge_revision
        == outbox_before.producer_purge_revision
    )


# ---------------------------------------------------------------------------
# 身份一致性：跨 tenant / 跨 conversation 写 fail closed（C2）
# ---------------------------------------------------------------------------


async def test_turn_outbox_cross_tenant_conversation_fails_closed(
    db_session,
):
    """writer 用不属于当前 actor 的 conversation_id 调 submit_turn 必须 fail
    closed（不把 outbox 写到错误会话，C2 身份一致性 / C6 跨 tenant）。"""
    from app.contexts.agent_workspace.domain import (
        ConversationNotFoundError,
        WorkspaceIntegrationConflictError,
    )

    _, identity, launch = await bootstrap_workspace(db_session)
    # 另一个 actor 的 conversation（当前 actor 无权访问）。
    other_actor = uuid.uuid4()
    other_conversation_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, creation_digest, created_by) "
            "VALUES (:id, :tenant, :digest, :actor)"
        ),
        {
            "id": other_conversation_id,
            "tenant": TENANT_ID,
            "digest": "d" * 64,
            "actor": other_actor,
        },
    )
    await db_session.commit()

    coordinator = ConversationExecutionCoordinator(db_session)
    with pytest.raises(
        (ConversationNotFoundError, WorkspaceIntegrationConflictError)
    ):
        await coordinator.submit_turn(
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            conversation_id=other_conversation_id,
            command=turn_command(identity, "cross-tenant scope"),
            launch=launch,
        )
    await db_session.rollback()

    # 未产生任何 outbox 行（不写到错误会话）。
    count = await db_session.scalar(
        select(func.count()).select_from(WorkspaceOutboxModel)
    )
    assert count == 0
