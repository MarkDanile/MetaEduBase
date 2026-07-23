"""Conftest for due_diligence context tests needing a real DB session.

Mirrors ``tests/contexts/skill_registry/conftest.py``: an ``AsyncSession``
against the test DB (commits on clean teardown, rolls back on error,
NullPool). The domain / service tests that use an in-memory repository do not
need this; repository + orchestrator integration tests do.
"""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests.conftest import TEST_DB_URL


@pytest_asyncio.fixture
async def db_session():
    """Yield an ``AsyncSession`` against the test DB."""
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
