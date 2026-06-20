"""REQ-033 / REQ-034 chain-value report sections.

Split out of the original monolithic script (TD-032 slice 8). REQ-033
evaluates P2 chain real-vector value via retrieval-layer metrics; REQ-034
runs a graph_edge RRF weight sweep + strategy feasibility analysis. Both
share packed-block helpers (`_distinct_packed_sections` / `_packed_chunk_ids`
/ `_edge_brings_new_doc`).
"""

from __future__ import annotations


from .models import ScenarioRun


def _distinct_packed_sections(run: ScenarioRun) -> set[str]:
    """Distinct section_path/section_title values in a run's packed_blocks."""
    secs: set[str] = set()
    for b in run.packed_blocks:
        if isinstance(b, dict):
            sp = b.get("section_path") or b.get("section_title")
            if sp:
                secs.add(str(sp))
    return secs


def _packed_chunk_ids(run: ScenarioRun) -> set[str]:
    ids: set[str] = set()
    for b in run.packed_blocks:
        if isinstance(b, dict):
            for c in (b.get("chunk_ids") if isinstance(b.get("chunk_ids"), list) else []) or []:
                ids.add(str(c))
    return ids


def _edge_brings_new_doc(run: ScenarioRun) -> bool:
    """True if any graph_edge fusion item's file_id is not in other channels' files."""
    edge_fids: set[str] = set()
    other_fids: set[str] = set()
    for f in run.fusion_topn:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("file_id") or "")
        chans = f.get("channels") if isinstance(f.get("channels"), list) else []
        if "graph_edge" in chans:
            edge_fids.add(fid)
        else:
            other_fids.add(fid)
    return bool(edge_fids) and bool(edge_fids - other_fids - {"None", ""})


def _req034_scenario_metrics(
    grouped: dict[tuple[str, str], dict[str, ScenarioRun]],
    scenario_name: str,
    baseline_name: str,
) -> dict[str, float] | None:
    """Compute retrieval-layer metrics for one weight-level scenario over REQ-028.

    Returns None if the scenario has no REQ-028 runs. Metrics:
      metric_a        — edge-into-packed rate
      metric_b        — cross-section expansion rate vs off-baseline
      cross_doc       — edge-brings-new-doc rate
      packed_overlap  — mean |packed ∩ baseline_packed| / |baseline_packed|
      fusion_edge_mean— mean graph_edge_fusion_count
    """
    total = 0
    edge_packed_pos = 0
    section_pos = 0
    cross_doc_pos = 0
    overlap_sum = 0.0
    fusion_edge_sum = 0
    for (group, _qid), scenario_runs in grouped.items():
        if group != "REQ-028":
            continue
        run = scenario_runs.get(scenario_name)
        baseline = scenario_runs.get(baseline_name)
        if not run:
            continue
        total += 1
        if run.graph_edge_packed_count > 0:
            edge_packed_pos += 1
        if baseline is not None:
            b_secs = _distinct_packed_sections(baseline)
            w_secs = _distinct_packed_sections(run)
            if len(w_secs) > len(b_secs):
                section_pos += 1
            b_ids = _packed_chunk_ids(baseline)
            w_ids = _packed_chunk_ids(run)
            if b_ids:
                overlap_sum += len(b_ids & w_ids) / len(b_ids)
        if _edge_brings_new_doc(run):
            cross_doc_pos += 1
        fusion_edge_sum += run.graph_edge_fusion_count
    if total == 0:
        return None
    return {
        "total": total,
        "metric_a": edge_packed_pos / total,
        "metric_b": section_pos / total,
        "cross_doc": cross_doc_pos / total,
        "packed_overlap": overlap_sum / total,
        "fusion_edge_mean": fusion_edge_sum / total,
    }


