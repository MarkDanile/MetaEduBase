"""Test SemanticValidator: query_plan ↔ semantic_model field checks.

REQ-052 Task 4: the validator is a pure function — given a query_plan
dict and a semantic_model, return a list of error strings (empty list
means OK). It is called AFTER the LLM planner runs and BEFORE any DB
query; an error list short-circuits the pipeline and the user sees
"please clarify your question".

The validator covers four rules per the brief:

1. ``entity`` must equal ``semantic_model.entity_type``.
2. Every metric in ``metrics`` must be a key of ``metric_definitions``.
3. Every filter column must be a key of ``column_mapping``.
4. ``time_range.field`` (if present) must be a key of ``column_mapping``.

Tests also cover the "all good" baseline so we know the validator
returns ``[]`` when the plan is valid (the whole point of validation
is "no news is good news").
"""

from __future__ import annotations

import pytest

from app.contexts.structured_data.application.semantic_validator import (
    SemanticValidator,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


async def test_valid_query_plan_returns_no_errors(sample_semantic_model):
    """完整合法 query_plan → 返回 []（全部检查通过）。"""
    plan = {
        "entity": "bill",
        "metrics": ["total_amount", "unpaid_amount"],
        "filters": {
            "company_name": {"op": "eq", "value": "ACME"},
            "billing_date": {"op": "gte", "value": "2023-01-01"},
        },
        "time_range": {
            "field": "billing_date",
            "start": "2023-01-01",
            "end": "2026-01-01",
        },
        "limit": 100,
    }
    validator = SemanticValidator()

    errors = validator.validate(plan, sample_semantic_model)

    assert errors == []


# ---------------------------------------------------------------------------
# entity mismatch
# ---------------------------------------------------------------------------


async def test_entity_mismatch_returns_error(sample_semantic_model):
    """entity 不匹配 semantic_model.entity_type → 报告错误。

    例如 LLM 把 contract 写成 bill 但语义层只注册了 bill — 这种"合法但错
    entity"的情况必须被 validator 捕获，否则下游会查错数据集。
    """
    plan = {
        "entity": "contract",  # ≠ sample_semantic_model.entity_type (bill)
        "metrics": [],
        "filters": {},
    }
    validator = SemanticValidator()

    errors = validator.validate(plan, sample_semantic_model)

    assert any("entity" in e and "contract" in e for e in errors)


async def test_missing_entity_returns_error(sample_semantic_model):
    """query_plan 缺 entity → 报错（entity 是必填）。"""
    plan = {
        "metrics": [],
        "filters": {},
    }
    validator = SemanticValidator()

    errors = validator.validate(plan, sample_semantic_model)

    assert any("entity" in e for e in errors)


# ---------------------------------------------------------------------------
# metrics check
# ---------------------------------------------------------------------------


async def test_unknown_metric_returns_error(sample_semantic_model):
    """metrics 中有未定义的指标 → 报告错误。"""
    plan = {
        "entity": "bill",
        "metrics": ["ghost_metric"],
        "filters": {},
    }
    validator = SemanticValidator()

    errors = validator.validate(plan, sample_semantic_model)

    # 至少一条错误针对 ghost_metric
    assert any("ghost_metric" in e and "metric" in e for e in errors)


async def test_all_unknown_metrics_returns_one_error_each(sample_semantic_model):
    """多个未知 metric → 每个 metric 各报一条错误（便于上层提示具体哪个）。"""
    plan = {
        "entity": "bill",
        "metrics": ["alpha_metric", "beta_metric"],
        "filters": {},
    }
    validator = SemanticValidator()

    errors = validator.validate(plan, sample_semantic_model)

    assert any("alpha_metric" in e for e in errors)
    assert any("beta_metric" in e for e in errors)


# ---------------------------------------------------------------------------
# filters check
# ---------------------------------------------------------------------------


async def test_unknown_filter_column_returns_error(sample_semantic_model):
    """filter column 未在 column_mapping 注册 → 报告错误（防"暗字段"）。"""
    plan = {
        "entity": "bill",
        "metrics": [],
        "filters": {
            "ghost_column": {"op": "eq", "value": "x"},
        },
    }
    validator = SemanticValidator()

    errors = validator.validate(plan, sample_semantic_model)

    assert any("ghost_column" in e and ("filter" in e or "column" in e) for e in errors)


async def test_valid_filter_column_passes(sample_semantic_model):
    """合法 filter column（company_name / billing_date）→ 不报错。"""
    plan = {
        "entity": "bill",
        "metrics": [],
        "filters": {
            "company_name": {"op": "eq", "value": "ACME"},
            "billing_date": {"op": "gte", "value": "2023-01-01"},
        },
    }
    validator = SemanticValidator()

    errors = validator.validate(plan, sample_semantic_model)

    assert errors == []


# ---------------------------------------------------------------------------
# time_range check
# ---------------------------------------------------------------------------


async def test_time_range_field_unknown_returns_error(sample_semantic_model):
    """time_range.field 未注册 → 报告错误。"""
    plan = {
        "entity": "bill",
        "metrics": [],
        "filters": {},
        "time_range": {
            "field": "ghost_date_field",
            "start": "2023-01-01",
            "end": "2026-01-01",
        },
    }
    validator = SemanticValidator()

    errors = validator.validate(plan, sample_semantic_model)

    assert any("ghost_date_field" in e for e in errors)


async def test_time_range_known_field_passes(sample_semantic_model):
    """time_range.field 在 column_mapping → 不报错。"""
    plan = {
        "entity": "bill",
        "metrics": [],
        "filters": {},
        "time_range": {
            "field": "billing_date",
            "start": "2023-01-01",
            "end": "2026-01-01",
        },
    }
    validator = SemanticValidator()

    errors = validator.validate(plan, sample_semantic_model)

    assert errors == []


async def test_time_range_absent_passes(sample_semantic_model):
    """time_range 缺省 → 不检查（不是必填）。"""
    plan = {
        "entity": "bill",
        "metrics": [],
        "filters": {},
    }
    validator = SemanticValidator()

    errors = validator.validate(plan, sample_semantic_model)

    assert errors == []


# ---------------------------------------------------------------------------
# combined: multiple errors returned together
# ---------------------------------------------------------------------------


async def test_multiple_violations_all_reported(sample_semantic_model):
    """多个违规同时返回 — 不应该因一个错误就 short-circuit 其他的检查。"""
    plan = {
        "entity": "wrong_entity",
        "metrics": ["unknown_metric"],
        "filters": {"unknown_filter": {"op": "eq", "value": "x"}},
        "time_range": {"field": "unknown_date"},
    }
    validator = SemanticValidator()

    errors = validator.validate(plan, sample_semantic_model)

    # 三类错误都应被报告
    assert any("entity" in e for e in errors)
    assert any("unknown_metric" in e for e in errors)
    assert any("unknown_filter" in e for e in errors)
    assert any("unknown_date" in e for e in errors)
    assert len(errors) >= 4
