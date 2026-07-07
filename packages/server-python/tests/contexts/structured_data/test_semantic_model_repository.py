"""Test semantic model repository CRUD + column scan + drift detection.

REQ-052 Task 2. RED → GREEN: each test covers a behaviour of
:class:`SemanticModelRepository` against the real test PostgreSQL DB. The
fixtures (``db_session``, ``sample_dataset``) are provided by
``tests/contexts/structured_data/conftest.py``.

REQ-054 Task 5: the same test file now also exercises the new
``get_active_by_catalog_and_entity_type`` dual-key lookup. Each
persistence call resolves the seeded ``education`` catalog for
``DEFAULT_TENANT_ID`` and passes it explicitly to ``repo.create`` — auto-
resolve was removed in Task 5.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.contexts.structured_data.domain.semantic_model import (
    ColumnMapping,
    ColumnRole,
    ColumnType,
    DataSourceType,
    MetricDefinition,
    SemanticModel,
)
from app.contexts.structured_data.infrastructure.semantic_model_repository import (
    SemanticModelRepository,
)
from app.contexts.structured_data.infrastructure.semantic_models_models import (
    SemanticModelModel,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _clean_semantic_models(db_session):
    """Clear ``metaedu.semantic_models`` for ``DEFAULT_TENANT_ID`` before
    each test.

    REQ-054 Task 5: the new ``get_active_by_catalog_and_entity_type``
    lookup is dual-key, not triple-key — it does NOT filter by
    ``data_source_config``. As soon as two tests persist a row with the
    same ``(catalog_id, entity_type='bill')`` pair, the second
    ``scalar_one_or_none()`` raises ``MultipleResultsFound``.

    The pre-existing test suite didn't hit this because the original
    lookups were always triple-key (with ``data_source_config`` in the
    WHERE clause). The new method's coverage demands a clean slate, so
    this autouse fixture wipes the table at the start of each test.

    The fixture runs after ``db_session`` (alphabetical order) but
    before the test body — pytest_asyncio's standard ``function``
    scope gives us that ordering for free.
    """
    await db_session.execute(
        text(
            "DELETE FROM metaedu.semantic_models WHERE tenant_id = :tid"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.flush()
    yield


@pytest_asyncio.fixture
async def education_catalog_id(db_session) -> uuid.UUID:
    """Yield the seeded ``education`` catalog id for ``DEFAULT_TENANT_ID``.

    REQ-054 migration 018 guarantees every tenant has exactly one
    ``education`` catalog; tests use it as the default ``catalog_id``
    for the ``bill`` entity. The fixture resolves the id once per test
    so the test body never has to repeat the lookup boilerplate.
    """
    row = await db_session.execute(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = 'education'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    return row.scalar_one()


@pytest_asyncio.fixture
async def second_catalog_id(db_session) -> uuid.UUID:
    """Yield a second catalog for the same tenant, used to exercise
    ``(catalog_id, entity_type)`` dual-key routing.

    The catalog is inserted with a unique code (``hr_test_catalog``)
    scoped to ``DEFAULT_TENANT_ID``; it's cleaned up at the start of
    each test so the fixture is order-independent. This mirrors the
    pattern used by ``sample_dataset`` (which also resolves catalog_id
    via a fresh lookup each call) and avoids cross-test pollution.
    """
    # Idempotent cleanup: the catalog may already exist from a previous
    # test run.
    await db_session.execute(
        text(
            "DELETE FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = 'hr_test_catalog'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    new_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            "INSERT INTO metaedu.data_catalogs "
            "(id, tenant_id, code, name, description, is_active, "
            "created_by, created_at, updated_at) "
            "VALUES (:id, :tid, 'hr_test_catalog', 'HR Test', "
            "'second catalog for dual-key routing tests', true, :uid, :now, :now)"
        ),
        {"id": new_id, "tid": DEFAULT_TENANT_ID, "uid": DEFAULT_ADMIN_ID, "now": now},
    )
    await db_session.flush()
    return new_id


def _make_semantic_model(
    sample_dataset_id: uuid.UUID,
    catalog_id: uuid.UUID,
    entity_type: str = "bill",
    entity_name: str = "账单",
) -> SemanticModel:
    """Build a fully-populated SemanticModel for tests.

    Registers all three columns that ``sample_dataset`` actually contains
    (company_name / amount / billing_date) so tests that don't care about
    drift see a baseline with zero new / zero removed columns.

    REQ-054: ``catalog_id`` is now a required positional argument — the
    auto-resolve to ``education`` was removed in Task 5, and tests must
    pass the catalog id explicitly. ``entity_type`` / ``entity_name`` are
    kept as keyword args with the historical defaults so the existing
    8 tests don't have to change their intent.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    return SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        catalog_id=catalog_id,
        dataset_id=sample_dataset_id,
        entity_type=entity_type,
        entity_name=entity_name,
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(sample_dataset_id),
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
        },
        version="v1",
        status="active",
        created_by=DEFAULT_ADMIN_ID,
        created_at=now,
        updated_at=now,
    )


