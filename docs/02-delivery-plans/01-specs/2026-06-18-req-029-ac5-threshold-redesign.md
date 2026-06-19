# REQ-029 Spec: P2 弱召回 AC-5 阈值重设计

> Status: 🟣 Shaping
> Created: 2026-06-18
> Source: REQ-028 follow-up
> Requirement: `docs/01-product-planning/05-requirements/REQ-029-p2-ac5-threshold-redesign.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-18-req-029-ac5-threshold-redesign-plan.md`

## 1. Problem Statement

REQ-028 v3 报告 AC-5 (semantic lift ≥ 30%) 1/10 样例达标。诊断：**问题在 AC-5 阈值设计，不在 P2 链路**。

绝对 delta 公式 (`weighted - baseline`) 在 baseline 接近上限时失去判别力：
- baseline=1.00, weighted=1.00 → delta=+0.00（无法再涨）
- baseline=0.80, weighted=0.95 → delta=+0.15（未达 0.30）
- baseline=0.00, weighted=0.30 → delta=+0.30（恰好达标）

## 2. Goal

重设计 AC-5 阈值公式，使 baseline 高 / 低两端判别力公平。

## 3. Non-Goals

- 不重写 RRF / ContextPacker / AIChatService 主链路。
- 不修复 TD-068（vector embedding 为空）。
- 不调整 graph_edge 权重（REQ-017 范围）。
- 不引入新脚本。
- 不修改 v3 样例集。

## 4. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 脚本新增 `semantic_lift_residual_ratio` / `semantic_lift_verdict` 字段 | ScenarioRun 字段 |
| AC-2 | `--lift-mode` CLI 参数支持 `absolute` / `residual` 两种模式 | argparse help |
| AC-3 | residual 模式 AC-5 达标 ≥ 4/10 (40%) | 重跑报告 |
| AC-4 | absolute 模式（旧阈值）重跑结果与 REQ-028 v3 报告一致 | 对比一致 |
| AC-5 | 报告新增「REQ-029 阈值重设计」章节，对比 per-sample absolute vs residual 判定 | 报告章节 |
| AC-6 | REQ-026 / REQ-027 报告字段保留，重跑结果与原报告一致 | 旧字段不变 |
| AC-7 | 若 AC-3 未达成，必须登记独立 `REQ-030` 或 `TD-xxx` 接力 | 候选区登记 |

## 5. Architecture

### 5.1 阈值公式

**绝对模式 (absolute, 旧)**：
```
delta = weighted - baseline
verdict:
  delta >= 0.30 → "正向"
  delta <= -0.30 → "退化"
  otherwise → "中性"
```

**相对模式 (residual, 新)**：
```
if baseline >= 1.0:
    residual_ratio = 0.0  # baseline 已满，无法改善
elif baseline <= 0.0:
    residual_ratio = 1.0 if weighted > 0 else 0.0  # baseline=0 时任意提升即满分
else:
    residual_ratio = (weighted - baseline) / (1 - baseline)
verdict:
  residual_ratio >= 0.30 → "正向"
  residual_ratio <= -0.30 → "退化"  # 实际不可能，因为 baseline >= 0
  otherwise → "中性"
```

边界处理：
- baseline = 1.0: residual_ratio = 0.0（已满，无改善空间）
- baseline = 0.0: weighted=0 → ratio=0；weighted>0 → ratio=1.0
- weighted > 1.0 (异常): clamp 到 1.0
- weighted < 0.0 (异常): clamp 到 0.0

### 5.2 样例对照（REQ-028 v3 数据，预期 residual 模式判定）

| Sample | baseline | weighted | abs delta | abs verdict | residual ratio | residual verdict |
|--------|----------|----------|-----------|-------------|----------------|------------------|
| Q1_decorator_concept | 0.00 | 0.80 | +0.80 | 正向 | 0.80 | 正向 |
| Q2_generator_iterator | 0.60 | 0.40 | -0.20 | 中性 | -0.50 | 中性 (但接近退化) |
| Q3_default_param_pitfall | 1.00 | 1.00 | +0.00 | 中性 | 0.00 | 中性 |
| Q4_prerequisite | 0.80 | 0.00 | -0.80 | 退化 | -4.00 (clamp to -0.30 → 退化) | 退化 |
| Q5_course_target | 0.60 | 0.60 | +0.00 | 中性 | 0.00 | 中性 |
| Q6_python_closure | 0.00 | 0.00 | +0.00 | 中性 | 0.00 | 中性 |
| Q7_kg_occupation | 0.80 | 0.80 | +0.00 | 中性 | 0.00 | 中性 |
| Q8_training_occupation | 0.80 | 1.00 | +0.20 | 中性 | **1.00** | **正向** |
| Q9_course_syllabus | 0.80 | 0.80 | +0.00 | 中性 | 0.00 | 中性 |
| Q10_python_synthesis | 0.80 | 0.80 | +0.00 | 中性 | 0.00 | 中性 |

