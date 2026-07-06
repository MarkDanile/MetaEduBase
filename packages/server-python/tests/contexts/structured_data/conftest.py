"""Conftest for structured_data context — db_session + sample_dataset + seed_rbac fixtures.

REQ-052 Tasks 2 & 3: These fixtures back the repository, adapter, RBAC and PII
tests in this context. They live in the context-specific conftest so they
don't pollute the global tests/conftest.py with REQ-052-only setup. The
existing global fixtures (``client``, ``auth_token``, ``auth_headers``) and
the ``mock_celery_tasks`` autouse fixture from tests/conftest.py remain in
effect.

Conventions:
- ``db_session`` yields an ``AsyncSession`` bound to the test DB; commits at
  end of test, rolls back on exception. Uses NullPool so each test gets a
  clean session without cross-test state in the pool.
- ``sample_dataset`` persists a ``DatasetModel`` row + a couple of JSONB rows
  so that column-scan / adapter tests have real data to work with.
- ``seed_rbac`` (Task 3) inserts per-role visibility_rules for ``bill``
  entity_type into ``metaedu.role_permissions`` so that the field-level RBAC
  tests can observe different visibility outcomes per role without each test
  having to hand-insert rules.
- All fixtures default to the seeded ``DEFAULT_TENANT_ID`` so we satisfy any
  FK that the test DB enforces.
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


@pytest_asyncio.fixture
async def seed_rbac(db_session):
    """Insert per-role visibility_rules into ``metaedu.role_permissions``.

    REQ-052 Task 3: provides the seed data that the RBAC tests assume. The
    fixture is idempotent — it deletes any existing rows for the
    ``(tenant_id, role, entity_type)`` tuples it manages before inserting,
    so the test suite stays order-independent even though ``db_session``
    commits at end-of-test.

    The matrix is intentionally a partial subset: 2 roles (manager + leader)
    with two fields (``amount`` + ``company_name``) on entity_type
    ``bill``. Other roles (employee, data_admin, auditor) have no row in
    this fixture, which lets the service's strict-default (MASKED) path be
    tested naturally.

    Visibility choices:
    - manager can see ``amount`` (VISIBLE) but ``company_name`` is MASKED
      to verify per-field granularity.
    - leader can see both (VISIBLE) — full read access at leader level.

    Each test that needs different per-entity rules can write its own INSERT
    with a unique ``entity_type`` and clean up explicitly, or use the
    ``cleanup_rbac`` fixture for ergonomic teardown.
    """
    # Idempotent: clear prior rows for these (tenant, role, entity) tuples
    # so re-running a test doesn't trip the uq_role_permissions_... index.
    await db_session.execute(
        text(
            "DELETE FROM metaedu.role_permissions WHERE tenant_id = :tid "
            "AND role IN ('manager', 'leader') AND entity_type = 'bill'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    # Also clear tenant grants + audit log so each test starts from a
    # clean slate for cross-tenant + audit tests.
    await db_session.execute(
        text("DELETE FROM metaedu.tenant_access_grants WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.execute(
        text("DELETE FROM metaedu.query_audit_log WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.flush()

    now = datetime.now(UTC).replace(tzinfo=None)

    # manager: amount VISIBLE, company_name MASKED
    manager_rules = json.dumps({"amount": "visible", "company_name": "masked"})
    await db_session.execute(
        text(
            f"INSERT INTO metaedu.role_permissions "
            f"(id, tenant_id, role, entity_type, visibility_rules, created_at) "
            f"VALUES (:id, :tid, 'manager', 'bill', '{manager_rules}'::jsonb, :now)"
        ),
        {"id": uuid.uuid4(), "tid": DEFAULT_TENANT_ID, "now": now},
    )

    # leader: both fields VISIBLE
    leader_rules = json.dumps({"amount": "visible", "company_name": "visible"})
    await db_session.execute(
        text(
            f"INSERT INTO metaedu.role_permissions "
            f"(id, tenant_id, role, entity_type, visibility_rules, created_at) "
            f"VALUES (:id, :tid, 'leader', 'bill', '{leader_rules}'::jsonb, :now)"
        ),
        {"id": uuid.uuid4(), "tid": DEFAULT_TENANT_ID, "now": now},
    )

    await db_session.flush()
    yield {
        "tenant_id": DEFAULT_TENANT_ID,
        "manager_rules": {"amount": "visible", "company_name": "masked"},
        "leader_rules": {"amount": "visible", "company_name": "visible"},
    }
