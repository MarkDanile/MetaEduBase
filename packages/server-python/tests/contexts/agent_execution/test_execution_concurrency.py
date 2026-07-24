from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    RunConflictError,
    RunStatus,
    TerminalResult,
)
from tests.conftest import TEST_DB_URL
from tests.contexts.agent_execution.e1_helpers import (
    TENANT_A,
    AllowStartBarrier,
    bootstrap_compatibility,
    make_event,
    make_run_command,
)


@pytest.mark.asyncio
async def test_two_schedulers_cannot_acquire_the_same_queued_run(db_session):
    identity = await bootstrap_compatibility(db_session)
    command = make_run_command(identity)
    await RunCoordinator(db_session).create_run(command)
    await db_session.commit()

    engine = create_async_engine(TEST_DB_URL, pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def start():
        async with factory() as session:
            try:
                result = await RunCoordinator(
                    session, start_barrier=AllowStartBarrier()
                ).start_run(
                    tenant_id=TENANT_A,
                    run_id=command.run_id,
                    expected_revision=1,
                )
                await session.commit()
                return result[0]
            except Exception as exc:
                await session.rollback()
                return exc

    try:
        results = await asyncio.gather(start(), start())
    finally:
        await engine.dispose()

    assert sum(
        getattr(result, "status", None) is RunStatus.STARTING for result in results
    ) == 1
    assert sum(isinstance(result, RunConflictError) for result in results) == 1


@pytest.mark.asyncio
async def test_transition_revision_cas_allows_only_one_winner(db_session):
    identity = await bootstrap_compatibility(db_session)
    command = make_run_command(identity)
    coordinator = RunCoordinator(db_session, start_barrier=AllowStartBarrier())
    await coordinator.create_run(command)
    run, _ = await coordinator.start_run(
        tenant_id=TENANT_A,
        run_id=command.run_id,
        expected_revision=1,
    )
    await db_session.commit()

    engine = create_async_engine(TEST_DB_URL, pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def transition():
        async with factory() as session:
            try:
                result = await RunCoordinator(session).transition_run(
                    tenant_id=TENANT_A,
                    run_id=run.id,
                    expected_status=RunStatus.STARTING,
                    expected_revision=run.status_revision,
                    target_status=RunStatus.RUNNING,
                    summary="CAS winner",
                )
                await session.commit()
                return result[0]
            except Exception as exc:
                await session.rollback()
                return exc

    try:
        results = await asyncio.gather(transition(), transition())
    finally:
        await engine.dispose()

    assert sum(
        getattr(result, "status", None) is RunStatus.RUNNING for result in results
    ) == 1
    assert sum(isinstance(result, RunConflictError) for result in results) == 1


@pytest.mark.asyncio
async def test_adjacent_queued_starts_lock_the_conversation_prefix_in_fifo_order(
    db_session,
):
    identity = await bootstrap_compatibility(db_session)
    conversation_id = make_run_command(identity).conversation_id
    commands = [
        make_run_command(
            identity,
            conversation_id=conversation_id,
            queue_seq=queue_seq,
        )
        for queue_seq in (1, 2, 3)
    ]
    coordinator = RunCoordinator(db_session, start_barrier=AllowStartBarrier())
    for command in commands:
        await coordinator.create_run(command)
    first, _ = await coordinator.start_run(
        tenant_id=TENANT_A,
        run_id=commands[0].run_id,
        expected_revision=1,
    )
    first, _, _ = await coordinator.commit_terminal(
        tenant_id=TENANT_A,
        run_id=first.id,
        expected_status=RunStatus.STARTING,
        expected_revision=first.status_revision,
        result=TerminalResult(
            outcome="failed",
            code="setup_failed",
            reason="Release the FIFO predecessor for the race",
        ),
    )
    assert first.status is RunStatus.FAILED
    await db_session.commit()

    engine = create_async_engine(TEST_DB_URL, pool_size=4, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def start(run_id):
        async with factory() as session:
            try:
                result = await RunCoordinator(
                    session, start_barrier=AllowStartBarrier()
                ).start_run(
                    tenant_id=TENANT_A,
                    run_id=run_id,
                    expected_revision=1,
                )
                await session.commit()
                return result[0]
            except Exception as exc:
                await session.rollback()
                return exc

    try:
        results = await asyncio.gather(
            start(commands[1].run_id),
            start(commands[2].run_id),
        )
    finally:
        await engine.dispose()

    winners = [result for result in results if getattr(result, "status", None)]
    assert len(winners) == 1
    assert winners[0].id == commands[1].run_id
    assert winners[0].status is RunStatus.STARTING
    assert sum(isinstance(result, RunConflictError) for result in results) == 1


@pytest.mark.asyncio
async def test_one_hundred_concurrent_appends_allocate_gapless_canonical_seq(
    db_session,
):
    identity = await bootstrap_compatibility(db_session)
    command = make_run_command(identity)
    await RunCoordinator(db_session).create_run(command)
    await db_session.commit()

    engine = create_async_engine(TEST_DB_URL, pool_size=12, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def append(index: int) -> int:
        async with factory() as session:
            event = await RunCoordinator(session).append_event(
                tenant_id=TENANT_A,
                run_id=command.run_id,
                event=make_event(
                    summary=f"Concurrent event {index}",
                    correlation_id=command.correlation_id,
                ),
            )
            await session.commit()
            return event.seq

    try:
        allocated = await asyncio.gather(*(append(index) for index in range(100)))
    finally:
        await engine.dispose()

    assert sorted(allocated) == list(range(1, 101))
    events = await RunCoordinator(db_session).list_events(
        tenant_id=TENANT_A,
        run_id=command.run_id,
    )
    assert [event.seq for event in events] == list(range(1, 101))
