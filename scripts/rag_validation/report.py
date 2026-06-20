"""Report rendering orchestrator + REQ-026 / REQ-028 sections.

Split out of the original monolithic script (TD-032 slice 8). `_render_report`
is the top-level orchestrator that calls into `report_quality`
(REQ-030) and `report_chain` (REQ-033 / REQ-034) for the appended sections.
"""

from __future__ import annotations

from typing import Any

from .loader import _mask_db_url
from .models import ScenarioRun
from .report_chain import _render_req033_section, _render_req034_section
from .report_quality import _render_req030_section
from .runner import (
    _compact_run,
    _compute_lift_metrics,
    _graph_edge_supplement_count,
    _group_runs,
    _json_preview,
)


def _render_req026_section(
    runs: list[ScenarioRun],
    grouped: dict[tuple[str, str], dict[str, ScenarioRun]],
    lift_mode: str = "residual",
) -> tuple[str, dict[str, Any]]:
    """Render REQ-026 weak recall section + collect summary stats."""
    stats = {
        "samples_total": 0,
        "samples_p2_better": 0,
        "samples_p2_worse": 0,
        "samples_p2_neutral": 0,
        "samples_qu_helps": 0,
        "samples_graph_edge_in_packed": 0,
        "samples_graph_edge_positive": 0,
        "data_gaps": [],
        "lift_mode": lift_mode,
    }
    lines: list[str] = []
    lines.append("## REQ-026 弱召回样例关键事实覆盖度对比")
    lines.append("")
    lines.append(f"- **Lift mode**: `{lift_mode}` (REQ-029 redesign: residual = (weighted - baseline) / (1 - baseline))")
    lines.append("")
    lines.append("| Sample | Category | baseline cov | +QU cov | +graph_edge cov | +weighted RRF cov | delta | residual_ratio | 判定 | edge_in_packed |")
    lines.append("|--------|----------|--------------|---------|-----------------|-------------------|-------|----------------|------|----------------|")
    sample_rows = 0
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-026":
            continue
        sample_rows += 1
        stats["samples_total"] += 1
        baseline = scenario_runs.get("baseline_rule_no_edge")
        qu = scenario_runs.get("query_understanding")
        edge = scenario_runs.get("graph_edge")
        weighted = scenario_runs.get("weighted_rrf")
        baseline_cov = baseline.keypoint_coverage_pct if baseline else 0.0
        qu_cov = qu.keypoint_coverage_pct if qu else 0.0
        edge_cov = edge.keypoint_coverage_pct if edge else 0.0
        weighted_cov = weighted.keypoint_coverage_pct if weighted else 0.0
        lift = _compute_lift_metrics(baseline_cov, weighted_cov, mode=lift_mode)
        delta = lift["delta"]
        residual_ratio = lift["residual_ratio"]
        verdict = lift["verdict"]
        if verdict == "正向":
            stats["samples_p2_better"] += 1
        elif verdict == "退化":
            stats["samples_p2_worse"] += 1
        else:
            stats["samples_p2_neutral"] += 1
        if (qu_cov - baseline_cov) >= 0.3:
            stats["samples_qu_helps"] += 1
        edge_packed = weighted.graph_edge_packed_count if weighted else 0
        if edge_packed > 0:
            stats["samples_graph_edge_in_packed"] += 1
            if verdict == "正向":
                stats["samples_graph_edge_positive"] += 1
        residual_str = (
            f"{residual_ratio:+.2f}" if residual_ratio is not None else "-"
        )
        lines.append(
            f"| {qid} | {group} | {baseline_cov:.2f} | {qu_cov:.2f} | "
            f"{edge_cov:.2f} | {weighted_cov:.2f} | {delta:+.2f} | {residual_str} | {verdict} | {edge_packed} |"
        )
    lines.append("")
    if sample_rows == 0:
        lines.append("- 本次未加载任何 REQ-026 弱召回样例，请检查 `--weak-recall-samples` 路径。")
        lines.append("")

    lines.append("### 自动比较结论")
    lines.append("")
    lines.append("- **机制层** (代码能力已接入): REQ-026 样例通过 `validate_req024_p2_real_validation.py` "
                 "脚本与 4 个 scenario (`baseline_rule_no_edge` / `query_understanding` / `graph_edge` / "
                 "`weighted_rrf`) 完成执行。")
    lines.append(
        f"- **prompt 层** (evidence 已进入 prompt): REQ-026 样例中 `graph_edge_in_packed > 0` 的样例数 = "
        f"`{stats['samples_graph_edge_in_packed']}` / `{stats['samples_total']}`。"
    )
    lines.append(
        f"- **质量层** (真实 LLM 回答覆盖度提升): P2 完整链路相对 baseline 覆盖度提升 >= 30% 的样例数 = "
        f"`{stats['samples_p2_better']}` / `{stats['samples_total']}`；退化样例数 = "
        f"`{stats['samples_p2_worse']}`。"
    )
    lines.append(
        f"- **Query Understanding 价值**: `+QU` 覆盖度相对 baseline 提升 >= 30% 的样例数 = "
        f"`{stats['samples_qu_helps']}` / `{stats['samples_total']}`。"
    )
    lines.append(
        f"- **graph_edge 价值**: `graph_edge in packed > 0` 且 delta >= 0.3 的样例数 = "
        f"`{stats['samples_graph_edge_positive']}` / `{stats['samples_total']}`。"
    )
    lines.append("")

    lines.append("### 数据缺口与后续任务")
    lines.append("")
    if stats["samples_p2_better"] < 1:
        lines.append("- 当前 dev DB 数据集未能构造足够的弱召回样例来证明 P2 完整链路相对 baseline 提升 >= 30%。")
        lines.append("- 后续任务候选：")
        lines.append("  - `TD-068`: query embedding 为空导致 vector 通道降级为 keyword fallback（已登记，需修）")
        lines.append("  - 新增 `REQ-027` (待登记): 增加 P2 弱召回知识覆盖 — 课程标准 / Python 高级特性 / 跨课程先导关系")
        stats["data_gaps"].append("P2 弱召回样例不足")
    if stats["samples_graph_edge_in_packed"] < 1:
        lines.append("- 当前所有 REQ-026 弱召回样例中 graph_edge 都未进入 packed context。")
        lines.append("- 后续任务候选：")
        lines.append("  - 复核 ContextPacker 对 `knowledge_edge` source block 的 packed 阈值")
        lines.append("  - 增加 `knowledge_edges` 真实样本数据（dev DB backfill）")
        stats["data_gaps"].append("graph_edge 未进入 packed context")
    if stats["samples_qu_helps"] < 1:
        lines.append("- Query Understanding 对自然问法的增益证据不足。")
        lines.append("- 后续任务候选：")
        lines.append("  - 复核 HybridQueryUnderstandingService 在自然问法场景下的 expanded_terms 命中率")
        lines.append("  - 增强规则优先 + LLM 低置信触发的样本多样性")
        stats["data_gaps"].append("Query Understanding 增益不足")
    if not stats["data_gaps"]:
        lines.append("- 当前未发现数据缺口；后续根据样本扩展决定是否新增独立任务。")
    lines.append("")
    return "\n".join(lines), stats


