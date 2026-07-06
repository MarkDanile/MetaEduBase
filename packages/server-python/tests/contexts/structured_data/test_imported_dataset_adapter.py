"""Test ImportedDatasetAdapter — JSONB query implementation (REQ-052 first slice).

The adapter contract is small for now:
- ``get_data_source_type`` returns ``"imported_dataset"``.
- ``query`` filters by ``tenant_id`` + ``dataset_id`` and returns the
  ``data`` JSONB column as plain dicts (no JSONB filtering yet — that
  comes with the JsonbQueryBuilder in Slice 1).
- ``validate_query`` returns an empty list (no validation rules yet).

These tests cover the happy path, tenant isolation, the limit cap, and
the placeholder behaviour of ``DirectDBAdapter`` / ``MCPAdapter``.
"""

from __future__ import annotations

import uuid

import pytest

from app.contexts.structured_data.domain.data_source_adapter import (
    DataSourceAdapter,
)
from app.contexts.structured_data.domain.semantic_model import (
    ColumnMapping,
    ColumnRole,
    ColumnType,
    DataSourceType,
    MetricDefinition,
    SemanticModel,
)
from app.contexts.structured_data.infrastructure.direct_db_adapter import (
    DirectDBAdapter,
)
from app.contexts.structured_data.infrastructure.imported_dataset_adapter import (
    ImportedDatasetAdapter,
)
from app.contexts.structured_data.infrastructure.mcp_adapter import MCPAdapter
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio


def _make_semantic_model(dataset_id: uuid.UUID) -> SemanticModel:
    return SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=dataset_id,
        entity_type="bill",
        entity_name="账单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(dataset_id),
        },
        column_mapping={
            "company_name": ColumnMapping(
                role=ColumnRole.ENTITY_KEY, type=ColumnType.STR
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
        },
        created_by=DEFAULT_ADMIN_ID,
    )


async def test_get_data_source_type_returns_imported_dataset(db_session):
    adapter = ImportedDatasetAdapter(db_session)

    assert adapter.get_data_source_type() == "imported_dataset"


async def test_query_returns_jsonb_rows_for_tenant(db_session, sample_dataset):
    """Happy path: rows for the seeded dataset are returned as dicts."""
    adapter = ImportedDatasetAdapter(db_session)
    model = _make_semantic_model(sample_dataset["id"])

    rows = await adapter.query(
        query_plan={},
        semantic_model=model,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )

    assert isinstance(rows, list)
    assert len(rows) == 2
    companies = sorted(r["company_name"] for r in rows)
    assert companies == ["ACME", "BetaCorp"]


async def test_query_respects_limit(db_session, sample_dataset):
    adapter = ImportedDatasetAdapter(db_session)
    model = _make_semantic_model(sample_dataset["id"])

    rows = await adapter.query(
        query_plan={"limit": 1},
        semantic_model=model,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )

    assert len(rows) == 1


async def test_query_filters_by_tenant_id(db_session, sample_dataset):
    """A query with a different tenant_id must return zero rows.

    This is the security boundary: the adapter must always inject the
    ``tenant_id`` predicate, never trust the query_plan to do it.
    """
    adapter = ImportedDatasetAdapter(db_session)
    model = _make_semantic_model(sample_dataset["id"])
    other_tenant = uuid.uuid4()

    rows = await adapter.query(
        query_plan={},
        semantic_model=model,
        tenant_id=other_tenant,
        user_role="manager",
    )

    assert rows == []


async def test_query_uses_data_source_ref_override(db_session, sample_dataset):
    """If ``query_plan.data_source_ref`` is set, it overrides semantic_model.dataset_id."""
    adapter = ImportedDatasetAdapter(db_session)
    model = _make_semantic_model(sample_dataset["id"])

    rows = await adapter.query(
        query_plan={"data_source_ref": str(sample_dataset["id"])},
        semantic_model=model,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )

    assert len(rows) == 2


async def test_query_returns_empty_when_no_dataset_id(db_session, sample_dataset):
    """If neither data_source_ref nor dataset_id is present, return []."""
    adapter = ImportedDatasetAdapter(db_session)
    model = _make_semantic_model(sample_dataset["id"])
    model.dataset_id = None

    rows = await adapter.query(
        query_plan={},
        semantic_model=model,
        tenant_id=DEFAULT_TENANT_ID,
        user_role="manager",
    )

    assert rows == []


async def test_validate_query_returns_empty_for_now(db_session, sample_dataset):
    """First-slice: no validation rules — the adapter accepts any plan."""
    adapter = ImportedDatasetAdapter(db_session)
    model = _make_semantic_model(sample_dataset["id"])

    errors = adapter.validate_query({"limit": 100}, model)

    assert errors == []


async def test_direct_db_adapter_raises_not_implemented(db_session):
    """DirectDBAdapter is a V1 placeholder — every entry point must reject."""
    with pytest.raises(NotImplementedError):
        DirectDBAdapter(db_session)

    with pytest.raises(NotImplementedError):
        DirectDBAdapter().query({}, None, DEFAULT_TENANT_ID, "manager")

    with pytest.raises(NotImplementedError):
        DirectDBAdapter().validate_query({}, None)


async def test_mcp_adapter_raises_not_implemented(db_session):
    """MCPAdapter is a V1 placeholder — every entry point must reject."""
    with pytest.raises(NotImplementedError):
        MCPAdapter(db_session)

    with pytest.raises(NotImplementedError):
        MCPAdapter().query({}, None, DEFAULT_TENANT_ID, "manager")

    with pytest.raises(NotImplementedError):
        MCPAdapter().validate_query({}, None)


async def test_adapters_inherit_from_abc():
    """All adapter implementations must extend ``DataSourceAdapter``."""
    assert issubclass(ImportedDatasetAdapter, DataSourceAdapter)
    assert issubclass(DirectDBAdapter, DataSourceAdapter)
    assert issubclass(MCPAdapter, DataSourceAdapter)


async def test_direct_db_and_mcp_get_data_source_type():
    """The placeholder classes still expose their type identifier."""
    # Even though __init__ raises, get_data_source_type is a class-level
    # concern — we exercise it without instantiating.
    assert DirectDBAdapter.get_data_source_type(None) == "direct_db"  # type: ignore[arg-type]
    assert MCPAdapter.get_data_source_type(None) == "mcp"  # type: ignore[arg-type]