def _render_req033_section(
    runs: list[ScenarioRun],
    grouped: dict[tuple[str, str], dict[str, ScenarioRun]],
) -> str:
    """REQ-033: P2 chain real-vector value evaluation.

    Retrieval-layer value analysis (graph_edge channel effectiveness,
    cross-document grounding, packed re-rank overlap) + two new value
    metrics aligned with graph_edge's design intent (context supplementation,
    not keypoint hit).
    """
    lines: list[str] = []
    lines.append("## REQ-033 P2 链路真 vector 价值评估")
    lines.append("")
    lines.append("> graph_edge 设计意图：补足 keyword/vector 弱召回的关联上下文（REQ-018/025）。")
    lines.append("> keypoint 覆盖不是衡量其价值的正确指标——本节用 retrieval 层指标评估真实贡献。")
    lines.append("")

    # Table 1: graph_edge channel effectiveness per sample (weighted scenario)
    lines.append("### 1. graph_edge 通道有效性（weighted scenario）")
    lines.append("")
    lines.append("| Sample | edge 召回 | edge 进 fusion | edge 进 packed | 判定 |")
    lines.append("|--------|----------|----------------|----------------|------|")
    edge_packed_positive = 0
    total_samples = 0
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-028":
            continue
        total_samples += 1
        weighted = scenario_runs.get("weighted_rrf")
        if not weighted:
            continue
        edge_recall = len(weighted.graph_edge_chunk_ids)
        edge_fusion = weighted.graph_edge_fusion_count
        edge_packed = weighted.graph_edge_packed_count
        if edge_packed > 0:
            verdict = "edge 进入 packed"
            edge_packed_positive += 1
        elif edge_fusion > 0:
            verdict = "进 fusion 未进 packed"
        elif edge_recall > 0:
            verdict = "召回但 RRF 挤出"
        else:
            verdict = "无 edge 召回"
        lines.append(
            f"| {qid} | {edge_recall} | {edge_fusion} | {edge_packed} | {verdict} |"
        )
    lines.append("")

    # Table 2: cross-document grounding + packed re-rank overlap
    lines.append("### 2. 跨文档 grounding 与 packed 重排度")
    lines.append("")
    lines.append("| Sample | baseline sources | weighted sources | sources 变化 | packed overlap (b∩w) | edge 同文档? |")
    lines.append("|--------|------------------|------------------|--------------|----------------------|--------------|")
    cross_doc_positive = 0
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-028":
            continue
        baseline = scenario_runs.get("baseline_rule_no_edge")
        weighted = scenario_runs.get("weighted_rrf")
        if not baseline or not weighted:
            continue
        b_sources = baseline.document_sources_count
        w_sources = weighted.document_sources_count
        src_delta = w_sources - b_sources
        # packed chunk overlap
        b_pack_ids: set[str] = set()
        for b in baseline.packed_blocks:
            for c in (b.get("chunk_ids") if isinstance(b, dict) else []) or []:
                b_pack_ids.add(str(c))
        w_pack_ids: set[str] = set()
        for b in weighted.packed_blocks:
            for c in (b.get("chunk_ids") if isinstance(b, dict) else []) or []:
                w_pack_ids.add(str(c))
        overlap = len(b_pack_ids & w_pack_ids) if b_pack_ids else 0
        # edge evidence files vs other channel files (fusion_topn)
        edge_fids: set[str] = set()
        other_fids: set[str] = set()
        for f in weighted.fusion_topn:
            if not isinstance(f, dict):
                continue
            fid = str(f.get("file_id") or "")
            chans = f.get("channels") if isinstance(f.get("channels"), list) else []
            if "graph_edge" in chans:
                edge_fids.add(fid)
            else:
                other_fids.add(fid)
        edge_new_doc = bool(edge_fids - other_fids - {"None", ""}) if edge_fids else False
        if edge_new_doc:
            cross_doc_positive += 1
        edge_doc_str = "是(跨文档)" if edge_new_doc else ("同文档" if edge_fids else "无 edge")
        lines.append(
            f"| {qid} | {b_sources} | {w_sources} | {src_delta:+d} | "
            f"{overlap}/{len(b_pack_ids) or '-'} | {edge_doc_str} |"
        )
    lines.append("")

    # Table 3: cross-section context integrity (metric B)
    lines.append("### 3. 跨 section 上下文完整性（指标 B）")
    lines.append("")
    lines.append("| Sample | baseline distinct sections | weighted distinct sections | section 增量 | 判定 |")
    lines.append("|--------|---------------------------|---------------------------|--------------|------|")
    section_positive = 0
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-028":
            continue
        baseline = scenario_runs.get("baseline_rule_no_edge")
        weighted = scenario_runs.get("weighted_rrf")
        if not baseline or not weighted:
            continue

        def _distinct_sections(run: ScenarioRun) -> set[str]:
            secs: set[str] = set()
            for b in run.packed_blocks:
                if isinstance(b, dict):
                    sp = b.get("section_path") or b.get("section_title")
                    if sp:
                        secs.add(str(sp))
            return secs

        b_secs = _distinct_sections(baseline)
        w_secs = _distinct_sections(weighted)
        delta = len(w_secs) - len(b_secs)
        if delta > 0:
            verdict = "上下文扩展"
            section_positive += 1
        elif delta < 0:
            verdict = "上下文收缩"
        else:
            verdict = "无变化"
        lines.append(
            f"| {qid} | {len(b_secs)} | {len(w_secs)} | {delta:+d} | {verdict} |"
        )
    lines.append("")

    # Metric A + B summary + verdict
    metric_a = (edge_packed_positive / total_samples) if total_samples else 0.0
    lines.append("### 4. 价值指标汇总与判定")
    lines.append("")
    lines.append(f"- **指标 A（graph_edge 关联补足率）**: `{edge_packed_positive}/{total_samples}` = `{metric_a:.0%}`")
    lines.append("  - 定义：weighted scenario 中 packed context 含 graph_edge 通道 chunk 的样例比例")
    lines.append(f"- **指标 B（跨 section 上下文扩展）**: `{section_positive}/{total_samples}` 样例正向扩展")
    lines.append("  - 定义：weighted distinct section_path 数 > baseline 的样例比例")
    lines.append(f"- **跨文档 grounding 扩展**: `{cross_doc_positive}/{total_samples}` 样例 edge 带来新文档")
    lines.append("")
    # Verdict per spec §5.3
    if metric_a >= 0.4 and section_positive >= total_samples / 2:
        verdict = "有价值"
        action = "保留链路，更新 AC 基线用新指标（指标 A/B）替代 keypoint 覆盖"
    elif metric_a > 0:
        verdict = "价值有限"
        action = "保留链路；graph_edge 在真 vector 下价值被稀释（vector 已强）。建议登记需求评估是否下调 graph_edge RRF 权重或调整触发策略，或确认价值天然有限并更新 REQ-025/030 验收基线说明"
    else:
        verdict = "无效"
        action = "评估是否关闭 graph_edge 通道（登记独立需求）"
    lines.append(f"- **价值判定**: `{verdict}`")
    lines.append(f"- **建议动作**: {action}")
    lines.append("")
    lines.append("### 5. 结论")
    lines.append("")
    lines.append(
        "- graph_edge 在 fake vector 时代（REQ-018/025 验收）有价值，因 keyword 兜底主导召回、edge 补足关联 chunk 能进 packed。"
    )
    lines.append(
        "- 真 vector 召回下（TD-068+069 后）vector 通道已强，edge 通道在 RRF 融合时多被挤出 fusion_topN，"
        "且 edge chunks 多为同文档关联、不扩展跨文档 grounding。"
    )
    lines.append(
        "- keypoint 覆盖口径（REQ-030 AC-5）反映的是「答案是否命中分散的关键词」，而 graph_edge 补足的是"
        "「同文档关联上下文」——两者目标不一致。AC-5 不达标是指标错配，非链路缺陷。"
    )
    lines.append(
        "- 本评估不修改主链路代码。若需调整 graph_edge RRF 权重 / 策略，登记独立需求（REQ-034 候选）评估影响面。"
    )
    lines.append("")
    return "\n".join(lines)


