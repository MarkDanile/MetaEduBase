import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.contexts.agent_execution.infrastructure.models  # noqa: F401
import app.contexts.agent_workspace.infrastructure.models  # noqa: F401
import app.contexts.identity.infrastructure.models  # noqa: F401
import app.contexts.knowledge.infrastructure.models  # noqa: F401
import app.contexts.resource.infrastructure.models  # noqa: F401
import app.shared.infrastructure.models  # noqa: F401
from alembic import context
from app.config import settings
from app.shared.infrastructure.database import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    # TD-080: disable_existing_loggers=False 避免污染测试中已创建的 logger
    # （fileConfig 默认 True 会把已存在 logger 设 disabled=True，导致后续测试
    # caplog 收不到 warning，全量顺序下 test_embedding_empty_logs_warning 失败）。
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version",
        version_table_schema="metaedu",
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="alembic_version",
        version_table_schema="metaedu",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
