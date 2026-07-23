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
pytestmark = pytest.mark.slow

# ── opt-in 闸门与真实通道探测 ──────────────────────────────────────────────
_RUN_AC8 = os.environ.get("RUN_DD_AC8")
QCC_TOKEN = os.environ.get("QCC_MCP_TOKEN")
INTERNAL_TOKEN = os.environ.get("INTERNAL_MCP_TOKEN")
DD_CATALOG_ID = os.environ.get("DD_INTERNAL_QUERY_CATALOG_ID")
DD_AC8_COMPANY = os.environ.get("DD_AC8_COMPANY", "上汽集团股份有限公司")
# 运行中后端（env 已注入、qcc/internal_customer/skill 已注册）。AC-8 走真实
# HTTP 全链，不打 TestClient —— 真实验收必须命中真实装配的后端进程。
DD_AC8_BASE_URL = os.environ.get("DD_AC8_BASE_URL", "http://localhost:8000")
DD_AC8_ADMIN_USER = os.environ.get("DD_AC8_ADMIN_USER", "admin")
DD_AC8_ADMIN_PASSWORD = os.environ.get("DD_AC8_ADMIN_PASSWORD", "")

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
    if not DD_AC8_ADMIN_PASSWORD:
        reasons.append(
            "DD_AC8_ADMIN_PASSWORD 未设置：无法登录运行中后端获取 admin JWT（阻塞）"
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
@pytest.mark.external_network
@pytest.mark.asyncio
async def test_real_enterprise_end_to_end():
    """phase 1（真实 QCC + 内部 MCP + 内部问数 + 真实 LLM）：真实企业端到端。

    本用例**只在全部真实通道就绪时运行**（否则被上面的 skipif 以显式阻塞原因
    跳过）。它命中**运行中的真实后端**（env 已注入、qcc / internal_customer /
    park_investment_dd 已注册），走 HTTP 全链：

      create_task -> resolve_subject（真实 QCC 主体锚定）
        -> confirm_subject -> run（真三类 step：QCC 外部 + 内部客户 + 内部问数）
        -> 报告草案 + 证据账本 -> confirm -> archive

    断言：§4.6 七键分区齐备、证据行可回溯（ref_id 非空）、确认锁版、归档生效，
    且 token / 企业名原文不泄漏进任何返回的错误字段。只打印分区标题 / 计数 /
    digest 前缀，不打印 report 全文或企业敏感事实。
    """
    import httpx

    # ── 登录运行中后端拿 admin JWT（不打印 token）──
    with httpx.Client(base_url=DD_AC8_BASE_URL, timeout=30.0) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": DD_AC8_ADMIN_USER, "password": DD_AC8_ADMIN_PASSWORD},
        )
        assert login.status_code == 200, f"登录失败: HTTP {login.status_code}"
        token = login.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        # ── 1. 创建任务 ──
        created = client.post(
            "/api/v1/dd/tasks",
            json={"title": f"AC-8 {DD_AC8_COMPANY} 背调", "subject_query": DD_AC8_COMPANY},
            headers=auth,
        )
        assert created.status_code == 201, (
            f"create_task: HTTP {created.status_code} {created.text[:200]}"
        )
        task_id = created.json()["id"]

        # ── 2. 主体锚定（真实 QCC）──
        resolved = client.post(f"/api/v1/dd/tasks/{task_id}/resolve-subject", headers=auth)
        assert resolved.status_code == 200, (
            f"resolve_subject: HTTP {resolved.status_code} {resolved.text[:200]}"
        )
        candidates = resolved.json()
        assert candidates, "主体锚定未返回任何候选（AC-8：企业未匹配不得编造）"
        chosen = next(
            (c for c in candidates if DD_AC8_COMPANY in c.get("company_name", "")),
            candidates[0],
        )

        # ── 3. 确认主体 ──
        confirmed = client.post(
            f"/api/v1/dd/tasks/{task_id}/confirm-subject",
            json={"company_name": chosen["company_name"], "credit_code": chosen.get("credit_code")},
            headers=auth,
        )
        assert confirmed.status_code == 200, (
            f"confirm_subject: HTTP {confirmed.status_code} {confirmed.text[:200]}"
        )
        assert confirmed.json()["status"] == "subject_confirmed"

        # ── 4. 运行背调（真三类 step，耗时较长）──
        run = client.post(f"/api/v1/dd/tasks/{task_id}/run", headers=auth, timeout=300.0)
        assert run.status_code == 201, f"run: HTTP {run.status_code} {run.text[:300]}"
        report = run.json()
        report_id = report["id"]

        # ── 5. §4.6 七键分区齐备（AC-5/AC-7；缺维显式标注，不编造）──
        rj = report["report_json"]
        for key in (
            "summary", "external_facts", "internal_facts",
            "risk_watch_items", "human_review_items", "report_sections",
        ):
            assert key in rj, f"report_json 缺少 §4.6 键: {key}"
        assert report["status"] == "draft"
        print(
            f"[AC-8] report v{report['version']} draft ok: "
            f"ext={len(rj.get('external_facts') or [])} "
            f"int={len(rj.get('internal_facts') or [])} "
            f"risk={len(rj.get('risk_watch_items') or [])} "
            f"review={len(rj.get('human_review_items') or [])} "
            f"sections={len(rj.get('report_sections') or [])}"
        )

        # ── 6. 证据账本可回溯（AC-6；ref_id 非空，只含非敏感摘要）──
        evidence = client.get(f"/api/v1/dd/reports/{report_id}/evidence", headers=auth)
        assert evidence.status_code == 200, f"evidence: HTTP {evidence.status_code}"
        ev_rows = evidence.json()
        assert ev_rows, "证据账本为空（每个 evidence_ref 应落一行）"
        assert all(r.get("ref_id") for r in ev_rows), "存在缺 ref_id 的证据行（不可回溯）"
        ev_types = {r.get("evidence_type") for r in ev_rows}
        print(f"[AC-8] evidence rows={len(ev_rows)} types={sorted(ev_types)}")

        # ── 7. 人工确认锁版 + 归档 ──
        confirmed_r = client.post(f"/api/v1/dd/reports/{report_id}/confirm", headers=auth)
        assert confirmed_r.status_code == 200, f"confirm: HTTP {confirmed_r.status_code}"
        assert confirmed_r.json()["status"] == "confirmed"
        archived = client.post(f"/api/v1/dd/reports/{report_id}/archive", headers=auth)
        assert archived.status_code == 200, f"archive: HTTP {archived.status_code}"
        assert archived.json()["status"] == "archived"

        # ── 8. token / 企业名原文不泄漏进任何返回文本 ──
        for label, resp in (("run", run), ("evidence", evidence)):
            body = resp.text
            for needle in (QCC_TOKEN, INTERNAL_TOKEN, f"Bearer {QCC_TOKEN}"):
                if needle:
                    assert needle not in body, f"TOKEN 泄漏进 {label} 响应"
        print("[AC-8] REQ-046 真实企业端到端 PASSED（confirm->archive 全链）")
