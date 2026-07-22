#!/usr/bin/env python3
"""Seed active semantic models for REQ-046 DD internal_query (Slice 4).

The ``internal_query`` step resolves a semantic model by
``(tenant, catalog, entity_type)`` and runs a governed structured-data query.
Nothing else writes ``metaedu.semantic_models`` in production, so after the
park XLSX bundle is uploaded (``upload_park_datasets.py``) this script binds
each DD entity_type to its latest ``processed`` dataset.

Per entity_type it creates one active :class:`SemanticModel`:
- ``dataset_id`` = the latest ``processed`` dataset (re-upload safe; a newer
  upload wins on the next run once the old model is retired).
- ``column_mapping`` derived from the dataset's declared ``column_names``,
  with the ``客户ID`` relation key marked ``entity_key`` and the rest as
  ``dimension`` (operators refine roles/sensitivity afterwards in the console).
- idempotent: an entity_type that already has an active model is skipped.

Run (test DB / dev DB selected by ``DATABASE_URL`` env or settings)::

    cd packages/server-python
    uv run python scripts/seed_dd_semantic_models.py
"""
from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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

_CATALOG_CODE = "park_operations"
# DD internal_query entity_types (spec §4.5) + the join-graph sources the
# questions may draw on. Only these get a semantic model.
_DD_ENTITY_TYPES = (
    "customer",
    "contract",
    "contract_property",
    "lease_term",
    "bill",
    "payment",
    "payment_allocation",
    "ticket",
    "cooperation_note",
)
_ENTITY_KEY_COLUMN = "客户ID"

# Per-entity metric definitions (REQ-046 AC-8). The planner prompt only injects
# ``metric_definitions.keys()``; an empty map leaves the LLM nothing to anchor
# on (it omits ``entity`` / invents metrics and the validator rejects the plan).
# Each metric's ``column`` is a real Chinese dataset column and the aggregation
# is one the result explainer actually computes (sum / count / avg).
_METRIC_DEFINITIONS: dict[str, dict[str, tuple[str, str, str]]] = {
    "bill": {
        "unpaid_amount": ("未付金额(元)", "sum", "欠费金额"),
        "unpaid_count": ("未付金额(元)", "count", "欠费笔数"),
    },
    "lease_term": {
        "expiring_count": ("条款ID", "count", "租约条款数"),
    },
    "ticket": {
        "ticket_count": ("工单ID", "count", "工单数量"),
        "total_cost": ("费用(元)", "sum", "工单费用"),
    },
}

# Column-type inference by Chinese column-name shape. The default STR stays
# correct for free-text columns; only numeric / date columns need a precise
# type so the planner + time_range reasoning treat them correctly.
def _column_type(column: str) -> ColumnType:
    if column.endswith("日期") or column.endswith("时间") or column == "到期日":
        return ColumnType.DATE
    if ("金额" in column) or ("费用" in column) or ("单价" in column):
        return ColumnType.FLOAT
    return ColumnType.STR


async def _catalog_id(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID | None:
    return await session.scalar(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = :code AND is_active"
        ),
        {"tid": tenant_id, "code": _CATALOG_CODE},
    )


async def _latest_processed_dataset(
    session: AsyncSession, tenant_id: uuid.UUID, catalog_id: uuid.UUID, entity_type: str
) -> tuple[uuid.UUID, list[str]] | None:
    row = (
        await session.execute(
            text(
                "SELECT id, column_names FROM metaedu.datasets "
                "WHERE tenant_id = :tid AND catalog_id = :cid "
                "AND entity_type = :et AND status = 'processed' "
                "ORDER BY created_at DESC, id DESC LIMIT 1"
            ),
            {"tid": tenant_id, "cid": catalog_id, "et": entity_type},
        )
    ).first()
    if row is None:
        return None
    return row[0], list(row[1] or [])


async def _has_active_model(
    session: AsyncSession, tenant_id: uuid.UUID, catalog_id: uuid.UUID, entity_type: str
) -> bool:
    return bool(
        await session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM metaedu.semantic_models "
                "WHERE tenant_id = :tid AND catalog_id = :cid "
                "AND entity_type = :et AND status = 'active')"
            ),
            {"tid": tenant_id, "cid": catalog_id, "et": entity_type},
        )
    )


def _column_mapping(entity_type: str, columns: list[str]) -> dict[str, ColumnMapping]:
    metric_columns = {spec[0] for spec in _METRIC_DEFINITIONS.get(entity_type, {}).values()}
    mapping: dict[str, ColumnMapping] = {}
    for column in columns:
        if not column:
            continue
        if column == _ENTITY_KEY_COLUMN:
            role = ColumnRole.ENTITY_KEY
        elif column in metric_columns:
            role = ColumnRole.METRIC
        else:
            role = ColumnRole.DIMENSION
        mapping[column] = ColumnMapping(role=role, type=_column_type(column), sensitive=False)
    return mapping


def _metric_definitions(entity_type: str) -> dict[str, MetricDefinition]:
    return {
        name: MetricDefinition(column=column, aggregation=agg, label=label)
        for name, (column, agg, label) in _METRIC_DEFINITIONS.get(entity_type, {}).items()
    }


async def seed(
    session: AsyncSession, *, tenant_id: uuid.UUID, created_by: uuid.UUID
) -> list[str]:
    """Create active semantic models for DD entity_types; return the seeded list."""
    catalog_id = await _catalog_id(session, tenant_id)
    if catalog_id is None:
        raise SystemExit(
            f"catalog '{_CATALOG_CODE}' 不存在于 tenant {tenant_id}；"
            "请先运行 upload_park_datasets.py"
        )
    repo = SemanticModelRepository(session)
    seeded: list[str] = []
    for entity_type in _DD_ENTITY_TYPES:
        if await _has_active_model(session, tenant_id, catalog_id, entity_type):
            continue
        found = await _latest_processed_dataset(
            session, tenant_id, catalog_id, entity_type
        )
        if found is None:
            continue
        dataset_id, columns = found
        model = SemanticModel(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            entity_type=entity_type,
            entity_name=entity_type,
            data_source_config={
                "type": DataSourceType.IMPORTED_DATASET.value,
                "dataset_id": str(dataset_id),
            },
            column_mapping=_column_mapping(entity_type, columns),
            metric_definitions=_metric_definitions(entity_type),
            version="v1",
            status="active",
            created_by=created_by,
            catalog_id=catalog_id,
        )
        await repo.create(model, catalog_id=catalog_id)
        seeded.append(entity_type)
    return seeded


async def _amain() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True, help="目标 tenant UUID")
    parser.add_argument("--created-by", required=True, help="操作人 user UUID")
    args = parser.parse_args()

    from app.shared.infrastructure.database import async_session_factory

    async with async_session_factory() as session:
        seeded = await seed(
            session,
            tenant_id=uuid.UUID(args.tenant_id),
            created_by=uuid.UUID(args.created_by),
        )
        await session.commit()
    print(f"seeded semantic models: {seeded or '(none; all present or no processed dataset)'}")


if __name__ == "__main__":
    asyncio.run(_amain())