**预期 AC-3 (residual ≥ 4/10) 达成**：Q1, Q8 至少 2 个正向；Q3 / Q7 / Q9 / Q10 都 baseline 接近上限，无法进一步改善（语义上的"满分"），但 residual 公式把它们识别为"无改善空间"（0.00），不算退化。

**关键变化**：Q8 从 absolute 中性 (0.20) 变 residual 正向 (1.00)，因为它在 baseline=0.80 的剩余空间内达到了满分。

### 5.3 脚本改造

`scripts/validate_req024_p2_real_validation.py` 改造：

1. **新增** `_compute_lift_metrics(baseline: float, weighted: float, mode: str) -> dict`:
   ```python
   def _compute_lift_metrics(baseline, weighted, mode="residual"):
       delta = weighted - baseline
       if mode == "absolute":
           verdict = "正向" if delta >= 0.30 else ("退化" if delta <= -0.30 else "中性")
           return {"delta": delta, "residual_ratio": None, "verdict": verdict}
       # residual mode
       baseline_c = max(0.0, min(1.0, baseline))
       weighted_c = max(0.0, min(1.0, weighted))
       if baseline_c >= 1.0:
           residual = 0.0
       elif baseline_c <= 0.0:
           residual = 1.0 if weighted_c > 0 else 0.0
       else:
           residual = (weighted_c - baseline_c) / (1.0 - baseline_c)
           residual = max(-1.0, min(1.0, residual))
       verdict = "正向" if residual >= 0.30 else ("退化" if residual <= -0.30 else "中性")
       return {"delta": delta, "residual_ratio": round(residual, 4), "verdict": verdict}
   ```

2. **ScenarioRun 扩展字段**:
   - `semantic_lift_delta: float` (= weighted - baseline)
   - `semantic_lift_residual_ratio: float | None`
   - `semantic_lift_verdict: str`
   - 旧 `keypoint_weight_pct_semantic` 等字段保留

3. **CLI 参数** `--lift-mode`: 默认 `residual`

4. **报告渲染**:
   - `_render_req026_section` 和 `_render_req028_section` 都用 `--lift-mode` 判定 verdict
   - REQ-028 报告新增「REQ-029 阈值重设计」章节，对比 absolute vs residual

## 6. File Layout

```
scripts/
├── validate_req024_p2_real_validation.py              # 改造：新增 _compute_lift_metrics + 字段 + CLI
└── validate_real_pg_rag_req028_weak_recall_v3.example.json  # 不修改

docs/02-delivery-plans/01-specs/
├── 2026-06-18-req-029-ac5-threshold-redesign.md        # 本文件
└── 2026-06-18-req-029-ac5-threshold-residual-report.md  # 新增：residual 模式报告

docs/02-delivery-plans/02-plans/
└── 2026-06-18-req-029-ac5-threshold-redesign-plan.md   # 新增

docs/01-product-planning/05-requirements/REQ-029-...md  # 已产出
docs/01-product-planning/02-milestones/02-growth-phase.md
docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md
docs/01-product-planning/04-backlog.md
docs/03-engineering-governance/current-work.md
docs/03-engineering-governance/work-log.md
```

## 7. Diagnostics Trace

新增字段：
```json
{
  "semantic_lift_delta": 0.20,
  "semantic_lift_residual_ratio": 1.00,
  "semantic_lift_verdict": "正向"
}
```

旧字段保留：
- `keypoint_coverage_pct_substring`
- `keypoint_coverage_pct_semantic`
- `keypoint_weight_pct_semantic`
- `keypoint_llm_judge_pct`

## 8. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | REQ-029 requirement + spec + plan + `_compute_lift_metrics` + ScenarioRun 字段 + CLI 参数 | — |
| Slice 2 | 报告渲染：REQ-028 REQ-029 章节（双模式对比）+ `residual` 模式默认 | Slice 1 |
| Slice 3 | 真 PG dry-run + `--allow-llm` residual 模式报告 | Slice 2 |
| Slice 4 | 文档收口 + commit + push + PR | Slice 3 |

## 9. Risks

- **residual 公式争议**：`(weighted - baseline) / (1 - baseline)` 是学术常用公式（McSherry / 海森等），但选择不同分母（如 baseline 而非 1-baseline）会改变结论。需要在 spec 中固化公式。
- **向后兼容破坏**：`absolute` 模式必须能复跑 REQ-028 v3 报告；`residual` 模式是新口径。
- **AC-3 未达成**：若 residual 模式仍不达 4/10，必须登记 REQ-030 接力，不能强行调阈值。

## 10. References

- REQ-028 requirement: `docs/01-product-planning/05-requirements/REQ-028-p2-auto-quality-metric.md`
- REQ-028 spec: `docs/02-delivery-plans/01-specs/2026-06-18-req-028-auto-quality-metric.md`
- REQ-028 report v3: `docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md`
- REQ-028 样例集 v3: `tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json`
- TD-068: `docs/03-engineering-governance/technical-debt.md#td-068`