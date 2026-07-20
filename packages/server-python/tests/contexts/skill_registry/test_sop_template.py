"""Unit tests for the SOP template value object (REQ-045 Task 1).

Covers spec section 4.3 structural validation: a valid template parses
into structured steps; every structural violation (missing / malformed
``name`` / ``description`` / ``steps`` / step fields / uncovered
``mcp_dependencies`` / oversized template) raises ``SopTemplateError``.
Whether a referenced server is registered in the tenant is a service-layer
concern (needs DB) and is intentionally not covered here.
"""
from __future__ import annotations

import pytest

from app.contexts.skill_registry.domain.skill import (
    SopTemplate,
    SopTemplateError,
)

VALID_TEMPLATE = """\
name: enterprise-360-dd
description: 企业 360 背调：入驻/投决前核验主体与风险
metadata: {version: "1.0.0", category: due-diligence, author: platform}
mcp_dependencies:
  - {server: qcc-company, required: true}
  - {server: qcc-risk, required: true}
principles:
  - 缺失数据显式标注，不编造默认值
steps:
  - id: subject_verify
    title: 主体工商核验与实控人穿透
    server: qcc-company
    tool: get_company_registration_info
    analysis_rules: [工商二要素不一致即标记高风险]
    output: 主体身份档案
  - id: risk_scan
    title: 司法与经营风险扫描
    server: qcc-risk
    tool: scan_risk
    output: 风险清单
report_template: |
  ## 事实数据
  ## AI 分析
  ## 待人工确认项
params: [{name: company_name, required: true}]
"""


def test_valid_template_parses_into_structured_steps():
    tpl = SopTemplate.parse(VALID_TEMPLATE)
    assert tpl.name == "enterprise-360-dd"
    assert "背调" in tpl.description
    assert [s.id for s in tpl.steps] == ["subject_verify", "risk_scan"]
    assert tpl.steps[0].server == "qcc-company"
    assert tpl.steps[0].tool == "get_company_registration_info"
    assert tpl.steps[1].server == "qcc-risk"
    assert "qcc-company" in tpl.mcp_dependencies
    assert "qcc-risk" in tpl.mcp_dependencies
    assert "事实数据" in (tpl.report_template or "")


def test_missing_name_rejected():
    bad = VALID_TEMPLATE.replace("name: enterprise-360-dd\n", "")
    with pytest.raises(SopTemplateError, match="name"):
        SopTemplate.parse(bad)


@pytest.mark.parametrize(
    "bad_name",
    ["Enterprise-360-DD", "enterprise_360_dd", "-enterprise", "enterprise-", "a" * 65],
)
def test_non_kebab_case_name_rejected(bad_name: str):
    bad = VALID_TEMPLATE.replace("name: enterprise-360-dd", f"name: {bad_name}")
    with pytest.raises(SopTemplateError, match="name"):
        SopTemplate.parse(bad)


def test_empty_description_rejected():
    bad = VALID_TEMPLATE.replace(
        "description: 企业 360 背调：入驻/投决前核验主体与风险",
        'description: ""',
    )
    with pytest.raises(SopTemplateError, match="description"):
        SopTemplate.parse(bad)


def test_missing_description_rejected():
    bad = VALID_TEMPLATE.replace(
        "description: 企业 360 背调：入驻/投决前核验主体与风险\n", ""
    )
    with pytest.raises(SopTemplateError, match="description"):
        SopTemplate.parse(bad)


def test_overlong_description_rejected():
    bad = VALID_TEMPLATE.replace(
        "description: 企业 360 背调：入驻/投决前核验主体与风险",
        "description: " + "x" * 1025,
    )
    with pytest.raises(SopTemplateError, match="description"):
        SopTemplate.parse(bad)


def test_missing_steps_rejected():
    bad = """\
name: enterprise-360-dd
description: 背调
"""
    with pytest.raises(SopTemplateError, match="steps"):
        SopTemplate.parse(bad)


def test_empty_steps_rejected():
    bad = """\
name: enterprise-360-dd
description: 背调
steps: []
"""
    with pytest.raises(SopTemplateError, match="steps"):
        SopTemplate.parse(bad)


def test_duplicate_step_id_rejected():
    bad = VALID_TEMPLATE.replace("id: risk_scan", "id: subject_verify")
    with pytest.raises(SopTemplateError, match="subject_verify"):
        SopTemplate.parse(bad)


