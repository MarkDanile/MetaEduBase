"""Conftest for structured_data context — db_session + sample_dataset fixtures.

REQ-052 Task 2: These fixtures back the repository and adapter tests in this
context. They live in the context-specific conftest so they don't pollute the
global tests/conftest.py with REQ-052-only setup. The existing global fixtures
(``client``, ``auth_token``, ``auth_headers``) and the ``mock_celery_tasks``
autouse fixture from tests/conftest.py remain in effect.

Conventions:
- ``db_session`` yields an ``AsyncSession`` bound to the test DB; commits at
  end of test, rolls back on exception. Uses NullPool so each test gets a
  clean session without cross-test state in the pool.
- ``sample_dataset`` persists a ``DatasetModel`` row + a couple of JSONB rows
  so that column-scan / adapter tests have real data to work with.
- Both fixtures default to the seeded ``DEFAULT_TENANT_ID`` so we satisfy
  any FK that the test DB enforces.
"""

from __future__ import annotations

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
    """Yield an ``AsyncSession`` against the test DB.

    Commits on clean teardown, rolls back on test error. Uses ``NullPool``
    so that the session's connection is closed at end-of-test — matches
    the pattern used by tests/conftest.py's ``client`` fixture.
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
async def sample_dataset(db_session):
    """Persist a ``DatasetModel`` + a few ``DatasetRowModel`` rows for tests.

    Uses the seeded ``DEFAULT_TENANT_ID`` / ``DEFAULT_ADMIN_ID`` so the row
    conforms to any FK that may be added in later migrations. Two JSONB
    rows with overlapping keys are inserted so that ``scan_dataset_columns``
    / ``ImportedDatasetAdapter.query`` tests have meaningful data.
    """
    dataset_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    # Note: we splice JSON strings directly into the SQL rather than binding
    # them, because asyncpg's parameter style is positional ($1, $2, ...) and
    # using ``:cnames::jsonb`` would clash with SQLAlchemy's named-to-positional
    # rebinding. Inline literals are safe here: the values are deterministic
    # and come from this fixture, not from user input.
    cnames_literal = json.dumps(["company_name", "amount", "billing_date"])
    ctypes_literal = json.dumps(["str", "float", "date"])
    await db_session.execute(
        text(
            f"INSERT INTO metaedu.datasets "
            f"(id, tenant_id, name, description, column_names, column_types, "
            f"row_count, source_file, tags, status, kg_status, sort_order, "
            f"created_by, created_at, updated_at) "
            f"VALUES (:id, :tid, :name, :desc, '{cnames_literal}'::jsonb, "
            f"'{ctypes_literal}'::jsonb, :rcount, NULL, NULL, 'uploaded', "
            f"'pending', 0, :uid, :now, :now)"
        ),
        {
            "id": dataset_id,
            "tid": DEFAULT_TENANT_ID,
            "name": "bill-test-dataset",
            "desc": "sample dataset for REQ-052 tests",
            "rcount": 2,
            "uid": DEFAULT_ADMIN_ID,
            "now": now,
        },
    )

    for i, payload in enumerate(
        [
            {"company_name": "ACME", "amount": 100.0, "billing_date": "2026-01-01"},
            {"company_name": "BetaCorp", "amount": 50.5, "billing_date": "2026-02-01"},
        ]
    ):
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
