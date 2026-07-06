"""Test ResultExplainer — LLM-generated summary + Python-computed metrics + caveats.

REQ-052 Task 5: the explainer is the last step before the answer reaches
the user. Two responsibilities:

1. **Metric aggregation** (Python-side, not LLM) — for each metric in
   ``query_plan.metrics``, read the matching ``MetricDefinition`` from the
   ``semantic_model.metric_definitions`` and aggregate the rows. This MUST
   be Python (not LLM) so the numbers are auditable and reproducible.

2. **Natural-language summary** (LLM-side) — the LLM is asked to write a
   one-paragraph answer in Chinese. This is the only LLM step in the
   explainer, and it's tested with ``chat`` patched (Task 4 pattern).

3. **Caveats** (rule-based, Python-side) — empty result + company_name
   filter are the two heuristics Task 5 requires. More will be added in
   later slices.

Tests cover the brief's two required cases + edge cases that flow from
the implementation choices:

- ``test_explain_with_no_results`` — empty rows → caveat present, no LLM
  call made, ``confidence="low"``.
- ``test_explain_with_results`` — non-empty rows → LLM called once,
  metric_values reflects Python-side aggregation, ``confidence="high"``.
- ``test_explain_avg_metric_aggregation`` — exercises the ``avg`` branch
  of ``_compute_metrics`` (the brief only sketched sum/count).
- ``test_detect_caveats_company_name_filter`` — exercises the
  ``company_name`` filter caveat independently of any LLM.
- ``test_explain_does_not_call_llm_on_empty`` — LLM MUST NOT be called
  when ``result_rows`` is empty (per the implementation rule in the brief:
  summary is the empty string).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.contexts.structured_data.application.result_explainer import (
    ExplainerResult,
    ResultExplainer,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Brief's 2 required cases
# ---------------------------------------------------------------------------


async def test_explain_with_no_results(sample_semantic_model):
    """空结果应返回 caveat：数据未录入或无匹配记录。

    The brief mandates a caveat for empty results. The explainer MUST also
    skip the LLM call entirely when rows is empty (saves tokens + avoids
    hallucinating a summary from no data).
    """
    with patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ) as mock_chat:
        explainer = ResultExplainer()
        result = await explainer.explain(
            result_rows=[],
            semantic_model=sample_semantic_model,
            query_plan={"entity": "bill", "metrics": ["unpaid_amount"]},
            question="这企业欠费多少",
        )

    assert any("空" in c or "无匹配" in c for c in result.caveats)
    assert result.confidence == "low"
    # No LLM call when there is nothing to summarise.
    mock_chat.assert_not_awaited()
    # metric_values should still be present (computed to 0 / empty).
    assert "unpaid_amount" in result.metric_values
    assert result.metric_values["unpaid_amount"]["value"] == 0


async def test_explain_with_results(sample_semantic_model):
    """有结果应返回 summary + metric_values。

    LLM returns a fixed string so we can assert it's wired through to
    ``result.summary``. Metric aggregation is verified independently —
    Python sums the 25 × 5000 amounts = 125000.
    """
    llm_response = "该企业过去三年累计欠费 12.5 万元"
    with patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ) as mock_chat:
        mock_chat.return_value = llm_response
        explainer = ResultExplainer()
        result = await explainer.explain(
            result_rows=[{"amount": 5000, "billing_date": "2024-01-01"}] * 25,
            semantic_model=sample_semantic_model,
            query_plan={"entity": "bill", "metrics": ["unpaid_amount"]},
            question="这企业欠费多少",
        )

    assert "12.5 万" in result.summary
    assert result.metric_values["unpaid_amount"]["aggregation"] == "sum"
    assert result.metric_values["unpaid_amount"]["value"] == 125000
    assert result.metric_values["unpaid_amount"]["label"] == "欠费金额"
    assert result.confidence == "high"
    # LLM is called exactly once (system + user messages).
    mock_chat.assert_awaited_once()


# ---------------------------------------------------------------------------
# Edge cases beyond the brief
# ---------------------------------------------------------------------------


async def test_explain_avg_metric_aggregation(sample_semantic_model):
    """avg aggregation branch of ``_compute_metrics``.

    Uses a synthetic metric that averages ``amount``. Verifies the avg
    branch computes correctly (60 = (10 + 20 + 30 + 80 + 100) / 5).
    """
    from app.contexts.structured_data.domain.semantic_model import (
        MetricDefinition,
    )

    sample_semantic_model.metric_definitions["avg_amount"] = MetricDefinition(
        column="amount", aggregation="avg", label="平均金额"
    )

    with patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ):
        explainer = ResultExplainer()
        result = await explainer.explain(
            result_rows=[{"amount": v} for v in [10, 20, 30, 80, 100]],
            semantic_model=sample_semantic_model,
            query_plan={
                "entity": "bill",
                "metrics": ["avg_amount"],
                "filters": {},
            },
            question="平均账单金额",
        )

    assert result.metric_values["avg_amount"]["aggregation"] == "avg"
    assert result.metric_values["avg_amount"]["value"] == 48.0
    assert result.metric_values["avg_amount"]["label"] == "平均金额"


async def test_detect_caveats_company_name_filter(sample_semantic_model):
    """When the query_plan has a ``company_name`` filter, the caveat about
    exact-match-may-miss-synonyms is appended.

    Independent of LLM — the caveat detector is pure-Python.
    """
    with patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ) as mock_chat:
        mock_chat.return_value = "summary"
        explainer = ResultExplainer()
        result = await explainer.explain(
            result_rows=[{"amount": 100.0}],
            semantic_model=sample_semantic_model,
            query_plan={
                "entity": "bill",
                "metrics": ["unpaid_amount"],
                "filters": {
                    "company_name": {"op": "eq", "value": "ACME"},
                },
            },
            question="这企业欠费多少",
        )

    company_caveat = next(
        (c for c in result.caveats if "简称" in c or "全称" in c), None
    )
    assert company_caveat is not None
    mock_chat.assert_awaited_once()


async def test_explain_unknown_metric_skipped(sample_semantic_model):
    """query_plan references a metric not in semantic_model.metric_definitions.

    The validator upstream should normally catch this, but the explainer
    must be tolerant (defence-in-depth): unknown metric names are skipped
    silently rather than raising.
    """
    with patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ):
        explainer = ResultExplainer()
        result = await explainer.explain(
            result_rows=[{"amount": 100.0}],
            semantic_model=sample_semantic_model,
            query_plan={
                "entity": "bill",
                "metrics": ["nonexistent_metric", "unpaid_amount"],
            },
            question="这企业欠费多少",
        )

    assert "nonexistent_metric" not in result.metric_values
    assert "unpaid_amount" in result.metric_values


async def test_explain_result_dataclass_shape(sample_semantic_model):
    """ExplainerResult must carry summary + metric_values + filters_applied
    + caveats + confidence as documented.

    Locks down the public surface so a downstream consumer (router,
    future backtrack_skill) doesn't break if someone refactors the
    dataclass.
    """
    with patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ):
        explainer = ResultExplainer()
        result = await explainer.explain(
            result_rows=[{"amount": 50.0}],
            semantic_model=sample_semantic_model,
            query_plan={
                "entity": "bill",
                "metrics": ["unpaid_amount"],
                "filters": {"company_name": {"op": "eq", "value": "ACME"}},
            },
            question="test",
        )

    assert isinstance(result, ExplainerResult)
    assert hasattr(result, "summary")
    assert hasattr(result, "metric_values")
    assert hasattr(result, "filters_applied")
    assert hasattr(result, "caveats")
    assert hasattr(result, "confidence")
    # filters_applied mirrors query_plan.filters so the router can echo it.
    assert "company_name" in result.filters_applied
