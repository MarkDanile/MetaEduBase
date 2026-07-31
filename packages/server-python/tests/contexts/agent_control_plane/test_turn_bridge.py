from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.composition.agent_control_plane import (
    AgentBridgeDispatcher,
    ConversationExecutionCoordinator,
    ConversationExecutionGuard,
    ConversationHasNonTerminalRunError,
    ConversationHasPendingTurnError,
    DispatchPolicy,
    PoisonedIntegrationEventError,
)
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    AgentExecutionError,
    ExecutionIntegrationConflictError,
    RunConflictError,
    RunStatus,
    TerminalResult,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    ExecutionInboxModel,
    TurnInputModel,
)
from app.contexts.agent_workspace.application.bridge import AgentWorkspaceBridgeService
from app.contexts.agent_workspace.domain import (
    ConversationState,
    TurnDispatchState,
    WorkspaceIntegrationConflictError,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    MessageModel,
    WorkspaceOutboxModel,
)
from app.shared.schemas.agent_integration import TurnLaunchSpecV1
from tests.contexts.agent_control_plane.helpers import (
    ACTOR_ID,
    TENANT_ID,
    bootstrap_workspace,
    create_baseline_fences,
    turn_command,
)

pytestmark = pytest.mark.asyncio


async def test_submit_and_dispatch_are_atomic_idempotent_and_ack_driven(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    command = turn_command(identity, "durable turn")
    coordinator = ConversationExecutionCoordinator(db_session)

    first = await coordinator.submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=command,
        launch=launch,
    )
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
    assert replay.reserved.message.id == first.reserved.message.id
    assert first.dispatch_state is TurnDispatchState.PENDING
    outbox_count = await db_session.scalar(
        select(func.count()).select_from(WorkspaceOutboxModel)
    )
    assert outbox_count == 1

    run = await AgentBridgeDispatcher(
        session_factory, worker_id="turn-worker"
    ).dispatch_turn(event_id=first.event_id)
    assert run is not None
    assert run.id == first.reserved.message.requested_run_id
    assert run.status is RunStatus.QUEUED

    message = await db_session.get(MessageModel, first.reserved.message.id)
    assert message is not None
    await db_session.refresh(message)
    assert message.turn_dispatch_state == TurnDispatchState.ACCEPTED.value
    assert await db_session.scalar(
        select(func.count()).select_from(AgentRunModel)
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(TurnInputModel)
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(ExecutionInboxModel)
    ) == 1


async def test_execution_commit_before_workspace_ack_replays_without_duplicate_run(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "ack loss"),
        launch=launch,
    )
    await db_session.commit()
    claimed_at = datetime.now(UTC)

    async with session_factory() as session, session.begin():
        claimed = await AgentWorkspaceBridgeService(session).claim_turn_event(
            worker_id="worker-a",
            now=claimed_at,
            stale_before=claimed_at - timedelta(seconds=60),
            event_id=receipt.event_id,
        )
    assert claimed is not None
    async with session_factory() as session, session.begin():
        _, first_ack, _ = await ConversationExecutionCoordinator(
            session
        ).consume_turn_event(claimed, consumed_at=claimed_at)

    retry_at = claimed_at + timedelta(seconds=120)
    async with session_factory() as session, session.begin():
        replay = await AgentWorkspaceBridgeService(session).claim_turn_event(
            worker_id="worker-b",
            now=retry_at,
            stale_before=retry_at - timedelta(seconds=60),
            event_id=receipt.event_id,
        )
    assert replay is not None
    assert replay.attempt_count == 2
    async with session_factory() as session, session.begin():
        _, replay_ack, _ = await ConversationExecutionCoordinator(
            session
        ).consume_turn_event(replay, consumed_at=retry_at)
    assert replay_ack.payload_digest == first_ack.payload_digest
    async with session_factory() as session, session.begin():
        await AgentWorkspaceBridgeService(session).acknowledge_turn(replay_ack)

    assert await db_session.scalar(
        select(func.count()).select_from(AgentRunModel)
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(TurnInputModel)
    ) == 1


