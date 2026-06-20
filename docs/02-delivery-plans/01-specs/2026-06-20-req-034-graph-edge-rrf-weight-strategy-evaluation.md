# REQ-034 Spec: P2 graph_edge RRF 权重/策略调整评估

> Status: 🟢 完成
> Created: 2026-06-20
> Source: REQ-033 follow-up（graph_edge 在真 vector 下价值有限）
> Requirement: `docs/01-product-planning/05-requirements/REQ-034-p2-graph-edge-rrf-weight-strategy-evaluation.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation-plan.md`

## 1. Problem Statement

REQ-033 判定 P2 链路 graph_edge 通道在真 vector 召回下价值有限（Metric A=5/10、B=1/10、跨文档=0/10），并建议登记需求评估是否调整 graph_edge RRF 权重 / 触发策略 / ContextPacker 优先级。本任务完成该评估，不改主链路代码。

当前架构事实（已 codegraph 确认）：

- `RRFFusion.fuse` 公式 `score(e) = sum(weight / (k + rank))`，k=60，未配置通道权重默认 1.0。
- 默认权重 `{vector: 1.0, keyword: 1.0, graph_node: 0.5, graph_edge: 0.5}`（`ai_router._RRF_DEFAULT_WEIGHTS`），可经 `RRF_CHANNEL_WEIGHTS` env 覆盖。
- `PgEdgeRecallChannel.recall` **无条件触发**：每次 query 都 ILIKE 种子 → knowledge_edges → 关联节点，与 vector 召回强度无关。
- `ContextPacker.pack` Phase 2 处理 `knowledge_edge` evidence：fetch source chunk + neighbors，`_ensure_graph_edge_source_block` 在 budget 裁剪后保证 edge source block 不丢；budget 内按 score 降序裁剪。

## 2. Goal

基于 dry-run retrieval 层数据评估三个候选策略，给出明确建议。**不改主链路代码。**

## 3. Non-Goals

- 不改 RRFFusion / ContextPacker / AIChatService / recall_service / PgEdgeRecallChannel
- 不重跑 REQ-026/027/028/029 真 LLM 报告
- 不强行让任何指标达标
- 不在本任务实施代码调整

## 4. Acceptance Criteria

见 requirement AC-1 ~ AC-7。

## 5. Architecture

### 5.1 Weight sweep（数据驱动，评估策略 1）

新增 2 个 scenario（`use_graph_edge=True`），与已有 `graph_edge`(0.5) / `weighted_rrf`(1.2) 组成 5 点 sweep：

| Scenario | use_graph_edge | graph_edge weight | 角色 |
|----------|----------------|-------------------|------|
| `baseline_rule_no_edge`（已有） | False | — | off-baseline 参考 |
| `graph_edge_w03`（新增） | True | 0.3 | 下调 |
| `graph_edge`（已有） | True | 0.5 | 当前默认 |
| `graph_edge_w07`（新增） | True | 0.7 | 上调 |
| `weighted_rrf`（已有） | True | 1.2 | 强化 |

keypoint 覆盖已被 REQ-033 证明为指标错配，**weight sweep 只测 retrieval 层指标**（不需要 LLM answer），dry-run 即可：

- **Metric A**（edge 进 packed 率）：`count(edge_packed > 0) / total`
- **Metric B**（跨 section 扩展 vs off-baseline）：`count(distinct section_path > baseline) / total`
- **跨文档 grounding**：`count(edge 带来新文档) / total`
- **packed overlap vs off-baseline**：`|packed ∩ baseline_packed| / |baseline_packed|`
- **fusion edge 计数**：`graph_edge_fusion_count` 均值

判定 weight sensitivity：
- 若 Metric A/B 随权重单调变化且 0.3 显著优于 0.5 → 建议下调
- 若各权重下 Metric A/B 几乎不变（weight-insensitive）→ 权重非杠杆，问题在 RRF 融合机制 / packer 优先级，策略 1 无效

### 5.2 策略可行性分析（代码驱动，评估策略 2/3）

**策略 2：conditional trigger（仅在 vector 召回弱时触发 edge）**

