"""REQ-035 report section: graph_edge channel keep / disable / boost decision.

Split out of `report_chain.py` (TD-032 slice 8 follow-up) to keep each module
≤500 lines. Cost-benefit decision built on REQ-033/034 evidence from the same
dry-run. Reuses `_req034_scenario_metrics` from `report_chain`.
"""

from __future__ import annotations

from .models import ScenarioRun
from .report_chain import _req034_scenario_metrics


def _render_req035_section(
    runs: list[ScenarioRun],
    grouped: dict[tuple[str, str], dict[str, ScenarioRun]],
) -> str:
    """REQ-035: graph_edge channel keep / disable / boost decision.

    Cost-benefit analysis built on REQ-033/034 evidence (same dry-run data):
    - cost side: edge recall runs 3 SQLs per query, ~8 chunks recalled, 0 into
      fusion/packed at production default weight 0.5.
    - benefit side: even at w=1.2 boosting, edge into packed = 50% but Metric B
      (cross-section) = 1/10 and cross-doc grounding = 0/10 (REQ-033) — limited
      answer-quality gain.
    Renders the decision framework + recommendation. No main-chain change.
    """
    lines: list[str] = []
    lines.append("## REQ-035 graph_edge 通道去留决策")
    lines.append("")
    lines.append("> REQ-034 证生产默认权重 0.5 下 graph_edge 惰性（召回 8 chunks/样例但 0 进 fusion/packed）。")
    lines.append("> 本节在「禁用（省召回成本）」vs「上调权重使贡献」vs「维持现状」间给出决策。")
    lines.append("")

    # Gather production-default (w=0.5) cost/produce numbers from REQ-028 dry-run.
    default_recall = 0.0
    default_packed_pos = 0
    total = 0
    for (group, _qid), scenario_runs in grouped.items():
        if group != "REQ-028":
            continue
        run = scenario_runs.get("graph_edge")  # production default weight 0.5
        if not run:
            continue
        total += 1
        default_recall += len(run.graph_edge_chunk_ids)
        if run.graph_edge_packed_count > 0:
            default_packed_pos += 1
    default_recall_mean = (default_recall / total) if total else 0.0
    default_packed_rate = (default_packed_pos / total) if total else 0.0

    # w=1.2 boosted produce numbers (REQ-034 sweep).
    boosted = _req034_scenario_metrics(grouped, "weighted_rrf", "baseline_rule_no_edge")
    boosted_packed_rate = boosted["metric_a"] if boosted else 0.0
    boosted_section_rate = boosted["metric_b"] if boosted else 0.0
    boosted_crossdoc_rate = boosted["cross_doc"] if boosted else 0.0

    # Table 1: cost/benefit across three options
    lines.append("### 1. 成本/收益对照（REQ-028 10 样例 dry-run）")
    lines.append("")
    lines.append("| 方案 | 每 query 召回成本 | edge 进 packed | 跨 section 扩展 | 跨文档 grounding |")
    lines.append("|------|------------------|----------------|-----------------|------------------|")
    lines.append(
        f"| 维持现状（默认 0.5） | ~{default_recall_mean:.0f} chunks / 3 SQL（全无效） | "
        f"{default_packed_rate:.0%} | 0% | 0% |"
    )
    lines.append(
        f"| 上调权重（≥1.2 boosting） | ~{default_recall_mean:.0f} chunks / 3 SQL | "
        f"{boosted_packed_rate:.0%} | {boosted_section_rate:.0%} | {boosted_crossdoc_rate:.0%} |"
    )
    lines.append("| 禁用通道（edge_retriever=None） | 0 chunks / 0 SQL | 0% | 0% | 0% |")
    lines.append("")
    lines.append(
        f"- 生产默认 0.5：graph_edge 每样例召回 ~{default_recall_mean:.0f} chunks（3 SQL），"
        f"进 packed {default_packed_pos}/{total}（{default_packed_rate:.0%}）——纯无效召回成本。"
    )
    lines.append(
        f"- 上调到 1.2 boosting：edge 进 packed 提升至 {boosted_packed_rate:.0%}，但跨 section 扩展仅 "
        f"{boosted_section_rate:.0%}、跨文档 grounding {boosted_crossdoc_rate:.0%}（REQ-033）——对答案质量增益有限。"
    )
    lines.append("- 禁用通道：召回成本归零，产出与维持现状相同（0 进 packed）。")
    lines.append("")

    # Table 2: disable feasibility
    lines.append("### 2. 禁用通道可行性")
    lines.append("")
    lines.append("| 维度 | 评估 |")
    lines.append("|------|------|")
    lines.append(
        "| 机制 | `edge_retriever=None` 已存在（`_safe_retrieve_edge` 直接 return []）；生产禁用 = `ai_router._build_evidence_service` 不注入 `PgEdgeRetriever()` 或 config 门控。代码改动小 |"
    )
    lines.append(
        "| REQ-018 影响 | 验收点「4 通道 graph_edge 召回能力」——禁用即生产降为 3 通道，验收需重判；但 `PgEdgeRecallChannel` 召回能力代码保留，仅生产未启用 |"
    )
    lines.append(
        "| REQ-025 影响 | REQ-034 已补「生产默认 0.5 下 edge 0 进 prompt」说明，禁用与之一致，不引入新回归；需重跑真 LLM 验收确认 baseline 答案质量不退步 |"
    )
    lines.append(
        "| 测试覆盖 | `test_pg_edge_retriever.py` 测召回能力本身，禁用生产注入不影响单测；`test_ai_chat_service.py` / `test_context_packer.py` 部分 scenario 注入 edge 需复核 |"
    )
    lines.append("")

    # Table 3: boost feasibility
    lines.append("### 3. 上调权重可行性")
    lines.append("")
    lines.append("| 维度 | 评估 |")
    lines.append("|------|------|")
    lines.append(
        "| 机制 | 改 `_RRF_DEFAULT_WEIGHTS['graph_edge']` 0.5 → ≥1.2，或文档建议生产设 `RRF_CHANNEL_WEIGHTS` env。配置改动 |"
    )
    lines.append(
        f"| 收益 | weight sweep：1.2 下 Metric A 0%→{boosted_packed_rate:.0%}（edge 进 packed）。但 REQ-033 证即使进 packed，Metric B={boosted_section_rate:.0%}、跨文档={boosted_crossdoc_rate:.0%}——对答案质量增益有限 |"
    )
    lines.append(
        "| 成本 | 维持每 query 3 SQL 召回成本；且 edge 进 packed 占 budget 替换 baseline chunk（REQ-033 packed_overlap 5-6/8） |"
    )
    lines.append(
        "| REQ-018/025 影响 | 通道保留，REQ-018 不受影响；REQ-025 edge 进 prompt 样例 0→50%，需重跑真 LLM 验收 |"
    )
    lines.append("")

    # Decision per spec §5.4
    lines.append("### 4. 决策判定")
    lines.append("")
    lines.append(
        f"- 成本侧：生产默认 0.5 下每 query ~{default_recall_mean:.0f} chunks 召回（3 SQL）完全无效（0 进 fusion/packed）。"
    )
    lines.append(
        f"- 收益侧上限：即使上调到 1.2 boosting 使 edge 进 packed {boosted_packed_rate:.0%}，REQ-033 证跨 section 扩展仅 "
        f"{boosted_section_rate:.0%}、跨文档 grounding {boosted_crossdoc_rate:.0%}——对答案质量增益有限，且维持召回成本。"
    )
    lines.append("")
    # Decision logic: cost (pure waste at default) vs benefit ceiling (limited even when boosted).
    # Production default already inert -> disable removes pure waste at no output loss;
    # boost pays full cost for limited gain. Disable is the dominant option.
    decision = "禁用 graph_edge 通道（省召回成本）"
    action = (
        "成本侧确定（生产默认 0.5 下召回完全无效，纯浪费每 query 3 SQL）；收益侧上限有限（即使 boosting 亦不改善 Metric B/跨文档，"
        "REQ-033 已证）。禁用消除纯浪费且产出与现状相同（0 进 packed）；上调需维持成本换取有限增益，性价比低。"
        "决策：禁用 graph_edge 通道。登记独立实现需求做 config 门控（`edge_retriever` 经 env/配置注入，保留 `PgEdgeRecallChannel` 代码），"
        "并重跑 REQ-025 真 LLM 验收确认 baseline 答案质量不退步 + REQ-018 4 通道验收降级为「3 通道生产 + edge 通道保留可启用」。"
        "本任务不改代码。"
    )
    lines.append(f"- **决策**: `{decision}`")
    lines.append(f"- **依据与动作**: {action}")
    lines.append("")

    lines.append("### 5. 结论")
    lines.append("")
    lines.append(
        "- 本评估不修改主链路代码（RRFFusion / ContextPacker / AIChatService / recall_service / PgEdgeRecallChannel / ai_router）。"
    )
    lines.append(
        "- graph_edge 通道召回能力（`PgEdgeRecallChannel`）代码保留；禁用仅指生产环境不注入 `PgEdgeRetriever()`，"
        "经 config 门控后可随时重新启用（如 vector 召回退化或图谱扩充时）。"
    )
    lines.append(
        "- 决策为禁用，需独立实现需求承接：(1) config 门控 edge_retriever 注入；(2) 重跑 REQ-025 真 LLM 验收；"
        "(3) REQ-018 验收基线降级说明（3 通道生产 + edge 通道保留可启用）。"
    )
    lines.append(
        "- 与 REQ-034 一致：graph_edge 在真 vector 下价值有限是技术演进自然结果，非链路缺陷。"
    )
    lines.append("")
    return "\n".join(lines)
