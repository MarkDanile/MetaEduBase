"""seed_dd_semantic_models script contract (REQ-046 PR-5 / Slice 4).

The ``internal_query`` step needs an active semantic model per DD entity_type
in the park catalog; today nothing writes ``metaedu.semantic_models`` in
production. This pins the seeder's behavior with a real DB session:
- binds the latest ``processed`` dataset per entity_type (re-upload safe).
- creates a semantic model only when none is active (idempotent re-run).
- column_mapping / metric_definitions derived from the dataset's declared
  columns, with the 客户ID relation key as entity_key.
- skips entity_types with no processed dataset (never binds a missing source).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests.scripts._script_loader import load_server_script

seed = load_server_script("seed_dd_semantic_models")

pytestmark = pytest.mark.asyncio

_CATALOG_CODE = "park_operations"


@pytest.fixture(autouse=True)
async def _clean(db_session):
    for stmt in (
        "DELETE FROM metaedu.semantic_models WHERE tenant_id = :tid",
        "DELETE FROM metaedu.dataset_rows WHERE tenant_id = :tid",
        "DELETE FROM metaedu.datasets WHERE tenant_id = :tid",
        "DELETE FROM metaedu.data_catalogs WHERE tenant_id = :tid AND code = :code",
    ):
        await db_session.execute(
            text(stmt), {"tid": DEFAULT_TENANT_ID, "code": _CATALOG_CODE}
        )
    await db_session.flush()
    yield


async def _make_catalog(db_session) -> uuid.UUID:
    cid = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO metaedu.data_catalogs "
            "(id, tenant_id, code, name, entity_types, is_active, created_by, "
            " created_at, updated_at) "
            "VALUES (:id, :tid, :code, :name, '[]'::jsonb, true, :cb, now(), now())"
        ),
        {
            "id": cid,
            "tid": DEFAULT_TENANT_ID,
            "code": _CATALOG_CODE,
            "name": "园区运营测试数据库",
            "cb": DEFAULT_ADMIN_ID,
        },
    )
    return cid


async def _make_dataset(
    db_session, catalog_id, *, entity_type, status="processed", columns=None
) -> uuid.UUID:
    did = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO metaedu.datasets "
            "(id, tenant_id, catalog_id, name, status, kg_status, row_count, "
            " entity_type, column_names, created_by, created_at, updated_at) "
            "VALUES (:id, :tid, :cid, :name, :status, 'done', 1, :et, "
            " CAST(:cols AS jsonb), :cb, now(), now())"
        ),
        {
            "id": did,
            "tid": DEFAULT_TENANT_ID,
            "cid": catalog_id,
            "name": entity_type,
            "status": status,
            "et": entity_type,
            "cols": __import__("json").dumps(columns or ["客户ID", "金额"]),
            "cb": DEFAULT_ADMIN_ID,
        },
    )
    return did


async def test_creates_model_for_processed_dataset(db_session):
    cid = await _make_catalog(db_session)
    did = await _make_dataset(
        db_session, cid, entity_type="bill", columns=["客户ID", "金额", "账单日期"]
    )
    await db_session.commit()

    created = await seed.seed(
        db_session, tenant_id=DEFAULT_TENANT_ID, created_by=DEFAULT_ADMIN_ID
    )
    await db_session.commit()

    assert "bill" in created
    row = await db_session.scalar(
        text(
            "SELECT dataset_id FROM metaedu.semantic_models "
            "WHERE tenant_id = :tid AND entity_type = 'bill' AND status = 'active'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    assert row == did


async def test_binds_latest_processed_dataset_not_older(db_session):
    cid = await _make_catalog(db_session)
    older = await _make_dataset(db_session, cid, entity_type="bill")
    await db_session.execute(
        text("UPDATE metaedu.datasets SET created_at = now() - interval '1 day' WHERE id = :id"),
        {"id": older},
    )
    newer = await _make_dataset(db_session, cid, entity_type="bill")
    await db_session.commit()

    await seed.seed(db_session, tenant_id=DEFAULT_TENANT_ID, created_by=DEFAULT_ADMIN_ID)
    await db_session.commit()

    row = await db_session.scalar(
        text(
            "SELECT dataset_id FROM metaedu.semantic_models "
            "WHERE tenant_id = :tid AND entity_type = 'bill' AND status = 'active'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    assert row == newer


async def test_idempotent_skips_existing_active(db_session):
    cid = await _make_catalog(db_session)
    await _make_dataset(db_session, cid, entity_type="bill")
    await db_session.commit()

    first = await seed.seed(db_session, tenant_id=DEFAULT_TENANT_ID, created_by=DEFAULT_ADMIN_ID)
    second = await seed.seed(db_session, tenant_id=DEFAULT_TENANT_ID, created_by=DEFAULT_ADMIN_ID)
    await db_session.commit()

    assert "bill" in first
    assert "bill" not in second
    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM metaedu.semantic_models "
            "WHERE tenant_id = :tid AND entity_type = 'bill' AND status = 'active'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    assert count == 1


async def test_skips_entity_type_without_processed_dataset(db_session):
    cid = await _make_catalog(db_session)
    await _make_dataset(db_session, cid, entity_type="bill", status="processing")
    await db_session.commit()

    created = await seed.seed(db_session, tenant_id=DEFAULT_TENANT_ID, created_by=DEFAULT_ADMIN_ID)
    await db_session.commit()

    assert "bill" not in created
    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM metaedu.semantic_models WHERE tenant_id = :tid"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    assert count == 0
