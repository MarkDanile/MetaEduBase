"""ImportedDatasetAdapter — JSONB query over uploaded datasets (REQ-052 first slice).

This is the only data source adapter that is **fully implemented** in Task 2.
It serves semantic models whose ``data_source_config.type == "imported_dataset"``:
queries are answered by reading rows from ``metaedu.dataset_rows`` and returning
their ``data`` JSONB column as plain ``dict``s.

What it does today:

- Delegates SQL emission to :class:`JsonbQueryBuilder`, which applies the
  ``tenant_id`` (security boundary) + ``dataset_id`` predicates, JSONB
  ``filters``, ``time_range`` and a clamped ``limit`` (REQ-056 Task 1).
- Returns an empty list (not an error) when no dataset id is discoverable
  (the builder returns ``None``).

What it does **not** do yet:

- Aggregation / metric resolution (``SUM(amount)`` etc). The repository's
  ``metric_definitions`` are consumed by the Query Planner, not here.
- RBAC / PII masking on the returned rows (lands in a later slice); the
  ``user_role`` argument is accepted for symmetry with the ABC.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.domain.data_source_adapter import (
    DataSourceAdapter,
)
from app.contexts.structured_data.infrastructure.jsonb_query_builder import (
    JsonbQueryBuilder,
)


class ImportedDatasetAdapter(DataSourceAdapter):
    """First-slice adapter for uploaded (CSV/Excel) datasets."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._builder = JsonbQueryBuilder(session)

    def get_data_source_type(self) -> str:
        return "imported_dataset"

    async def query(
        self,
        query_plan: dict,
        semantic_model: Any,
        tenant_id: uuid.UUID,
        user_role: str,
    ) -> list[dict]:
        """Return the JSONB ``data`` payload of each matching row.

        SQL emission is delegated to :class:`JsonbQueryBuilder`, which
        applies the ``tenant_id`` predicate (the **non-negotiable** tenant
        isolation boundary), the ``dataset_id`` predicate, plus any
        ``filters`` / ``time_range`` / clamped ``limit`` from the plan.
        The builder returns ``None`` when no dataset id can be resolved —
        we treat that as "no query" and return an empty list rather than
        an error. ``user_role`` is accepted for symmetry with the ABC; no
        role-aware filtering is applied yet (RBAC lands in a later slice).
        """
        stmt = self._builder.build(query_plan, semantic_model, tenant_id)
        if stmt is None:
            return []
        result = await self._session.execute(stmt)
        return [data for (data,) in result.all()]

    def validate_query(self, query_plan: dict, semantic_model: Any) -> list[str]:
        """First-slice: no validation rules.

        The contract returns an empty list so the calling planner treats the
        plan as acceptable. SqlGuard / PII rules will populate this in later
        slices.
        """
        return []
