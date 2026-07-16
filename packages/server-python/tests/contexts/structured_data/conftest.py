"""Conftest for structured_data context.

Provides db_session + sample_dataset + sample_semantic_model + seed_rbac
fixtures.

REQ-052 Tasks 2 & 3 & 4: These fixtures back the repository, adapter, RBAC,
PII, query planner, validator and SQL guard tests in this context. They live
in the context-specific conftest so they don't pollute the global
``tests/conftest.py`` with REQ-052-only setup. The existing global fixtures
(``client``, ``auth_token``, ``auth_headers``) and the ``mock_celery_tasks``
autouse fixture from tests/conftest.py remain in effect.

Conventions:
- ``db_session`` yields an ``AsyncSession`` bound to the test DB; commits at
  end of test, rolls back on exception. Uses NullPool so each test gets a
  clean session without cross-test state in the pool.
- ``sample_dataset`` persists a ``DatasetModel`` row + a couple of JSONB rows
  so that column-scan / adapter tests have real data to work with.
- ``sample_semantic_model`` (Task 4) builds an in-memory ``SemanticModel``
  dataclass wired to ``sample_dataset``. It does NOT persist to the DB — the
  query_planner / semantic_validator / sql_guard tests operate on the
  dataclass directly and don't need round-trip JSONB serialisation.
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

from app.contexts.structured_data.domain.semantic_model import (
    ColumnMapping,
    ColumnRole,
    ColumnType,
    DataSourceType,
    MetricDefinition,
    SemanticModel,
)
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
    # Resolve the default education catalog for the tenant so the NOT NULL
    # catalog_id column (REQ-054 migration 018) is satisfied. The catalog is
    # seeded by alembic 018 for every tenant that exists in the DB.
    catalog_row = await db_session.execute(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = 'education'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    catalog_id = catalog_row.scalar_one()
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
            f"(id, tenant_id, catalog_id, name, description, column_names, column_types, "
            f"row_count, source_file, tags, status, kg_status, sort_order, "
            f"created_by, created_at, updated_at) "
            f"VALUES (:id, :tid, :cid, :name, :desc, '{cnames_literal}'::jsonb, "
            f"'{ctypes_literal}'::jsonb, :rcount, NULL, NULL, 'uploaded', "
            f"'pending', 0, :uid, :now, :now)"
        ),
        {
            "id": dataset_id,
            "tid": DEFAULT_TENANT_ID,
            "cid": catalog_id,
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
async def sample_dataset_with_rows(db_session):
    """Persist a ``DatasetModel`` + 5 ``DatasetRowModel`` rows for filter tests.

    REQ-056 Task 1: the end-to-end filtering test needs a dataset whose rows
    have a distinguishable ``company_name`` distribution so that applying a
    filter changes the result count. Five rows are inserted with
    ``company_name`` in ``{A, A, B, B, C}`` (2 × A, 2 × B, 1 × C) and
    monotonically increasing ``billing_date`` so ``time_range`` narrowing is
    also observable. Mirrors ``sample_dataset`` but with a richer row set.
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
            f"(id, tenant_id, catalog_id, name, description, column_names, column_types, "
            f"row_count, source_file, tags, status, kg_status, sort_order, "
            f"created_by, created_at, updated_at) "
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


@pytest_asyncio.fixture
async def sample_semantic_model(sample_dataset):
    """Build an in-memory :class:`SemanticModel` wired to ``sample_dataset``.

    REQ-052 Task 4: the Query Planner / Semantic Validator / SQL Guard tests
    consume the dataclass form directly (no DB round-trip) so this fixture
    just constructs the dataclass with a representative schema for the bill
    entity. Mirrors the helper used in
    ``test_semantic_model_repository._make_semantic_model`` but as a
    context-level fixture so all Task 4 tests can reuse it.

    Columns chosen to exercise the key validator branches:

    - ``company_name`` (entity_key, str) — used by query_plan filters and
      SqlGuard visibility checks.
    - ``amount`` (metric, float, sensitive) — used by metric aggregations
      and PII masking tests.
    - ``billing_date`` (filter, date) — used by query_plan time_range and
      filter tests.

    Metric ``total_amount`` (``SUM(amount)``) covers the metric-validation
    branch of the validator. Tenant and dataset ids both come from the
    default seed so the model satisfies any FK the test DB enforces.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=sample_dataset["tenant_id"],
        dataset_id=sample_dataset["id"],
        entity_type="bill",
        entity_name="账单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(sample_dataset["id"]),
        },
        column_mapping={
            "company_name": ColumnMapping(
                role=ColumnRole.ENTITY_KEY,
                type=ColumnType.STR,
                sensitive=False,
                synonym=["企业名称"],
            ),
            "amount": ColumnMapping(
                role=ColumnRole.METRIC,
                type=ColumnType.FLOAT,
                sensitive=True,
                synonym=["金额"],
            ),
            "billing_date": ColumnMapping(
                role=ColumnRole.FILTER,
                type=ColumnType.DATE,
                sensitive=False,
                synonym=["账单日期"],
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
            "unpaid_amount": MetricDefinition(
                column="amount", aggregation="sum", label="欠费金额"
            ),
        },
        version="v1",
        status="active",
        created_by=DEFAULT_ADMIN_ID,
        created_at=now,
        updated_at=now,
    )
    yield model
