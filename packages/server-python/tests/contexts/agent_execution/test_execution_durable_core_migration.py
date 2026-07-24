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
    "agent_runs",
    "agent_turn_inputs",
    "agent_run_events",
    "agent_execution_inbox",
    "agent_execution_outbox",
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
async def test_030_schema_indexes_trigger_and_context_local_foreign_keys():
    assert await _existing_tables() == TABLES
    connection = await asyncpg.connect(_db_url())
    try:
        indexes = await connection.fetch(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname='metaedu' AND tablename = ANY($1::text[])",
            list(TABLES),
        )
        index_defs = {row["indexname"]: row["indexdef"] for row in indexes}
        assert "uq_agent_run_one_active" in index_defs
        assert "WHERE" in index_defs["uq_agent_run_one_active"]
        assert "uq_agent_run_event_runtime_seq" in index_defs
        assert "uq_agent_run_event_runtime_id" in index_defs
        assert "uq_agent_run_event_terminal" in index_defs
        assert "uq_agent_turn_input_root" in index_defs
        assert "ix_agent_run_recovery" in index_defs
        assert "ix_agent_exec_inbox_status" in index_defs
        assert "ix_agent_exec_outbox_dispatch" in index_defs

        referenced = await connection.fetch(
            "SELECT constraint_row.conname, owner.relname AS owner_table, "
            "referenced.relname AS referenced_table "
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
        } == {
            ("agent_runs", "agent_definition_versions"),
            ("agent_runs", "agent_runtime_profiles"),
            ("agent_runs", "agent_runtime_session_bindings"),
            ("agent_runs", "agent_runs"),
            ("agent_turn_inputs", "agent_runs"),
            ("agent_run_events", "agent_runs"),
            ("agent_run_events", "agent_runtime_profiles"),
            ("agent_run_events", "agent_runtime_session_bindings"),
        }
        assert {
            "fk_agent_run_binding_owner",
            "fk_agent_run_event_conversation",
            "fk_agent_run_event_owner",
            "fk_agent_run_event_runtime_owner",
        }.issubset({row["conname"] for row in referenced})

        triggers = await connection.fetch(
            "SELECT trigger_name FROM information_schema.triggers "
            "WHERE event_object_schema='metaedu' "
            "AND event_object_table='agent_run_events'"
        )
        assert {row["trigger_name"] for row in triggers} == {
            "trg_agent_run_event_append_only"
        }

        terminal_output_constraint = await connection.fetchval(
            "SELECT pg_get_constraintdef(constraint_row.oid) "
            "FROM pg_constraint constraint_row "
            "JOIN pg_class owner ON owner.oid = constraint_row.conrelid "
            "JOIN pg_namespace owner_ns ON owner_ns.oid = owner.relnamespace "
            "WHERE owner_ns.nspname='metaedu' AND owner.relname='agent_runs' "
            "AND constraint_row.conname='ck_agent_run_terminal_output'"
        )
        assert "terminal_output_ref" in terminal_output_constraint
        assert "terminal_output_media_type" in terminal_output_constraint
        assert terminal_output_constraint.count("> 0") == 2
        assert "position" in terminal_output_constraint.lower()
        assert "> 1" in terminal_output_constraint
        assert "char_length" in terminal_output_constraint

        runtime_provenance_constraint = await connection.fetchval(
            "SELECT pg_get_constraintdef(constraint_row.oid) "
            "FROM pg_constraint constraint_row "
            "JOIN pg_class owner ON owner.oid = constraint_row.conrelid "
            "JOIN pg_namespace owner_ns ON owner_ns.oid = owner.relnamespace "
            "WHERE owner_ns.nspname='metaedu' "
            "AND owner.relname='agent_run_events' "
            "AND constraint_row.conname='ck_agent_run_event_runtime_provenance'"
        )
        assert "runtime_epoch IS NOT NULL" in runtime_provenance_constraint
        assert "runtime_seq IS NOT NULL" in runtime_provenance_constraint
        assert "runtime_event_digest IS NOT NULL" in runtime_provenance_constraint
    finally:
        await connection.close()


def test_030_downgrade_upgrade_round_trip():
    try:
        _run_alembic("downgrade", "029_agent_execution_identity")
        assert asyncio.run(_existing_tables()) == set()
    finally:
        _run_alembic("upgrade", "head")
    assert asyncio.run(_existing_tables()) == TABLES