def _render_req028_section(
    runs: list[ScenarioRun],
    grouped: dict[tuple[str, str], dict[str, ScenarioRun]],
    lift_mode: str = "residual",
) -> str:
    """REQ-028: render three-metric coverage (substring / semantic / llm_judge)."""
    lines: list[str] = []
    lines.append("## REQ-028 三口径覆盖度对比")
    lines.append("")
    lines.append(f"- **Lift mode**: `{lift_mode}` (REQ-029 redesign)")
    lines.append("")
    lines.append("| Sample | Scenario | substring cov | semantic cov | weight cov | llm_judge cov | semantic 命中明细 |")
    lines.append("|--------|----------|---------------|--------------|------------|---------------|-------------------|")
    rows = 0
    semantic_above_threshold = 0
    semantic_lift_threshold = 0
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-028":
            continue
        for scenario_name in [
            "baseline_rule_no_edge",
            "query_understanding",
            "graph_edge",
            "weighted_rrf",
        ]:
            run = scenario_runs.get(scenario_name)
            if not run:
                continue
            rows += 1
            judge_str = (
                f"{run.keypoint_llm_judge_pct:.2f}"
                if isinstance(run.keypoint_llm_judge_pct, (int, float))
                else "-"
            )
            sem_terms = ",".join(run.keypoint_hit_list_semantic[:5]) or "-"
            lines.append(
                f"| {qid} | {scenario_name} | "
                f"{run.keypoint_coverage_pct_substring:.2f} | "
                f"{run.keypoint_coverage_pct_semantic:.2f} | "
                f"{run.keypoint_weight_pct_semantic:.2f} | "
                f"{judge_str} | "
                f"{sem_terms} |"
            )
    lines.append("")
    # Per-sample summary (delta on semantic metric)
    lines.append("### REQ-028 per-sample summary (semantic metric)")
    lines.append("")
    lines.append("| Sample | baseline sem | weighted sem | delta | residual_ratio | 判定 (sem) | edge_in_packed |")
    lines.append("|--------|--------------|--------------|-------|----------------|-------------|----------------|")
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-028":
            continue
        baseline = scenario_runs.get("baseline_rule_no_edge")
        weighted = scenario_runs.get("weighted_rrf")
        if not baseline or not weighted:
            continue
        baseline_sem = baseline.keypoint_coverage_pct_semantic
        weighted_sem = weighted.keypoint_coverage_pct_semantic
        lift = _compute_lift_metrics(baseline_sem, weighted_sem, mode=lift_mode)
        delta = lift["delta"]
        residual_ratio = lift["residual_ratio"]
        verdict = lift["verdict"]
        if weighted_sem >= 0.5:
            semantic_above_threshold += 1
        if verdict == "正向":
            semantic_lift_threshold += 1
        residual_str = (
            f"{residual_ratio:+.2f}" if residual_ratio is not None else "-"
        )
        lines.append(
            f"| {qid} | {baseline_sem:.2f} | "
            f"{weighted_sem:.2f} | {delta:+.2f} | {residual_str} | {verdict} | "
            f"{weighted.graph_edge_packed_count} |"
        )
    lines.append("")
    lines.append("### REQ-028 三口径决策依据")
    lines.append("")
    lines.append("- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致；保留向后兼容。")
    lines.append("- **semantic 口径 (主验收)**: term + synonyms 集合匹配，命中权重 1.0，修饰词权重 ≤0.5。")
    lines.append("- **weight 口径 (semantic 加权)**: 按 Keypoint.weight 加权后的覆盖率；用于区分核心词与修饰词。")
    lines.append("- **llm_judge 口径 (secondary signal)**: 由 LLM-as-judge 评估，仅在 `--allow-llm` 模式下生效；不作为唯一判定。")
    lines.append("- **lift 口径 (REQ-029 阈值)**: residual_ratio = (weighted - baseline) / (1 - baseline)，解决 baseline 接近上限时绝对 delta 失去判别力的问题。")
    lines.append("- **决策规则**: 当 semantic 与 substring 不一致时（如 semantic ≥ 0.50 但 substring = 0），优先看 semantic；语义匹配覆盖更准确反映真实命中。")
    lines.append("")
    lines.append(f"- **AC-4 (semantic ≥ 0.50)**: `{semantic_above_threshold}` 样例达标（独立看 weighted scenario）")
    lines.append(f"- **AC-5 (semantic lift >= 0.30 in `{lift_mode}` mode)**: `{semantic_lift_threshold}` 样例达标")
    if lift_mode == "residual" and semantic_lift_threshold < 4:
        lines.append("- **未达成**: AC-5 residual 模式仍不达 4/10。已登记 REQ-030 接力。")
    lines.append("")
    return "\n".join(lines)


