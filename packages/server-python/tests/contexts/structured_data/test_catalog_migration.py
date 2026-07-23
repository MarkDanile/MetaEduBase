"""Verify REQ-054 alembic migrations 016-018 create catalog schema + default catalog."""
from __future__ import annotations

import os

import asyncpg
import pytest


@pytest.mark.asyncio
async def test_016_018_create_catalog_schema_and_default():
    """data_catalogs 表创建 + 4 表 catalog_id FK + 默认 education 库回填."""
    db_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://metaedu:dev_only_123@localhost:5432/metaedu_test",
    ).replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(db_url)
    try:
        # data_catalogs 表存在 + 列正确
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='metaedu' AND table_name='data_catalogs' "
            "ORDER BY ordinal_position"
        )
        col_names = {r["column_name"] for r in cols}
        assert "code" in col_names
        assert "entity_types" in col_names
        assert "is_active" in col_names
        assert "tenant_id" in col_names

        # datasets.catalog_id 存在 + NOT NULL
        ds_nullable = await conn.fetchval(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema='metaedu' AND table_name='datasets' "
            "AND column_name='catalog_id'"
        )
        assert ds_nullable == "NO"  # NOT NULL after 018

        # semantic_models.catalog_id NOT NULL
        sm_nullable = await conn.fetchval(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema='metaedu' AND table_name='semantic_models' "
            "AND column_name='catalog_id'"
        )
        assert sm_nullable == "NO"

        # knowledge_nodes.catalog_id 存在（nullable 标签）
        kn_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='metaedu' AND table_name='knowledge_nodes' "
            "AND column_name='catalog_id')"
        )
        assert kn_exists

        # query_audit_log.catalog_id 存在
        al_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='metaedu' AND table_name='query_audit_log' "
            "AND column_name='catalog_id')"
        )
        assert al_exists

        # 新唯一约束存在
        new_constraint = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_schema='metaedu' AND table_name='semantic_models' "
            "AND constraint_name='uq_semantic_models_tenant_catalog_entity_datasource')"
        )
        assert new_constraint

        # 默认 education 库存在
        catalog_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM metaedu.data_catalogs WHERE code='education')"
        )
        assert catalog_exists

        # 现有 datasets 全部有 catalog_id（回填验证）
        null_count = await conn.fetchval(
            "SELECT COUNT(*) FROM metaedu.datasets WHERE catalog_id IS NULL"
        )
        assert null_count == 0
    finally:
        await conn.close()
