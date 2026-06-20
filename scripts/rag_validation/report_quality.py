"""REQ-030 report section: semantic embedding + LLM-as-judge four-metric comparison.

Split out of the original monolithic script (TD-032 slice 8). Reads the
process-singleton `_EMB_STATS` from `coverage` for the REQ-031 cache
diagnostics line.
"""

from __future__ import annotations


from .coverage import _EMB_STATS
from .models import ScenarioRun


def _render_req030_section(
    runs: list[ScenarioRun],
    grouped: dict[tuple[str, str], dict[str, ScenarioRun]],
) -> str:
    """REQ-030: render semantic embedding + LLM-as-judge four-metric comparison.

    Per-sample matrix: substring / semantic / semantic embedding / LLM-as-judge
    coverage. Plus Spearman correlation between semantic embedding and LLM-as-judge.
    """
    lines: list[str] = []
    lines.append("## REQ-030 新口径对比（semantic embedding + LLM-as-judge）")
    lines.append("")
    # REQ-031: embedding cache stats (hit / miss / timeout / error)
    total_emb = sum(_EMB_STATS.values())
    if total_emb > 0:
        lines.append(
            f"> REQ-031 embedding cache: hit=`{_EMB_STATS['hit']}` miss=`{_EMB_STATS['miss']}` "
            f"timeout=`{_EMB_STATS['timeout']}` error=`{_EMB_STATS['error']}` (total=`{total_emb}`)"
        )
        lines.append("")
    lines.append("| Sample | Scenario | substring cov | semantic cov | semantic_emb cov | semantic_emb weight | cont cov | LLM-as-judge cov |")
    lines.append("|--------|----------|----------------|--------------|--------------------|----------------------|----------|-------------------|")
    sem_emb_pairs: list[tuple[float, float]] = []
    cont_judge_pairs: list[tuple[float, float]] = []
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
            judge_str = (
                f"{run.keypoint_llm_judge_pct:.2f}"
                if isinstance(run.keypoint_llm_judge_pct, (int, float))
                else "-"
            )
            lines.append(
                f"| {qid} | {scenario_name} | "
                f"{run.keypoint_coverage_pct_substring:.2f} | "
                f"{run.keypoint_coverage_pct_semantic:.2f} | "
                f"{run.keypoint_semantic_embedding_pct:.2f} | "
                f"{run.keypoint_semantic_embedding_weight_pct:.2f} | "
                f"{run.keypoint_semantic_embedding_continuous_pct:.2f} | "
                f"{judge_str} |"
            )
            if isinstance(run.keypoint_llm_judge_pct, (int, float)):
                sem_emb_pairs.append(
                    (run.keypoint_semantic_embedding_pct, run.keypoint_llm_judge_pct)
                )
                cont_judge_pairs.append(
                    (run.keypoint_semantic_embedding_continuous_pct, run.keypoint_llm_judge_pct)
                )
    lines.append("")

    # Spearman correlation between semantic_emb and llm_judge
    if len(sem_emb_pairs) >= 3:
        try:
            from scipy.stats import spearmanr  # type: ignore
            xs, ys = zip(*sem_emb_pairs)
            rho, _ = spearmanr(xs, ys)
            rho_str = f"{rho:.3f}"
        except ImportError:
            # fallback: simple Pearson
            n = len(sem_emb_pairs)
            mx = sum(p[0] for p in sem_emb_pairs) / n
            my = sum(p[1] for p in sem_emb_pairs) / n
            num = sum((p[0] - mx) * (p[1] - my) for p in sem_emb_pairs)
            den_a = sum((p[0] - mx) ** 2 for p in sem_emb_pairs) ** 0.5
            den_b = sum((p[1] - my) ** 2 for p in sem_emb_pairs) ** 0.5
            rho = num / (den_a * den_b) if den_a * den_b > 0 else 0.0
            rho_str = f"{rho:.3f} (Pearson fallback, scipy unavailable)"
    else:
        rho = 0.0
        rho_str = "n/a"

    def _pearson(pairs: list[tuple[float, float]]) -> str:
        if len(pairs) < 3:
            return "n/a"
        n = len(pairs)
        mx = sum(p[0] for p in pairs) / n
        my = sum(p[1] for p in pairs) / n
        num = sum((p[0] - mx) * (p[1] - my) for p in pairs)
        da = sum((p[0] - mx) ** 2 for p in pairs) ** 0.5
        db = sum((p[1] - my) ** 2 for p in pairs) ** 0.5
        r = num / (da * db) if da * db > 0 else 0.0
        return f"{r:.3f} (Pearson)"

    cont_rho_str = _pearson(cont_judge_pairs)
    lines.append("### REQ-030 双口径一致性")
    lines.append("")
    lines.append(
        f"- semantic embedding (threshold-based) vs LLM-as-judge: `{rho_str}` (n={len(sem_emb_pairs)})"
    )
    lines.append(
        f"- continuous weighted coverage vs LLM-as-judge: `{cont_rho_str}` (n={len(cont_judge_pairs)})"
    )
    lines.append("- AC-5 (semantic embedding delta ≥ 0.30) threshold: 见下方 per-sample summary")
    lines.append("")

    # Per-sample summary (semantic embedding delta)
    lines.append("### REQ-030 per-sample summary (semantic embedding metric)")
    lines.append("")
    lines.append("| Sample | baseline sem_emb | weighted sem_emb | delta | 判定 (sem_emb) | baseline cont | weighted cont | cont delta | 判定 (cont) | LLM-judge delta | 判定 (judge) |")
    lines.append("|--------|------------------|------------------|-------|-----------------|---------------|---------------|------------|--------------|-----------------|----------------|")
    sem_emb_above = 0
    sem_emb_lift = 0
    judge_lift = 0
    cont_lift = 0
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-028":
            continue
        baseline = scenario_runs.get("baseline_rule_no_edge")
        weighted = scenario_runs.get("weighted_rrf")
        if not baseline or not weighted:
            continue
        delta = weighted.keypoint_semantic_embedding_pct - baseline.keypoint_semantic_embedding_pct
        if delta >= 0.30:
            verdict_se = "正向"
            sem_emb_lift += 1
        elif delta <= -0.30:
            verdict_se = "退化"
        else:
            verdict_se = "中性"
        if weighted.keypoint_semantic_embedding_pct >= 0.5:
            sem_emb_above += 1
        # REQ-032: continuous delta
        cont_delta = (
            weighted.keypoint_semantic_embedding_continuous_pct
            - baseline.keypoint_semantic_embedding_continuous_pct
        )
        if cont_delta >= 0.30:
            verdict_cont = "正向"
            cont_lift += 1
        elif cont_delta <= -0.30:
            verdict_cont = "退化"
        else:
            verdict_cont = "中性"
        if (
            isinstance(baseline.keypoint_llm_judge_pct, (int, float))
            and isinstance(weighted.keypoint_llm_judge_pct, (int, float))
        ):
            judge_delta = weighted.keypoint_llm_judge_pct - baseline.keypoint_llm_judge_pct
            if judge_delta >= 0.30:
                verdict_j = "正向"
                judge_lift += 1
            elif judge_delta <= -0.30:
                verdict_j = "退化"
            else:
                verdict_j = "中性"
        else:
            judge_delta = 0.0
            verdict_j = "-"
        lines.append(
            f"| {qid} | {baseline.keypoint_semantic_embedding_pct:.2f} | "
            f"{weighted.keypoint_semantic_embedding_pct:.2f} | {delta:+.2f} | {verdict_se} | "
            f"{baseline.keypoint_semantic_embedding_continuous_pct:.2f} | "
            f"{weighted.keypoint_semantic_embedding_continuous_pct:.2f} | {cont_delta:+.2f} | {verdict_cont} | "
            f"{judge_delta:+.2f} | {verdict_j} |"
        )
    lines.append("")
    lines.append("### REQ-030 三口径决策依据")
    lines.append("")
    lines.append("- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致。子串匹配，**不能识别 LLM 同义改写**——这是 REQ-028 v3 重跑后 AC 退步的根因。")
    lines.append("- **semantic 口径 (REQ-028)**: term + synonyms 子串匹配集合，weight 加权。")
    lines.append("- **semantic embedding 口径 (REQ-030, 主验收)**: 硅流 embedding 计算 answer 与 keypoint 余弦相似度，threshold 0.5 命中。**能识别同义改写**。")
    lines.append("- **LLM-as-judge 口径 (REQ-028+030 secondary signal)**: LLM 评估 answer 与 keypoints 覆盖度，输出 JSON。仅在 `--allow-llm` 启用。")
    lines.append("- **决策规则**: 在真 vector 召回下，substring / semantic 口径系统性低估 P2 长链能力；semantic embedding 是主验收口径，LLM-as-judge 是双口径一致性验证。")
    lines.append("")
    lines.append(f"- **AC-4 (semantic_emb ≥ 0.50)**: `{sem_emb_above}` 样例达标")
    lines.append(f"- **AC-5 (semantic_emb lift >= 0.30)**: `{sem_emb_lift}` 样例达标")
    lines.append(f"- **AC-5 (continuous lift >= 0.30)**: `{cont_lift}` 样例达标 (REQ-032 secondary)")
    lines.append(f"- **AC-5 (LLM-judge lift >= 0.30)**: `{judge_lift}` 样例达标 (secondary signal)")
    if sem_emb_lift < 4 and cont_lift < 4:
        lines.append("- **未达成**: AC-5 semantic_emb + continuous 双口径均不达 4/10。根因诊断见报告 §0.1（P2 链路在真 vector 下对 keypoint 覆盖无系统性正向贡献，非阈值问题）。")
    lines.append("")
    return "\n".join(lines)
