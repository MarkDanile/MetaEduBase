import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

_advisory_claim_engines: dict[tuple[int, str], AsyncEngine] = {}


def get_advisory_claim_engine(source_engine: AsyncEngine) -> AsyncEngine:
    """Return a bounded pool isolated from request/repository database traffic."""
    if isinstance(source_engine.pool, NullPool):
        return create_async_engine(
            source_engine.url,
            echo=False,
            poolclass=NullPool,
        )
    key = (
        id(asyncio.get_running_loop()),
        source_engine.url.render_as_string(hide_password=False),
    )
    claim_engine = _advisory_claim_engines.get(key)
    if claim_engine is None:
        claim_engine = create_async_engine(
            source_engine.url,
            echo=False,
            pool_size=4,
            max_overflow=0,
            pool_timeout=1,
            pool_pre_ping=True,
        )
        _advisory_claim_engines[key] = claim_engine
    return claim_engine


async def dispose_advisory_claim_engines() -> None:
    engines = tuple(_advisory_claim_engines.values())
    _advisory_claim_engines.clear()
    for claim_engine in engines:
        await claim_engine.dispose()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Expose the short-lived session factory for durable streaming readers."""

    return async_session_factory


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ensure_metaedu_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS metaedu"))


async def run_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    await ensure_metaedu_schema()

    server_root = Path(__file__).resolve().parents[3]
    alembic_cfg = Config(str(server_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(server_root / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, command.upgrade, alembic_cfg, "head")
    logger.info("数据库迁移完成 (alembic upgrade head)")
