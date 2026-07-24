from __future__ import annotations

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests.conftest import TEST_DB_URL

_CLEAN_SQL = (
    "DELETE FROM metaedu.agent_workspace_inbox",
    "DELETE FROM metaedu.agent_workspace_outbox",
    "DELETE FROM metaedu.agent_message_parts",
    "DELETE FROM metaedu.agent_messages",
    "DELETE FROM metaedu.agent_conversation_user_state",
    "DELETE FROM metaedu.agent_conversations",
)


async def _clean(engine) -> None:
    async with engine.begin() as connection:
        for statement in _CLEAN_SQL:
            await connection.execute(text(statement))


@pytest_asyncio.fixture(autouse=True)
async def clean_agent_workspace():
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
