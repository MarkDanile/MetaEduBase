"""Test QueryPlanner: 5 real-question cases for the LLM mock path.

REQ-052 Task 4: every test here mocks ``app.shared.llm.chat.chat`` (the
project's actual LLM entry point) — NO real LLM call is made during the
test suite. The planner dispatches to ``chat`` with the messages list
format ``[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]``
the production client expects.

The five cases mirror realistic state-owned park back-office questions:

1. ``test_plan_bill_unpaid_query`` — "这企业欠费多少" → entity=bill +
   metric=unpaid_amount + company filter + time range.
2. ``test_plan_contract_count`` — "这企业签了几份合同" → entity=contract +
   metric=count + company filter.
3. ``test_plan_no_metric_question`` — "这家企业是什么行业" → no metric, just
   a filter on industry.
4. ``test_plan_handles_markdown_fence`` — LLM output wrapped in
   ```` ```json ... ``` ```` (very common in practice) — planner must
   strip the fence before json.loads.
5. ``test_plan_enforces_confirmed_company_injection`` — when the caller
   passes ``confirmed_company_name``, the planner MUST overwrite / inject
   the company_name filter even if the LLM omitted it.

Together these cover: metric + non-metric questions, markdown fence
handling, and the company-confirmation injection requirement.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.contexts.structured_data.application.query_planner import QueryPlanner

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Real-question cases (5)
# ---------------------------------------------------------------------------


async def test_plan_bill_unpaid_query(sample_semantic_model):
    """用户问"这企业欠费多少" → entity=bill, metrics=[unpaid_amount]。

    LLM 响应包成 JSON 字符串返回（生产中 chat() 直接返回 content 字符串）。
    Planner 解析后强制注入 company_name 过滤器（确认企业全称）。
    """
    llm_response = json.dumps(
        {
            "entity": "bill",
            "metrics": ["unpaid_amount"],
            "filters": {
                "billing_date": {"op": "gte", "value": "2023-07-01"},
            },
            "time_range": {
                "field": "billing_date",
                "start": "2023-07-01",
                "end": "2026-07-01",
            },
            "limit": 100,
        }
    )
    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_chat:
        mock_chat.return_value = llm_response
        planner = QueryPlanner()
        plan = await planner.plan(
            question="这企业欠费多少",
            semantic_model=sample_semantic_model,
            confirmed_company_name="江苏神码信息技术有限公司",
        )

    assert plan["entity"] == "bill"
    assert "unpaid_amount" in plan["metrics"]
    assert plan["limit"] == 100
    # confirmed_company_name 强制注入
    assert plan["filters"]["company_name"]["op"] == "eq"
    assert plan["filters"]["company_name"]["value"] == "江苏神码信息技术有限公司"
    # chat() 被调一次（system + user 两条消息）
    mock_chat.assert_awaited_once()
    messages = mock_chat.await_args.kwargs["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


async def test_plan_contract_count(sample_semantic_model):
    """用户问"这企业签了几份合同" → entity=bill, metrics=[total_amount], count question。

    此例修改 sample_semantic_model 的 entity_type 为 contract 以模拟多 entity；
    metric_definitions 借用 total_amount（合约金额求和）。
    """
    sample_semantic_model.entity_type = "contract"
    sample_semantic_model.metric_definitions["contract_count"] = (
        sample_semantic_model.metric_definitions["unpaid_amount"]
    )

    llm_response = json.dumps(
        {
            "entity": "contract",
            "metrics": ["contract_count"],
            "filters": {},
            "limit": 50,
        }
    )
    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_chat:
        mock_chat.return_value = llm_response
        planner = QueryPlanner()
        plan = await planner.plan(
            question="这企业签了几份合同",
            semantic_model=sample_semantic_model,
            confirmed_company_name="江苏神码信息技术有限公司",
        )

    assert plan["entity"] == "contract"
    assert "contract_count" in plan["metrics"]
    # 即使 LLM 没用 limit 100，user 指定 limit=50 也被保留
    assert plan["limit"] == 50
    # confirmed_company_name 注入
    assert plan["filters"]["company_name"]["value"] == "江苏神码信息技术有限公司"


async def test_plan_no_metric_question(sample_semantic_model):
    """用户问"这家企业是什么行业" → 没有 metric（仅 filter）。

    列表查询 → metrics 为空数组 / 缺省。Planner 必须容忍 metrics 缺省，
    不能 raise。
    """
    llm_response = json.dumps(
        {
            "entity": "bill",
            "metrics": [],
            "filters": {},
            "limit": 100,
        }
    )
    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_chat:
        mock_chat.return_value = llm_response
        planner = QueryPlanner()
        plan = await planner.plan(
            question="这家企业是什么行业",
            semantic_model=sample_semantic_model,
            confirmed_company_name=None,  # 没确认企业 — 不注入
        )

    assert plan["entity"] == "bill"
    assert plan["metrics"] == []
    # 没传 confirmed_company_name → filters 不应有 company_name
    assert "company_name" not in plan["filters"]
    # limit 没设 → 默认 100
    assert plan["limit"] == 100


async def test_plan_handles_markdown_fence(sample_semantic_model):
    """LLM 输出含 markdown ```json ...``` 代码块 → planner 必须剥离。

    这是实践中最高频的格式错误。Planner 用正则提取首个 {...} JSON 块。
    """
    # markdown fence: triple-backtick + json + JSON + triple-backtick
    fence_open = "\x60\x60\x60" + "json\n"
    fence_close = "\n" + "\x60\x60\x60" + "\n"
    llm_response = (
        "好的，我帮你查询：\n\n"
        + fence_open
        + json.dumps(
            {
                "entity": "bill",
                "metrics": ["total_amount"],
                "filters": {},
                "limit": 100,
            }
        )
        + fence_close
    )
    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_chat:
        mock_chat.return_value = llm_response
        planner = QueryPlanner()
        plan = await planner.plan(
            question="这企业总金额多少",
            semantic_model=sample_semantic_model,
            confirmed_company_name="江苏神码信息技术有限公司",
        )

    assert plan["entity"] == "bill"
    assert plan["metrics"] == ["total_amount"]
    # fence 被剥离后 JSON 正常解析，confirmed_company_name 仍注入
    assert plan["filters"]["company_name"]["value"] == "江苏神码信息技术有限公司"


async def test_plan_enforces_confirmed_company_injection(sample_semantic_model):
    """LLM 自己生成 company_name 过滤器 → planner 用 confirmed_company_name 覆盖。

    这是企业主体确认的强制安全策略：即使 LLM 幻觉或猜错了企业名，
    caller 传入的 confirmed_company_name 是 ground truth，必须覆盖。
    """
    llm_response = json.dumps(
        {
            "entity": "bill",
            "metrics": ["total_amount"],
            "filters": {
                "company_name": {"op": "eq", "value": "幻觉企业名"},
            },
            "limit": 100,
        }
    )
    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_chat:
        mock_chat.return_value = llm_response
        planner = QueryPlanner()
        plan = await planner.plan(
            question="这企业欠费多少",
            semantic_model=sample_semantic_model,
            confirmed_company_name="江苏神码信息技术有限公司",
        )

    # confirmed_company_name 必须覆盖 LLM 输出
    assert plan["filters"]["company_name"]["value"] == "江苏神码信息技术有限公司"


# ---------------------------------------------------------------------------
# Additional check: default limit & filter normalization
# ---------------------------------------------------------------------------


async def test_plan_default_limit_when_missing(sample_semantic_model):
    """LLM 不返回 limit → planner 默认 100（spec 软上限）。"""
    llm_response = json.dumps(
        {
            "entity": "bill",
            "metrics": ["total_amount"],
            "filters": {},
        }
    )
    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_chat:
        mock_chat.return_value = llm_response
        planner = QueryPlanner()
        plan = await planner.plan(
            question="这企业欠费多少",
            semantic_model=sample_semantic_model,
            confirmed_company_name="江苏神码信息技术有限公司",
        )

    assert plan["limit"] == 100
