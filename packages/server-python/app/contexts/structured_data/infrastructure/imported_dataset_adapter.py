"""ImportedDatasetAdapter — JSONB query over uploaded datasets (REQ-052 first slice).

This is the only data source adapter that is **fully implemented** in Task 2.
It serves semantic models whose ``data_source_config.type == "imported_dataset"``:
queries are answered by reading rows from ``metaedu.dataset_rows`` and returning
their ``data`` JSONB column as plain ``dict``s.

What it does today:

- Filters strictly by ``tenant_id`` (security boundary) and ``dataset_id``.
- Honors ``query_plan.limit`` (defaults to 100) and ``query_plan.data_source_ref``
  as a per-call override of the dataset id.
- Returns an empty list (not an error) when no dataset id is discoverable.

What it does **not** do yet:

- JSONB predicate filtering (``company_name = 'ACME'``). That lands with the
  JsonbQueryBuilder in a later slice, where ``validate_query`` will also
  start returning real rule violations instead of an empty list.
- Aggregation / metric resolution (``SUM(amount)`` etc). The repository's
  ``metric_definitions`` are consumed by the Query Planner, not here.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.domain.data_source_adapter import (
    DataSourceAdapter,
)
from app.contexts.structured_data.infrastructure.models import DatasetRowModel


class ImportedDatasetAdapter(DataSourceAdapter):
    """First-slice adapter for uploaded (CSV/Excel) datasets."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def get_data_source_type(self) -> str:
        return "imported_dataset"

    async def query(
        self,
        query_plan: dict,
        semantic_model: Any,
        tenant_id: uuid.UUID,
        user_role: str,
    ) -> list[dict]:
        """Return the JSONB ``data`` payload of each row for the given dataset.

        The ``tenant_id`` predicate is **non-negotiable** — it's the only
        guarantee that a user from tenant A cannot see tenant B's rows even
        if they spoof ``query_plan`` or ``semantic_model.dataset_id``.
        ``user_role`` is accepted for symmetry with the ABC; no role-aware
        filtering is applied yet (RBAC lands in Task 5).
        """
        dataset_id = query_plan.get("data_source_ref") or (
            semantic_model.dataset_id if semantic_model is not None else None
        )
        if not dataset_id:
            return []

        stmt = select(DatasetRowModel).where(
            DatasetRowModel.tenant_id == tenant_id,
            DatasetRowModel.dataset_id == uuid.UUID(str(dataset_id)),
        )
        limit = int(query_plan.get("limit", 100))
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [row.data for row in result.scalars().all()]

    def validate_query(self, query_plan: dict, semantic_model: Any) -> list[str]:
        """First-slice: no validation rules.

        The contract returns an empty list so the calling planner treats the
        plan as acceptable. SqlGuard / PII rules will populate this in later
        slices.
        """
        return []