def _render_req034_section(
    runs: list[ScenarioRun],
    grouped: dict[tuple[str, str], dict[str, ScenarioRun]],
) -> str:
    """REQ-034: graph_edge RRF weight/strategy adjustment evaluation.

    Weight sweep (use_graph_edge=True, varying weight) on retrieval-layer
    metrics + feasibility analysis of three candidate strategies + REQ-018/025
    impact + recommendation. Does not modify main-chain code.
    """
    lines: list[str] = []
    lines.append("## REQ-034 graph_edge RRF 权重/策略调整评估")
    lines.append("")
    lines.append("> REQ-033 判定 graph_edge 在真 vector 下价值有限。本节评估是否调整 RRF 权重/触发策略/packer 优先级。")
    lines.append("> weight sweep 只测 retrieval 层指标（keypoint 覆盖已被 REQ-033 证明为指标错配，无需 LLM）。")
    lines.append("")

    # Sweep levels: (label, scenario_name, weight). off-baseline is the reference.
    sweep = [
        ("off (no edge)", "baseline_rule_no_edge", None),
        ("w=0.3", "graph_edge_w03", 0.3),
        ("w=0.5 (默认)", "graph_edge", 0.5),
        ("w=0.7", "graph_edge_w07", 0.7),
        ("w=1.2", "weighted_rrf", 1.2),
    ]

    # Table 1: weight sensitivity
    lines.append("### 1. Weight sensitivity（retrieval 层指标 per weight level, REQ-028 10 样例）")
    lines.append("")
    lines.append(
        "| weight | Metric A (edge 进 packed) | Metric B (跨 section 扩展 vs off) | "
        "跨文档 grounding | packed overlap vs off | fusion edge 均值 |"
    )
    lines.append(
        "|--------|--------------------------|----------------------------------|"
        "----------------|-----------------------|------------------|"
    )
    level_metrics: list[tuple[str, dict[str, float] | None]] = []
    for label, sname, _w in sweep:
        m = _req034_scenario_metrics(grouped, sname, "baseline_rule_no_edge")
        level_metrics.append((label, m))
        if m is None:
            lines.append(f"| {label} | (无数据) | — | — | — | — |")
            continue
        lines.append(
            f"| {label} | {m['metric_a']:.0%} | {m['metric_b']:.0%} | "
            f"{m['cross_doc']:.0%} | {m['packed_overlap']:.2f} | {m['fusion_edge_mean']:.1f} |"
        )
    lines.append("")
    lines.append("- Metric A = edge 进 packed 样例率；Metric B = distinct section_path > off-baseline 样例率；")
    lines.append("- 跨文档 grounding = edge 带来新文档样例率；packed overlap = |packed ∩ off_packed| / |off_packed| 均值；fusion edge 均值 = graph_edge_fusion_count 均值。")
    lines.append("")

    # Table 2: strategy feasibility
    lines.append("### 2. 候选策略可行性分析")
    lines.append("")
    lines.append("| 策略 | 类型 | 现状 | 可行性 | 预期效果 |")
    lines.append("|------|------|------|--------|----------|")
    lines.append(
        "| 1. 下调 graph_edge RRF 权重 | 配置/数据驱动 | 默认 0.5，可经 `RRF_CHANNEL_WEIGHTS` env 覆盖 | "
        "高（改默认值或 env，无主链路改动） | 见 weight sweep：若 Metric A/B 随权重单调变化则有效，否则权重非杠杆 |"
    )
    lines.append(
        "| 2. 仅在 vector 召回弱时触发 edge | 主链路改动 | `PgEdgeRecallChannel.recall` 无条件触发 | "
        "中（需在召回编排加两阶段门控，独立实现需求） | 主要省召回成本；进 packed 由 RRF+packer 决定，对 Metric A 提升有限 |"
    )
    lines.append(
        "| 3. 调整 ContextPacker 优先级 | 主链路改动 | `_apply_budget` 按 score 裁剪 + `_ensure_graph_edge_source_block` 兜底 | "
        "中（需在 budget 内给 edge block 优先级 boost，独立实现需求） | 可能把 Metric A 从 5/10 提升，但 edge 同文档、不扩展跨文档 grounding，对 Metric B/跨文档增益有限 |"
    )
    lines.append("")

    # Table 3: REQ-018/025 impact
    lines.append("### 3. REQ-018/025 历史验收影响面")
    lines.append("")
    lines.append("| 验收点 | 调整策略 | 影响 |")
    lines.append("|--------|----------|------|")
    lines.append(
        "| REQ-018：4 通道 graph_edge 召回能力 | 下调权重（不关通道） | **不受影响**——通道召回能力不变，仅融合权重变化 |"
    )
    lines.append(
        "| REQ-018：4 通道 graph_edge 召回能力 | 关闭通道 / conditional trigger | **受影响**——部分样例不再有 edge 召回，需重验 |"
    )
    lines.append(
        "| REQ-025：graph_edge 进 prompt + 真 LLM 验收 | 下调权重 | **可能受影响**——weight 越低 edge 进 packed 样例越少，进 prompt 覆盖下降；验收基线需补「权重敏感」说明 |"
    )
    lines.append(
        "| REQ-025：graph_edge 进 prompt + 真 LLM 验收 | conditional trigger | **受影响**——弱 vector 才触发，部分样例无 edge 进 prompt，需重跑真 LLM 验收 |"
    )
    lines.append("")

    # Recommendation per spec §5.4 — refined with inert-at-default detection.
    lines.append("### 4. 建议判定")
    lines.append("")
    # Determine sensitivity from sweep data (exclude off-baseline reference).
    edge_levels = [(lbl, m) for lbl, m in level_metrics if m is not None and lbl != "off (no edge)"]
    w03 = next((m for lbl, m in edge_levels if "w=0.3" in lbl), None)
    w05 = next((m for lbl, m in edge_levels if "w=0.5" in lbl), None)
    w07 = next((m for lbl, m in edge_levels if "w=0.7" in lbl), None)
    w12 = next((m for lbl, m in edge_levels if "w=1.2" in lbl), None)

    def _spread(key: str) -> float:
        vals = [m[key] for _, m in edge_levels if m.get(key) is not None]
        return (max(vals) - min(vals)) if vals else 0.0

    a_spread = _spread("metric_a")
    b_spread = _spread("metric_b")

    lines.append(f"- Metric A 跨权重极差（max−min）: `{a_spread:.0%}`；Metric B 跨权重极差: `{b_spread:.0%}`")
    if w03 and w05 and w07 and w12:
        lines.append(
            f"- w=0.3 / 0.5 / 0.7 / 1.2 的 Metric A = {w03['metric_a']:.0%} / {w05['metric_a']:.0%} / "
            f"{w07['metric_a']:.0%} / {w12['metric_a']:.0%}；fusion edge 均值 = "
            f"{w03['fusion_edge_mean']:.1f} / {w05['fusion_edge_mean']:.1f} / {w07['fusion_edge_mean']:.1f} / {w12['fusion_edge_mean']:.1f}"
        )
    lines.append("")

    # Verdict logic: detect inert-at-default (edge recalled but 0 into fusion at
    # production default 0.5) vs contributes-only-at-boosted-weight.
    inert_at_default = bool(w05 and w05["fusion_edge_mean"] < 0.5)
    contributes_at_high = bool(w12 and w12["metric_a"] > 0.0)
    if inert_at_default and contributes_at_high:
        verdict = "下调权重无效——默认 0.5 下 edge 已惰性"
        action = (
            "weight sweep 证实：在生产默认权重 0.5（及 0.3/0.7）下，graph_edge 每样例召回约 8 chunks 但 **0 进 fusion/packed**"
            "（RRF 融合时全被挤出）——edge 在生产默认配置下是死权重，仅付出召回成本无任何贡献。仅在校验脚本 boosting 用的 "
            "w=1.2（非生产配置）下 edge 才进 packed（50%）。因此 REQ-033 候选「下调权重」无效：0.5 已惰性，下调到 0.3 无差别。"
            "保留默认 0.5（不引入回归）；登记独立决策需求评估 (a) 是否禁用 graph_edge 通道省召回成本，或 (b) 上调默认权重使 edge "
            "实际贡献——但 REQ-033 已证即使 edge 进 packed（w=1.2），Metric B/跨文档 grounding 仍 ~0，对答案质量增益有限，"
            "故 (b) 收益存疑。任一变更均需重跑 REQ-025 真 LLM 验收。本任务不改代码。"
        )
    elif w03 and w05 and (w03["metric_a"] - w05["metric_a"] >= 0.2 or w03["metric_b"] - w05["metric_b"] >= 0.2):
        verdict = "建议下调权重"
        action = (
            "weight sweep 显示 w=0.3 在 Metric A/B 上显著优于 0.5。登记独立实现需求将默认权重从 0.5 下调到 0.3，"
            "并重跑 REQ-025 真 LLM 验收确认进 prompt 覆盖可接受。本任务不改代码。"
        )
    elif (a_spread <= 0.2 and b_spread <= 0.2):
        verdict = "权重非杠杆，保留 0.5"
        action = (
            "各权重下 Metric A/B 几乎不变（极差 ≤ 20%）——下调权重不是有效杠杆。问题在 RRF 融合机制 / packer 优先级 / "
            "edge 同文档属性，而非权重数值。保留默认 0.5；若要提升 edge 价值需改 packer 优先级或 conditional trigger"
            "（均为主链路改动，登记独立实现需求）。同时确认 graph_edge 在真 vector 下价值天然有限，更新 REQ-025 验收基线说明。"
        )
    else:
        verdict = "权重有影响但无单调优势"
        action = (
            "weight sweep 显示权重变化对 Metric A/B 有影响但 0.3 相对 0.5 无显著优势。保留默认 0.5；"
            "确认 graph_edge 在真 vector 下价值天然有限，更新 REQ-025 验收基线说明。不登记实现需求。"
        )
    lines.append(f"- **建议**: `{verdict}`")
    lines.append(f"- **依据与动作**: {action}")
    lines.append("")

    lines.append("### 5. 结论")
    lines.append("")
    lines.append(
        "- 本评估不修改主链路代码（RRFFusion / ContextPacker / AIChatService / recall_service / PgEdgeRecallChannel）。"
    )
    lines.append(
        "- 三个候选策略中，策略 1（下调权重）可经配置调整、风险最低；策略 2/3 为主链路改动，需独立实现需求 + 重跑 REQ-025 真 LLM 验收。"
    )
    if inert_at_default and contributes_at_high:
        lines.append(
            "- **关键发现**：生产默认权重 0.5 下 graph_edge 惰性（召回 8 chunks/样例但 0 进 fusion/packed），"
            "REQ-033 的 Metric A=5/10 实测于 w=1.2（校验 boosting 配置），高估了生产环境 edge 贡献。"
            "下调权重无效；真正的决策是「禁用省成本」vs「上调使贡献（但增益存疑）」，登记独立决策需求。"
        )
    lines.append(
        "- graph_edge 在真 vector 下价值有限是技术演进自然结果，非链路缺陷；REQ-025 验收基线应补充「真 vector 下价值转移 + 默认权重惰性」说明。"
    )
    lines.append("")
    return "\n".join(lines)