async def test_create_and_get_semantic_model(
    db_session, sample_dataset, education_catalog_id
):
    repo = SemanticModelRepository(db_session)
    model = _make_semantic_model(sample_dataset["id"], education_catalog_id)

    await repo.create(model, catalog_id=education_catalog_id)
    await db_session.commit()

    got = await repo.get_by_entity_type(
        tenant_id=model.tenant_id,
        entity_type="bill",
        data_source_config=model.data_source_config,
    )

    assert got is not None
    assert got.entity_type == "bill"
    assert got.catalog_id == education_catalog_id
    assert got.dataset_id == sample_dataset["id"]
    assert got.column_mapping["company_name"].role == ColumnRole.ENTITY_KEY
    assert got.column_mapping["company_name"].type == ColumnType.STR
    assert got.column_mapping["company_name"].synonym == ["企业名称"]
    assert got.column_mapping["amount"].sensitive is True
    assert got.metric_definitions["total_amount"].aggregation == "sum"
    assert got.metric_definitions["total_amount"].label == "总金额"


async def test_get_by_entity_type_returns_none_when_missing(db_session):
    repo = SemanticModelRepository(db_session)

    got = await repo.get_by_entity_type(
        tenant_id=DEFAULT_TENANT_ID,
        entity_type="does_not_exist",
        data_source_config={"type": "imported_dataset", "dataset_id": str(uuid.uuid4())},
    )

    assert got is None


async def test_scan_dataset_columns_returns_distinct_keys(db_session, sample_dataset):
    """``scan_dataset_columns`` reads JSONB keys from ``dataset_rows.data``.

    The ``sample_dataset`` fixture inserts rows with keys
    ``{company_name, amount, billing_date}`` so we expect exactly that set.
    """
    repo = SemanticModelRepository(db_session)

    keys = await repo.scan_dataset_columns(sample_dataset["id"])

    assert keys == {"company_name", "amount", "billing_date"}


async def test_scan_dataset_columns_empty_dataset(db_session):
    """An unknown dataset_id returns an empty set, not an error."""
    repo = SemanticModelRepository(db_session)

    keys = await repo.scan_dataset_columns(uuid.uuid4())

    assert keys == set()


async def test_detect_drift_reports_new_and_removed(
    db_session, sample_dataset, education_catalog_id
):
    """``detect_drift`` lists columns present in the data but not registered
    (new) and registered but no longer present (removed)."""
    repo = SemanticModelRepository(db_session)
    # Registered columns: only "company_name" — "amount" and "billing_date"
    # should appear as new, nothing registered is removed.
    model = _make_semantic_model(sample_dataset["id"], education_catalog_id)
    model.column_mapping = {
        "company_name": model.column_mapping["company_name"],
        "ghost_column": ColumnMapping(
            role=ColumnRole.DIMENSION, type=ColumnType.STR
        ),
    }

    drift = await repo.detect_drift(sample_dataset["id"], model)

    assert sorted(drift["new_columns"]) == ["amount", "billing_date"]
    assert drift["removed_columns"] == ["ghost_column"]


async def test_detect_drift_no_drift(
    db_session, sample_dataset, education_catalog_id
):
    """When every registered column exists in the data, both lists are empty."""
    repo = SemanticModelRepository(db_session)
    model = _make_semantic_model(sample_dataset["id"], education_catalog_id)

    drift = await repo.detect_drift(sample_dataset["id"], model)

    assert drift["new_columns"] == []
    assert drift["removed_columns"] == []


