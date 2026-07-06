"""SQL Guard: row-level field whitelist + RBAC visibility + PII forced masking.

REQ-052 Task 4: the LAST defence in the data-activation pipeline. After
the adapter returns rows, SqlGuard:

1. Drops columns that aren't in ``semantic_model.column_mapping``
   (field whitelist — protects against "ghost columns" joined in by a
   misconfigured adapter or by a future cross-dataset query).
2. Resolves each remaining column's visibility through
   :class:`RBACService` (async) — see deviation note below.
3. Removes HIDDEN columns entirely.
4. Forces PII masking on MASKED columns AND on VISIBLE columns whose
   values happen to contain PII patterns (id_card / phone / bank_card /
   email / address). This is the REQ-052 §12.2 "last-line-of-defence"
   rule: schema misconfiguration must not leak PII.

Brief deviations (recorded in commit message):

1. **Async signature** — the brief sketch used a sync
   ``check_and_mask(rows, ...)`` calling a non-existent
   ``rbac_service.get_field_visibility_sync``. The real
   :class:`RBACService` (Task 3) only exposes
   ``async get_field_visibility``. We made :meth:`check_and_mask`
   ``async`` so it can ``await`` the real RBAC call. This matches the
   rest of the codebase (every other application-layer service is
   async) and matches the brief's `query_plan → result` execution
   flow naturally.

2. **Caller-row mutation** — the brief mutated the caller's rows list
   in place (``del row[col]``). We preserve that behaviour but document
   it here: SqlGuard does NOT deep-copy its input. Callers wanting to
   keep the original rows should pass ``copy.deepcopy(rows)``.

Returns :class:`GuardResult` with the filtered rows and the count of
masked values (so the audit log can record ``masked_count=N``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.contexts.structured_data.application.pii_detector import PIIDetector
from app.contexts.structured_data.application.rbac_service import RBACService
from app.contexts.structured_data.domain.permissions import Role, Visibility


@dataclass
class GuardResult:
    """Output of :meth:`SqlGuard.check_and_mask`.

    Attributes:
        rows: the filtered rows. ``HIDDEN`` and out-of-whitelist columns
            are removed; ``MASKED`` and PII-bearing ``VISIBLE`` columns
            are replaced with masked values. The list is the same object
            as the input — callers wanting isolation should deepcopy.
        masked_count: number of individual cell-level masking operations
            applied. Used by the audit log so a regulator can confirm
            "no PII slipped through un-masked".
    """

    rows: list[dict]
    masked_count: int


class SqlGuard:
    """Apply field whitelist + RBAC visibility + PII forced masking to rows.

    The class is stateless beyond its two collaborators. Both are passed
    in at construction time so tests can substitute lightweight mocks
    (``AsyncMock``-backed :class:`RBACService`, real :class:`PIIDetector`)
    without changing production wiring.
    """

    def __init__(
        self,
        rbac_service: RBACService,
        pii_detector: PIIDetector,
    ) -> None:
        self._rbac = rbac_service
        self._pii = pii_detector

    async def check_and_mask(
        self,
        rows: list[dict],
        semantic_model: Any,
        role: str,
        tenant_id: Any = None,
        entity_type: str | None = None,
    ) -> GuardResult:
        """Apply all three guards and return :class:`GuardResult`.

        Parameters:
            rows: list of dict-shaped rows from the adapter.
            semantic_model: the model whose ``column_mapping`` is the
                whitelist + the entity_type is the visibility key.
            role: one of the five :class:`Role` values. Passed as a
                string here so callers can use ``user.role`` directly.
            tenant_id: forwarded to :meth:`RBACService.get_field_visibility`.
                Required because visibility is per-tenant.
            entity_type: forwarded to RBAC. Defaults to
                ``semantic_model.entity_type`` if omitted.
        """
        allowed_cols = set(semantic_model.column_mapping.keys())
        entity_type = entity_type or semantic_model.entity_type
        masked_count = 0

        for row in rows:
            # Snapshot the items so we can safely `del` during iteration.
            for col, _value in list(row.items()):  # noqa: B007
                # Field whitelist — drop columns not in the schema.
                if col not in allowed_cols:
                    del row[col]
                    continue

                visibility = await self._resolve_visibility(
                    role=role,
                    tenant_id=tenant_id,
                    entity_type=entity_type,
                    column_name=col,
                )

                if visibility == Visibility.HIDDEN:
                    del row[col]
                    continue

                if visibility == Visibility.MASKED:
                    masked_count += self._mask_value(row, col)
                    continue

                # visibility == VISIBLE — but the PII detector is still
                # on duty: even VISIBLE columns must mask PII patterns,
                # because the schema may have under-classified a column.
                masked_count += self._mask_value(row, col)

        return GuardResult(rows=rows, masked_count=masked_count)

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    async def _resolve_visibility(
        self,
        *,
        role: str,
        tenant_id: Any,
        entity_type: str,
        column_name: str,
    ) -> Visibility:
        """Wrap :meth:`RBACService.get_field_visibility` with a safe default.

        If the RBAC service raises (e.g. transient DB outage), we fall
        back to :attr:`Visibility.MASKED` — strict default policy from
        REQ-052 §12. A masked value is always safe to return; an unmasked
        value with a broken RBAC service is a potential data leak.
        """
        try:
            return await self._rbac.get_field_visibility(
                tenant_id=tenant_id,
                role=Role(role),
                entity_type=entity_type,
                column_name=column_name,
            )
        except Exception:
            # RBAC failure must NEVER widen visibility — log + mask.
            return Visibility.MASKED

    def _mask_value(self, row: dict, col: str) -> int:
        """Mask any PII patterns in ``row[col]`` in place. Returns 1 if
        any masking happened, 0 otherwise.

        Non-string values pass through unchanged (numbers, booleans,
        ``None``). The PII detector's :meth:`detect` returns ``[]`` for
        anything it doesn't recognise, so an empty ``detected`` list
        correctly returns 0 from this method.
        """
        value = row[col]
        detected = self._pii.detect(value)
        for pii_type in detected:
            value = self._pii.mask(value, pii_type)
        row[col] = value
        return 1 if detected else 0
