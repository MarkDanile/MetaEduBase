"""Conftest for script tests that need a real DB session (REQ-046 PR-5).

Mirrors ``tests/contexts/skill_registry/conftest.py``: an ``AsyncSession``
against the test DB (commits on clean teardown, rolls back on error,
NullPool). Only script tests that persist/read governed tables use this.
"""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests.conftest import DEFAULT_TEST_DB_URL


@pytest_asyncio.fixture
async def db_session():
    """Yield an ``AsyncSession`` against the test DB."""
    engine = create_async_engine(DEFAULT_TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await engine.dispose()