async def test_missing_workspace_prefix_blocks_later_run_start(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    coordinator = ConversationExecutionCoordinator(db_session)
    first = await coordinator.submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "first"),
        launch=launch,
    )
    second = await coordinator.submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "second"),
        launch=launch,
    )
    await db_session.commit()
    dispatcher = AgentBridgeDispatcher(session_factory, worker_id="fifo-worker")

    second_run = await dispatcher.dispatch_turn(event_id=second.event_id)
    assert second_run is not None
    async with session_factory() as session, session.begin():
        with pytest.raises(RunConflictError, match="barrier"):
            await ConversationExecutionCoordinator(session).start_run(
                tenant_id=TENANT_ID,
                run_id=second_run.id,
                expected_revision=1,
            )

    first_run = await dispatcher.dispatch_turn(event_id=first.event_id)
    assert first_run is not None
    async with session_factory() as session, session.begin():
        started, _ = await ConversationExecutionCoordinator(session).start_run(
            tenant_id=TENANT_ID,
            run_id=first_run.id,
            expected_revision=1,
        )
        await RunCoordinator(session).commit_terminal(
            tenant_id=TENANT_ID,
            run_id=first_run.id,
            expected_status=RunStatus.STARTING,
            expected_revision=started.status_revision,
            result=TerminalResult(
                outcome="failed", code="test", reason="first finished"
            ),
        )
    async with session_factory() as session, session.begin():
        started_second, _ = await ConversationExecutionCoordinator(session).start_run(
            tenant_id=TENANT_ID,
            run_id=second_run.id,
            expected_revision=1,
        )
    assert started_second.status is RunStatus.STARTING


async def test_delete_fails_closed_for_pending_and_non_terminal_then_restores(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "delete guard"),
        launch=launch,
    )
    await db_session.commit()

    with pytest.raises(ConversationHasPendingTurnError):
        await ConversationExecutionCoordinator(db_session).delete_conversation(
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            conversation_id=conversation_id,
            expected_revision=1,
        )
    await db_session.rollback()

    run = await AgentBridgeDispatcher(
        session_factory, worker_id="delete-worker"
    ).dispatch_turn(event_id=receipt.event_id)
    assert run is not None
    with pytest.raises(ConversationHasNonTerminalRunError):
        await ConversationExecutionCoordinator(db_session).delete_conversation(
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            conversation_id=conversation_id,
            expected_revision=1,
        )
    await db_session.rollback()

    await RunCoordinator(db_session).commit_terminal(
        tenant_id=TENANT_ID,
        run_id=run.id,
        expected_status=RunStatus.QUEUED,
        expected_revision=1,
        result=TerminalResult(
            outcome="cancelled", code="user_cancel", reason="safe to delete"
        ),
    )
    deleted = await ConversationExecutionCoordinator(db_session).delete_conversation(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        expected_revision=1,
    )
    assert deleted.state is ConversationState.DELETED
    assert deleted.purge_after is not None
    # R1-S2：restore 要求预期 owner fence 集合完整且全部 active（backfill 基线）。
    await create_baseline_fences(
        db_session, tenant_id=TENANT_ID, conversation_id=conversation_id
    )
    restored = await ConversationExecutionCoordinator(db_session).restore_conversation(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        expected_revision=2,
    )
    assert restored.state is ConversationState.ACTIVE


async def test_delete_and_claimed_dispatch_are_serialized_without_late_run(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "delete race"),
        launch=launch,
    )
    await db_session.commit()
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        claimed = await AgentWorkspaceBridgeService(session).claim_turn_event(
            worker_id="race-worker",
            now=now,
            stale_before=now - timedelta(seconds=60),
            event_id=receipt.event_id,
        )
    assert claimed is not None

    acquired = asyncio.Event()
    release = asyncio.Event()

    class PausingGuard(ConversationExecutionGuard):
        async def acquire(self, session, *, tenant_id, conversation_id):
            await super().acquire(
                session,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
            )
            acquired.set()
            await release.wait()

    async def consume():
        async with session_factory() as session, session.begin():
            return await ConversationExecutionCoordinator(
                session, guard=PausingGuard()
            ).consume_turn_event(claimed, consumed_at=datetime.now(UTC))

    async def delete():
        async with session_factory() as session, session.begin():
            return await ConversationExecutionCoordinator(session).delete_conversation(
                tenant_id=TENANT_ID,
                actor_id=ACTOR_ID,
                conversation_id=conversation_id,
                expected_revision=1,
            )

    consume_task = asyncio.create_task(consume())
    await acquired.wait()
    delete_task = asyncio.create_task(delete())
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(delete_task), timeout=0.1)
    release.set()
    await consume_task
    with pytest.raises(
        (ConversationHasPendingTurnError, ConversationHasNonTerminalRunError)
    ):
        await delete_task

    conversation = await db_session.get(ConversationModel, conversation_id)
    assert conversation is not None
    await db_session.refresh(conversation)
    assert conversation.state == ConversationState.ACTIVE.value
    assert await db_session.scalar(
        select(func.count()).select_from(AgentRunModel)
    ) == 1


