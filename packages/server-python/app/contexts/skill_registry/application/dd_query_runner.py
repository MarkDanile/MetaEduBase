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

from sqlalchemy import String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
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

# Subject-resolution join graph (REQ-046 AC-8). The Chinese park datasets have
# no ``company_name`` column; each queriable entity is scoped to the confirmed
# subject through a relation key resolved from the customer dataset:
#   bill       — has 客户ID directly            -> eq 客户ID
#   lease_term — has 合同ID; 客户ID -> 合同ID (contract)   -> in 合同ID
#   ticket     — has 房间ID; 客户ID -> 合同ID -> 房间ID
#                (contract_property)                       -> in 房间ID
# Mirrors the proven two-stage lookup in ``app.internal_mcp.customer_repository``.


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

    async def _model_for(entity_type: str, tenant_id: uuid.UUID):
        return await repo.get_active_by_catalog_and_entity_type(
            tenant_id=tenant_id, catalog_id=_catalog_id(), entity_type=entity_type
        )

    async def _resolve_customer_id(tenant_id: uuid.UUID, subject: dict) -> str | None:
        """Resolve the confirmed subject to its ``客户ID`` via the customer model.

        Three-tier lookup, most-authoritative first (REQ-046 AC-8). The park
        customer dataset is synthetic, so a real company's QCC credit code may
        not exist there; exact name and unique fuzzy name are the fallbacks:

        1. ``统一社会信用代码`` exact (stable, unique) — when a credit code is
           confirmed.
        2. ``客户名称`` exact (registered full name).
        3. ``客户名称`` fuzzy (``%name%``) — only when it collapses to a single
           distinct ``客户ID``; an ambiguous match returns ``None`` rather than
           guessing the wrong subject (fail-closed).

        Returns ``None`` when no tier resolves a unique subject.
        """
        customer = await _model_for("customer", tenant_id)
        if customer is None or customer.dataset_id is None:
            return None
        company_name = (subject or {}).get("company_name")
        credit_code = (subject or {}).get("credit_code")
        ds = customer.dataset_id

        async def _by(column: str, value: str) -> str | None:
            return await session.scalar(
                text(
                    f"SELECT data->>'客户ID' FROM metaedu.dataset_rows "
                    f"WHERE tenant_id = :tid AND dataset_id = :ds "
                    f"AND data->>'{column}' = :v ORDER BY row_index LIMIT 1"
                ),
                {"tid": tenant_id, "ds": ds, "v": value},
            )

        if credit_code:
            found = await _by("统一社会信用代码", credit_code)
            if found:
                return found
        if not company_name:
            return None
        found = await _by("客户名称", company_name)
        if found:
            return found
        # Fuzzy fallback — unique distinct 客户ID only.
        stmt = text(
            "SELECT DISTINCT data->>'客户ID', data->>'客户名称' "
            "FROM metaedu.dataset_rows WHERE tenant_id = :tid AND dataset_id = :ds "
            "AND data->>'客户名称' LIKE :pat"
        )
        rows = (
            await session.execute(
                stmt, {"tid": tenant_id, "ds": ds, "pat": f"%{company_name}%"}
            )
        ).all()
        distinct_ids = {r[0] for r in rows if r[0]}
        if len(distinct_ids) == 1:
            return distinct_ids.pop()
        return None

    async def _resolve_ids(
        tenant_id: uuid.UUID,
        *,
        entity_type: str,
        in_column: str,
        out_column: str,
        values: list[str],
    ) -> list[str]:
        """Map ``in_column`` values to ``out_column`` values via an entity dataset.

        Used to walk the join graph one hop (客户ID -> 合同ID, 合同ID -> 房间ID).
        Returns ``[]`` when the entity has no active model or no rows match.
        """
        model = await _model_for(entity_type, tenant_id)
        if model is None or model.dataset_id is None or not values:
            return []
        stmt = text(
            f"SELECT DISTINCT data->>'{out_column}' FROM metaedu.dataset_rows "
            f"WHERE tenant_id = :tid AND dataset_id = :ds "
            f"AND data->>'{in_column}' = ANY(:vals)"
        ).bindparams(bindparam("vals", type_=ARRAY(String())))
        result = await session.scalars(
            stmt, {"tid": tenant_id, "ds": model.dataset_id, "vals": list(values)}
        )
        return [v for v in result.all() if v]

    async def _resolve_confirmed_filters(
        tenant_id: uuid.UUID, entity_type: str, subject: dict
    ) -> dict | None:
        """Build the subject-scoping filter for ``entity_type``; ``None`` = fail-closed.

        Every internal_query question is about ONE confirmed enterprise, so a
        filter that cannot be resolved must NOT silently degrade to a park-wide
        scan — return ``None`` and let the runner fail the step closed.
        """
        customer_id = await _resolve_customer_id(tenant_id, subject)
        if not customer_id:
            return None
        if entity_type == "bill":
            return {"客户ID": {"op": "eq", "value": customer_id}}
        if entity_type == "lease_term":
            contract_ids = await _resolve_ids(
                tenant_id, entity_type="contract",
                in_column="客户ID", out_column="合同ID", values=[customer_id],
            )
            if not contract_ids:
                return None
            return {"合同ID": {"op": "in", "value": contract_ids}}
        if entity_type == "ticket":
            contract_ids = await _resolve_ids(
                tenant_id, entity_type="contract",
                in_column="客户ID", out_column="合同ID", values=[customer_id],
            )
            if not contract_ids:
                return None
            room_ids = await _resolve_ids(
                tenant_id, entity_type="contract_property",
                in_column="合同ID", out_column="房间ID", values=contract_ids,
            )
            if not room_ids:
                return None
            return {"房间ID": {"op": "in", "value": room_ids}}
        # Unknown entity_type: no join graph defined — scope by 客户ID only if the
        # model carries that column, else fail closed.
        return None

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
        model = await _model_for(entity_type, tenant_id)
        if model is None:
            return {
                "ok": False,
                "errors": [
                    f"entity_type '{entity_type}' 在 DD 内部问数 catalog 无 active 语义模型"
                ],
            }
        confirmed_filters = await _resolve_confirmed_filters(
            tenant_id, entity_type, subject
        )
        if confirmed_filters is None:
            return {
                "ok": False,
                "errors": [
                    f"主体无法映射到 {entity_type} 数据(客户/合同/房间解析落空),已 fail-closed"
                ],
            }
        return await bound_service.ask(
            question=question,
            semantic_model=model,
            user_id=caller.user_id,
            tenant_id=tenant_id,
            role=caller.role,
            business_purpose="REQ-046 园区招商背调 internal_query",
            confirmed_filters=confirmed_filters,
        )

    return _run
