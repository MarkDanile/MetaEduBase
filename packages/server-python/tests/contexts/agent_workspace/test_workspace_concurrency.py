from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.application.dto import MessagePartInput, TurnCommand
from app.contexts.agent_workspace.domain import IdempotencyConflictError, MessagePartType
from tests.conftest import TEST_DB_URL

pytestmark = pytest.mark.asyncio


async def test_fifty_concurrent_turns_allocate_gapless_message_and_queue_seq(db_session):
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=tenant_id,
        actor_id=actor_id,
    )
    await db_session.commit()

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def reserve(index: int) -> tuple[int, int]:
        async with factory() as session:
            turn = await AgentWorkspaceService(
                session, cursor_secret="test-secret"
            ).reserve_user_turn(
                tenant_id=tenant_id,
                actor_id=actor_id,
                conversation_id=view.conversation.id,
                command=TurnCommand(
                    client_message_id=uuid.uuid4(),
                    parts=(
                        MessagePartInput(
                            type=MessagePartType.TEXT,
                            text=f"message-{index}",
                        ),
                    ),
                    agent_definition_version_id=uuid.uuid4(),
                ),
            )
            await session.commit()
            return turn.message.seq, turn.message.requested_run_queue_seq or 0

    try:
        allocated = await asyncio.gather(*(reserve(index) for index in range(50)))
    finally:
        await engine.dispose()
    assert sorted(seq for seq, _ in allocated) == list(range(1, 51))
    assert sorted(queue_seq for _, queue_seq in allocated) == list(range(1, 51))


async def test_concurrent_same_idempotency_key_returns_one_receipt(db_session):
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=tenant_id,
        actor_id=actor_id,
    )
    await db_session.commit()
    client_message_id = uuid.uuid4()
    agent_version_id = uuid.uuid4()
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def reserve(text: str):
        async with factory() as session:
            try:
                result = await AgentWorkspaceService(
                    session, cursor_secret="test-secret"
                ).reserve_user_turn(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    conversation_id=view.conversation.id,
                    command=TurnCommand(
                        client_message_id=client_message_id,
                        parts=(MessagePartInput(type=MessagePartType.TEXT, text=text),),
                        agent_definition_version_id=agent_version_id,
                    ),
                )
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    try:
        identical = await asyncio.gather(*(reserve("same") for _ in range(10)))
        assert len({item.message.id for item in identical}) == 1
        assert len({item.message.requested_run_id for item in identical}) == 1
        assert {item.message.seq for item in identical} == {1}
        assert {item.message.requested_run_queue_seq for item in identical} == {1}

        results = await asyncio.gather(
            reserve("same"), reserve("different"), return_exceptions=True
        )
    finally:
        await engine.dispose()
    assert sum(isinstance(item, IdempotencyConflictError) for item in results) == 1