async def test_turn_dead_letter_can_be_abandoned_only_without_execution_receipt(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    invalid_profile_id = uuid.uuid4()
    invalid_config = launch.run_config_snapshot.model_dump(mode="json")
    invalid_config["runtime_profile_id"] = str(invalid_profile_id)
    invalid_launch = TurnLaunchSpecV1(
        agent_definition_version_id=launch.agent_definition_version_id,
        runtime_profile_id=invalid_profile_id,
        runtime_capability_snapshot=launch.runtime_capability_snapshot,
        run_config_snapshot=invalid_config,
        budget_snapshot=launch.budget_snapshot,
    )
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "invalid launch"),
        launch=invalid_launch,
    )
    await db_session.commit()

    dispatcher = AgentBridgeDispatcher(
        session_factory,
        worker_id="dead-letter-worker",
        policy=DispatchPolicy(max_attempts=1),
    )
    with pytest.raises(AgentExecutionError):
        await dispatcher.dispatch_turn(event_id=receipt.event_id)
    message = await db_session.get(MessageModel, receipt.reserved.message.id)
    outbox = await db_session.get(WorkspaceOutboxModel, receipt.event_id)
    assert message is not None
    assert outbox is not None
    await db_session.refresh(message)
    await db_session.refresh(outbox)
    assert message.turn_dispatch_state == TurnDispatchState.DEAD_LETTER.value
    assert outbox.status == "dead_letter"

    state = await ConversationExecutionCoordinator(db_session).abandon_turn_dispatch(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        message_id=message.id,
    )
    assert state is TurnDispatchState.ABANDONED
    assert await db_session.scalar(
        select(func.count()).select_from(AgentRunModel)
    ) == 0


async def test_stale_turn_claim_is_fenced_after_a_new_delivery_attempt(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "fence stale worker"),
        launch=launch,
    )
    await db_session.commit()
    first_at = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        first_claim = await AgentWorkspaceBridgeService(session).claim_turn_event(
            worker_id="stale-worker",
            now=first_at,
            stale_before=first_at - timedelta(seconds=60),
            event_id=receipt.event_id,
        )
    assert first_claim is not None
    retry_at = first_at + timedelta(seconds=120)
    async with session_factory() as session, session.begin():
        second_claim = await AgentWorkspaceBridgeService(session).claim_turn_event(
            worker_id="current-worker",
            now=retry_at,
            stale_before=retry_at - timedelta(seconds=60),
            event_id=receipt.event_id,
        )
    assert second_claim is not None

    async with session_factory() as session, session.begin():
        with pytest.raises(WorkspaceIntegrationConflictError, match="superseded"):
            await ConversationExecutionCoordinator(session).consume_turn_event(
                first_claim, consumed_at=retry_at
            )
    assert await db_session.scalar(
        select(func.count()).select_from(AgentRunModel)
    ) == 0
    async with session_factory() as session, session.begin():
        run, ack, _ = await ConversationExecutionCoordinator(session).consume_turn_event(
            second_claim, consumed_at=retry_at
        )
    async with session_factory() as session, session.begin():
        await AgentWorkspaceBridgeService(session).acknowledge_turn(ack)
    assert run.status is RunStatus.QUEUED


async def test_corrupt_turn_outbox_is_quarantined_without_hot_loop(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "poison envelope"),
        launch=launch,
    )
    await db_session.commit()
    await db_session.execute(
        update(WorkspaceOutboxModel)
        .where(WorkspaceOutboxModel.id == receipt.event_id)
        .values(payload_inline={"event_type": "turn.requested.v1"})
    )
    await db_session.commit()

    dispatcher = AgentBridgeDispatcher(session_factory, worker_id="poison-worker")
    with pytest.raises(PoisonedIntegrationEventError, match="quarantined"):
        await dispatcher.dispatch_turn(event_id=receipt.event_id)
    row = await db_session.get(WorkspaceOutboxModel, receipt.event_id)
    message = await db_session.get(MessageModel, receipt.reserved.message.id)
    assert row is not None
    assert message is not None
    await db_session.refresh(row)
    await db_session.refresh(message)
    assert row.status == "dead_letter"
    assert row.last_error_code == "invalid_event_envelope"
    assert message.turn_dispatch_state == TurnDispatchState.DEAD_LETTER.value
    assert await dispatcher.dispatch_turn(event_id=receipt.event_id) is None