def _render_report(
    *,
    runs: list[ScenarioRun],
    tenant_id: str,
    db_url: str,
    allow_llm: bool,
    started_at: str,
    errors: list[str],
    report_title: str,
    lift_mode: str = "residual",
) -> str:
    grouped = _group_runs(runs)
    lines: list[str] = []
    lines.append(f"# {report_title}")
    lines.append("")
    lines.append("## 环境")
    lines.append("")
    lines.append(f"- Generated At: `{started_at}`")
    lines.append(f"- DB: `{_mask_db_url(db_url)}`")
    lines.append(f"- Tenant: `{tenant_id}`")
    lines.append(f"- External LLM: `{'enabled' if allow_llm else 'disabled-dry-run'}`")
    lines.append(f"- Validation Status: `{'real-llm-run' if allow_llm else 'partial-dry-run-only'}`")
    lines.append("")

    if errors:
        lines.append("## 运行错误")
        lines.append("")
        for err in errors:
            lines.append(f"- {err}")
        lines.append("")

    lines.append("## REQ-016 Query Understanding 验收")
    lines.append("")
    lines.append("| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |")
    lines.append("|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|")
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-016":
            continue
        for scenario_name in [
            "baseline_rule_no_edge",
            "query_understanding",
            "graph_edge",
            "weighted_rrf",
        ]:
            run = scenario_runs.get(scenario_name)
            if not run:
                continue
            qu = run.query_understanding or {}
            lines.append(
                f"| {qid} | {scenario_name} | "
                f"{qu.get('method', '-')} | {qu.get('confidence', '-')} | "
                f"{_json_preview(qu.get('expanded_terms', []), limit=160)} | "
                f"{_json_preview(run.retrieval_counts, limit=160)} | "
                f"{run.vector_fallback_count} | "
                f"{len(run.packed_blocks)} | {run.final_answer_preview[:120]} |"
            )
    lines.append("")

    lines.append("## REQ-018 graph_edge 补足样例分析")
    lines.append("")
    lines.append("| Query | graph_edge topN | edge in fusion | edge in packed | edge chunks not in baseline fusion | retrieval counts |")
    lines.append("|-------|-----------------|----------------|----------------|------------------------------------|------------------|")
    fusion_level_supplement_examples = 0
    prompt_level_supplement_examples = 0
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-018":
            continue
        edge = scenario_runs.get("graph_edge")
        weighted = scenario_runs.get("weighted_rrf")
        selected = weighted or edge
        if not selected:
            continue
        supplement_count = _graph_edge_supplement_count(scenario_runs)
        if supplement_count > 0:
            fusion_level_supplement_examples += 1
        if supplement_count > 0 and selected.graph_edge_packed_count > 0:
            prompt_level_supplement_examples += 1
        lines.append(
            f"| {qid} | {selected.graph_edge_retrieval_count} | "
            f"{selected.graph_edge_fusion_count} | {selected.graph_edge_packed_count} | "
            f"{supplement_count} | {_json_preview(selected.retrieval_counts, limit=180)} |"
        )
    lines.append("")

    lines.append("## 对比结论")
    lines.append("")
    if not allow_llm:
        lines.append("- 本报告以 `External LLM: disabled-dry-run` 生成，不能作为最终真实效果验收通过证据。")
        lines.append("- dry-run 只证明脚本、DB 链路、召回 diagnostics 和报告结构可复跑。")
        lines.append("- dry-run 下的 Query Understanding 使用脚本内 fake provider，不代表真实 LLM 解析质量。")
    else:
        lines.append("- 本报告启用了外部 LLM，可用于 REQ-016 / REQ-018 的真实效果验收判断。")
    vector_fallback_total = sum(run.vector_fallback_count for run in runs)
    lines.append(
        f"- vector fallback trace count: `{vector_fallback_total}` "
        "(大于 0 表示 vector 通道结果来自 keyword fallback，不代表真实语义向量召回)。"
    )
    lines.append(
        f"- graph_edge fusion-level supplement examples: `{fusion_level_supplement_examples}` "
        "(只表示 graph_edge 召回的新 chunk 进入 fusion 阶段)。"
    )
    lines.append(
        f"- graph_edge prompt-level supplement examples: `{prompt_level_supplement_examples}` "
        "(REQ-024 AC-2 的强验收应以进入 packed context / prompt 并改善最终回答为准)。"
    )
    if prompt_level_supplement_examples < 2:
        lines.append(
            "- 结论：graph_edge 已能补足 fusion 候选，但尚未证明进入最终 prompt；"
            "需要登记后续数据 / 权重 / context packer 任务。"
        )
    elif not allow_llm:
        lines.append(
            "- 结论：graph_edge 已在 dry-run 中满足至少 2 个样例进入 packed context；"
            "仍需真实 LLM provider 验收最终回答改善。"
        )
    else:
        lines.append(
            "- 结论：本报告已完成真实 LLM provider run；prompt-level 是否达标可由 "
            "`graph_edge prompt-level supplement examples` 判断，最终回答是否改善仍需结合 "
            "baseline / graph_edge / weighted_rrf 的 answer preview 做人工或自动质量比较。"
        )
    lines.append("")

    lines.append("## 原始 JSON 摘要")
    lines.append("")
    lines.append("```json")
    lines.append(_json_preview([_compact_run(run) for run in runs], limit=4000))
    lines.append("```")
    lines.append("")

    # REQ-026 section (added in REQ-026 extension)
    if any(run.question_group == "REQ-026" for run in runs):
        req026_section, req026_stats = _render_req026_section(runs, grouped, lift_mode=lift_mode)
        lines.append(req026_section)
        lines.append("")

    # REQ-028 section (three-metric comparison)
    if any(run.question_group == "REQ-028" for run in runs):
        req028_section = _render_req028_section(runs, grouped, lift_mode=lift_mode)
        lines.append(req028_section)
        lines.append("")

    # REQ-030 section (semantic embedding + LLM-as-judge)
    if any(run.question_group == "REQ-028" for run in runs) and any(
        run.keypoint_semantic_embedding_pct > 0.0 or run.keypoint_llm_judge_pct is not None
        for run in runs
    ):
        req030_section = _render_req030_section(runs, grouped)
        lines.append(req030_section)
        lines.append("")

    # REQ-033 section (P2 chain real-vector value evaluation, retrieval-layer metrics)
    if any(run.question_group == "REQ-028" for run in runs):
        req033_section = _render_req033_section(runs, grouped)
        lines.append(req033_section)
        lines.append("")

    # REQ-034 section (graph_edge RRF weight/strategy adjustment evaluation)
    if any(run.question_group == "REQ-028" for run in runs):
        req034_section = _render_req034_section(runs, grouped)
        lines.append(req034_section)
        lines.append("")

    return "\n".join(lines)
