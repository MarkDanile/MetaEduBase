"""JSONB Query Builder: query_plan → SQLAlchemy JSONB select.

REQ-052 Task 4: translates a validated ``query_plan`` dict into a
SQLAlchemy ``select(DatasetRowModel.data)`` statement with all required
predicates applied. The builder is the SQL-emission point for the
ImportedDatasetAdapter and is responsible for three security invariants:

1. **Tenant isolation** — every emitted statement has
   ``WHERE tenant_id = :tenant_id``. The ``tenant_id`` argument is the
   ONLY thing that can satisfy this clause; a malicious query_plan cannot
   override it. Cross-tenant requests yield zero rows because the
   ``tenant_id`` predicate excludes them.

2. **Limit clamp** — the spec §5.5 / AC-4 cap is 1000 (max). The brief's
   sketch used raw ``int(query_plan.get("limit", 100))`` with no upper
   bound; we add ``min(limit, MAX_LIMIT)`` plus a floor of 1 to guard
   against 0 / negative values. The default is 100 (soft limit).

3. **JSONB operator safety** — ``OPERATOR_MAP`` is a closed set; any
   operator the LLM invents (e.g. ``REGEX_MATCH``) is silently dropped
   rather than passed to the DB. This prevents a LLM hallucination from
   introducing a SQL injection vector.

Brief deviations:

- The brief uses ``data[col].astext`` for every comparison. This works
  for string-typed columns. Numeric / boolean JSONB values would need
  different casting; we keep the brief behaviour for now (Phase 1 data
  sets store dates and strings — see ``sample_dataset`` fixture).

- ``time_range.start`` / ``end`` are applied as ``>=`` / ``<=`` over the
  JSONB ``.astext``. For ISO-formatted dates this is correct
  lexicographically. We document this limitation rather than re-parsing
  to ``timestamptz`` — the planner emits ISO strings today and changing
  the casting mid-pipeline would require a migration.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.infrastructure.models import DatasetRowModel

logger = logging.getLogger(__name__)


class JsonbQueryBuilder:
    """Build a JSONB-backed SQLAlchemy select from a query_plan.

    The class holds only the ``AsyncSession``. Every query parameter is a
    method argument; the same builder can serve concurrent requests safely.
    """

    # Spec §5.5 / AC-4 — soft limit 100, hard max 1000.
    DEFAULT_LIMIT: int = 100
    MAX_LIMIT: int = 1000

    # Operator whitelist. Any operator the planner/LLM emits that isn't
    # in this map is silently dropped from the WHERE clause — see
    # "JSONB operator safety" in the module docstring.
    OPERATOR_MAP: dict[str, Any] = {
        "eq": lambda col, v: col == v,
        "ne": lambda col, v: col != v,
        "gt": lambda col, v: col > v,
        "lt": lambda col, v: col < v,
        "gte": lambda col, v: col >= v,
        "lte": lambda col, v: col <= v,
        "contains": lambda col, v: col.contains(v),
        "in": lambda col, v: col.in_(v) if isinstance(v, list) else col == v,
    }

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def build(
        self,
        query_plan: dict,
        semantic_model: Any,
        tenant_id: uuid.UUID,
    ):
        """Return a ``select(DatasetRowModel.data)`` statement.

        Returns ``None`` if no dataset_id can be resolved — the caller
        should treat that as "no query" rather than "error". A missing
        dataset_id can happen if neither ``semantic_model.dataset_id`` nor
        ``query_plan.data_source_ref`` is populated.

        The returned statement selects only the JSONB ``data`` column so
        the downstream SqlGuard never sees tenant / dataset ids.
        """
        dataset_id = semantic_model.dataset_id or query_plan.get("data_source_ref")
        if not dataset_id:
            return None

        stmt = select(DatasetRowModel.data).where(
            DatasetRowModel.tenant_id == tenant_id,
            DatasetRowModel.dataset_id == uuid.UUID(str(dataset_id)),
        )

        stmt = self._apply_filters(stmt, query_plan.get("filters") or {})
        stmt = self._apply_time_range(stmt, query_plan.get("time_range"))
        stmt = self._apply_limit(stmt, query_plan.get("limit"))

        return stmt

    # ------------------------------------------------------------------
    # clause builders
    # ------------------------------------------------------------------

    def _apply_filters(self, stmt, filters: dict):
        """Apply each ``filters`` entry as a WHERE clause on the JSONB column.

        Operators not in :data:`OPERATOR_MAP` are silently dropped — see
        "JSONB operator safety" in the module docstring.
        """
        for col, cond in filters.items():
            op = (cond or {}).get("op", "eq")
            value = (cond or {}).get("value")
            op_fn = self.OPERATOR_MAP.get(op)
            if op_fn is None:
                logger.warning(
                    "JsonbQueryBuilder: dropping unknown operator %r on %r",
                    op,
                    col,
                )
                continue
            stmt = stmt.where(op_fn(DatasetRowModel.data[col].astext, value))
        return stmt

    def _apply_time_range(self, stmt, time_range):
        """Apply ``time_range`` as ``>= start`` / ``<= end`` over ``.astext``.

        Time-range is optional — a missing or empty dict leaves the
        statement untouched. The brief's sketch only applied the lower
        bound if ``start`` was truthy; we keep the same behaviour so a
        one-sided range still narrows results.
        """
        if not time_range:
            return stmt
        field = time_range.get("field")
        start = time_range.get("start")
        end = time_range.get("end")
        if field and start:
            stmt = stmt.where(DatasetRowModel.data[field].astext >= start)
        if field and end:
            stmt = stmt.where(DatasetRowModel.data[field].astext <= end)
        return stmt

    def _apply_limit(self, stmt, raw_limit):
        """Clamp the limit to the spec's ``[1, 1000]`` window.

        - Missing / None → ``DEFAULT_LIMIT`` (100).
        - Non-int values → ``DEFAULT_LIMIT`` (defensive — guards against
          an LLM that emits a string).
        - Int values are clamped: ``min(limit, MAX_LIMIT)`` and
          ``max(limit, 1)`` so 0 / negative values still return at least
          one row.
        """
        try:
            limit = int(raw_limit) if raw_limit is not None else self.DEFAULT_LIMIT
        except (TypeError, ValueError):
            limit = self.DEFAULT_LIMIT
        # Clamp to [1, MAX_LIMIT]
        if limit < 1:
            limit = 1
        if limit > self.MAX_LIMIT:
            limit = self.MAX_LIMIT
        return stmt.limit(limit)
