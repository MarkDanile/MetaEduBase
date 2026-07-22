"""Subject Resolver: 企业主体识别与确认 (REQ-046 Slice 1, spec §4.2 / AC-1).

Wraps the QCC entity-anchoring rule: a raw company-name input (简称 / 品牌 /
不完整名称) must be resolved to candidate subjects via the QCC anchoring tool
and confirmed by the user before any downstream risk / shareholder tool may
run. This module only ever calls the *anchoring* tool — it never touches
risk-scan or profile tools, so an unconfirmed subject cannot leak downstream.

The resolver delegates the actual MCP call to ``MCPInvocationService`` (the
single orchestration entry from REQ-044), inheriting its enabled / role /
credential gates and digest-only audit. Candidate subjects are returned to the
business caller only; they never appear in audit columns (which hold digests).
"""
from __future__ import annotations

import json
import uuid

from app.contexts.due_diligence.domain.dd_task import SubjectCandidate
from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
    MCPInvocationService,
)

# QCC 实体锚定工具(spec §4.2;若运行时该工具不存在,降级方案见 plan 风险点 1)
_ANCHOR_TOOL = "get_company_by_query"
_QCC_SERVER = "qcc"


def _parse_candidates(payload: dict) -> list[dict]:
    """Extract the company list from a real QCC ``get_company_by_query`` result.

    The MCP envelope is ``{"content": [{"type": "text", "text": "<json>"}]}``;
    the inner JSON holds the company array under ``企业信息`` with fields
    ``企业名称`` / ``统一社会信用代码``. Both the envelope and the inner JSON
    are tolerated in either already-parsed or raw form so the resolver stays
    robust to client normalization. Anything unparseable yields ``[]`` (AC-8:
    no match -> empty, never fabricated).
    """
    inner: object = payload
    content = payload.get("content") if isinstance(payload, dict) else None
    if isinstance(content, list) and content:
        text = content[0].get("text") if isinstance(content[0], dict) else None
        if isinstance(text, str):
            try:
                inner = json.loads(text)
            except (ValueError, TypeError):
                return []
    if not isinstance(inner, dict):
        return []
    companies = inner.get("企业信息") or inner.get("items") or []
    if not isinstance(companies, list):
        return []
    return [c for c in companies if isinstance(c, dict)]


class SubjectResolver:
    """Resolve a raw company-name query to anchor candidates via QCC."""

    def __init__(self, invocation: MCPInvocationService) -> None:
        self._invocation = invocation

    async def resolve(
        self,
        *,
        tenant_id: uuid.UUID,
        query: str,
        caller: InvocationCaller,
    ) -> list[SubjectCandidate]:
        """Anchor ``query`` to candidate subjects; empty list = no match.

        The user must pick one candidate (or refine keywords when empty) and
        confirm it before the task may run — see ``DdTask.assert_can_run``.
        """
        result = await self._invocation.invoke(
            tenant_id=tenant_id,
            server_code=_QCC_SERVER,
            tool_name=_ANCHOR_TOOL,
            params={"searchKey": query},
            caller=caller,
        )
        candidates: list[SubjectCandidate] = []
        for item in _parse_candidates(result):
            name = item.get("企业名称") or item.get("company_name") or ""
            code = item.get("统一社会信用代码") or item.get("credit_code")
            if name:
                candidates.append(SubjectCandidate(company_name=name, credit_code=code))
        return candidates

    @staticmethod
    def to_candidate(company_name: str, credit_code: str | None) -> SubjectCandidate:
        """Build the candidate the user confirmed (verbatim, no re-query)."""
        return SubjectCandidate(company_name=company_name, credit_code=credit_code)