async def test_create_persists_jsonb_serialization(
    db_session, sample_dataset, education_catalog_id
):
    """The repository serializes ColumnMapping / MetricDefinition via to_dict,
    then reads them back via from_dict. Verifies round-trip is symmetric."""
    repo = SemanticModelRepository(db_session)
    model = _make_semantic_model(sample_dataset["id"], education_catalog_id)

    await repo.create(model, catalog_id=education_catalog_id)
    await db_session.commit()

    # Read raw row to confirm JSONB columns were stored as expected.
    stmt = select(SemanticModelModel).where(SemanticModelModel.id == model.id)
    row = (await db_session.execute(stmt)).scalar_one()

    assert row.column_mapping["company_name"]["role"] == "entity_key"
    assert row.column_mapping["amount"]["sensitive"] is True
    assert row.metric_definitions["total_amount"]["column"] == "amount"
    assert row.metric_definitions["total_amount"]["aggregation"] == "sum"


async def test_get_by_entity_type_filters_by_status(
    db_session, sample_dataset, education_catalog_id
):
    """Inactive semantic models are not returned by ``get_by_entity_type``."""
    repo = SemanticModelRepository(db_session)
    model = _make_semantic_model(sample_dataset["id"], education_catalog_id)
    model.status = "deprecated"
    await repo.create(model, catalog_id=education_catalog_id)
    await db_session.commit()

    got = await repo.get_by_entity_type(
        tenant_id=model.tenant_id,
        entity_type="bill",
        data_source_config=model.data_source_config,
    )

    assert got is None


# ---------------------------------------------------------------------------
# REQ-054 Task 5: dual-key (catalog_id, entity_type) routing
# ---------------------------------------------------------------------------


async def test_get_active_by_catalog_and_entity_type_returns_active(
    db_session, sample_dataset, education_catalog_id
):
    """``get_active_by_catalog_and_entity_type`` returns the active model
    for the given (catalog, entity) pair."""
    repo = SemanticModelRepository(db_session)
    model = _make_semantic_model(sample_dataset["id"], education_catalog_id)
    await repo.create(model, catalog_id=education_catalog_id)
    await db_session.commit()

    got = await repo.get_active_by_catalog_and_entity_type(
        tenant_id=model.tenant_id,
        catalog_id=education_catalog_id,
        entity_type="bill",
    )

    assert got is not None
    assert got.id == model.id
    assert got.catalog_id == education_catalog_id
    assert got.entity_type == "bill"


async def test_get_active_by_catalog_and_entity_type_returns_none_when_missing(
    db_session, education_catalog_id
):
    """When no model exists for the (catalog, entity) pair, returns None."""
    repo = SemanticModelRepository(db_session)

    got = await repo.get_active_by_catalog_and_entity_type(
        tenant_id=DEFAULT_TENANT_ID,
        catalog_id=education_catalog_id,
        entity_type="does_not_exist_entity_type",
    )

    assert got is None


async def test_get_active_by_catalog_and_entity_type_skips_inactive(
    db_session, sample_dataset, education_catalog_id
):
    """Inactive models are NOT returned by the dual-key lookup.

    Mirrors ``test_get_by_entity_type_filters_by_status`` for the new
    method — only ``status='active'`` rows are visible.
    """
    repo = SemanticModelRepository(db_session)
    model = _make_semantic_model(sample_dataset["id"], education_catalog_id)
    model.status = "deprecated"
    await repo.create(model, catalog_id=education_catalog_id)
    await db_session.commit()

    got = await repo.get_active_by_catalog_and_entity_type(
        tenant_id=model.tenant_id,
        catalog_id=education_catalog_id,
        entity_type="bill",
    )

    assert got is None


async def test_get_active_by_catalog_and_entity_type_filters_by_status_active(
    db_session, sample_dataset, education_catalog_id
):
    """A deprecated row + an active row for the same (catalog, entity):
    only the active one is returned (status filter is enforced)."""
    repo = SemanticModelRepository(db_session)
    # Persist a deprecated model
    deprecated_model = _make_semantic_model(
        sample_dataset["id"], education_catalog_id
    )
    deprecated_model.status = "deprecated"
    await repo.create(deprecated_model, catalog_id=education_catalog_id)

    # Persist an active model with a different id but same (catalog, entity)
    active_model = _make_semantic_model(
        sample_dataset["id"], education_catalog_id
    )
    # data_source_config must differ for the unique constraint to allow
    # both rows to coexist — bump dataset_id in the config.
    active_model.data_source_config = {
        "type": DataSourceType.IMPORTED_DATASET.value,
        "dataset_id": str(uuid.uuid4()),
    }
    await repo.create(active_model, catalog_id=education_catalog_id)
    await db_session.commit()

    got = await repo.get_active_by_catalog_and_entity_type(
        tenant_id=active_model.tenant_id,
        catalog_id=education_catalog_id,
        entity_type="bill",
    )

    assert got is not None
    assert got.id == active_model.id
    assert got.status == "active"


