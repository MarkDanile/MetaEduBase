"""Verify REQ-046 alembic migration 023 creates the due-diligence workbench schema.

Covers: ``dd_tasks`` / ``dd_reports`` / ``dd_evidence`` tables, the
``uq_dd_reports_task_version`` unique constraint (same task + version rejected,
different version allowed), the ``dd_reports.task_id`` and
``dd_evidence.report_id`` foreign keys, named indexes, and symmetric
downgrade (all three tables dropped, then re-upgraded so the DB returns to
head).

Requires the test DB to be initialized once (``make init-test-db``); tests run
against TEST_DATABASE_URL or the default metaedu_test DSN.
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

# index=True 列由 alembic 自动命名为 ix_metaedu_<table>_<col>（同 021/022 惯例）
EXPECTED_INDEXES = {
    "ix_metaedu_dd_tasks_tenant_id",
    "ix_metaedu_dd_reports_tenant_id",
    "ix_metaedu_dd_evidence_tenant_id",
    "ix_dd_tasks_tenant_status",
    "ix_dd_reports_task",
    "ix_dd_evidence_report",
}

TABLES = ("dd_tasks", "dd_reports", "dd_evidence")


def _db_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


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


async def _insert_task(
    conn: asyncpg.Connection, tenant_id: uuid.UUID, title: str
) -> uuid.UUID:
    return await conn.fetchval(
        "INSERT INTO metaedu.dd_tasks (tenant_id, title, subject_query, created_by) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        tenant_id,
        title,
        "某企业简称",
        uuid.uuid4(),
    )


async def _insert_report(
    conn: asyncpg.Connection,
    tenant_id: uuid.UUID,
    task_id: uuid.UUID,
    version: int,
) -> uuid.UUID:
    return await conn.fetchval(
        "INSERT INTO metaedu.dd_reports "
        "(tenant_id, task_id, version, report_json, report_markdown) "
        "VALUES ($1, $2, $3, $4::jsonb, $5) RETURNING id",
        tenant_id,
        task_id,
        version,
        '{"summary": []}',
        "# 报告",
    )


@pytest.mark.asyncio
async def test_023_creates_tables_constraint_and_indexes():
    """upgrade head 后三表存在 + 唯一约束 + 外键 + 索引齐全。"""
    conn = await asyncpg.connect(_db_url())
    try:
        for table in TABLES:
            assert await _table_exists(conn, table), f"missing table {table}"

        uq = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_schema='metaedu' AND table_name='dd_reports' "
            "AND constraint_name='uq_dd_reports_task_version')"
        )
        assert uq

        for table in ("dd_reports", "dd_evidence"):
            fk = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.table_constraints "
                "WHERE constraint_schema='metaedu' AND table_name=$1 "
                "AND constraint_type='FOREIGN KEY')",
                table,
            )
            assert fk, f"missing FK on {table}"

        rows = await conn.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='metaedu' "
            "AND tablename = ANY($1::text[])",
            list(TABLES),
        )
        names = {r["indexname"] for r in rows}
        missing = EXPECTED_INDEXES - names
        assert not missing, f"Missing indexes: {sorted(missing)}"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_023_duplicate_task_version_rejected():
    """同 task 同 version 第二次插入触发唯一约束冲突。"""
    tenant_id = uuid.uuid4()
    conn = await asyncpg.connect(_db_url())
    try:
        task_id = await _insert_task(conn, tenant_id, "dup-task")
        await _insert_report(conn, tenant_id, task_id, 1)
        with pytest.raises(asyncpg.UniqueViolationError):
            await _insert_report(conn, tenant_id, task_id, 1)
    finally:
        await conn.execute(
            "DELETE FROM metaedu.dd_reports WHERE tenant_id=$1", tenant_id
        )
        await conn.execute(
            "DELETE FROM metaedu.dd_tasks WHERE tenant_id=$1", tenant_id
        )
        await conn.close()


@pytest.mark.asyncio
async def test_023_same_task_different_version_allowed():
    """同 task 不同 version 允许（报告多版本并存）。"""
    tenant_id = uuid.uuid4()
    conn = await asyncpg.connect(_db_url())
    try:
        task_id = await _insert_task(conn, tenant_id, "ver-task")
        await _insert_report(conn, tenant_id, task_id, 1)
        await _insert_report(conn, tenant_id, task_id, 2)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM metaedu.dd_reports WHERE task_id=$1", task_id
        )
        assert count == 2
    finally:
        await conn.execute(
            "DELETE FROM metaedu.dd_reports WHERE tenant_id=$1", tenant_id
        )
        await conn.execute(
            "DELETE FROM metaedu.dd_tasks WHERE tenant_id=$1", tenant_id
        )
        await conn.close()


@pytest.mark.asyncio
async def test_023_evidence_references_report():
    """dd_evidence.report_id 外键指向 dd_reports；同 report 可挂多条证据。"""
    tenant_id = uuid.uuid4()
    conn = await asyncpg.connect(_db_url())
    try:
        task_id = await _insert_task(conn, tenant_id, "ev-task")
        report_id = await _insert_report(conn, tenant_id, task_id, 1)
        for etype in ("mcp_invocation", "data_query"):
            await conn.execute(
                "INSERT INTO metaedu.dd_evidence "
                "(tenant_id, report_id, evidence_type, section, summary) "
                "VALUES ($1, $2, $3, $4, $5)",
                tenant_id,
                report_id,
                etype,
                "事实数据",
                "非敏感摘要",
            )
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM metaedu.dd_evidence WHERE report_id=$1",
            report_id,
        )
        assert count == 2
    finally:
        await conn.execute(
            "DELETE FROM metaedu.dd_evidence WHERE tenant_id=$1", tenant_id
        )
        await conn.execute(
            "DELETE FROM metaedu.dd_reports WHERE tenant_id=$1", tenant_id
        )
        await conn.execute(
            "DELETE FROM metaedu.dd_tasks WHERE tenant_id=$1", tenant_id
        )
        await conn.close()


def test_023_downgrade_drops_tables_and_reupgrade_restores():
    """downgrade 到 022 三表被删除；再 upgrade head 恢复（保证库回到 head）。"""

    async def _all_tables_exist() -> bool:
        conn = await asyncpg.connect(_db_url())
        try:
            exists = [await _table_exists(conn, t) for t in TABLES]
            return all(exists)
        finally:
            await conn.close()

    try:
        _run_alembic("downgrade", "022_skill_registry")
        assert not asyncio.run(_all_tables_exist())
    finally:
        _run_alembic("upgrade", "head")
    assert asyncio.run(_all_tables_exist())
