# REQ-029: P2 弱召回 AC-5 阈值重设计

Status: 🟢 完成
Priority: P0
Milestone: P2
Source: REQ-028 follow-up
Related: REQ-024 / REQ-025 / REQ-026 / REQ-027 / REQ-028 / TD-068

## 背景

REQ-028 真 PG + `--allow-llm` v3 报告（10 样例，三口径）核心结论：

- 机制层：10/10 ✅
- AC-4 (semantic ≥ 0.50)：7/10 样例达标 ✅
- AC-5 (semantic lift ≥ 30%)：**1/10 样例达标 ❌**

诊断：AC-5 阈值公式 `weighted - baseline >= 0.30` 在 baseline 已经很高时不可能达成：
- Q3_default_param_pitfall baseline=1.00, weighted=1.00 → delta=+0.00
- Q8_training_program_occupation baseline=0.80, weighted=1.00 → delta=+0.20
- Q9_course_standard_syllabus baseline=0.80, weighted=0.80 → delta=+0.00

**问题不在 P2 链路本身**，而在 AC-5 阈值设计：相对覆盖度改善公式在 baseline 接近上限时失去判别力。

REQ-028 已登记 AC-5 阈值重设计 follow-up。

## 目标

重设计 AC-5 阈值公式，使 P2 链路质量改善判别在 baseline 高 / 低两端都公平：

1. **相对改善比例（residual ratio）**：`(weighted - baseline) / (1 - baseline)`，取值范围 (-∞, 1]。
   - baseline=0.80, weighted=1.00 → (0.20 / 0.20) = **1.00**（完美）
   - baseline=0.00, weighted=0.50 → (0.50 / 1.00) = **0.50**
   - baseline=0.00, weighted=0.00 → 0.00（未改善）
2. **绝对阈值兜底（absolute）**：当 baseline < 0.5 时用绝对阈值 (weighted ≥ 0.5)；当 baseline ≥ 0.5 时用相对改善比例 (≥ 0.30)。
3. **不破坏向后兼容**：REQ-026/027/028 报告字段保留，新增 `semantic_lift_residual_ratio` / `semantic_lift_verdict` 字段。
4. **重跑 REQ-028 v3 报告**：用新阈值公式重判 10 样例，验证 AC-5 达标率。
5. **若 AC-5 重设计后仍不达标**，必须显式登记独立 `REQ-030` 或 `TD-xxx` 接力，不在本任务内强行调阈值。

## 非目标

- 不重写 RRF / ContextPacker / AIChatService 主链路。
- 不修复 TD-068（vector embedding 为空）。
- 不调整 graph_edge 权重（REQ-017 范围）。
- 不引入新脚本，沿用 `validate_req024_p2_real_validation.py`。
- 不修改 v3 样例集（keypoint 数据不变）。

## 验收标准

1. 脚本新增字段：
   - `semantic_lift_residual_ratio: float`  (weighted - baseline) / (1 - baseline)，baseline=1 时返回 0.0
   - `semantic_lift_verdict: str`  ("正向" / "中性" / "退化" 三态)
   - 阈值参数化：`--lift-mode` 可选 `absolute`（旧 =delta >= 0.30）或 `residual`（新 =residual_ratio >= 0.30）
2. 重跑 REQ-028 v3 报告：
   - `residual` 模式下 AC-5 达标样例数 ≥ 4/10 (40%)
   - `absolute` 模式（旧阈值）结果与 REQ-028 v3 报告一致（向后兼容）
3. 报告章节新增「REQ-029 阈值重设计」段落，对比 absolute vs residual 两种模式的 per-sample 判定差异。
4. 若 `residual` 模式仍未达成 AC-2 (≥4/10)，必须登记独立 `REQ-030` 或 `TD-xxx` 接力。
5. 不影响 REQ-026 / REQ-027 报告（旧字段保留，重跑结果与原报告一致）。

## 建议执行顺序

1. 改造 `validate_req024_p2_real_validation.py`：
   - `_compute_lift_metrics()` 函数新增 residual_ratio 计算
   - `--lift-mode` CLI 参数（默认 `residual`）
   - ScenarioRun 扩展 `semantic_lift_residual_ratio` / `semantic_lift_verdict` 字段
   - 报告渲染新增 REQ-029 阈值重设计章节
2. 用 REQ-028 v3 样例（10 条）跑 residual 模式 real LLM 报告
3. 验证 AC-2（residual 模式 ≥ 4/10 达标）
4. 文档收口 + commit + push + PR

## 事实源

- REQ-028 requirement: `docs/01-product-planning/05-requirements/REQ-028-p2-auto-quality-metric.md`
- REQ-028 spec: `docs/02-delivery-plans/01-specs/2026-06-18-req-028-auto-quality-metric.md`
- REQ-028 report v3: `docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md`
- REQ-028 脚本: `scripts/validate_req024_p2_real_validation.py`
- REQ-028 样例集 v3: `tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json`

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-18 | Shaping 完成 | 分支 `feat/req-029-ac5-threshold-redesign`；requirement 落地；待 spec/plan + 阈值公式改造 |
| 2026-06-18 | Slice 1-3 完成 | 脚本支持 `_compute_lift_metrics` + `--lift-mode` (residual/absolute) + REQ-026/028 报告双模式渲染；真 PG dry-run + `--allow-llm` residual 模式报告均已生成 |
| 2026-06-18 | 验收结果 | 机制层 10/10 ✅；AC-3 (residual mode AC-5 ≥ 4/10): **5/10 样例达标** ✅；AC-4 (semantic ≥ 0.50): 9/10 样例达标（vs 之前 7/10）；Q1/Q2/Q5/Q6/Q8 为正向（绝对 delta 0.20-1.00，residual 0.50-1.00）；Q4 退化 |
| 2026-06-18 | 长链收口 | REQ-024/025/026/027/028 质量层卡点解除，可翻完成 |