def test_step_missing_server_rejected():
    bad = VALID_TEMPLATE.replace("    server: qcc-risk\n", "")
    with pytest.raises(SopTemplateError, match="server"):
        SopTemplate.parse(bad)


def test_step_missing_tool_rejected():
    bad = VALID_TEMPLATE.replace("    tool: scan_risk\n", "")
    with pytest.raises(SopTemplateError, match="tool"):
        SopTemplate.parse(bad)


def test_mcp_dependencies_not_covering_step_server_rejected():
    bad = VALID_TEMPLATE.replace(
        "  - {server: qcc-risk, required: true}\n", ""
    )
    with pytest.raises(SopTemplateError, match="qcc-risk"):
        SopTemplate.parse(bad)


def test_oversized_template_rejected():
    big = VALID_TEMPLATE + "\n# " + "x" * (100 * 1024)
    with pytest.raises(SopTemplateError, match="size|100|limit"):
        SopTemplate.parse(big)


def test_invalid_yaml_rejected():
    with pytest.raises(SopTemplateError):
        SopTemplate.parse("name: [unclosed\n  - {broken")


def test_non_mapping_yaml_rejected():
    with pytest.raises(SopTemplateError):
        SopTemplate.parse("- just\n- a\n- list\n")


# ── Review findings: Important #1 / #2 + Minor #3 branch coverage ──


def test_missing_mcp_dependencies_with_step_servers_rejected():
    """Important #1: 完全不写 mcp_dependencies 但 steps 引用了 server -> 拒。

    mcp_dependencies 缺省按空列表处理并仍走覆盖校验；steps 非空时必然
    失败，即该字段事实上必填（spec §4.3 标注"必需"）。
    """
    bad = """\
name: enterprise-360-dd
description: 背调
steps:
  - id: s1
    server: qcc-company
    tool: get_company_registration_info
"""
    with pytest.raises(SopTemplateError, match="mcp_dependencies"):
        SopTemplate.parse(bad)


def test_analysis_rules_scalar_rejected_not_split_into_chars():
    """Important #2: analysis_rules 误写成标量 -> 拒，不得静默拆成单字符元组。"""
    bad = VALID_TEMPLATE.replace(
        "    analysis_rules: [工商二要素不一致即标记高风险]\n",
        "    analysis_rules: abc\n",
    )
    with pytest.raises(SopTemplateError, match="analysis_rules"):
        SopTemplate.parse(bad)


def test_principles_scalar_rejected():
    """Important #2: principles 误写成标量 -> 拒。"""
    bad = VALID_TEMPLATE.replace(
        "principles:\n  - 缺失数据显式标注，不编造默认值\n",
        "principles: abc\n",
    )
    with pytest.raises(SopTemplateError, match="principles"):
        SopTemplate.parse(bad)


def test_steps_non_list_rejected():
    bad = """\
name: enterprise-360-dd
description: 背调
steps: foo
"""
    with pytest.raises(SopTemplateError, match="steps"):
        SopTemplate.parse(bad)


def test_step_non_mapping_rejected():
    bad = VALID_TEMPLATE.replace(
        "  - id: subject_verify\n"
        "    title: 主体工商核验与实控人穿透\n"
        "    server: qcc-company\n"
        "    tool: get_company_registration_info\n"
        "    analysis_rules: [工商二要素不一致即标记高风险]\n"
        "    output: 主体身份档案\n",
        "  - justastring\n",
    )
    with pytest.raises(SopTemplateError, match="mapping"):
        SopTemplate.parse(bad)


def test_mcp_dependencies_non_list_rejected():
    bad = VALID_TEMPLATE.replace(
        "mcp_dependencies:\n"
        "  - {server: qcc-company, required: true}\n"
        "  - {server: qcc-risk, required: true}\n",
        "mcp_dependencies: foo\n",
    )
    with pytest.raises(SopTemplateError, match="mcp_dependencies"):
        SopTemplate.parse(bad)


def test_mcp_dependency_missing_server_rejected():
    bad = VALID_TEMPLATE.replace(
        "  - {server: qcc-risk, required: true}\n",
        "  - {required: true}\n",
    )
    with pytest.raises(SopTemplateError, match="server"):
        SopTemplate.parse(bad)


def test_name_non_string_rejected():
    bad = VALID_TEMPLATE.replace("name: enterprise-360-dd", "name: 123")
    with pytest.raises(SopTemplateError, match="name"):
        SopTemplate.parse(bad)