async def test_turn_ack_and_abandon_share_outbox_then_message_lock_order(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "lock order"),
        launch=launch,
    )
    await db_session.commit()
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        claimed = await AgentWorkspaceBridgeService(session).claim_turn_event(
            worker_id="lock-order-worker",
            now=now,
            stale_before=now - timedelta(seconds=60),
            event_id=receipt.event_id,
        )
    assert claimed is not None
    async with session_factory() as session, session.begin():
        _, _, _ = await ConversationExecutionCoordinator(session).consume_turn_event(
            claimed, consumed_at=now
        )

    outbox_locked = asyncio.Event()
    continue_holder = asyncio.Event()

    async def hold_outbox_then_message():
        async with session_factory() as session, session.begin():
            await session.execute(
                select(WorkspaceOutboxModel)
                .where(WorkspaceOutboxModel.id == receipt.event_id)
                .with_for_update()
            )
            outbox_locked.set()
            await continue_holder.wait()
            await session.execute(
                select(MessageModel)
                .where(MessageModel.id == receipt.reserved.message.id)
                .with_for_update()
            )

    async def abandon():
        async with session_factory() as session, session.begin():
            return await ConversationExecutionCoordinator(
                session
            ).abandon_turn_dispatch(
                tenant_id=TENANT_ID,
                actor_id=ACTOR_ID,
                conversation_id=conversation_id,
                message_id=receipt.reserved.message.id,
            )

    holder = asyncio.create_task(hold_outbox_then_message())
    await outbox_locked.wait()
    abandoner = asyncio.create_task(abandon())
    await asyncio.sleep(0.1)
    continue_holder.set()
    await asyncio.wait_for(holder, timeout=2)
    assert await asyncio.wait_for(abandoner, timeout=2) is TurnDispatchState.ACCEPTED


async def test_abandon_fails_closed_on_conflicting_execution_acceptance(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "conflicting acceptance"),
        launch=launch,
    )
    await db_session.commit()
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        claimed = await AgentWorkspaceBridgeService(session).claim_turn_event(
            worker_id="acceptance-worker",
            now=now,
            stale_before=now - timedelta(seconds=60),
            event_id=receipt.event_id,
        )
    assert claimed is not None
    async with session_factory() as session, session.begin():
        run, _, _ = await ConversationExecutionCoordinator(session).consume_turn_event(
            claimed, consumed_at=now
        )
    await db_session.execute(
        update(AgentRunModel)
        .where(AgentRunModel.id == run.id)
        .values(queue_seq=run.queue_seq + 1)
    )
    await db_session.commit()

    with pytest.raises(ExecutionIntegrationConflictError, match="Run conflicts"):
        await ConversationExecutionCoordinator(db_session).abandon_turn_dispatch(
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
            conversation_id=conversation_id,
            message_id=receipt.reserved.message.id,
        )


async def test_dispatcher_claim_does_not_hold_outbox_lock_into_purge_guard(
    db_session, session_factory
):
    conversation_id, identity, launch = await bootstrap_workspace(db_session)
    receipt = await ConversationExecutionCoordinator(db_session).submit_turn(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        command=turn_command(identity, "purge lock order"),
        launch=launch,
    )
    await db_session.commit()
    outbox_locked = asyncio.Event()
    release_claim = asyncio.Event()

    async def hold_claim_transaction():
        async with session_factory() as session, session.begin():
            claimed = await AgentWorkspaceBridgeService(session).claim_turn_event(
                worker_id="purge-race-worker",
                now=datetime.now(UTC),
                stale_before=datetime.now(UTC) - timedelta(seconds=60),
                event_id=receipt.event_id,
            )
            assert claimed is not None
            outbox_locked.set()
            await release_claim.wait()

    holder = asyncio.create_task(hold_claim_transaction())
    await outbox_locked.wait()
    async with session_factory() as session, session.begin():
        await asyncio.wait_for(
            ConversationExecutionCoordinator(session).acquire_purge_preflight(
                tenant_id=TENANT_ID,
                actor_id=ACTOR_ID,
                conversation_id=conversation_id,
            ),
            timeout=2,
        )
    release_claim.set()
    await holder
