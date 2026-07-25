from __future__ import annotations

import asyncio
import os
import warnings
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config

from alembic import command
from app.config import settings

DEFAULT_TEST_DB_URL = "postgresql://metaedu:dev_only_123@localhost:5432/metaedu_test"
SERVER_ROOT = Path(__file__).resolve().parents[3]
TABLE = "agent_compatibility_outputs"


def _db_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


def _run_alembic(direction: str, revision: str) -> None:
    original_url = settings.database_url
    settings.database_url = _db_url().replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
    try:
        config = Config(str(SERVER_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(SERVER_ROOT / "alembic"))
        fn = command.upgrade if direction == "upgrade" else command.downgrade
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            fn(config, revision)
    finally:
        settings.database_url = original_url


async def _table_exists() -> bool:
    connection = await asyncpg.connect(_db_url())
    try:
        return bool(
            await connection.fetchval(
                "SELECT to_regclass('metaedu.agent_compatibility_outputs')"
            )
        )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_033_compatibility_output_contract() -> None:
    assert await _table_exists()
    connection = await asyncpg.connect(_db_url())
    try:
        constraints = await connection.fetch(
            "SELECT constraint_row.conname, "
            "pg_get_constraintdef(constraint_row.oid) AS definition "
            "FROM pg_constraint constraint_row "
            "JOIN pg_class owner ON owner.oid = constraint_row.conrelid "
            "JOIN pg_namespace ns ON ns.oid = owner.relnamespace "
            "WHERE ns.nspname='metaedu' AND owner.relname=$1",
            TABLE,
        )
        definitions = {row["conname"]: row["definition"] for row in constraints}
        assert "fk_agent_compat_output_run" in definitions
        assert "ON DELETE CASCADE" in definitions["fk_agent_compat_output_run"]
        assert "conversation_id" in definitions["fk_agent_compat_output_run"]
        assert "ck_agent_compat_output_reply_size" in definitions
        assert "65536" in definitions["ck_agent_compat_output_reply_size"]
        assert "ck_agent_compat_output_envelope_size" in definitions
        assert "262144" in definitions["ck_agent_compat_output_envelope_size"]
        assert "jsonb_typeof" in definitions["ck_agent_compat_output_envelope_size"]
        indexes = await connection.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='metaedu' AND tablename=$1",
            TABLE,
        )
        assert "ix_agent_compat_output_conversation" in {
            row["indexname"] for row in indexes
        }
    finally:
        await connection.close()


def test_033_downgrade_upgrade_round_trip() -> None:
    try:
        _run_alembic("downgrade", "032_agent_run_cancel_intent")
        assert asyncio.run(_table_exists()) is False
    finally:
        _run_alembic("upgrade", "head")
    assert asyncio.run(_table_exists()) is True
