"""Verify alembic migrations 012-015 create expected schema.

REQ-052 Task 1 schema baseline smoke test. Confirms that all four REQ-052
tables exist in the ``metaedu`` schema after ``alembic upgrade head`` and that
the JSONB columns used by downstream tasks are present.
"""
from __future__ import annotations

import os

import asyncpg
import pytest

DEFAULT_TEST_DB_URL = (
    "postgresql://metaedu:dev_only_123@localhost:5432/metaedu_test"
)

REQ_052_TABLES = (
    "semantic_models",
    "role_permissions",
    "tenant_access_grants",
    "query_audit_log",
)

# JSONB columns the plan calls out for downstream tasks (semantic mapping +
# RBAC visibility rules + query plan).
EXPECTED_JSONB_COLUMNS = {
    "semantic_models": (
        "data_source_config",
        "column_mapping",
        "metric_definitions",
    ),
    "role_permissions": ("visibility_rules",),
    "query_audit_log": ("query_plan",),
}


def _db_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


@pytest.mark.asyncio
async def test_alembic_012_015_create_schema():
    """4 张表都创建成功 + JSONB 列定义正确。"""
    db_url = _db_url()
    conn = await asyncpg.connect(db_url)
    try:
        # Version stamp must reflect the current repository head.
        version = await conn.fetchval(
            "SELECT version_num FROM metaedu.alembic_version"
        )
        assert version == "039_run_event_tombstone_guard", (
            f"alembic head should be 039_run_event_tombstone_guard, got {version!r}"
        )

        # All 4 tables must exist.
        for table in REQ_052_TABLES:
            exists = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='metaedu' AND table_name=$1)",
                table,
            )
            assert exists, f"Table metaedu.{table} not found"

        # JSONB columns per table.
        for table, cols in EXPECTED_JSONB_COLUMNS.items():
            rows = await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='metaedu' AND table_name=$1",
                table,
            )
            actual = {r["column_name"]: r["data_type"] for r in rows}
            for col in cols:
                assert col in actual, f"{table}.{col} column missing"
                assert actual[col] == "jsonb", (
                    f"{table}.{col} should be jsonb, got {actual[col]!r}"
                )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_alembic_012_015_indexes_exist():
    """Named indexes from the migrations are present on the test DB."""
    db_url = _db_url()
    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='metaedu' AND tablename = ANY($1::text[])",
            list(REQ_052_TABLES),
        )
        names = {r["indexname"] for r in rows}
        expected = {
            "ix_semantic_models_dataset",
            "ix_tenant_access_grants_grantee",
            "ix_query_audit_log_tenant_created",
            "ix_query_audit_log_user_created",
        }
        missing = expected - names
        assert not missing, f"Missing indexes: {sorted(missing)}"
    finally:
        await conn.close()
