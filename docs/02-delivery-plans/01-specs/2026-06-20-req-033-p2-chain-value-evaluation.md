# REQ-033 Spec: P2 链路真 vector 价值评估

> Status: 🟣 Shaping
> Created: 2026-06-20
> Source: REQ-032 根因接力（P2 链路无正向贡献）
> Requirement: `docs/01-product-planning/05-requirements/REQ-033-p2-chain-real-vector-value-evaluation.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-033-p2-chain-value-evaluation-plan.md`

## 1. Problem Statement

REQ-032 证实 P2 链路在真 vector 下对 keypoint 覆盖无系统性正向贡献。离线分析 40 run 揭示三层问题：

1. **graph_edge 通道在 RRF 下几乎无效**：8 样例召回 edge chunks，但仅 Q2/Q6 进 packed（各 2 个），其余在 fusion_topN 排序时被挤出。
2. **graph_edge 不扩展跨文档 grounding**：edge chunks 全来自同文件，document_sources 几乎不变。
3. **weighted RRF 主要重排**：packed_overlap 5-6/8，weighted 用 edge 替换同文档 chunk，keypoint 覆盖反而退化。

keypoint 覆盖不是衡量 P2 链路价值的正确指标——graph_edge 设计意图是补足关联上下文（REQ-018），不是命中分散 keypoint。需要重新评估 P2 链路的真实价值。

## 2. Goal

基于真实数据评估 P2 链路（graph_edge + weighted RRF）在真 vector 下的价值，重新定义价值指标，给出链路调整建议或确认价值有限。**不改主链路代码。**

## 3. Non-Goals

- 不改 RRF / ContextPacker / AIChatService / PgEdgeRetriever 代码
- 不重跑 REQ-026/027/029
- 不引入新依赖
- 不强行让 AC-5 达标

## 4. Acceptance Criteria

见 requirement AC-1 ~ AC-8。

## 5. Architecture

### 5.1 Retrieval 层价值分析（脚本新增章节）

基于已有 ScenarioRun 数据（fusion_topn / packed_blocks / graph_edge_chunk_ids / document_sources），新增 `_render_req033_section`：

- **graph_edge 通道有效性**：edge 召回数 / 进 fusion 数 / 进 packed 数 per sample
- **跨文档 grounding**：edge evidence 是否来自新文件（vs vector/keyword）
- **packed 重排度**：baseline ∩ weighted packed chunk overlap
- **RRF 通道分布**：fusion_topN 各 channel 计数 baseline vs weighted

### 5.2 新价值指标定义（2 个）

graph_edge 设计意图 = 补足关联上下文。贴合该意图的指标：

**指标 A：graph_edge 关联补足率**
- 定义：weighted scenario 中，packed context 含 graph_edge 通道 chunk 的样例比例
- 计算：`count(weighted.edge_packed > 0) / total`
- 意义：graph_edge 是否真的把关联 chunk 喂给了 LLM

**指标 B：跨 section 上下文完整性**
- 定义：weighted scenario 的 packed_blocks 覆盖的 distinct section_path 数 vs baseline
- 计算：`len(distinct section_path in weighted packed) - len(distinct section_path in baseline packed)`
- 意义：graph_edge 是否让答案接触到更完整的上下文（同文档不同 section），即使不命中新 keypoint

### 5.3 价值判定框架

| 判定 | 条件 | 动作 |
|------|------|------|
| 有价值 | 指标 A ≥ 4/10 且指标 B 多数样例 > 0 | 保留链路，更新 AC 基线用新指标 |
| 价值有限 | 指标 A < 4/10 或指标 B 多数 = 0 | 保留链路但下调 graph_edge RRF 权重或调整策略（登记需求） |
| 无效 | 指标 A = 0 且指标 B 全 0 | 评估是否关闭 graph_edge 通道（登记需求） |

### 5.4 预期结论（基于离线分析）

- 指标 A：2/10（仅 Q2/Q6 edge_packed > 0）→ 价值有限
- 指标 B：需计算（预测多数 = 0，因 edge 同文档且重排）
- 判定：**价值有限** → 建议登记需求评估是否调整 graph_edge RRF 权重 / 策略，或确认在真 vector 下 graph_edge 价值天然有限（vector 已强），更新 REQ-025/030 验收基线说明

## 6. Risks

- **指标 B 难计算**：packed_blocks 的 section_path 字段需确认存在（已见 keys 含 section_path）。
- **结论"价值有限"被误读为"链路失败"**：graph_edge 在 fake vector 时代有价值（REQ-018/025 验收通过），真 vector 下价值转移是技术演进自然结果，需在报告明确。
- **调整建议触发大改**：若建议调 RRF 权重，需独立需求评估影响面，不在本任务改。

## 7. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | `_render_req033_section` retrieval 层价值分析 + 指标 A/B 计算 | — |
| Slice 2 | dry-run 验证机制 | Slice 1 |
| Slice 3 | 真 LLM 重跑（复用 req032 数据即可，或重跑）+ 价值判定 + 结论 | Slice 2 |
| Slice 4 | REQ-033 评估报告 + 文档收口 + commit + push + PR | Slice 3 |

## 8. References

- REQ-032 报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md`
- REQ-018: `docs/01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md`
- REQ-025: `docs/01-product-planning/05-requirements/REQ-025-p2-graph-edge-prompt-impact-and-real-llm-validation.md`
- 基线脚本: `scripts/validate_req024_p2_real_validation.py`
