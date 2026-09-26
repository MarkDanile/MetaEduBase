"""DD -> skill_registry skill execution port adapter (TD-085 Slice C).

due_diligence is the business consumer of the generic SkillRunner's
``internal_query`` channel (REQ-046 v2 contract, spec ADR-085-3). This module
is the single assembly point that binds the generic runner to DD business
semantics, so the runner itself stays business-neutral:

- ``query_runner``: the DD internal query channel (migrated here from
  ``skill_registry.application.dd_query_runner``) — resolves park datasets
  through the 客户/合同/房间 join graph and fails closed on ambiguity.
- ``step_params_mapper``: QCC tool param shaping (migrated out of the
  generic runner) — real QCC tools take a single ``searchKey``.
- ``report_persona``: the DD report persona for LLM synthesis.

Direction rule: due_diligence -> skill_registry is the ONLY allowed edge;
skill_registry must never import this module (guarded by
``tests/contexts/due_diligence/test_dd_skill_caller.py``).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.due_diligence.application.dd_query_runner import (
    build_dd_internal_query_runner,
)
from app.contexts.skill_registry.application.skill_runner import SkillRunner
from app.contexts.structured_data.application.query_service import QueryService

DD_REPORT_PERSONA = "你是企业尽调报告助手。"


def dd_mcp_step_params(server: str, subject: Any) -> dict:
    """Map the DD skill ``subject`` to the tool params an MCP server expects.

    Real QCC tools (any ``qcc*`` server — company / risk / history / executive)
    all take a single ``searchKey`` (the company name); the internal customer
    MCP takes ``company_name`` + ``credit_code`` (the same shape as
    ``confirmed_subject``). Without this mapping a QCC step would send
    ``{company_name, credit_code}`` and QCC would reject it (``searchKey``
    undefined) — the gap AC-8 surfaced. Non-QCC servers get the subject as-is.

    (Migrated verbatim from ``skill_runner._mcp_step_params``, TD-085 Slice C.)
    """
    if server.startswith("qcc") and isinstance(subject, dict):
        name = subject.get("company_name") or subject.get("searchKey") or ""
        return {"searchKey": name}
    return subject if isinstance(subject, dict) else {}


def build_dd_skill_runner(
    query_service: QueryService, session: AsyncSession
) -> SkillRunner:
    """Assemble the DD-wired SkillRunner — the single DD assembly point.

    Mirrors the previous inline wiring in ``dd_router`` /
    ``skill_registry_router``: binds the production ``internal_query``
    channel (request-scoped ``QueryService`` re-bound to ``session`` so the
    query audit row commits in the same transaction as the skill execution
    audit) plus DD param shaping and the DD report persona.
    """
    return SkillRunner(
        session,
        query_runner=build_dd_internal_query_runner(query_service, session),
        step_params_mapper=dd_mcp_step_params,
        report_persona=DD_REPORT_PERSONA,
    )
