"""Production ``query_runner`` for SkillRunner ``internal_query`` steps (REQ-046 PR-5).

The SkillRunner's ``internal_query`` channel is deliberately injectable (PR-3):
the runner stays decoupled from the REQ-052 semantic layer. This module is the
assembly point that binds that injection to the real ``QueryService`` so an
``internal_query`` step actually executes a governed structured-data query.

Resolution policy (V0 single-tenant): internal park datasets live in one
catalog, configured via ``settings.dd_internal_query_catalog_id``. The active
semantic model is resolved by the dual key ``(tenant, catalog, entity_type)``
so a same-named entity in another catalog is never read. Ambiguity (multiple
active rows) and an unconfigured catalog both fail closed — the step never
queries the wrong or an unscoped dataset.

The runner-facing callable returns the ``QueryService.ask`` dict unchanged on
success (it already carries ``ok`` + ``audit_id``, spec §4.5 / AC-4), and a
fail-closed ``{"ok": False, ...}`` when no active semantic model exists — the
SkillRunner turns ``ok=False`` into an audited ``tool_error`` (never fabricated).
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
)
from app.contexts.structured_data.application.query_service import QueryService
from app.contexts.structured_data.infrastructure.semantic_model_repository import (
    SemanticModelRepository,
)

QueryRunner = Callable[..., Awaitable[dict]]


def _catalog_id() -> uuid.UUID:
    raw = settings.dd_internal_query_catalog_id
    try:
        return uuid.UUID(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "DD_INTERNAL_QUERY_CATALOG_ID 未配置或非法，internal_query step 无法定位语义模型"
        ) from exc


def build_dd_internal_query_runner(
    query_service: QueryService, session: AsyncSession
) -> QueryRunner:
    """Bind a request-scoped ``QueryService`` + session into a query_runner.

    Mirrors the ``query_router`` wiring (``app.state.query_service`` rebound to
    the request session via ``with_session``) so the query audit row commits in
    the same transaction as the skill execution audit.
    """
    bound_service = query_service.with_session(session)
    repo = SemanticModelRepository(session)

    async def _run(
        *,
        question: str,
        entity_type: str | None,
        subject: dict,
        caller: InvocationCaller,
        tenant_id: uuid.UUID,
    ) -> dict[str, Any]:
        if not entity_type:
            return {"ok": False, "errors": ["internal_query step 缺少 entity_type"]}
        model = await repo.get_active_by_catalog_and_entity_type(
            tenant_id=tenant_id,
            catalog_id=_catalog_id(),
            entity_type=entity_type,
        )
        if model is None:
            return {
                "ok": False,
                "errors": [
                    f"entity_type '{entity_type}' 在 DD 内部问数 catalog 无 active 语义模型"
                ],
            }
        return await bound_service.ask(
            question=question,
            semantic_model=model,
            user_id=caller.user_id,
            tenant_id=tenant_id,
            role=caller.role,
            business_purpose="REQ-046 园区招商背调 internal_query",
        )

    return _run
