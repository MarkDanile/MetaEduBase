"""REQ-046 AC-8: 真实企业端到端验收（manual / 真实验证，非 CI）。

本文件是 REQ-046（企业 360 背调工作台 V0）的**真实企业**端到端验收：用 1 个
已授权样例企业，经真实企查查 QCC MCP + 真实内部客户 MCP + 真实内部问数 + 真实
LLM，跑通完整编排（主体确认 -> run -> 报告草案 + 证据账本 -> 人工确认 -> 归档）。

**手工验收**：默认 skip。仅在显式 opt-in（``RUN_DD_AC8=1``）且三类真实通道全部
就绪时运行；任何一类通道缺失都会以**显式阻塞原因** skip，**绝不用 mock 冒充通过**
（plan PR-7：「如果真实企查查 MCP 或内部 MCP 不可用，必须写明阻塞，不用 mock 冒充通过」）。

与 REQ-045 AC-9 的关系：AC-9 验证的是「外部 SKILL（enterprise_360_dd）单 skill
端到端」；AC-8 验证的是「工作台编排（park_investment_dd 三类 step + 任务/报告/证据
领域）」端到端 —— 覆盖面更宽，含内部客户 MCP 与内部问数两条平台特有通道。

真实通道就绪前置条件（全部满足才运行，否则对应 skip 原因）：

1. QCC 外部通道：``QCC_MCP_TOKEN``（仅 shell env，勿提交）。
2. 内部客户 MCP 通道：``INTERNAL_MCP_TOKEN`` + 已注册 ``internal-customer`` server。
3. 内部问数通道：``DD_INTERNAL_QUERY_CATALOG_ID`` + 该 catalog 下已 seed 背调
   语义模型（``scripts/seed_dd_semantic_models.py``），且园区数据集已灌库
   （``scripts/upload_park_datasets.py``）。
4. LLM provider key（MINIMAX_API_KEY 等）已在 .env。

安全约束（与 REQ-045 AC-9 同款）：

- token 仅从 ``os.environ`` 读，永不写入文件、永不进断言失败消息明文。
- 验收证据只打印 digest 前 12 字符 + 步骤数 + 报告分区标题，不含 token、
  不含完整企业敏感事实；report 仅验证结构分区，不打印全文。
- 审计列只存 digest；企业名原文不得出现在任何审计列。

运行方式（手工）::

    export RUN_DD_AC8=1
    export QCC_MCP_TOKEN=<token>            # 仅 shell env，勿提交
    export INTERNAL_MCP_TOKEN=<token>       # 仅 shell env，勿提交
    export DD_INTERNAL_QUERY_CATALOG_ID=<uuid>
    export DD_AC8_COMPANY=<授权样例企业名>   # 如已授权的园区目标企业
    cd packages/server-python
    pytest tests/real_world/test_req046_due_diligence_e2e_acceptance.py -v -s
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

# ── opt-in 闸门与真实通道探测 ──────────────────────────────────────────────
_RUN_AC8 = os.environ.get("RUN_DD_AC8")
QCC_TOKEN = os.environ.get("QCC_MCP_TOKEN")
INTERNAL_TOKEN = os.environ.get("INTERNAL_MCP_TOKEN")
DD_CATALOG_ID = os.environ.get("DD_INTERNAL_QUERY_CATALOG_ID")
DD_AC8_COMPANY = os.environ.get("DD_AC8_COMPANY", "")

PARK_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "contexts"
    / "skill_registry"
    / "templates"
    / "park_investment_dd.yaml"
)


def _block_reasons() -> list[str]:
    """Collect every missing real channel as an explicit block reason.

    AC-8 must never fake a pass: if any real channel (QCC / internal MCP /
    internal query / sample company) is not provisioned, we skip and *say why*.
    """
    reasons: list[str] = []
    if not _RUN_AC8:
        reasons.append("RUN_DD_AC8=1 未设置（manual opt-in）")
    if not DD_AC8_COMPANY:
        reasons.append("DD_AC8_COMPANY 未设置（无授权样例企业）")
    if not QCC_TOKEN:
        reasons.append("QCC_MCP_TOKEN 缺失：真实企查查外部通道不可用（阻塞）")
    if not INTERNAL_TOKEN:
        reasons.append("INTERNAL_MCP_TOKEN 缺失：真实内部客户 MCP 通道不可用（阻塞）")
    if not DD_CATALOG_ID:
        reasons.append(
            "DD_INTERNAL_QUERY_CATALOG_ID 未配置：内部问数通道不可用"
            "（阻塞，需先灌库+seed 语义模型）"
        )
    return reasons


def test_park_template_loads():
    """phase 0（不联网）：园区招商背调 SKILL 模板加载并通过结构校验。

    这是 AC-8 里**总是运行**的部分：验证 PR-5 交付的三类-step 模板可解析，
    为真实端到端提供可注册的 SOP。不联网、不依赖 token。
    """
    from app.contexts.skill_registry.domain.skill import SopTemplate

    assert PARK_TEMPLATE_PATH.exists(), f"template not found: {PARK_TEMPLATE_PATH}"
    tpl = SopTemplate.parse(PARK_TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert tpl.name == "park-investment-dd"
    # 三类 step 齐备：外部 QCC + 内部客户 MCP + 内部问数（internal_query）
    mcp_steps = [s for s in tpl.steps if s.type == "mcp"]
    internal_query_steps = [s for s in tpl.steps if s.type == "internal_query"]
    assert mcp_steps, "expected external/internal-customer mcp steps"
    assert internal_query_steps, "expected internal_query steps"
    # report_contract（§4.6 七键）声明齐备
    assert tpl.report_contract is not None, "report_contract (§4.6) missing"


@pytest.mark.skipif(
    bool(_block_reasons()),
    reason="AC-8 阻塞: " + "; ".join(_block_reasons() or ["ready"]),
)
@pytest.mark.asyncio
async def test_real_enterprise_end_to_end():
    """phase 1（真实 QCC + 内部 MCP + 内部问数 + 真实 LLM）：真实企业端到端。

    本用例**只在全部真实通道就绪时运行**（否则被上面的 skipif 以显式阻塞原因
    跳过）。它用真实授权企业跑通工作台编排，断言报告草案、证据账本与审计齐备，
    且 token / 企业名原文不泄漏进审计列。

    NOTE: 该用例的真实执行体在真实通道就绪后填充。当前为骨架：先把「就绪即运行、
    未就绪即显式阻塞」的闸门立起来，避免用 mock 冒充通过。真实执行体将：
      1. 注册 qcc + internal-customer server（credential_ref 仅 env-key 名）
      2. 注册 park_investment_dd skill（enable）
      3. DdTaskService.create_task -> resolve -> confirm_subject（真实主体锚定）
      4. DdOrchestrator.run（真三类 step）-> 报告草案 + 证据账本
      5. 断言 §4.6 七键分区齐备、证据行可回溯、审计 digest 齐备、无 token/原文泄漏
    """
    # 骨架阶段：到达这里说明四类真实通道全部就绪（否则已被 skipif 拦截）。
    # 真实执行体在真实通道联调后落地；此处先显式标记为未实现，而非默默通过。
    pytest.fail(
        "AC-8 真实执行体待联调落地：真实通道已就绪，但端到端执行体尚未实现。"
        "不用 mock 冒充通过 —— 请在真实 QCC/内部 MCP/问数联调后补全本用例。"
    )
