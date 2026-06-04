"""测试数据库初始化入口。

幂等创建测试库、安装 pgvector / ltree 扩展、创建 metaedu schema，
并通过 Alembic upgrade head 同步表结构。不写任何 seed；测试 seed
由 conftest._ensure_seed fixture 负责。

用法：
    python -m app.shared.infrastructure.test_db_setup

可通过 TEST_DATABASE_URL 环境变量覆盖默认连接串，默认值与
tests/conftest.py 一致。
"""

import asyncio
import logging
import os

import asyncpg
from sqlalchemy.engine import make_url

from app.config import settings
from app.shared.infrastructure.database import run_migrations

logger = logging.getLogger(__name__)

DEFAULT_TEST_DB_URL = (
    "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"
)


def _resolve_test_db_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)


async def _ensure_database(url) -> None:
    """连到 postgres 库，若目标库不存在则创建。"""
    admin_conn = await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database="postgres",
    )
    try:
        exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            url.database,
        )
        if exists:
            logger.info("测试数据库已存在：%s", url.database)
            return
        # CREATE DATABASE 不能在事务内执行；asyncpg 的 execute 默认 autocommit。
        await admin_conn.execute(f'CREATE DATABASE "{url.database}"')
        logger.info("已创建测试数据库：%s", url.database)
    finally:
        await admin_conn.close()


async def _ensure_extensions_and_schema(url) -> None:
    """连到测试库，幂等创建扩展与 metaedu schema。"""
    conn = await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database=url.database,
    )
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS ltree;")
        await conn.execute("CREATE SCHEMA IF NOT EXISTS metaedu;")
        logger.info("已确认扩展与 schema：vector, ltree, metaedu")
    finally:
        await conn.close()


async def _stamp_if_legacy_schema(url, test_url_str: str) -> bool:
    """兼容旧 conftest 留下的环境。

    旧 conftest 通过 `Base.metadata.create_all` 直接建表，但从未写入
    `metaedu.alembic_version`。直接跑 `alembic upgrade head` 会因为
    `tenants` 等表已存在而失败。检测到这种"业务表已建好但 alembic 版本表
    为空"的状态时，stamp 到 head 让 Alembic 重新认领。新环境（业务表
    完全不存在）不触发此路径。返回 True 表示已 stamp。

    `test_url_str` 必须传入原始连接串；不能用 `str(url)`，否则
    SQLAlchemy URL 对象会把密码 mask 成 `***`，alembic 后续连接会失败。
    """
    conn = await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database=url.database,
    )
    try:
        version_table_exists = await conn.fetchval(
            "SELECT to_regclass('metaedu.alembic_version') IS NOT NULL",
        )
        tenants_table_exists = await conn.fetchval(
            "SELECT to_regclass('metaedu.tenants') IS NOT NULL",
        )
    finally:
        await conn.close()

    if tenants_table_exists and not version_table_exists:
        logger.info("检测到遗留 schema（业务表已存在但缺 alembic_version），执行 stamp head")
        original = settings.database_url
        settings.database_url = test_url_str
        try:
            from pathlib import Path

            from alembic import command
            from alembic.config import Config

            server_root = Path(__file__).resolve().parents[3]
            alembic_cfg = Config(str(server_root / "alembic.ini"))
            alembic_cfg.set_main_option("script_location", str(server_root / "alembic"))
            alembic_cfg.set_main_option("sqlalchemy.url", test_url_str)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, command.stamp, alembic_cfg, "head")
        finally:
            settings.database_url = original
        return True
    return False


async def _run_alembic_against(test_url: str) -> None:
    """临时把 settings.database_url 指向测试库后调用既有 run_migrations。"""
    original = settings.database_url
    settings.database_url = test_url
    try:
        await run_migrations()
    finally:
        settings.database_url = original


async def init_test_database() -> None:
    test_url_str = _resolve_test_db_url()
    url = make_url(test_url_str)
    await _ensure_database(url)
    await _ensure_extensions_and_schema(url)
    await _stamp_if_legacy_schema(url, test_url_str)
    await _run_alembic_against(test_url_str)
    logger.info("测试数据库初始化完成：%s", url.database)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(init_test_database())


if __name__ == "__main__":
    main()
