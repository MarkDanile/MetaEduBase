from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests.conftest import TEST_DB_URL
from tests.shared.agent_control_plane import clean_agent_control_plane


@pytest_asyncio.fixture(autouse=True)
async def _clean_agent_tables():
    """每个 composition 测试前后清空 agent 控制面表。

    composition 测试用 ``db_session``（yield 后 commit）写入真实行；若不在
    teardown 清空，残留的 tombstone 行（如 redacted CompatibilityOutput 的
    ``response_envelope IS NULL``）会让其它上下文的迁移往返测试在 downgrade
    恢复 NOT NULL 时失败。与 agent_workspace/execution/control_plane conftest
    的 autouse clean 约定一致。
    """
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    await clean_agent_control_plane(engine)
    yield
    await clean_agent_control_plane(engine)
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
    """返回独立 async_sessionmaker；测试在测试体内自行 commit。

    并发 / backfill 测试需要在测试体中段提交父行，使其它独立连接能看到，
    因此不能用 commit 发生在 yield 之后的 ``db_session``。由测试自行决定
    commit / rollback 时机。teardown 由 autouse ``_clean_agent_tables`` 兜底。
    """
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()
