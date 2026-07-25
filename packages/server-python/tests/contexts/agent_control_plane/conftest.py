from __future__ import annotations

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests.conftest import TEST_DB_URL

_CLEAN_SQL = """
TRUNCATE TABLE
    metaedu.agent_compatibility_outputs,
    metaedu.agent_run_events,
    metaedu.agent_turn_inputs,
    metaedu.agent_execution_inbox,
    metaedu.agent_execution_outbox,
    metaedu.agent_runs,
    metaedu.agent_runtime_session_bindings,
    metaedu.agent_runtime_profiles,
    metaedu.agent_definition_versions,
    metaedu.agent_workspace_inbox,
    metaedu.agent_workspace_outbox,
    metaedu.agent_message_parts,
    metaedu.agent_messages,
    metaedu.agent_conversation_user_state,
    metaedu.agent_conversations
"""


async def _clean(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(_CLEAN_SQL))


@pytest_asyncio.fixture(autouse=True)
async def clean_agent_control_plane():
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    await _clean(engine)
    yield
    await _clean(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()
