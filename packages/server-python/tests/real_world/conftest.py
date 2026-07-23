"""Conftest for tests/real_world/.

Mirrors the db_session + sample_dataset fixtures from
``tests/contexts/structured_data/conftest.py`` so the REQ-056 real-world
samples can run as a standalone test file without depending on the
structured_data context's local conftest. The structured_data conftest
is intentionally NOT exported to sibling directories (it is rooted at
``tests/contexts/structured_data/``); pytest only walks upwards from the
test file until it finds a conftest.py, then stops — so the real_world
tests must provide their own session-level fixture.

REQ-056 Task 5: AC-6 + AC-7 end-to-end. The fixtures here are intentionally
minimal — only what's needed to drive 10 business samples against the real
PostgreSQL test DB.
"""

from __future__ import annotations

import pytest



import json
import uuid
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests.conftest import DEFAULT_TEST_DB_URL


@pytest_asyncio.fixture
async def db_session():
    """AsyncSession against the test DB.

    Commits on clean teardown, rolls back on exception. Uses ``NullPool``
    so each test gets a fresh connection (matches the pattern used by
    ``tests/contexts/structured_data/conftest.py:db_session``).
    """
    engine = create_async_engine(DEFAULT_TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await engine.dispose()


@pytest_asyncio.fixture
async def sample_dataset_with_rows(db_session):
    """Persist a dataset + 5 JSONB rows for ``bill`` filter testing.

    Mirrors the helper in
    ``tests/contexts/structured_data/conftest.py:sample_dataset_with_rows``
    so the real-world test file is self-contained. Rows are
    ``(A,A,B,B,C)`` so filter predicates are observable.
    """
    dataset_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    catalog_row = await db_session.execute(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = 'education'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    catalog_id = catalog_row.scalar_one()
    cnames_literal = json.dumps(["company_name", "amount", "billing_date"])
    ctypes_literal = json.dumps(["str", "float", "date"])
    await db_session.execute(
        text(
            f"INSERT INTO metaedu.datasets "
            f"(id, tenant_id, catalog_id, name, description, column_names, "
            f"column_types, row_count, source_file, tags, status, kg_status, "
            f"sort_order, created_by, created_at, updated_at) "
            f"VALUES (:id, :tid, :cid, :name, :desc, '{cnames_literal}'::jsonb, "
            f"'{ctypes_literal}'::jsonb, :rcount, NULL, NULL, 'uploaded', "
            f"'pending', 0, :uid, :now, :now)"
        ),
        {
            "id": dataset_id,
            "tid": DEFAULT_TENANT_ID,
            "cid": catalog_id,
            "name": "bill-filter-dataset",
            "desc": "5-row dataset for REQ-056 filtering tests",
            "rcount": 5,
            "uid": DEFAULT_ADMIN_ID,
            "now": now,
        },
    )

    rows = [
        {"company_name": "A", "amount": 10.0, "billing_date": "2026-01-01"},
        {"company_name": "A", "amount": 20.0, "billing_date": "2026-02-01"},
        {"company_name": "B", "amount": 30.0, "billing_date": "2026-03-01"},
        {"company_name": "B", "amount": 40.0, "billing_date": "2026-04-01"},
        {"company_name": "C", "amount": 50.0, "billing_date": "2026-05-01"},
    ]
    for i, payload in enumerate(rows):
        payload_literal = json.dumps(payload)
        await db_session.execute(
            text(
                f"INSERT INTO metaedu.dataset_rows "
                f"(id, tenant_id, dataset_id, row_index, data, created_at) "
                f"VALUES (:id, :tid, :did, :idx, '{payload_literal}'::jsonb, :now)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": DEFAULT_TENANT_ID,
                "did": dataset_id,
                "idx": i,
                "now": now,
            },
        )
    await db_session.flush()
    yield {"id": dataset_id, "tenant_id": DEFAULT_TENANT_ID}
