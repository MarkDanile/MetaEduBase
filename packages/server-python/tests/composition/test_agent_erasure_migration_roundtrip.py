"""034 erasure foundation migration upgrade/downgrade/upgrade 往返。

独立成模块并在其他 erasure schema 测试之后运行，避免迁移往返影响同进程
其他 DB 依赖测试（与 ``test_agent_erasure_schema.py`` 中的表/列存在性断言分离）。
"""

from __future__ import annotations

import asyncio
import warnings
from pathlib import Path

import asyncpg
from alembic.config import Config

from alembic import command
from app.config import settings
from tests.conftest import TEST_DB_URL

SERVER_ROOT = Path(__file__).resolve().parents[2]
COORD_TABLES = {
    "agent_erasure_fences",
    "agent_conversation_purges",
    "agent_conversation_purge_owners",
    "agent_conversation_legal_holds",
}

# downgrade 会把 tombstone 放宽的列还原为 NOT NULL；含 tombstone（NULL 正文）的
# 遗留行会破坏还原。往返前清空携带 tombstone 的表与 coordination 表。
_CLEAN_TABLES = (
    "agent_conversation_legal_holds",
    "agent_conversation_purge_owners",
    "agent_conversation_purges",
    "agent_erasure_fences",
    "agent_compatibility_outputs",
    "agent_run_events",
    "agent_turn_inputs",
    "agent_execution_inbox",
    "agent_execution_outbox",
    "agent_runs",
    "agent_workspace_inbox",
    "agent_workspace_outbox",
    "agent_message_parts",
    "agent_messages",
    "agent_conversation_user_state",
    "agent_conversations",
)


def _db_url() -> str:
    return TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


def _sqlalchemy_url() -> str:
    return _db_url().replace("postgresql://", "postgresql+asyncpg://", 1)


def _run_alembic(direction: str, revision: str) -> None:
    original_url = settings.database_url
    settings.database_url = _sqlalchemy_url()
    try:
        config = Config(str(SERVER_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(SERVER_ROOT / "alembic"))
        fn = command.upgrade if direction == "upgrade" else command.downgrade
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            fn(config, revision)
    finally:
        settings.database_url = original_url


async def _existing_coord_tables() -> set[str]:
    connection = await asyncpg.connect(_db_url())
    try:
        rows = await connection.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='metaedu' AND table_name = ANY($1::text[])",
            list(COORD_TABLES),
        )
        return {row["table_name"] for row in rows}
    finally:
        await connection.close()


def test_034_downgrade_upgrade_round_trip():
    asyncio.run(_clean_tombstone_tables())
    try:
        _run_alembic("downgrade", "033_agent_compat_output")
        assert asyncio.run(_existing_coord_tables()) == set()
    finally:
        _run_alembic("upgrade", "head")
    assert asyncio.run(_existing_coord_tables()) == COORD_TABLES


async def _clean_tombstone_tables() -> None:
    connection = await asyncpg.connect(_db_url())
    try:
        await connection.execute(
            "TRUNCATE TABLE " + ", ".join(f"metaedu.{t}" for t in _CLEAN_TABLES)
        )
    finally:
        await connection.close()


# ---------------------------------------------------------------------------
# round-6 P2-4：037 system_key_fingerprints 专属迁移回归
# ---------------------------------------------------------------------------

_037_TABLE = "system_key_fingerprints"


async def _system_key_fingerprint_schema() -> dict:
    """返回 037 表的存在性 + PK + CHECK 约束名集合。"""
    connection = await asyncpg.connect(_db_url())
    try:
        exists = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='metaedu' AND table_name=$1)",
            _037_TABLE,
        )
        if not exists:
            return {"exists": False, "constraints": set()}
        rows = await connection.fetch(
            "SELECT conname FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "WHERE n.nspname='metaedu' "
            "AND c.conrelid = $1::regclass",
            f"metaedu.{_037_TABLE}",
        )
        return {"exists": True, "constraints": {r["conname"] for r in rows}}
    finally:
        await connection.close()


def test_037_system_key_fingerprints_downgrade_upgrade_round_trip():
    """round-6 P2-4：037 真实 downgrade->upgrade--表 + PK + CHECK 重建。

    037 是纯 expand（新建表），downgrade drop_table，upgrade recreate。
    验证：(1) head 状态表存在且含 pk + check 约束；(2) downgrade 到 036 表消失；
    (3) upgrade 回 head 表重建且约束齐全。
    """
    # head 状态：表存在 + PK + CHECK。
    schema = asyncio.run(_system_key_fingerprint_schema())
    assert schema["exists"], "system_key_fingerprints should exist at head"
    assert "pk_system_key_fingerprints" in schema["constraints"]
    assert "ck_system_key_fingerprints_fingerprint" in schema["constraints"]

    try:
        _run_alembic("downgrade", "036_erasure_fence_empty_ingress")
        schema = asyncio.run(_system_key_fingerprint_schema())
        assert not schema["exists"], (
            "system_key_fingerprints should be dropped after downgrade to 036"
        )
    finally:
        _run_alembic("upgrade", "head")

    # upgrade 回 head：表 + 约束重建。
    schema = asyncio.run(_system_key_fingerprint_schema())
    assert schema["exists"], "system_key_fingerprints should exist after upgrade to head"
    assert "pk_system_key_fingerprints" in schema["constraints"]
    assert "ck_system_key_fingerprints_fingerprint" in schema["constraints"]
