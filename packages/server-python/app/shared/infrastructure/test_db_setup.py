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
import re
from pathlib import Path

import asyncpg
from alembic.config import Config
from sqlalchemy.engine import make_url

from alembic import command
from app.config import settings
from app.shared.infrastructure.database import run_migrations

logger = logging.getLogger(__name__)

DEFAULT_TEST_DB_URL = (
    "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"
)

# PostgreSQL unquoted identifier rules: start with letter/underscore,
# continue with letters/digits/underscores, max 63 bytes.
_DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

# 旧 conftest 通过 `Base.metadata.create_all` 在 metaedu schema 下一次性建出的
# 业务表集合。检测到「这些表全部存在且 alembic_version 缺失」时，认为是旧
# conftest 留下的完整 schema 形态，stamp head 让 Alembic 认领；避免把「只有
# 几张表 + 缺版本」的残缺 schema 也误判为可 stamp。
_LEGACY_TABLES_FROM_CREATE_ALL = (
    "tenants",
    "users",
    "templates",
    "resources",
    "folders",
    "files",
    "document_chunks",
    "document_tasks",
    "knowledge_nodes",
    "knowledge_edges",
    "datasets",
    "dataset_rows",
)

# 旧 conftest 通过 `Base.metadata.create_all` 建出、并被 `_ensure_seed` 或
# 业务测试显式 INSERT/SELECT 的几张表，其在 `create_all` 形态下必须存在的
# 关键代表列。缺任一列即视为「表存在但残缺」schema，stamp head 会掩盖掉
# 这种残缺，必须让后续 alembic upgrade head 显式报错。
#
# 列名按 PG 默认折叠小写存储；这里用小写匹配。
#
# 维护说明：模型加列时如该列属于"代表列"集合，需同步追加；非代表列加列
# 不需更新此处。这是精确列全集检查 vs. 维护成本的折衷。
_LEGACY_REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    # tenants: PK + 所有 NOT NULL 字段。
    "tenants": ("id", "name", "school_name", "created_at"),
    # users: PK + FK + 业务必填（password_hash）+ 时间戳。
    "users": ("id", "tenant_id", "username", "password_hash", "created_at"),
}


class DatabaseNameError(ValueError):
    """测试数据库名不合法，可能来自不受信的环境变量。"""


def _validate_database_name(name: str | None) -> str:
    """校验测试数据库名符合 PostgreSQL identifier 规则。

    `TEST_DATABASE_URL` 可由环境变量控制，恶意或拼错的库名不应被拼接进
    `CREATE DATABASE`。校验失败直接抛错，避免不可控 SQL 拼接。
    """
    if not name:
        raise DatabaseNameError("测试数据库名不能为空")
    if not _DATABASE_NAME_PATTERN.match(name):
        raise DatabaseNameError(
            f"测试数据库名不合法：{name!r}（需匹配 ^[A-Za-z_][A-Za-z0-9_]{{0,62}}$）"
        )
    return name


def _resolve_test_db_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)


async def _ensure_database(url) -> None:
    """连到 postgres 库，若目标库不存在则创建。"""
    db_name = _validate_database_name(url.database)
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
            db_name,
        )
        if exists:
            logger.info("测试数据库已存在：%s", db_name)
            return
        # CREATE DATABASE 不能在事务内执行；asyncpg 的 execute 默认 autocommit。
        # 库名已通过白名单严格校验，且是 SQL identifier 而非绑定参数，故此处
        # 仍以双引号包裹 PostgreSQL identifier；任何包含 " 的输入会先被拒绝。
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
        logger.info("已创建测试数据库：%s", db_name)
    finally:
        await admin_conn.close()


async def _ensure_extensions_and_schema(url) -> None:
    """连到测试库，幂等创建扩展与 metaedu schema。"""
    db_name = _validate_database_name(url.database)
    conn = await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database=db_name,
    )
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS ltree;")
        await conn.execute("CREATE SCHEMA IF NOT EXISTS metaedu;")
        logger.info("已确认扩展与 schema：vector, ltree, metaedu")
    finally:
        await conn.close()


def _is_legacy_create_all_shape(
    existing_tables: set[str], missing_version: bool
) -> bool:
    """判定当前 schema 是否属于旧 conftest 留下的完整 `create_all` 形态。

    条件：
    - `alembic_version` 表缺失（说明旧 conftest 没走过 Alembic 路径）；
    - 旧 conftest 一次性建出的核心表**全部**都已存在。

    只要有任一核心表缺失，就视为残缺 schema；stamp head 不会修复残缺，
    反而会掩盖问题，应让后续 `alembic upgrade head` 直接报错。

    注意：此函数仅校验表集合。TD-014 起，外层 `_stamp_if_legacy_schema`
    还会再调用 `_has_legacy_create_all_columns` 校验 INSERT 目标表的
    关键列形态，进一步避免「表都在但关键列缺失」的残缺 schema 被 stamp
    掩盖。
    """
    if not missing_version:
        return False
    return all(
        table in existing_tables for table in _LEGACY_TABLES_FROM_CREATE_ALL
    )


