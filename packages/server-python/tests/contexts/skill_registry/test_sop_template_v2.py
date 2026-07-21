"""SopTemplate v2: step ``type`` (mcp / internal_query) + report_contract (REQ-046 PR-3).

REQ-046 SkillRunner v2 lets a SOP mix external MCP steps, internal MCP steps,
and internal data-query steps in one SOP. This tests the domain extension:
- ``SopStep.type`` defaults to ``mcp`` (REQ-045 backward compat).
- ``internal_query`` steps declare ``question_template`` (+ optional
  ``entity_type`` / ``filters``) instead of ``server``/``tool``.
- ``mcp_dependencies`` coverage only constrains ``mcp``-typed steps.
- optional ``report_contract.schema`` (inline JSON Schema, §4.6) parses through.
"""
from __future__ import annotations

import pytest

from app.contexts.skill_registry.domain.skill import (
    SopTemplate,
    SopTemplateError,
)

MIXED_TEMPLATE = """\
name: park-investment-dd
description: 园区招商企业 360 背调(内外数据整合)
mcp_dependencies:
  - {server: qcc, required: true}
  - {server: internal-customer, required: true}
principles:
  - 缺失数据显式标注,不编造
steps:
  - id: subject_verify
    type: mcp
    server: qcc
    tool: get_company_registration_info
    output: 主体身份档案
  - id: internal_customer
    type: mcp
    server: internal-customer
    tool: get_customer_360
    output: 园区内部客户事实
  - id: unpaid_query
    type: internal_query
    question_template: "{company_name} 过去 3 年的欠费金额"
    entity_type: bill
    output: 欠费问数结果
report_contract:
  schema:
    type: object
    required: [summary, external_facts, internal_facts]
"""


def test_step_type_defaults_to_mcp():
    template = SopTemplate.parse(MIXED_TEMPLATE)
    by_id = {s.id: s for s in template.steps}
    assert by_id["subject_verify"].type == "mcp"
    assert by_id["internal_customer"].type == "mcp"


def test_internal_query_step_parses():
    template = SopTemplate.parse(MIXED_TEMPLATE)
    by_id = {s.id: s for s in template.steps}
    q = by_id["unpaid_query"]
    assert q.type == "internal_query"
    assert q.question_template == "{company_name} 过去 3 年的欠费金额"
    assert q.entity_type == "bill"


def test_internal_query_does_not_require_server_tool():
    """internal_query step 不需要 server/tool;mcp 依赖覆盖只约束 mcp step。"""
    template = SopTemplate.parse(MIXED_TEMPLATE)
    by_id = {s.id: s for s in template.steps}
    assert by_id["unpaid_query"].server is None
    assert by_id["unpaid_query"].tool is None


def test_report_contract_parses():
    template = SopTemplate.parse(MIXED_TEMPLATE)
    assert template.report_contract is not None
    assert template.report_contract["schema"]["required"] == [
        "summary",
        "external_facts",
        "internal_facts",
    ]


def test_report_contract_optional():
    """无 report_contract 的 REQ-045 模板 -> None(向后兼容)。"""
    minimal = """\
name: enterprise-360-dd
description: 企业 360 背调
mcp_dependencies:
  - {server: qcc, required: true}
steps:
  - id: s1
    server: qcc
    tool: get_company
"""
    template = SopTemplate.parse(minimal)
    assert template.report_contract is None
    assert template.steps[0].type == "mcp"


def test_invalid_step_type_rejected():
    bad = """\
name: x-y
description: 非法 step 类型
mcp_dependencies:
  - {server: qcc, required: true}
steps:
  - id: s1
    type: bogus
    server: qcc
    tool: get_company
"""
    with pytest.raises(SopTemplateError):
        SopTemplate.parse(bad)


def test_internal_query_requires_question_template():
    bad = """\
name: x-y
description: internal_query 缺 question_template
steps:
  - id: q1
    type: internal_query
"""
    with pytest.raises(SopTemplateError):
        SopTemplate.parse(bad)


def test_report_contract_requires_schema():
    bad = """\
name: x-y
description: 空报告契约
mcp_dependencies:
  - {server: qcc, required: true}
steps:
  - id: s1
    server: qcc
    tool: get_company
report_contract: {}
"""
    with pytest.raises(SopTemplateError, match="report_contract.schema"):
        SopTemplate.parse(bad)


def test_invalid_report_contract_schema_rejected():
    bad = """\
name: x-y
description: 非法 JSON Schema
mcp_dependencies:
  - {server: qcc, required: true}
steps:
  - id: s1
    server: qcc
    tool: get_company
report_contract:
  schema:
    type: definitely-not-a-json-schema-type
"""
    with pytest.raises(SopTemplateError, match="report_contract.schema"):
        SopTemplate.parse(bad)


def test_mcp_step_still_requires_server_tool():
    bad = """\
name: x-y
description: mcp step 缺 tool
mcp_dependencies:
  - {server: qcc, required: true}
steps:
  - id: s1
    type: mcp
    server: qcc
"""
    with pytest.raises(SopTemplateError):
        SopTemplate.parse(bad)
