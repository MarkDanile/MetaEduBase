# REQ-034 graph_edge RRF 权重/策略调整评估报告

> Status: 🟢 完成
> Created: 2026-06-20
> Requirement: `docs/01-product-planning/05-requirements/REQ-034-p2-graph-edge-rrf-weight-strategy-evaluation.md`
> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation-plan.md`
> 数据源: dry-run retrieval 层 weight sweep（REQ-028 v3 10 样例，5 个 weight level）

## 1. 评估目标

REQ-033 判定 graph_edge 在真 vector 下价值有限（Metric A=5/10、B=1/10、跨文档=0/10），建议登记需求评估是否调整 graph_edge RRF 权重 / 触发策略 / ContextPacker 优先级。本评估回答：

1. **下调 graph_edge RRF 权重是否有效？**（weight sweep）
2. **仅在 vector 召回弱时触发 edge 是否可行有效？**
3. **调整 ContextPacker 优先级是否可行有效？**
4. **上述调整对 REQ-018/025 历史验收的影响面？**

不改主链路代码，基于 dry-run retrieval 层数据 + 代码分析给出建议。

## 2. Weight sweep 数据（核心证据）

5 个 weight level × 10 样例（REQ-028 v3），retrieval 层指标：

| weight | Metric A (edge 进 packed) | Metric B (跨 section 扩展 vs off) | 跨文档 grounding | packed overlap vs off | fusion edge 均值 | edge 召回均值 |
|--------|--------------------------|----------------------------------|----------------|-----------------------|------------------|--------------|
| off (no edge) | 0% | 0% | 0% | 1.00 | 0.0 | 0.0 |
| w=0.3 | 0% | 10% | 0% | 0.91 | 0.0 | 8.0 |
| w=0.5（生产默认） | 0% | 10% | 0% | 0.91 | 0.0 | 8.0 |
| w=0.7 | 0% | 10% | 0% | 0.91 | 0.0 | 8.0 |
| w=1.2 | 50% | 10% | 0% | 0.72 | 3.1 | 8.0 |

> 注：weight = graph_edge 通道在 RRFFusion 中的 `channel_weights` 值；其余通道固定 `vector=1.0, keyword=1.0, graph_node=0.5`。`use_graph_edge=True`。

## 3. 关键发现：生产默认权重下 graph_edge 惰性

**最重大的发现**：在生产默认权重 0.5（及 0.3 / 0.7）下，graph_edge **每样例召回约 8 chunks，但 0 个进入 fusion_topN / packed**（RRF 融合时全被 vector/keyword 挤出）。只有在校验脚本 boosting 用的 w=1.2（非生产配置）下，edge 才进入 fusion（3.1/样例）和 packed（50% 样例）。

含义：

1. **graph_edge 在生产默认配置下是死权重**——每 query 付出 ~8 chunks 的 ILIKE + edge 遍历 + 节点 hydrate 召回成本，产出 0 进 prompt。
2. **REQ-033 的 Metric A=5/10 实测于 w=1.2**（`weighted_rrf` scenario，校验 boosting 配置），**高估了生产环境 edge 贡献**。生产默认 0.5 下真实 Metric A = 0/10。
3. **权重与贡献是阈值跳变，非单调**：≤0.7 全惰性，1.2 才贡献。下调权重（REQ-033 候选方向）从 0.5 → 0.3 **完全无效**（两者皆惰性）。

> 数据稳健性：weight sweep 在 10 样例上一致（fusion_edge_mean=0.0 表示全部 10 样例在 ≤0.7 权重下 edge 0 进 fusion）。dry-run 中 1 条 query 出现 embedding provider 瞬时失败（minimax `'data'`），但 graph_edge 召回为 keyword 种子驱动、不依赖 vector embedding，结论不受影响。

## 4. 候选策略可行性

| 策略 | 类型 | 可行性 | 预期效果 |
|------|------|--------|----------|
| 1. 下调 graph_edge RRF 权重 | 配置（env / 默认值），无主链路改动 | 高 | **无效**——0.5 已惰性，0.3 无差别。weight sweep 证实 |
| 2. 仅在 vector 召回弱时触发 edge | 主链路改动（召回编排两阶段门控） | 中，独立实现需求 | 主要省召回成本；进 packed 由 RRF+packer 决定，对 Metric A 无提升（默认权重下 edge 本就 0 进 fusion） |
| 3. 调整 ContextPacker 优先级 | 主链路改动（budget 内 edge block boost） | 中，独立实现需求 | 可能把 Metric A 提升，但 REQ-033 已证 edge 同文档、不扩展跨文档 grounding——即使全进 packed，Metric B/跨文档仍 ~0，答案质量增益有限 |

## 5. REQ-018/025 历史验收影响面

| 验收点 | 调整策略 | 影响 |
|--------|----------|------|
| REQ-018：4 通道 graph_edge 召回能力 | 下调权重（不关通道） | **不受影响**——通道召回能力不变，仅融合权重变化 |
| REQ-018：4 通道 graph_edge 召回能力 | 关闭通道 / conditional trigger | **受影响**——部分样例不再有 edge 召回，需重验 |
| REQ-025：graph_edge 进 prompt + 真 LLM 验收 | 下调权重 | **已天然不达标**——生产默认 0.5 下 edge 0 进 prompt；REQ-025 进 prompt 验收实际只在 w=1.2 boosting 配置下成立。验收基线需补「权重敏感 + 默认惰性」说明 |
| REQ-025：graph_edge 进 prompt + 真 LLM 验收 | conditional trigger / 关闭 | **受影响**——需重跑真 LLM 验收 |

**重要修正**：REQ-025 「graph_edge 进 prompt」验收在生产默认权重 0.5 下实际不成立（edge 0 进 packed/prompt）。历史上 REQ-025 验收通过依赖校验脚本的 `weighted_rrf` scenario（w=1.2 boosting）。这是 REQ-025 验收基线需要补充说明的核心事实。

## 6. 建议

**判定：下调权重无效——默认 0.5 下 edge 已惰性**

依据 weight sweep 数据：

- 策略 1（下调权重，REQ-033 候选方向）：**无效**。0.5 已惰性，0.3 无差别。排除。
- 策略 2/3（conditional trigger / packer 优先级）：主链路改动，且 REQ-033 已证即使 edge 进 packed（w=1.2），Metric B/跨文档仍 ~0，答案质量增益有限。收益存疑。

**建议动作**：

| 动作 | 说明 | 归属 |
|------|------|------|
| 保留生产默认权重 0.5 | 不引入回归；下调无效，上调收益存疑 | 本任务结论 |
| 登记 REQ-035 决策候选 | 评估 (a) 禁用 graph_edge 通道省召回成本 vs (b) 上调默认权重使 edge 实际贡献。任一变更需重跑 REQ-025 真 LLM 验收 | 候选区 |
| 更新 REQ-025 验收基线说明 | 补充「真 vector 下价值转移 + 生产默认权重 0.5 下 edge 惰性 + Metric A=5/10 实测于 w=1.2 boosting」 | REQ-025 Delivery Record |

## 7. 非目标（确认未做）

- 未修改 RRFFusion / ContextPacker / AIChatService / recall_service / PgEdgeRecallChannel 主链路代码
- 未重跑 REQ-026/027/028/029 真 LLM 报告
- 未强行让任何指标达标
- 未实施任何权重/策略代码变更（仅评估 + 建议）

## 8. 数据可复现

```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out <report.md> --json-out <data.json> \
  --report-title "REQ-034 graph_edge RRF 权重/策略评估 (dry-run)"
```

REQ-034 章节在报告末尾，含 weight sensitivity 表 + 策略可行性 + REQ-018/025 影响面 + 建议判定。dry-run 不调 LLM。
