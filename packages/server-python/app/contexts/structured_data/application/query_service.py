"""QueryService — orchestrator for the full data-activation pipeline.

REQ-052 Task 5: single entry point that wires Planner → Validator →
Adapter → SqlGuard → Explainer → Audit. The router delegates to this
service so the request handler stays small.

Pipeline order:

    1. Planner:  NL question → LLM-generated ``query_plan`` dict.
    2. Validator: query_plan against semantic_model; short-circuits on
       errors and returns ``{"ok": False, "errors": [...]}``.
    3. Adapter:   resolve ``DataSourceAdapter`` for the model's
       ``data_source_config.type`` and execute the query (tenant-scoped).
    4. SqlGuard:  apply field whitelist + RBAC visibility + PII masking.
       (REQ-052 §12.2 last-line-of-defence.)
    5. Explainer: produce the natural-language summary + metric values.
    6. Audit:     append a row to ``metaedu.query_audit_log`` — ALWAYS,
                 including failures (Step 2 short-circuits log a row too,
                 so the regulator sees "user asked X, validator rejected
                 with reasons Y").

The service is built once at app startup (lifespan) with all
collaborators and stored on ``app.state.query_service``. Tests build a
real instance per-test and inject it via the ``client`` fixture's
``app.state.query_service = ...`` assignment.

Brief deviations (recorded in commit message):

1. **Async SqlGuard** — the brief sketch called
   ``self._sql_guard.check_and_mask(...)`` synchronously. The Task 4
   :class:`SqlGuard` exposes an ``async`` signature (it awaits
   :meth:`RBACService.get_field_visibility`); we ``await`` it here.

2. **Audit-on-failure** — the brief sketch only logged when the query
   succeeded. The spec §12 (国资审计) requires a complete trail, so we
   log a row for validator-rejected requests too. We use a synthetic
   ``result_count=0`` and the original ``question`` so an auditor can
   see what was attempted.

3. **RBAC service ownership** — the brief passed ``rbac_service`` and
   ``pii_detector`` to the constructor only to forward them to
   ``SqlGuard``. We construct ``SqlGuard`` internally and forward the
   session-bound :class:`RBACService` to it, so the orchestrator's
   public surface is cleaner. The PII detector is stateless and is
   instantiated inside the constructor.

4. **Audit fail-closed (REQ-056 Task 4)** — the original
   implementation wrapped the audit write in a try/except that
   logged a WARNING and returned the user response anyway. REQ-056
   reverses this: an audit-write failure now propagates out of
   :meth:`_audit` and therefore out of :meth:`ask`, so the user
   never receives ``result_rows`` for a request the regulator cannot
   trace. The :class:`AsyncSession` context manager rolls back the
   request on the unwound exception, so no partial state is
   persisted either.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.application.pii_detector import PIIDetector
from app.contexts.structured_data.application.query_planner import QueryPlanner
from app.contexts.structured_data.application.rbac_service import RBACService
from app.contexts.structured_data.application.result_explainer import ResultExplainer
from app.contexts.structured_data.application.semantic_validator import (
    SemanticValidator,
)
from app.contexts.structured_data.application.sql_guard import SqlGuard
from app.contexts.structured_data.domain.data_source_adapter import (
    DataSourceAdapter,
)
from app.contexts.structured_data.infrastructure.direct_db_adapter import (
    DirectDBAdapter,
)
from app.contexts.structured_data.infrastructure.imported_dataset_adapter import (
    ImportedDatasetAdapter,
)
from app.contexts.structured_data.infrastructure.mcp_adapter import MCPAdapter
from app.contexts.structured_data.infrastructure.permissions_repository import (
    PermissionsRepository,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# adapter factory type
# ---------------------------------------------------------------------------

AdapterFactory = Callable[[AsyncSession, dict], Awaitable[DataSourceAdapter]]


async def default_adapter_factory(
    session: AsyncSession, data_source_config: dict
) -> DataSourceAdapter:
    """Build the data-source adapter for a model's ``data_source_config``.

    REQ-057: routes all three declared :class:`DataSourceType` values.
    ``imported_dataset`` is the fully-implemented path; ``direct_db``
    hands back the V1 :class:`DirectDBAdapter` (read-only SELECT +
    table_name regex whitelist + limit clamp); ``mcp`` hands back the
    V1 :class:`MCPAdapter` whose :meth:`MCPAdapter.query` raises
    :class:`CapabilityUnavailableError` so the gap is explicit rather
    than masquerading as an empty result. Any other type raises
    ``ValueError`` so the router can surface a 400 instead of a 500.
    """
    ds_type = (data_source_config or {}).get("type", "imported_dataset")
    if ds_type == "imported_dataset":
        return ImportedDatasetAdapter(session)
    if ds_type == "direct_db":
        return DirectDBAdapter(session, config=data_source_config)
    if ds_type == "mcp":
        return MCPAdapter(session, config=data_source_config)
    raise ValueError(
        f"Unknown data_source type: {ds_type!r} "
        f"(supported: 'imported_dataset', 'direct_db', 'mcp')"
    )


# ---------------------------------------------------------------------------
# QueryService
# ---------------------------------------------------------------------------


class QueryService:
    """End-to-end orchestrator for the data-activation pipeline."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        *,
        planner: QueryPlanner | None = None,
        validator: SemanticValidator | None = None,
        adapter_factory: AdapterFactory | None = None,
        explainer: ResultExplainer | None = None,
        pii_detector: PIIDetector | None = None,
    ) -> None:
        """The orchestrator takes a *session factory* (not a single
        session) so the lifespan-level singleton can mint a fresh
        AsyncSession per request — matches the existing pattern in
        :func:`app.shared.infrastructure.database.get_session`.
        """
        self._session_factory = session_factory
        self._planner = planner or QueryPlanner()
        self._validator = validator or SemanticValidator()
        self._adapter_factory = adapter_factory or default_adapter_factory
        self._explainer = explainer or ResultExplainer()
        self._pii_detector = pii_detector or PIIDetector()

    def with_session(self, session: AsyncSession) -> QueryService:
        """Return a copy of this service bound to a single request session.

        The lifespan-built singleton holds a *factory* so it can mint a
        fresh session per request. The router calls this to rebind the
        request-scoped ``session`` instead, so the audit row + the
        response commit together (and tests can observe audit writes
        without racing a separate session). Collaborators are shared;
        only the session source changes. Keeping the rebind here avoids
        the router reaching into private attributes.
        """
        return QueryService(
            session_factory=lambda: session,
            planner=self._planner,
            validator=self._validator,
            adapter_factory=self._adapter_factory,
            explainer=self._explainer,
            pii_detector=self._pii_detector,
        )

    async def ask(
        self,
        *,
        question: str,
        semantic_model: Any,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        role: str,
        business_purpose: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        """Run the full pipeline and return the API-shaped dict.

        Returns either ``{"ok": True, "query_plan": ..., ...}`` or
        ``{"ok": False, "errors": [...], "suggestion": "..."}``. The
        audit row is written in BOTH cases — see module docstring.

        BUG-015: ``business_purpose`` is optional. When ``None`` (user
        opted out of typing context) the audit log records it as NULL
        — the spec §12 (国资审计) invariant now relies on
        ``user_id / question / query_plan / result_count`` plus the
        IP / user-agent instead of intent text.
        """
        started = time.time()
        async with self._session_factory() as session:
            rbac = RBACService(session)
            sql_guard = SqlGuard(rbac_service=rbac, pii_detector=self._pii_detector)
            audit_repo = PermissionsRepository(session)

            # ---------- 1. Planner ----------
            query_plan = await self._planner.plan(
                question=question,
                semantic_model=semantic_model,
            )

            # ---------- 2. Validator ----------
            errors = self._validator.validate(query_plan, semantic_model)
            if errors:
                duration_ms = int((time.time() - started) * 1000)
                await self._audit(
                    audit_repo=audit_repo,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    role=role,
                    business_purpose=business_purpose,
                    question=question,
                    query_plan=query_plan,
                    semantic_model=semantic_model,
                    result_count=0,
                    duration_ms=duration_ms,
                    ip=ip,
                    user_agent=user_agent,
                )
                await session.commit()
                return {
                    "ok": False,
                    "errors": errors,
                    "suggestion": (
                        "请尝试更明确的问题，如"
                        '"这企业过去 3 年的欠费金额"'
                    ),
                }

            # ---------- 3. Adapter ----------
            adapter = await self._adapter_factory(
                session, semantic_model.data_source_config
            )
            result_rows = await adapter.query(
                query_plan=query_plan,
                semantic_model=semantic_model,
                tenant_id=tenant_id,
                user_role=role,
            )

            # ---------- 4. SqlGuard ----------
            guard_result = await sql_guard.check_and_mask(
                rows=result_rows,
                semantic_model=semantic_model,
                role=role,
                tenant_id=tenant_id,
                entity_type=semantic_model.entity_type,
            )

            # ---------- 5. Explainer ----------
            explainer_result = await self._explainer.explain(
                result_rows=guard_result.rows,
                semantic_model=semantic_model,
                query_plan=query_plan,
                question=question,
            )

            duration_ms = int((time.time() - started) * 1000)

            # ---------- 6. Audit ----------
            await self._audit(
                audit_repo=audit_repo,
                user_id=user_id,
                tenant_id=tenant_id,
                role=role,
                business_purpose=business_purpose,
                question=question,
                query_plan=query_plan,
                semantic_model=semantic_model,
                result_count=len(guard_result.rows),
                duration_ms=duration_ms,
                ip=ip,
                user_agent=user_agent,
            )
            await session.commit()

            return {
                "ok": True,
                "query_plan": query_plan,
                "result_rows": guard_result.rows,
                "result_count": len(guard_result.rows),
                "summary": explainer_result.summary,
                "metric_values": explainer_result.metric_values,
                "filters_applied": explainer_result.filters_applied,
                "caveats": explainer_result.caveats,
                "confidence": explainer_result.confidence,
                "duration_ms": duration_ms,
            }

    # ------------------------------------------------------------------
    # internal — audit write helper
    # ------------------------------------------------------------------

    async def _audit(
        self,
        *,
        audit_repo: PermissionsRepository,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        role: str,
        business_purpose: str | None,
        question: str,
        query_plan: dict,
        semantic_model: Any,
        result_count: int,
        duration_ms: int,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        """Persist one row to ``metaedu.query_audit_log``.

        REQ-054: also writes ``catalog_id`` (resolved from
        ``semantic_model.catalog_id``) so every audit row carries the
        database attribution the regulator needs. The column is
        nullable, but the resolved semantic model always has a
        catalog_id set — a missing value here would indicate a bug
        upstream (the resolver must never return a model without
        catalog_id).

        REQ-056 Task 4: fail-closed. An audit-write failure MUST
        propagate out of this method (and therefore out of
        :meth:`ask`) — the user-visible ``result_rows`` are only
        returned after the audit row is durably written, otherwise we
        would leak sensitive data to a user whose activity the
        regulator cannot trace. This is a deliberate reversal of the
        pre-REQ-056 policy ("defensive: log and return the answer
        anyway") which the spec §12 (国资审计) integrity story
        requires we close.
        """
        # REQ-054: catalog_id from the resolved semantic model. The
        # dataclass declares it as ``uuid.UUID | None`` for backward
        # compat with pre-REQ-054 callers, but the router now guarantees
        # it is always set; we still defensively coerce to None if it's
        # somehow missing so the audit row never raises on missing
        # columns.
        catalog_id: uuid.UUID | None = getattr(semantic_model, "catalog_id", None)
        # REQ-056 Task 4: NO try/except. The exception propagates so
        # that ``ask`` aborts the request before returning result_rows.
        # ``session.commit()`` (the next line in ``ask``) is also
        # skipped because the exception unwinds the ``async with``
        # context manager, which rolls back the request session.
        await audit_repo.log_query(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            business_purpose=business_purpose,
            question=question,
            query_plan=query_plan,
            data_source_type=semantic_model.data_source_config.get(
                "type", "imported_dataset"
            ),
            data_source_ref=(
                str(semantic_model.dataset_id)
                if semantic_model.dataset_id
                else None
            ),
            result_count=result_count,
            duration_ms=duration_ms,
            ip=ip,
            user_agent=user_agent,
            catalog_id=catalog_id,
        )
