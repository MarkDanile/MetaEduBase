"""POST /api/v1/data-query/ask — the single entry point for ask-the-data.

REQ-052 Task 5: the request handler is intentionally thin. All real
work is delegated to :class:`QueryService`; the router's only jobs are:

1. Validate the request payload (pydantic — ``business_purpose`` >= 5
   chars; missing fields → 422).
2. Authenticate via the existing
   :func:`app.contexts.identity.interfaces.api.dependencies.get_current_user`.
3. Resolve the :class:`SemanticModel` from the DB (via
   :meth:`SemanticModelRepository.get_active_by_entity_type` — the
   Task 5 deviation).
4. Call :meth:`QueryService.ask` and serialise the result.

DI wiring: the router reads ``request.app.state.query_service`` (built
at lifespan startup, see ``app.main.lifespan``) and binds the
request-scoped :class:`AsyncSession` (injected via
:func:`app.shared.infrastructure.database.get_session`) so the audit
row commits in the same transaction as the response.

Brief deviations:

- **Auth import path** — the brief imported
  ``app.contexts.knowledge.interfaces.api.auth.get_current_user`` which
  doesn't exist in this codebase. The real auth dependency is
  :func:`app.contexts.identity.interfaces.api.dependencies.get_current_user`
  and returns a ``dict`` (not a pydantic model), so we read
  ``user["id"]``, ``user["tenant_id"]``, ``user["role"]``.

- **SemanticModel lookup** — the brief passed
  ``data_source_config={}`` to ``get_by_entity_type`` which silently
  fails. We use the new :meth:`get_active_by_entity_type` helper added
  in Task 5 (option A in the deviation plan).

- **Missing entity_type** — returns 404 (semantic model not found),
  not 422. ``entity_type`` IS a required field in pydantic but the
  *value* may not exist in the DB — that's a 404 not a 422.

- **Session injection** — the brief sketch read
  ``request.state.db_session`` (assumed middleware-injected). The
  codebase uses FastAPI ``Depends(get_session)`` for the
  request-scoped session, so we use that pattern.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.structured_data.application.query_service import QueryService
from app.contexts.structured_data.infrastructure.semantic_model_repository import (
    SemanticModelRepository,
)
from app.shared.infrastructure.database import get_session

router = APIRouter(prefix="/api/v1/data-query", tags=["data-query"])


class AskRequest(BaseModel):
    """Pydantic request body for POST /api/v1/data-query/ask.

    ``business_purpose`` is mandatory (min_length=5) per REQ-052 §12
    (国资审计). Missing or too-short returns 422.
    """

    entity_type: str = Field(..., description="entity_type, e.g. 'bill'")
    question: str = Field(..., min_length=1)
    business_purpose: str = Field(
        ..., min_length=5, description="查询背景（必填，用于审计）"
    )
    confirmed_company_name: str | None = None


class AskResponse(BaseModel):
    """Response shape returned to the client.

    Every field is optional because a failed validation returns
    ``{"ok": False, "errors": [...], "suggestion": "..."}`` without the
    success fields populated.
    """

    ok: bool
    query_plan: dict | None = None
    result_rows: list[dict] | None = None
    result_count: int | None = None
    summary: str | None = None
    metric_values: dict | None = None
    filters_applied: dict | None = None
    caveats: list[str] | None = None
    confidence: str | None = None
    duration_ms: int | None = None
    errors: list[str] | None = None
    suggestion: str | None = None


def _bind_service_to_session(
    base_service: QueryService, db_session: AsyncSession
) -> QueryService:
    """Return a new :class:`QueryService` bound to the request session.

    The lifespan-built service holds a *factory* (``async_session_factory``)
    so it can mint fresh sessions per request. We reuse the
    request-scoped ``db_session`` instead so the audit row + the
    response commit together (and so tests can observe audit writes
    without racing a separate session).
    """
    return QueryService(
        session_factory=lambda: db_session,
        planner=base_service._planner,
        validator=base_service._validator,
        adapter_factory=base_service._adapter_factory,
        explainer=base_service._explainer,
        pii_detector=base_service._pii_detector,
    )


@router.post("/ask", response_model=AskResponse)
async def ask(
    req: AskRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """问数 API：用户传入问题 + 业务背景，返回 query_plan + 结果 + 摘要。"""
    # ---- auth ----
    tenant_id = uuid.UUID(str(current_user["tenant_id"]))
    user_id = uuid.UUID(str(current_user["id"]))
    # ``current_user["role"]`` carries the user's app-level role (e.g.
    # ``"super_admin"``); SqlGuard's RBAC fallback handles unknown roles
    # safely (MASKED default), so we don't need to translate.
    role = str(current_user.get("role", "employee"))

    # ---- resolve semantic model ----
    repo = SemanticModelRepository(db_session)
    semantic_model = await repo.get_active_by_entity_type(
        tenant_id=tenant_id, entity_type=req.entity_type
    )
    if semantic_model is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"entity_type '{req.entity_type}' not found in semantic model "
                f"for tenant {tenant_id}"
            ),
        )

    # ---- delegate to the orchestrator ----
    base_service: QueryService = request.app.state.query_service
    bound_service = _bind_service_to_session(base_service, db_session)

    result = await bound_service.ask(
        question=req.question,
        semantic_model=semantic_model,
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        business_purpose=req.business_purpose,
        confirmed_company_name=req.confirmed_company_name,
        ip=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    return AskResponse(**result)