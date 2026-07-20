"""Verify REQ-044 alembic migration 021 creates the MCP registry schema.

Covers: ``mcp_servers`` / ``mcp_invocation_audit`` tables, the
``uq_mcp_servers_tenant_code`` unique constraint (same tenant + code
rejected, different tenant allowed), named indexes, and symmetric
downgrade (both tables dropped, then re-upgraded so the DB returns to
head).

Requires the test DB to be initialized once (``make init-test-db``);
tests run against TEST_DATABASE_URL or the default metaedu_test DSN.
"""
from __future__ import annotations

import asyncio
import os
import uuid
import warnings
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config

from alembic import command
from app.config import settings

DEFAULT_TEST_DB_URL = (
    "postgresql://metaedu:dev_only_123@localhost:5432/metaedu_test"
)

SERVER_ROOT = Path(__file__).resolve().parents[3]

# index=True 列由 alembic 自动命名为 ix_metaedu_<table>_<col>（同 016 惯例）
EXPECTED_INDEXES = {
    "ix_metaedu_mcp_servers_tenant_id",
    "ix_metaedu_mcp_invocation_audit_tenant_id",
    "ix_mcp_invocation_audit_tenant_server_created",
    "ix_mcp_invocation_audit_tenant_created",
}


def _db_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)


def _sqlalchemy_url() -> str:
    """asyncpg DSN -> SQLAlchemy async driver URL for alembic env."""
    url = _db_url()
    if "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _run_alembic(direction: str, revision: str) -> None:
    """Run alembic upgrade/downgrade against the test DB (sync context)."""
    original_url = settings.database_url
    settings.database_url = _sqlalchemy_url()
    try:
        cfg = Config(str(SERVER_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(SERVER_ROOT / "alembic"))
        # alembic.ini 缺 path_separator 会触发 DeprecationWarning；
        # 与本次 migration 无关，局部忽略以保持 -W error 下可跑
        fn = command.upgrade if direction == "upgrade" else command.downgrade
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            fn(cfg, revision)
    finally:
        settings.database_url = original_url


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    return await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='metaedu' AND table_name=$1)",
        table,
    )


async def _insert_server(
    conn: asyncpg.Connection, tenant_id: uuid.UUID, code: str
) -> None:
    await conn.execute(
        "INSERT INTO metaedu.mcp_servers "
        "(tenant_id, code, name, server_url, created_by) "
        "VALUES ($1, $2, $3, $4, $5)",
        tenant_id,
        code,
        f"name-{code}",
        "https://mcp.example.com/rpc",
        uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_021_creates_tables_constraint_and_indexes():
    """upgrade head 后两表存在 + 唯一约束 + 四个索引齐全。"""
    conn = await asyncpg.connect(_db_url())
    try:
        assert await _table_exists(conn, "mcp_servers")
        assert await _table_exists(conn, "mcp_invocation_audit")

        uq = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_schema='metaedu' AND table_name='mcp_servers' "
            "AND constraint_name='uq_mcp_servers_tenant_code')"
        )
        assert uq

        fk = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_schema='metaedu' "
            "AND table_name='mcp_invocation_audit' "
            "AND constraint_type='FOREIGN KEY')"
        )
        assert fk

        rows = await conn.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='metaedu' "
            "AND tablename IN ('mcp_servers', 'mcp_invocation_audit')"
        )
        names = {r["indexname"] for r in rows}
        missing = EXPECTED_INDEXES - names
        assert not missing, f"Missing indexes: {sorted(missing)}"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_021_duplicate_tenant_code_rejected():
    """同 tenant 同 code 第二次插入触发唯一约束冲突。"""
    tenant_id = uuid.uuid4()
    code = f"dup-{uuid.uuid4().hex[:8]}"
    conn = await asyncpg.connect(_db_url())
    try:
        await _insert_server(conn, tenant_id, code)
        with pytest.raises(asyncpg.UniqueViolationError):
            await _insert_server(conn, tenant_id, code)
    finally:
        # asyncpg 默认每条语句独立事务，失败语句不会污染后续清理
        await conn.execute(
            "DELETE FROM metaedu.mcp_servers WHERE tenant_id=$1 AND code=$2",
            tenant_id,
            code,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_021_same_code_different_tenant_allowed():
    """不同 tenant 使用相同 code 允许（tenant 隔离边界）。"""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    code = f"shared-{uuid.uuid4().hex[:8]}"
    conn = await asyncpg.connect(_db_url())
    try:
        await _insert_server(conn, tenant_a, code)
        await _insert_server(conn, tenant_b, code)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM metaedu.mcp_servers WHERE code=$1",
            code,
        )
        assert count == 2
    finally:
        await conn.execute(
            "DELETE FROM metaedu.mcp_servers WHERE code=$1",
            code,
        )
        await conn.close()


def test_021_downgrade_drops_tables_and_reupgrade_restores():
    """downgrade 到 020 两表被删除；再 upgrade head 恢复（保证库回到 head）。"""

    async def _both_tables_exist() -> bool:
        conn = await asyncpg.connect(_db_url())
        try:
            servers = await _table_exists(conn, "mcp_servers")
            audit = await _table_exists(conn, "mcp_invocation_audit")
            return servers and audit
        finally:
            await conn.close()

    try:
        _run_alembic("downgrade", "020_audit_bp_nullable")
        assert not asyncio.run(_both_tables_exist())
    finally:
        _run_alembic("upgrade", "head")
    assert asyncio.run(_both_tables_exist())