def _has_legacy_create_all_columns(
    existing_columns_by_table: dict[str, set[str]],
) -> bool:
    """判定 INSERT 目标表的关键列是否齐全。

    传入 `existing_columns_by_table`：key 为表名（小写），value 为该表在
    `information_schema.columns` 中已存在的列名集合（小写）。

    返回 True 表示 `_LEGACY_REQUIRED_COLUMNS` 中所有表的代表列都已存在。
    """
    for table, required_columns in _LEGACY_REQUIRED_COLUMNS.items():
        existing = existing_columns_by_table.get(table)
        if existing is None:
            # 表不在字典里说明连表都没建到；这种情况由表集合检查负责拦截。
            continue
        if not all(col in existing for col in required_columns):
            return False
    return True


async def _stamp_if_legacy_schema(url, test_url_str: str) -> bool:
    """兼容旧 conftest 留下的环境。

    旧 conftest 通过 `Base.metadata.create_all` 直接建表，但从未写入
    `metaedu.alembic_version`。直接跑 `alembic upgrade head` 会因为
    `tenants` 等表已存在而失败。检测到这种"业务表已建好但 alembic 版本表
    为空"的状态时，stamp 到 head 让 Alembic 重新认领。新环境（业务表
    完全不存在）不触发此路径。返回 True 表示已 stamp。

    「业务表已建好」需要进一步收紧为：
    1. 旧 conftest 通过 `create_all` 一次性建出的核心表**全部**都存在；
    2. INSERT 目标表（`tenants` / `users`）的关键代表列都齐全。

    任一不满足都视为残缺 schema，stamp head 不会修复残缺，反而会掩盖
    问题，应让后续 `alembic upgrade head` 直接报错。

    `test_url_str` 必须传入原始连接串；不能用 `str(url)`，否则
    SQLAlchemy URL 对象会把密码 mask 成 `***`，alembic 后续连接会失败。
    """
    db_name = _validate_database_name(url.database)
    conn = await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database=db_name,
    )
    try:
        version_table_exists = await conn.fetchval(
            "SELECT to_regclass('metaedu.alembic_version') IS NOT NULL",
        )
        # 一次性把核心业务表的实际存在性查出来，避免分别 round-trip。
        table_rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'metaedu'"
        )
        existing_tables = {r["tablename"] for r in table_rows}
        # 列级形态校验：仅对 `_LEGACY_REQUIRED_COLUMNS` 中出现的几张 INSERT
        # 目标表查询列名集合（PG 默认小写存储），用小写匹配。
        legacy_target_tables = list(_LEGACY_REQUIRED_COLUMNS)
        column_rows = await conn.fetch(
            "SELECT table_name, column_name "
            "FROM information_schema.columns "
            "WHERE table_schema = 'metaedu' "
            "AND table_name = ANY($1::text[])",
            legacy_target_tables,
        )
        existing_columns_by_table: dict[str, set[str]] = {}
        for r in column_rows:
            existing_columns_by_table.setdefault(
                r["table_name"], set()
            ).add(r["column_name"])
    finally:
        await conn.close()

    shape_ok = _is_legacy_create_all_shape(
        existing_tables, missing_version=not version_table_exists
    )
    columns_ok = _has_legacy_create_all_columns(existing_columns_by_table)
    if shape_ok and columns_ok:
        logger.info(
            "检测到遗留 schema（旧 conftest create_all 形态完整 + 缺 alembic_version），"
            "执行 stamp head"
        )
        original = settings.database_url
        settings.database_url = test_url_str
        try:
            server_root = Path(__file__).resolve().parents[3]
            alembic_cfg = Config(str(server_root / "alembic.ini"))
            alembic_cfg.set_main_option("script_location", str(server_root / "alembic"))
            alembic_cfg.set_main_option("sqlalchemy.url", test_url_str)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, command.stamp, alembic_cfg, "head")
        finally:
            settings.database_url = original
        return True
    if shape_ok and not columns_ok:
        logger.info(
            "检测到「表集合齐全但 INSERT 目标表关键列缺失」的残缺 schema，"
            "不执行 stamp head，留给 alembic upgrade head 显式报错"
        )
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
    # 显式校验一次；后续子函数也会再校验，重复但能尽早失败并产出清晰日志。
    db_name = _validate_database_name(url.database)
    await _ensure_database(url)
    await _ensure_extensions_and_schema(url)
    await _stamp_if_legacy_schema(url, test_url_str)
    await _run_alembic_against(test_url_str)
    logger.info("测试数据库初始化完成：%s", db_name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(init_test_database())


if __name__ == "__main__":
    main()
