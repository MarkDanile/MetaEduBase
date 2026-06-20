# REQ-032 Spec: P2 semantic_emb 阈值校准与 continuous 口径

> Status: 🟣 Shaping
> Created: 2026-06-20
> Source: REQ-031 follow-up（threshold 0.5 过严致 AC-4/5 仍 0/10）
> Requirement: `docs/01-product-planning/05-requirements/REQ-032-p2-semantic-emb-threshold-calibration.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-032-semantic-emb-threshold-calibration-plan.md`

## 1. Problem Statement

REQ-031 修复 embedding 通路后，semantic_emb 8/10 非零，但 AC-4/5 仍 0/10。离线分析 200 个 keypoint-similarity 对：

| 统计 | 值 |
|------|----|
| median similarity | 0.329 |
| p75 | 0.440 |
| p90 | 0.537 |
| hit rate @0.50 | 14% |
| hit rate @0.35 | 44% |

threshold 0.5 命中率仅 14%，median 都达不到。但预诊断显示：**即使降到 0.35 或改 continuous，AC-5 (delta ≥ 0.30) 仍 0/10**，因为 baseline vs weighted 的 coverage 差异本身就 < 0.30。

预诊断 continuous weighted coverage（不二值化）：

| qid | baseline | weighted | delta |
|-----|----------|----------|-------|
| Q1 | 0.394 | 0.388 | -0.007 |
| Q2 | 0.439 | 0.301 | -0.138 |
| Q5 | 0.262 | 0.499 | +0.238 |
| Q6 | 0.411 | 0.265 | -0.146 |
| ... | ... | ... | 全部 \|delta\| < 0.30 |

continuous vs LLM-judge Pearson = **-0.266（负相关）**。

**根因预判**：不是阈值问题，而是 P2 链路（graph_edge / weighted RRF）在真 vector 召回下对 answer 的 keypoint 覆盖**无系统性正向贡献**——weighted 经常比 baseline 差（Q2/Q6 负 delta）。semantic_emb 口径如实反映这一点；substring 口径反而是"假阳性"。

## 2. Goal

加 threshold 可配置 + continuous 口径 secondary signal，基于真实数据判定 AC-4/5。**若不达标，如实记录根因并登记后续 P2 链路评估任务，不强行调阈值。**

## 3. Non-Goals

- 不修 P2 主链路
- 不引入新依赖
- 不改 REQ-031 缓存/超时机制

## 4. Acceptance Criteria

见 requirement AC-1 ~ AC-8。

## 5. Architecture

### 5.1 可配置 threshold

`_compute_semantic_embedding_coverage` 已有 `threshold` 参数（默认 0.5）。新增 CLI `--semantic-emb-threshold`（默认 0.5），透传到函数。报告新增"threshold 敏感性"段：展示 0.50/0.45/0.40/0.35 四档命中率（从已缓存的 per_keypoint similarity 重算，无需重新调 API）。

### 5.2 continuous weighted coverage

ScenarioRun 新增 `keypoint_semantic_embedding_continuous_pct`：

```python
continuous = sum(kp.weight * best_sim for kp) / sum(kp.weight for kp)
```

不二值化，值连续 [0, 1]。`_compute_semantic_embedding_coverage` 返回值已含 per_keypoint similarity，连续覆盖率 = 加权平均 similarity。

### 5.3 报告增强

REQ-030 章节 per-sample 矩阵增加 `cont cov` 列。per-sample summary 增加 continuous delta + verdict。Spearman 增加 continuous vs LLM-judge。

### 5.4 预期结果（基于预诊断）

- threshold 0.35：AC-5 仍 0/10（delta < 0.30）
- continuous：AC-5 仍 0/10
- 根因：P2 链路无正向贡献
- 登记后续任务：评估 P2 链路在真 vector 下的实际价值（可能需调整 RRF 权重或 graph_edge 策略）

## 6. Risks

- **threshold 0.35 仍不达**：预诊断已确认，本任务如实记录。
- **continuous 负相关 LLM-judge**：说明两种语义评估方法对 P2 链路的排序不一致，需在报告解释（非 bug，反映 P2 链路行为）。
- **误判根因**：若实际是 keypoint 标注问题（Q4/Q9 全零可能 keypoints 偏抽象），需 review。本任务在报告标注，留 follow-up。

## 7. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | `--semantic-emb-threshold` CLI + continuous 字段 + 报告增强 | — |
| Slice 2 | dry-run 验证 | Slice 1 |
| Slice 3 | `--allow-llm` 真 LLM 重跑 + AC 补判 + 根因诊断 | Slice 2 |
| Slice 4 | 文档收口 + commit + push + PR | Slice 3 |

## 8. References

- REQ-030 报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md`
- REQ-031 requirement: `docs/01-product-planning/05-requirements/REQ-031-p2-semantic-embedding-coverage-stabilization.md`
- 基线脚本: `scripts/validate_req024_p2_real_validation.py`
