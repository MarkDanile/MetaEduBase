"""Database fixture for internal MCP tests."""
from __future__ import annotations

import os

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

DEFAULT_TEST_DB_URL = (
    "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"
)
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        try:
            await session.execute(
                text(
                    "DELETE FROM metaedu.datasets "
                    "WHERE name LIKE 'test-%' AND 'req046-test' = ANY(tags)"
                )
            )
            await session.commit()
            yield session
        finally:
            await session.rollback()
            await session.execute(
                text(
                    "DELETE FROM metaedu.datasets "
                    "WHERE name LIKE 'test-%' AND 'req046-test' = ANY(tags)"
                )
            )
            await session.execute(
                text(
                    "DELETE FROM metaedu.data_catalogs WHERE code LIKE 'park_%' "
                    "AND name = 'REQ-046 园区测试库'"
                )
            )
            await session.execute(
                text("DELETE FROM metaedu.tenants WHERE name LIKE 'other-%'")
            )
            await session.commit()
    await engine.dispose()
