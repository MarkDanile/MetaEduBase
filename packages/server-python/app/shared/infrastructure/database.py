import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

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
