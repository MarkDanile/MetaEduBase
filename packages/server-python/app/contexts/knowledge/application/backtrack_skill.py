"""REQ-046 / REQ-052 Task 8 — 背调 Skill（V0）。

``BacktrackSkill`` 是 REQ-046 企业 360 背调工作台接入 REQ-052 智能问数
的 Skill 入口。背调流程在每个数据维度（合同 / 账单 / 工单 …）调用一次
``BacktrackSkill.execute``，Skill 内部：

1. 通过注入的 ``semantic_model_repository_factory`` 拿到
   :class:`SemanticModelRepository`，按 ``(tenant_id, entity_type)`` 查
   active semantic model（V0 默认 ``entity_type="bill"``）。
2. 把 ``company_name + question`` 拼成完整问句，传给 REQ-052 Task 5 的
   :meth:`QueryService.ask`（与 AI Chat tool calling 复用同一入口 —
   audit 行由 QueryService 写入；spec §12 国资审计）。
3. 把结果包装成 ``evidence_refs`` 返回给上游（V0 暂不持久化；REQ-046
   后续 task 加 ``EvidenceRepository`` 落盘）。

设计要点：

- **直接调 ``QueryService.ask``，不走 AI Chat tool calling** —— 这是
  REQ-046 背调场景的独立 Skill，与 AI Chat 的 tool calling 是两条
  并行路径。两条路径都消费同一个 ``QueryService``，audit row 自然落
  在同一张表（``metaedu.query_audit_log``）。
- **无状态、可注入** —— 通过 ``query_service`` + ``semantic_model_repository_factory``
  注入，不直接依赖 FastAPI lifespan / DB；测试可以传 AsyncMock。
- **V0 不写 evidence_repo** —— brief 假设 ``evidence_repo`` 已存在
  （沿用 REQ-046 spec），但 REQ-046 V0 还没建 ``EvidenceRepository``。
  evidence_ref 通过返回 dict 透传给上游，由后续 REQ-046 task 加持久化。

Brief 偏差（见 commit message + report）：

1. **``evidence_repo`` 未持久化** —— V0 选择 (A)：evidence_ref 在返回
   dict 里，不落盘。
2. **``semantic_model=...`` 占位 → 用 repo factory 默认 ``entity_type="bill"``**。
3. **``role`` 不硬编码** —— 从 caller 传入，默认 ``"employee"``（与 AI
   Chat tool calling 默认值一致）。
4. **``confirmed_company_name=company_name`` 透传** —— 与 Task 5
   ``QueryService.ask`` 签名一致，确保 SqlGuard 知道是已确认企业。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Defaults — V0 contract
# ---------------------------------------------------------------------------

#: V0 默认 entity_type；与 REQ-052 §3 Slice 0 "账单" 维度一致。
DEFAULT_ENTITY_TYPE = "bill"

#: V0 默认 role；背调 Skill 通常以 employee 身份跑（与 AI Chat tool
#: calling 默认 role 对齐）。caller 可覆盖。
DEFAULT_ROLE = "employee"

#: V0 默认 business_purpose —— REQ-052 §12 国资审计必须非空。
DEFAULT_BUSINESS_PURPOSE = "企业 360 背调"


class BacktrackSkill:
    """REQ-046 背调 Skill —— REQ-052 问数入口（V0）。

    ``execute`` 是 Skill 的唯一对外方法。返回 dict 包含：

    - ``answer`` —— QueryService.ask 的 summary（自然语言结论）
    - ``evidence_refs`` —— ``[{"type": "data_query", "ref": <uuid>, ...}]``
    - ``raw_data`` —— QueryService.ask 的 ``result_rows``
    - ``query_plan`` —— QueryService.ask 的 ``query_plan``

    V0 evidence_ref 不持久化；由 REQ-046 后续 task 加 ``EvidenceRepository``。
    """

    def __init__(
        self,
        query_service: Any,
        semantic_model_repository_factory: Callable[[AsyncSession], Any] | None = None,
    ) -> None:
        """构造 Skill。

        ``query_service`` —— REQ-052 Task 5 的 :class:`QueryService` 实例
        （production 由 lifespan 构造，测试用 AsyncMock）。

        ``semantic_model_repository_factory`` —— 接收 ``AsyncSession``、返回
        SemanticModelRepository 实例的工厂。生产路径默认用
        ``SemanticModelRepository(session)``（与 AI Chat tool calling 复用
        同一 repo）。
        """
        self._query_service = query_service
        if semantic_model_repository_factory is None:
            def _default_repo_factory(session: AsyncSession):
                from app.contexts.structured_data.infrastructure.semantic_model_repository import (
                    SemanticModelRepository,
                )
                return SemanticModelRepository(session)
            self._semantic_model_repository_factory = _default_repo_factory
        else:
            self._semantic_model_repository_factory = semantic_model_repository_factory

    async def execute(
        self,
        *,
        company_name: str,
        question: str,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        role: str = DEFAULT_ROLE,
        business_purpose: str = DEFAULT_BUSINESS_PURPOSE,
        entity_type: str = DEFAULT_ENTITY_TYPE,
        session: AsyncSession | None = None,
    ) -> dict:
        """执行一次问数 → 返回 evidence_ref。

        Args:
            company_name: 已确认的企业主体名（用于 SqlGuard 与 audit）。
            question: 用户问句（不带企业名前缀；Skill 内部拼 ``f"{company} {q}"``）。
            user_id: 调用方 user UUID（写 audit 行）。
            tenant_id: 租户 UUID（写 audit 行 + semantic_model 查询）。
            role: 5 类角色之一（employee / analyst / admin / auditor / system）。
            business_purpose: 业务背景（spec §12 国资审计必填）。
            entity_type: 实体类型（bill / contract / ticket 等）；默认 ``"bill"``。
            session: 可选 AsyncSession；生产路径由调用方注入，测试用 mock。

        Returns:
            ``{"answer": str, "evidence_refs": [dict], "raw_data": list,
               "query_plan": dict}``。
        """
        # ---- 1. Resolve semantic model ------------------------------------
        # V0 default entity_type="bill"; production will pass through caller's
        # semantic_model_resolver once REQ-046's broader Skill registry lands.
        repo = self._semantic_model_repository_factory(session)
        semantic_model = await repo.get_active_by_entity_type(
            tenant_id=tenant_id, entity_type=entity_type
        )
        if semantic_model is None:
            # No active semantic model for this entity_type + tenant —
            # degrade gracefully so the upstream 背调 report doesn't blow up.
            logger.warning(
                "BacktrackSkill: no semantic_model for tenant=%s entity_type=%r; "
                "skipping QueryService.ask.",
                tenant_id,
                entity_type,
            )
            return {
                "answer": "",
                "evidence_refs": [],
                "raw_data": [],
                "query_plan": {},
            }

        # ---- 2. Call QueryService.ask (writes audit row, spec §12) --------
        full_question = f"{company_name} {question}"
        result = await self._query_service.ask(
            question=full_question,
            semantic_model=semantic_model,
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            business_purpose=business_purpose,
            confirmed_company_name=company_name,
        )

        # ---- 3. Build evidence_ref (V0: in-memory, not persisted) ----------
        evidence_ref: dict[str, Any] = {
            "type": "data_query",
            "ref": str(uuid.uuid4()),
            "question": question,
            "summary": result.get("summary"),
            "result_count": result.get("result_count", 0),
            "source": "REQ-052 semantic query",
        }
        # Forward query_plan so the report can link back to the executed plan
        if result.get("query_plan") is not None:
            evidence_ref["query_plan"] = result["query_plan"]
        # Forward caveats when present (validator / SqlGuard warnings)
        caveats = result.get("caveats")
        if caveats:
            evidence_ref["caveats"] = list(caveats)

        return {
            "answer": result.get("summary", ""),
            "evidence_refs": [evidence_ref],
            "raw_data": result.get("result_rows", []),
            "query_plan": result.get("query_plan", {}),
        }