async def test_same_entity_type_different_catalog_returns_different_models(
    db_session, sample_dataset, education_catalog_id, second_catalog_id
):
    """**Dual-key routing evidence**: the same ``entity_type`` registered
    under two different catalogs must yield two distinct models, looked
    up via the catalog_id-aware method.

    This is the regression test for the "latent multi-results risk"
    flagged by the Task 1 reviewer — the old single-key method
    ``get_active_by_entity_type`` could not distinguish these rows.
    """
    repo = SemanticModelRepository(db_session)
    # Education catalog model
    edu_model = _make_semantic_model(
        sample_dataset["id"], education_catalog_id, entity_type="shared_type"
    )
    await repo.create(edu_model, catalog_id=education_catalog_id)
    # Second catalog model — different catalog, different column_mapping
    hr_model = _make_semantic_model(
        sample_dataset["id"],
        second_catalog_id,
        entity_type="shared_type",
        entity_name="HR 共享实体",
    )
    hr_model.data_source_config = {
        "type": DataSourceType.IMPORTED_DATASET.value,
        "dataset_id": str(uuid.uuid4()),
    }
    hr_model.column_mapping = {
        "employee_id": ColumnMapping(
            role=ColumnRole.ENTITY_KEY,
            type=ColumnType.STR,
        ),
        "salary": ColumnMapping(
            role=ColumnRole.METRIC,
            type=ColumnType.FLOAT,
            sensitive=True,
        ),
    }
    await repo.create(hr_model, catalog_id=second_catalog_id)
    await db_session.commit()

    # Look up by the education catalog → must return the edu model only.
    got_edu = await repo.get_active_by_catalog_and_entity_type(
        tenant_id=DEFAULT_TENANT_ID,
        catalog_id=education_catalog_id,
        entity_type="shared_type",
    )
    # Look up by the second catalog → must return the hr model only.
    got_hr = await repo.get_active_by_catalog_and_entity_type(
        tenant_id=DEFAULT_TENANT_ID,
        catalog_id=second_catalog_id,
        entity_type="shared_type",
    )

    assert got_edu is not None
    assert got_hr is not None
    assert got_edu.id == edu_model.id
    assert got_hr.id == hr_model.id
    # They must be distinct rows with different column_mappings.
    assert got_edu.id != got_hr.id
    assert got_edu.catalog_id == education_catalog_id
    assert got_hr.catalog_id == second_catalog_id
    assert "company_name" in got_edu.column_mapping
    assert "salary" in got_hr.column_mapping
    assert "salary" not in got_edu.column_mapping


async def test_create_without_catalog_id_raises_value_error(
    db_session, sample_dataset
):
    """REQ-054: ``create()`` no longer auto-resolves catalog_id. The caller
    must pass it explicitly (or set ``model.catalog_id``); otherwise the
    repository raises ``ValueError`` rather than silently writing NULL to
    a NOT NULL column."""
    repo = SemanticModelRepository(db_session)
    model = _make_semantic_model(sample_dataset["id"], catalog_id=uuid.uuid4())
    # Wipe the model.catalog_id to simulate a caller that didn't supply one.
    model.catalog_id = None

    with pytest.raises(ValueError, match="catalog_id is required"):
        await repo.create(model)


async def test_create_uses_model_catalog_id_when_no_arg(
    db_session, sample_dataset, education_catalog_id
):
    """The catalog_id can also be supplied via ``model.catalog_id`` —
    the repository picks it up when no explicit ``catalog_id`` arg is
    passed to ``create()``. This is the secondary path (the param arg
    wins, but the field is honoured if the arg is omitted)."""
    repo = SemanticModelRepository(db_session)
    model = _make_semantic_model(
        sample_dataset["id"], education_catalog_id
    )
    # catalog_id is already set on the model by the helper; call create()
    # without the explicit arg.
    await repo.create(model)
    await db_session.commit()

    got = await repo.get_active_by_catalog_and_entity_type(
        tenant_id=model.tenant_id,
        catalog_id=education_catalog_id,
        entity_type="bill",
    )
    assert got is not None
    assert got.catalog_id == education_catalog_id
