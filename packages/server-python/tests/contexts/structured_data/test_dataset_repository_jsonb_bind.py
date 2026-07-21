"""DatasetRepository JSONB binding regression (REQ-046 PR-4)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.contexts.structured_data.infrastructure.dataset_repository import (
    DatasetRepository,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio


async def test_bulk_insert_rows_binds_jsonb_with_asyncpg(db_session):
    dataset_id = uuid.uuid4()
    now = await db_session.scalar(text("SELECT now() AT TIME ZONE 'UTC'"))
    catalog_id = await db_session.scalar(
        text(
            "SELECT id FROM metaedu.data_catalogs WHERE tenant_id = :tid "
            "ORDER BY created_at LIMIT 1"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    assert catalog_id is not None
    await db_session.execute(
        text(
            "INSERT INTO metaedu.datasets "
            "(id, tenant_id, catalog_id, name, status, kg_status, row_count, "
            "sort_order, created_by, created_at, updated_at) VALUES "
            "(:id, :tid, :cid, :name, 'processed', 'pending', 0, 0, "
            ":uid, :now, :now)"
        ),
        {
            "id": dataset_id,
            "tid": DEFAULT_TENANT_ID,
            "cid": catalog_id,
            "name": f"req046-jsonb-{dataset_id.hex[:8]}",
            "uid": DEFAULT_ADMIN_ID,
            "now": now,
        },
    )
    marker = f"req046-{uuid.uuid4().hex}"

    repo = DatasetRepository(db_session)
    await repo.bulk_insert_rows(
        DEFAULT_TENANT_ID,
        dataset_id,
        [{"req046_marker": marker}],
    )
    assert await repo.count_rows(dataset_id, DEFAULT_TENANT_ID) == 1

    await repo.delete_rows(dataset_id, DEFAULT_TENANT_ID)
    await repo.delete(dataset_id, DEFAULT_TENANT_ID)