- 现状：`PgEdgeRecallChannel.recall` 无条件执行；`AIChatService` 并行召回所有通道。
- 可行性：需在 `AIChatService` 召回编排层增加「先 vector → 若 `len(vector_results) < threshold` 再 edge」的两阶段逻辑，或在 `PgEdgeRecallChannel` 注入 vector 召回结果作为门控。**属主链路改动**，需独立实现需求。
- 预期效果：REQ-033 显示 edge 召回 7-8 chunks 但多在 fusion 被挤出——conditional trigger 主要省召回成本，对「进 packed」提升有限（进不进 packed 由 RRF + packer 决定，非触发与否）。

**策略 3：ContextPacker 优先级调整**

- 现状：`_apply_budget` 按 score 降序裁剪；`_ensure_graph_edge_source_block` 已保证 edge source block 在裁剪后保留。
- 可行性：edge 进 packed 率已由 `_ensure_graph_edge_source_block` 兜底（Metric A=5/10 的 5 个正是这个保证的结果）。进一步提升需在 budget 内给 edge block 加优先级 boost，**属主链路改动**。
- 预期效果：可能把 Metric A 从 5/10 提升，但 REQ-033 已证 edge 同文档、不扩展跨文档 grounding——即使全进 packed，Metric B/跨文档仍低，对答案质量增益有限。

### 5.3 REQ-018/025 影响面评估

- **REQ-018**（4 通道 graph_edge 召回）：验收点是「edge 通道能召回并产出 EvidenceItem」。下调权重不关闭通道，通道召回能力不变 → REQ-018 验收**不受影响**。仅关闭通道（weight 无关，`use_graph_edge=False`）才影响。
- **REQ-025**（graph_edge 进 prompt + 真 LLM 验收）：验收点是「edge chunks 进 packed/prompt」。下调权重会减少 edge 进 fusion/packed 的样例数（weight 越低越少）→ **可能影响 REQ-025 进 prompt 验收的样例覆盖**。REQ-025 验收基线需补充「权重敏感」说明。conditional trigger 同理（弱 vector 才触发，部分样例不再有 edge 进 prompt）。

### 5.4 建议判定框架

| 条件 | 建议 |
|------|------|
| weight sweep 显示 0.3 显著优于 0.5（Metric A/B 提升且不损 REQ-025） | 登记实现需求下调默认权重到 0.3 |
| weight sweep 显示权重不敏感（各权重 Metric A/B 几乎不变） | 权重非杠杆；保留 0.5；若要提升 edge 价值需改 packer 优先级或 conditional trigger（登记实现需求） |
| 三个策略预期增益均有限 | 确认 graph_edge 在真 vector 下价值天然有限；保留 0.5；更新 REQ-025 验收基线说明；不登记实现需求 |

## 6. Risks

- **weight sweep 增加 dry-run 运行时间**：新增 2 scenario × 全样例。dry-run 无 LLM/embedding coverage，可接受。
- **结论"权重不敏感"被误读为"评估失败"**：权重不敏感本身是高价值结论——排除权重作为杠杆，缩小后续优化空间。
- **建议改代码触发大改**：若建议下调权重或改 packer，需独立实现需求 + 重跑 REQ-025 真 LLM 验收，不在本任务做。

## 7. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | 新增 `graph_edge_w03` / `graph_edge_w07` scenario + `_render_req034_section` weight sensitivity 表 + 策略可行性 + REQ-018/025 影响面 + 建议 | — |
| Slice 2 | dry-run 验证机制 + weight sweep 数据 | Slice 1 |
| Slice 3 | 价值判定 + 结论 + 报告 | Slice 2 |
| Slice 4 | 文档收口 + commit + push + PR | Slice 3 |

## 8. References

- REQ-033 评估报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation-report.md`
- REQ-018: `docs/01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md`
- REQ-025: `docs/01-product-planning/05-requirements/REQ-025-p2-graph-edge-prompt-impact-and-real-llm-validation.md`
- 基线脚本: `scripts/validate_req024_p2_real_validation.py`
