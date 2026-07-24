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

DEFAULT_TEST_DB_URL = (
    "postgresql://metaedu:dev_only_123@localhost:5432/metaedu_test"
)
SERVER_ROOT = Path(__file__).resolve().parents[3]
TABLES = {
    "agent_definition_versions",
    "agent_runtime_profiles",
    "agent_runtime_session_bindings",
}


def _db_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


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


async def _existing_tables() -> set[str]:
    connection = await asyncpg.connect(_db_url())
    try:
        rows = await connection.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='metaedu' AND table_name = ANY($1::text[])",
            list(TABLES),
        )
        return {row["table_name"] for row in rows}
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_029_schema_indexes_triggers_and_context_local_foreign_keys():
    assert await _existing_tables() == TABLES
    connection = await asyncpg.connect(_db_url())
    try:
        indexes = await connection.fetch(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname='metaedu' AND tablename = ANY($1::text[])",
            list(TABLES),
        )
        index_defs = {row["indexname"]: row["indexdef"] for row in indexes}
        assert "uq_agent_definition_key_version" in index_defs
        assert "uq_agent_runtime_profile_key" in index_defs
        assert "uq_agent_runtime_binding_session_ref" in index_defs
        assert "WHERE" in index_defs["uq_agent_runtime_binding_session_ref"]
        assert "ix_agent_runtime_binding_stream_lease" in index_defs

        referenced = await connection.fetch(
            "SELECT owner.relname AS owner_table, referenced.relname AS referenced_table "
            "FROM pg_constraint constraint_row "
            "JOIN pg_class owner ON owner.oid = constraint_row.conrelid "
            "JOIN pg_namespace owner_ns ON owner_ns.oid = owner.relnamespace "
            "JOIN pg_class referenced ON referenced.oid = constraint_row.confrelid "
            "WHERE constraint_row.contype='f' AND owner_ns.nspname='metaedu' "
            "AND owner.relname = ANY($1::text[])",
            list(TABLES),
        )
        assert {
            (row["owner_table"], row["referenced_table"]) for row in referenced
        } == {("agent_runtime_session_bindings", "agent_runtime_profiles")}

        triggers = await connection.fetch(
            "SELECT trigger_name FROM information_schema.triggers "
            "WHERE event_object_schema='metaedu' "
            "AND event_object_table = ANY($1::text[])",
            list(TABLES),
        )
        assert {row["trigger_name"] for row in triggers} == {
            "trg_agent_definition_version_immutable",
            "trg_agent_runtime_binding_profile",
            "trg_agent_runtime_profile_immutable",
        }

        timestamp_type = await connection.fetchval(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema='metaedu' "
            "AND table_name='agent_runtime_session_bindings' "
            "AND column_name='stream_lease_expires_at'"
        )
        assert timestamp_type == "timestamp with time zone"
    finally:
        await connection.close()


def test_029_downgrade_upgrade_round_trip():
    try:
        _run_alembic("downgrade", "028_agent_workspace_store")
        assert asyncio.run(_existing_tables()) == set()
    finally:
        _run_alembic("upgrade", "head")
    assert asyncio.run(_existing_tables()) == TABLES
