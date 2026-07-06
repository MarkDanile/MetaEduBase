"""Test semantic model repository CRUD + column scan + drift detection.

REQ-052 Task 2. RED → GREEN: each test covers a behaviour of
:class:`SemanticModelRepository` against the real test PostgreSQL DB. The
fixtures (``db_session``, ``sample_dataset``) are provided by
``tests/contexts/structured_data/conftest.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

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


def _make_semantic_model(sample_dataset_id: uuid.UUID) -> SemanticModel:
    """Build a fully-populated SemanticModel for tests.

    Registers all three columns that ``sample_dataset`` actually contains
    (company_name / amount / billing_date) so tests that don't care about
    drift see a baseline with zero new / zero removed columns.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    return SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=sample_dataset_id,
        entity_type="bill",
        entity_name="账单",
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


async def test_create_and_get_semantic_model(db_session, sample_dataset):
    repo = SemanticModelRepository(db_session)
    model = _make_semantic_model(sample_dataset["id"])

    await repo.create(model)
    await db_session.commit()

    got = await repo.get_by_entity_type(
        tenant_id=model.tenant_id,
        entity_type="bill",
        data_source_config=model.data_source_config,
    )

    assert got is not None
    assert got.entity_type == "bill"
    assert got.dataset_id == sample_dataset["id"]
    assert got.column_mapping["company_name"].role == ColumnRole.ENTITY_KEY
    assert got.column_mapping["company_name"].type == ColumnType.STR
    assert got.column_mapping["company_name"].synonym == ["企业名称"]
    assert got.column_mapping["amount"].sensitive is True
    assert got.metric_definitions["total_amount"].aggregation == "sum"
    assert got.metric_definitions["total_amount"].label == "总金额"


async def test_get_by_entity_type_returns_none_when_missing(db_session, sample_dataset):
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


async def test_detect_drift_reports_new_and_removed(db_session, sample_dataset):
    """``detect_drift`` lists columns present in the data but not registered
    (new) and registered but no longer present (removed)."""
    repo = SemanticModelRepository(db_session)
    # Registered columns: only "company_name" — "amount" and "billing_date"
    # should appear as new, nothing registered is removed.
    model = _make_semantic_model(sample_dataset["id"])
    model.column_mapping = {
        "company_name": model.column_mapping["company_name"],
        "ghost_column": ColumnMapping(
            role=ColumnRole.DIMENSION, type=ColumnType.STR
        ),
    }

    drift = await repo.detect_drift(sample_dataset["id"], model)

    assert sorted(drift["new_columns"]) == ["amount", "billing_date"]
    assert drift["removed_columns"] == ["ghost_column"]


async def test_detect_drift_no_drift(db_session, sample_dataset):
    """When every registered column exists in the data, both lists are empty."""
    repo = SemanticModelRepository(db_session)
    model = _make_semantic_model(sample_dataset["id"])

    drift = await repo.detect_drift(sample_dataset["id"], model)

    assert drift["new_columns"] == []
    assert drift["removed_columns"] == []


async def test_create_persists_jsonb_serialization(db_session, sample_dataset):
    """The repository serializes ColumnMapping / MetricDefinition via to_dict,
    then reads them back via from_dict. Verifies round-trip is symmetric."""
    repo = SemanticModelRepository(db_session)
    model = _make_semantic_model(sample_dataset["id"])

    await repo.create(model)
    await db_session.commit()

    # Read raw row to confirm JSONB columns were stored as expected.
    stmt = select(SemanticModelModel).where(SemanticModelModel.id == model.id)
    row = (await db_session.execute(stmt)).scalar_one()

    assert row.column_mapping["company_name"]["role"] == "entity_key"
    assert row.column_mapping["amount"]["sensitive"] is True
    assert row.metric_definitions["total_amount"]["column"] == "amount"
    assert row.metric_definitions["total_amount"]["aggregation"] == "sum"


async def test_get_by_entity_type_filters_by_status(db_session, sample_dataset):
    """Inactive semantic models are not returned by ``get_by_entity_type``."""
    repo = SemanticModelRepository(db_session)
    model = _make_semantic_model(sample_dataset["id"])
    model.status = "deprecated"
    await repo.create(model)
    await db_session.commit()

    got = await repo.get_by_entity_type(
        tenant_id=model.tenant_id,
        entity_type="bill",
        data_source_config=model.data_source_config,
    )

    assert got is None
