"""Semantic Validator: query_plan ↔ semantic_model field-level checks.

REQ-052 Task 4: pure-function validator that runs AFTER the LLM planner
and BEFORE the JsonbQueryBuilder. It returns a list of error strings
(empty list means "plan is valid"); any error short-circuits the
pipeline so the user sees a "please clarify your question" hint.

Rules (per brief + spec §5.4):

1. ``entity`` must equal ``semantic_model.entity_type`` — the planner may
   guess wrong entity_type; the validator catches the misroute before
   the wrong dataset is queried.
2. Every metric in ``metrics`` must be a key of
   ``metric_definitions``. Catches "ghost metrics" invented by the LLM.
3. Every filter column must be a key of ``column_mapping`` — field
   whitelist enforcement at the schema level (a separate per-row
   whitelist check lives in SqlGuard).
4. ``time_range.field`` (if present) must be a key of
   ``column_mapping`` — same rationale as #3.

The validator is intentionally tolerant of missing optional fields
(``metrics`` and ``time_range`` can be absent). Only ``entity`` is
required. Errors are reported individually — a plan with three issues
yields three error strings so the caller can prompt-fix all of them.
"""

from __future__ import annotations

from typing import Any


class SemanticValidator:
    """Validate that ``query_plan`` references only declared schema fields."""

    def validate(self, query_plan: dict, semantic_model: Any) -> list[str]:
        """Return a list of error strings. ``[]`` means the plan is valid."""
        errors: list[str] = []

        errors.extend(self._check_entity(query_plan, semantic_model))
        errors.extend(self._check_metrics(query_plan, semantic_model))
        errors.extend(self._check_filters(query_plan, semantic_model))
        errors.extend(self._check_time_range(query_plan, semantic_model))

        return errors

    # ------------------------------------------------------------------
    # individual checks
    # ------------------------------------------------------------------

    def _check_entity(self, query_plan: dict, semantic_model: Any) -> list[str]:
        entity = query_plan.get("entity")
        if entity is None:
            return [
                f"entity is required (expected: {semantic_model.entity_type})"
            ]
        if entity != semantic_model.entity_type:
            return [
                f"entity '{entity}' not in semantic model "
                f"(expected: {semantic_model.entity_type})"
            ]
        return []

    def _check_metrics(self, query_plan: dict, semantic_model: Any) -> list[str]:
        declared = semantic_model.metric_definitions
        errors: list[str] = []
        for metric in query_plan.get("metrics", []) or []:
            if metric not in declared:
                errors.append(
                    f"metric '{metric}' not defined in semantic model. "
                    f"Available: {list(declared.keys())}"
                )
        return errors

    def _check_filters(self, query_plan: dict, semantic_model: Any) -> list[str]:
        declared = semantic_model.column_mapping
        errors: list[str] = []
        for col in query_plan.get("filters", {}) or {}:
            if col not in declared:
                errors.append(
                    f"filter column '{col}' not defined in semantic model. "
                    f"Available: {list(declared.keys())}"
                )
        return errors

    def _check_time_range(self, query_plan: dict, semantic_model: Any) -> list[str]:
        tr = query_plan.get("time_range")
        if not tr:
            return []  # time_range is optional
        field = tr.get("field")
        if not field:
            return []  # empty time_range field is a planner no-op
        declared = semantic_model.column_mapping
        if field not in declared:
            return [f"time_range field '{field}' not defined in semantic model"]
        return []
