"""End-to-end filtering tests for ImportedDatasetAdapter (REQ-056 Task 1).

These tests prove that the adapter now delegates SQL emission to
:class:`JsonbQueryBuilder` — so ``query_plan.filters`` and
``query_plan.time_range`` are actually applied against the JSONB ``data``
column instead of being ignored. Before this slice the adapter built its
own ``select`` with only ``tenant_id`` / ``dataset_id`` / ``limit``, so
filters had no effect on the result set.

Coverage:
- A ``filters`` clause changes the returned row count (5 → 2) and every
  returned row matches the predicate.
- A ``time_range`` clause combined with ``limit`` narrows the result set.
"""

from __future__ import annotations

import uuid

import pytest

from app.contexts.structured_data.domain.semantic_model import (
    ColumnMapping,
    ColumnRole,
    ColumnType,
    DataSourceType,
    MetricDefinition,
    SemanticModel,
)
from app.contexts.structured_data.infrastructure.imported_dataset_adapter import (
    ImportedDatasetAdapter,
)
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
            "billing_date": ColumnMapping(
                role=ColumnRole.FILTER, type=ColumnType.DATE
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
        },
        created_by=DEFAULT_ADMIN_ID,
    )


async def test_filters_change_results(db_session, sample_dataset_with_rows):
    """A ``filters`` predicate must reduce the result count (5 → 2)."""
    adapter = ImportedDatasetAdapter(db_session)
    sm = _make_semantic_model(sample_dataset_with_rows["id"])
    tenant_id = sample_dataset_with_rows["tenant_id"]

    # No filter -> all 5 rows.
    res_all = await adapter.query(
        query_plan={"limit": 100},
        semantic_model=sm,
        tenant_id=tenant_id,
        user_role="employee",
    )
    assert len(res_all) == 5

    # Filter company_name == "A" -> only the 2 matching rows.
    res_filtered = await adapter.query(
        query_plan={
            "limit": 100,
            "filters": {"company_name": {"op": "eq", "value": "A"}},
        },
        semantic_model=sm,
        tenant_id=tenant_id,
        user_role="employee",
    )
    assert len(res_filtered) == 2
    assert all(r["company_name"] == "A" for r in res_filtered)
    # Evidence: filtering strictly narrows the result set.
    assert len(res_filtered) < len(res_all)


async def test_time_range_and_limit_narrow_results(
    db_session, sample_dataset_with_rows
):
    """``time_range`` + ``limit`` together narrow the result set.

    Rows span billing_date 2026-01-01 .. 2026-05-01. A range of
    2026-02-01 .. 2026-04-01 matches 3 rows (Feb/Mar/Apr); a ``limit`` of
    2 then caps the returned rows to 2.
    """
    adapter = ImportedDatasetAdapter(db_session)
    sm = _make_semantic_model(sample_dataset_with_rows["id"])
    tenant_id = sample_dataset_with_rows["tenant_id"]

    res_range = await adapter.query(
        query_plan={
            "limit": 100,
            "time_range": {
                "field": "billing_date",
                "start": "2026-02-01",
                "end": "2026-04-01",
            },
        },
        semantic_model=sm,
        tenant_id=tenant_id,
        user_role="employee",
    )
    assert len(res_range) == 3
    assert all("2026-02-01" <= r["billing_date"] <= "2026-04-01" for r in res_range)

    # Same range but capped to 2 rows via limit.
    res_limited = await adapter.query(
        query_plan={
            "limit": 2,
            "time_range": {
                "field": "billing_date",
                "start": "2026-02-01",
                "end": "2026-04-01",
            },
        },
        semantic_model=sm,
        tenant_id=tenant_id,
        user_role="employee",
    )
    assert len(res_limited) == 2
