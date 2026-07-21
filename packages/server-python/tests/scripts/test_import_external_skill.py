"""import_external_skill converter contract (REQ-046 PR-7 / Slice 6).

Converts an external SKILL.md (free Markdown: metadata + MCP dependency +
workflow dimensions + fill-in report skeleton) into a platform SopTemplate
YAML draft. Heuristic by design (plan PR-7): the goal is a *registrable*
draft for human review, not a lossless auto-import. These tests pin the
mapping against the real QCC SKILL.md shape:
- name / description from the command + title.
- mcp_dependencies from the ``mcp__{server}__{tool}`` tool tokens.
- one mcp step per workflow "维度" (first tool of its chain; the rest become
  analysis_rules so no tool call is silently dropped).
- report_template from the "报告输出格式" fenced markdown block.
- the emitted YAML must round-trip through ``SopTemplate.parse``.
Pure string transform — no DB, no network.
"""
from __future__ import annotations

import pytest

from app.contexts.skill_registry.domain.skill import SopTemplate
from tests.scripts._script_loader import load_server_script

conv = load_server_script("import_external_skill")

SAMPLE_SKILL_MD = """\
> 授信尽调报告 SKILL · 企查查 MCP V2.0。
> 信贷审批放款前的全维度企业尽调工具。

**命令**：`/credit-due-diligence` · **MCP 工具集**：`qcc-company, qcc-risk`

# 授信尽调报告 · 企查查 MCP V2.0 增强版

## SKILL 定位

本 SKILL 服务于银行对公贷款审批。

## MCP 依赖与配置

必选：
- `qcc-company`（企业基座）
- `qcc-risk`（风控大脑）

## 工作流

### 维度一：主体工商核验与实控人穿透

工具链：
- `mcp__qcc-company__get_company_registration_info` — 工商登记信息
- `mcp__qcc-company__get_actual_controller` — 实际控制人穿透链路

产出：《主体身份档案》

### 维度二：司法风险扫描

工具链：
- `mcp__qcc-risk__get_dishonest_info` — 失信被执行人
- `mcp__qcc-risk__get_judgment_debtor_info` — 被执行人

## 报告输出格式（严格填空骨架 · 模型只填值、不造结构）

```markdown
# 授信尽调底稿

## {企业完整登记名}
```
"""


def test_extracts_name_from_command():
    draft = conv.convert(SAMPLE_SKILL_MD)
    assert draft["name"] == "credit-due-diligence"


def test_extracts_mcp_dependencies_covering_step_servers():
    draft = conv.convert(SAMPLE_SKILL_MD)
    servers = {d["server"] for d in draft["mcp_dependencies"]}
    assert servers == {"qcc-company", "qcc-risk"}


def test_one_step_per_workflow_dimension():
    draft = conv.convert(SAMPLE_SKILL_MD)
    assert len(draft["steps"]) == 2
    first = draft["steps"][0]
    assert first["type"] == "mcp"
    assert first["server"] == "qcc-company"
    assert first["tool"] == "get_company_registration_info"
    # 其余工具进 analysis_rules，不静默丢弃
    assert any("get_actual_controller" in r for r in first["analysis_rules"])


def test_report_template_from_fenced_block():
    draft = conv.convert(SAMPLE_SKILL_MD)
    assert "# 授信尽调底稿" in draft["report_template"]
    assert "{企业完整登记名}" in draft["report_template"]


def test_emitted_yaml_round_trips_sop_parse():
    draft = conv.convert(SAMPLE_SKILL_MD)
    yaml_text = conv.to_yaml(draft)
    template = SopTemplate.parse(yaml_text)  # 不 raise 即合法
    assert template.name == "credit-due-diligence"
    assert len(template.steps) == 2
    declared = set(template.mcp_dependencies)
    used = {s.server for s in template.steps if s.type == "mcp"}
    assert used <= declared


def test_missing_workflow_dimensions_rejected():
    with pytest.raises(ValueError, match="维度|工作流|step"):
        conv.convert("# 空 SKILL\n\n## 工作流\n\n（无维度）\n")
