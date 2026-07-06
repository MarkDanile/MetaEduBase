"""REQ-052 Task 8 — REQ-046 背调 Skill 接入。

测试 ``BacktrackSkill`` —— REQ-046 企业 360 背调流程接入 REQ-052 问数
闭环的 V0 入口：

1. ``test_backtrack_skill_happy_path_calls_query_service`` — Happy path:
   Skill.execute → QueryService.ask 被调用，参数正确（question 加
   ``company_name`` 前缀、confirmed_company_name、business_purpose、
   semantic_model、role、user_id、tenant_id）。
2. ``test_backtrack_skill_looks_up_semantic_model_by_entity_type`` — Skill
   通过 ``semantic_model_repository_factory`` 拿到 repo，并调
   ``get_active_by_entity_type(tenant_id, entity_type)``。
3. ``test_backtrack_skill_evidence_ref_shape`` — 返回的 ``evidence_refs``
   形状完整：type/ref/question/summary/result_count/source。
4. ``test_backtrack_skill_returns_answer_and_raw_data`` — 返回的 dict
   包含 ``answer``（=summary）、``evidence_refs``、``raw_data``
   （=result_rows）、``query_plan``。

设计要点（TDD 锚点）：

- 不依赖真实 PostgreSQL / QueryService —— 测试用 ``AsyncMock`` 替代
  ``QueryService``，用 ``MagicMock`` 替代 ``SemanticModelRepository``。
- ``BacktrackSkill`` 是直接调 ``QueryService.ask`` 的 Skill 入口（不走
  AI Chat tool calling）；是独立的 V0 流程。
- V0 不持久化 evidence_ref（REQ-046 后续 task 加 ``EvidenceRepository``）；
  evidence_ref 通过返回 dict 提供给上游。
- V0 默认 ``entity_type="bill"``；通过 ``entity_type`` kwarg 可覆盖。
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.contexts.knowledge.application.backtrack_skill import BacktrackSkill

# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------


def _make_fake_semantic_model() -> MagicMock:
    """SemanticModel mock — BacktrackSkill 仅把 semantic_model 透传给
    QueryService.ask，不需要真实属性访问。"""
    sm = MagicMock()
    sm.entity_type = "bill"
    sm.entity_name = "账单"
    sm.data_source_config = {"type": "imported_dataset", "dataset_id": "ds-test"}
    sm.id = uuid.uuid4()
    sm.tenant_id = uuid.uuid4()
    return sm


def _make_fake_query_service(
    return_value: dict[str, Any] | None = None,
) -> AsyncMock:
    """QueryService mock — 默认返回一个 ``ok=True`` 的 stub 响应。"""
    qs = AsyncMock()
    qs.ask = AsyncMock(
        return_value=return_value
        or {
            "ok": True,
            "query_plan": {"metric": "total_unpaid", "filters": {}},
            "result_rows": [{"company_name": "江苏神码信息技术有限公司", "total_unpaid": 125000.0}],
            "result_count": 1,
            "summary": "过去三年累计欠费 12.5 万元",
            "metric_values": {"total_unpaid": {"value": 125000.0, "label": "累计欠费"}},
            "filters_applied": {},
            "caveats": [],
            "confidence": "high",
            "duration_ms": 42,
        }
    )
    return qs


def _make_fake_semantic_repo_factory(semantic_model: Any | None = None) -> Any:
    """构建一个返回 fake ``SemanticModelRepository`` 的 factory。"""
    repo = MagicMock()
    repo.get_active_by_entity_type = AsyncMock(return_value=semantic_model)
    return lambda session: repo


def _build_skill(
    *,
    query_service: AsyncMock | None = None,
    semantic_model: Any | None = None,
    semantic_repo_factory: Any | None = None,
) -> tuple[BacktrackSkill, AsyncMock, MagicMock]:
    """组装 BacktrackSkill + 返回 mock 以便断言。"""
    qs = query_service or _make_fake_query_service()
    sm = semantic_model if semantic_model is not None else _make_fake_semantic_model()

    if semantic_repo_factory is None:
        semantic_repo_factory = _make_fake_semantic_repo_factory(semantic_model=sm)

    skill = BacktrackSkill(
        query_service=qs,
        semantic_model_repository_factory=semantic_repo_factory,
    )
    # 提取 inner repo mock（用于断言 get_active_by_entity_type 调用）
    fake_repo = semantic_repo_factory(MagicMock())
    return skill, qs, fake_repo


# ---------------------------------------------------------------------------
# 1) Happy path — BacktrackSkill.execute → QueryService.ask
# ---------------------------------------------------------------------------


async def test_backtrack_skill_happy_path_calls_query_service() -> None:
    """Skill.execute → QueryService.ask 被调一次，参数正确。"""
    skill, query_service, _ = _build_skill()

    company_name = "江苏神码信息技术有限公司"
    question = "这企业过去 3 年的欠费金额"
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    result = await skill.execute(
        company_name=company_name,
        question=question,
        user_id=user_id,
        tenant_id=tenant_id,
    )

    # 1. QueryService.ask fired exactly once
    assert query_service.ask.await_count == 1, (
        f"QueryService.ask should be called exactly once; got "
        f"{query_service.ask.await_count}"
    )

    # 2. Parameters are correct
    ask_kwargs = query_service.ask.await_args.kwargs
    # question is "company_name + question" concatenation
    assert ask_kwargs["question"] == f"{company_name} {question}"
    # semantic_model is the one resolved from the repo
    assert ask_kwargs["semantic_model"] is not None
    # audit chain kwargs
    assert ask_kwargs["user_id"] == user_id
    assert ask_kwargs["tenant_id"] == tenant_id
    assert ask_kwargs["role"] == "employee"  # V0 default
    assert ask_kwargs["business_purpose"] == "企业 360 背调"  # V0 default
    # confirmed_company_name keeps the canonical name for SqlGuard/audit
    assert ask_kwargs["confirmed_company_name"] == company_name

    # 3. Return shape
    assert "evidence_refs" in result
    assert any(r["type"] == "data_query" for r in result["evidence_refs"])


# ---------------------------------------------------------------------------
# 2) semantic_model lookup — BacktrackSkill uses repo.get_active_by_entity_type
# ---------------------------------------------------------------------------


async def test_backtrack_skill_looks_up_semantic_model_by_entity_type() -> None:
    """Skill 通过 factory 拿 repo，并按 tenant_id + entity_type 查询。"""
    skill, query_service, fake_repo = _build_skill()

    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    await skill.execute(
        company_name="某企业",
        question="这企业合同情况",
        user_id=user_id,
        tenant_id=tenant_id,
    )

    # 1. SemanticModelRepository.get_active_by_entity_type called once
    assert fake_repo.get_active_by_entity_type.await_count == 1

    # 2. Call kwargs match: tenant_id (UUID) + entity_type (default "bill")
    call_kwargs = fake_repo.get_active_by_entity_type.await_args.kwargs
    assert call_kwargs["tenant_id"] == tenant_id
    assert call_kwargs["entity_type"] == "bill"

    # 3. QueryService.ask received the same semantic_model that repo returned
    ask_kwargs = query_service.ask.await_args.kwargs
    assert ask_kwargs["semantic_model"] is not None


async def test_backtrack_skill_uses_custom_entity_type() -> None:
    """entity_type 显式传入时，传给 repo.get_active_by_entity_type。"""
    skill, _, fake_repo = _build_skill()

    await skill.execute(
        company_name="某企业",
        question="这企业合同情况",
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        entity_type="contract",
    )

    call_kwargs = fake_repo.get_active_by_entity_type.await_args.kwargs
    assert call_kwargs["entity_type"] == "contract"


# ---------------------------------------------------------------------------
# 3) evidence_ref shape — all required fields present
# ---------------------------------------------------------------------------


async def test_backtrack_skill_evidence_ref_shape() -> None:
    """evidence_ref 包含 type/ref/question/summary/result_count/source。"""
    skill, _, _ = _build_skill()

    question = "这企业过去 3 年的欠费金额"
    result = await skill.execute(
        company_name="江苏神码信息技术有限公司",
        question=question,
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
    )

    assert len(result["evidence_refs"]) == 1
    ref = result["evidence_refs"][0]
    # All required fields
    assert ref["type"] == "data_query"
    # ref is a UUID-shaped string
    assert isinstance(ref["ref"], str)
    uuid.UUID(ref["ref"])  # raises if not a valid UUID
    # question preserves the user-facing question (not the prefixed one)
    assert ref["question"] == question
    # summary comes from QueryService.ask result
    assert ref["summary"] == "过去三年累计欠费 12.5 万元"
    assert ref["result_count"] == 1
    assert ref["source"] == "REQ-052 semantic query"


# ---------------------------------------------------------------------------
# 4) Return shape — answer + evidence_refs + raw_data + query_plan
# ---------------------------------------------------------------------------


async def test_backtrack_skill_returns_answer_and_raw_data() -> None:
    """返回 dict 包含 answer (=summary) / evidence_refs / raw_data (=result_rows)
    / query_plan。"""
    skill, _, _ = _build_skill()

    result = await skill.execute(
        company_name="江苏神码信息技术有限公司",
        question="这企业过去 3 年的欠费金额",
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
    )

    # answer = summary from QueryService.ask
    assert result["answer"] == "过去三年累计欠费 12.5 万元"
    # evidence_refs is a list
    assert isinstance(result["evidence_refs"], list)
    assert len(result["evidence_refs"]) == 1
    # raw_data = result_rows from QueryService.ask
    assert result["raw_data"] == [
        {"company_name": "江苏神码信息技术有限公司", "total_unpaid": 125000.0}
    ]
    # query_plan is forwarded
    assert result["query_plan"] == {"metric": "total_unpaid", "filters": {}}


# ---------------------------------------------------------------------------
# 5) Caveats are forwarded into evidence_ref when present
# ---------------------------------------------------------------------------


async def test_backtrack_skill_evidence_ref_includes_caveats_when_present() -> None:
    """当 QueryService.ask 返回 caveats 时，evidence_ref 也带 caveats。"""
    qs = _make_fake_query_service(
        return_value={
            "ok": True,
            "query_plan": {"metric": "total_unpaid"},
            "result_rows": [],
            "result_count": 0,
            "summary": "无可用数据",
            "caveats": ["无 active 数据集"],
            "confidence": "low",
        }
    )
    skill, _, _ = _build_skill(query_service=qs)

    result = await skill.execute(
        company_name="某企业",
        question="这企业欠费",
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
    )

    ref = result["evidence_refs"][0]
    assert ref.get("caveats") == ["无 active 数据集"]
    assert ref["result_count"] == 0
    assert ref["summary"] == "无可用数据"


# ---------------------------------------------------------------------------
# 6) role can be overridden from caller
# ---------------------------------------------------------------------------


async def test_backtrack_skill_respects_caller_role() -> None:
    """当 caller 显式传入 role（如 admin / analyst）时，透传给 QueryService。"""
    skill, query_service, _ = _build_skill()

    await skill.execute(
        company_name="某企业",
        question="这企业欠费",
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role="admin",
    )

    ask_kwargs = query_service.ask.await_args.kwargs
    assert ask_kwargs["role"] == "admin"
