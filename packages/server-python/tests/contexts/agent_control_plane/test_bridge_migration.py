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


async def _bridge_schema() -> tuple[set[tuple[str, str]], set[str], set[str]]:
    connection = await asyncpg.connect(_db_url())
    try:
        columns = await connection.fetch(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='metaedu' AND table_name = ANY($1::text[]) "
            "AND column_name = ANY($2::text[])",
            ["agent_workspace_outbox", "agent_execution_outbox"],
            [
                "payload_inline",
                "decision_actor_id",
                "decision_reason",
                "decision_digest",
                "decided_at",
            ],
        )
        indexes = await connection.fetch(
            "SELECT indexname FROM pg_indexes WHERE schemaname='metaedu' "
            "AND indexname = ANY($1::text[])",
            ["uq_agent_ws_outbox_turn", "uq_agent_exec_outbox_publish"],
        )
        constraints = await connection.fetch(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE constraint_schema='metaedu' "
            "AND constraint_name = ANY($1::text[])",
            [
                "ck_agent_ws_outbox_payload",
                "ck_agent_exec_outbox_payload",
                "ck_agent_exec_outbox_decision",
            ],
        )
        return (
            {(row["table_name"], row["column_name"]) for row in columns},
            {row["indexname"] for row in indexes},
            {row["constraint_name"] for row in constraints},
        )
    finally:
        await connection.close()


async def _insert_durable_inline_payload() -> None:
    connection = await asyncpg.connect(_db_url())
    try:
        await connection.execute(
            "INSERT INTO metaedu.agent_workspace_outbox "
            "(id, tenant_id, event_type, schema_version, aggregate_id, "
            "aggregate_type, payload_inline, payload_ref, payload_digest, "
            "correlation_id, status, attempt_count, next_attempt_at, created_at) "
            "VALUES ($1, $2, 'turn.requested.v1', 1, $3, "
            "'workspace.message', $4::jsonb, NULL, $5, $6, "
            "'pending', 0, now(), now())",
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            '{"schema_version":1}',
            "a" * 64,
            uuid.uuid4(),
        )
    finally:
        await connection.close()


async def _clear_durable_inline_payload() -> None:
    connection = await asyncpg.connect(_db_url())
    try:
        await connection.execute("DELETE FROM metaedu.agent_workspace_outbox")
    finally:
        await connection.close()


def test_031_schema_and_downgrade_upgrade_round_trip():
    expected_columns = {
        ("agent_workspace_outbox", "payload_inline"),
        ("agent_execution_outbox", "payload_inline"),
        ("agent_execution_outbox", "decision_actor_id"),
        ("agent_execution_outbox", "decision_reason"),
        ("agent_execution_outbox", "decision_digest"),
        ("agent_execution_outbox", "decided_at"),
    }
    expected_indexes = {
        "uq_agent_ws_outbox_turn",
        "uq_agent_exec_outbox_publish",
    }
    expected_constraints = {
        "ck_agent_ws_outbox_payload",
        "ck_agent_exec_outbox_payload",
        "ck_agent_exec_outbox_decision",
    }
    assert asyncio.run(_bridge_schema()) == (
        expected_columns,
        expected_indexes,
        expected_constraints,
    )
    asyncio.run(_insert_durable_inline_payload())
    with pytest.raises(RuntimeError, match="durable inline integration payloads"):
        _run_alembic("downgrade", "030_agent_execution_durable_core")
    assert asyncio.run(_bridge_schema()) == (
        expected_columns,
        expected_indexes,
        expected_constraints,
    )
    asyncio.run(_clear_durable_inline_payload())
    try:
        _run_alembic("downgrade", "030_agent_execution_durable_core")
        assert asyncio.run(_bridge_schema()) == (set(), set(), set())
    finally:
        _run_alembic("upgrade", "head")
    assert asyncio.run(_bridge_schema()) == (
        expected_columns,
        expected_indexes,
        expected_constraints,
    )
