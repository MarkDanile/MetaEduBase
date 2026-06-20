# REQ-035 graph_edge 通道去留决策报告

> Status: 🟢 完成
> Created: 2026-06-20
> Requirement: `docs/01-product-planning/05-requirements/REQ-035-p2-graph-edge-channel-decision.md`
> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-035-graph-edge-channel-decision.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-035-graph-edge-channel-decision-plan.md`
> 数据源: dry-run retrieval 层数据（REQ-028 v3 10 样例，复用 REQ-033/034 weight sweep）

## 1. 决策目标

REQ-034 weight sweep 证实在**生产默认权重 0.5**下 graph_edge 每样例召回约 8 chunks 但 0 进 fusion/packed（惰性死权重），仅付出召回成本无产出。本决策回答：**graph_edge 通道应禁用、上调权重、还是维持现状？**

不改主链路代码，基于 REQ-033/034 既有证据 + 召回成本分析给出决策。

## 2. 成本/收益证据（REQ-028 10 样例 dry-run）

| 方案 | 每 query 召回成本 | edge 进 packed | 跨 section 扩展 | 跨文档 grounding |
|------|------------------|----------------|-----------------|------------------|
| 维持现状（默认 0.5） | ~8 chunks / 3 SQL（全无效） | 0% | 0% | 0% |
| 上调权重（≥1.2 boosting） | ~8 chunks / 3 SQL | 50% | 10% | 0% |
| 禁用通道（edge_retriever=None） | 0 chunks / 0 SQL | 0% | 0% | 0% |

### 成本侧（确定）

- 召回编排串行（`AIChatService._retrieve` 因 SQLAlchemy AsyncSession 禁并发，`chunk` → `graph` → `edge` 顺序执行），edge 召回成本完全叠加在每个 query 上。
- `PgEdgeRecallChannel.recall` 每 query 跑 3 条 SQL：ILIKE 种子节点 → `knowledge_edges` 遍历（`ORDER BY e.weight DESC`）→ 关联节点 hydrate。
- 生产默认 0.5 下每样例召回 ~8 chunks，进 packed 0/10——**纯无效召回成本**。

### 收益侧（上限有限）

- 上调到 1.2 boosting：edge 进 packed 0%→50%（Metric A 提升），但 REQ-033 证即使进 packed：
  - 跨 section 扩展（Metric B）= 10%（多数样例上下文无扩展甚至收缩）
  - 跨文档 grounding = 0%（edge chunks 全同文档，不扩展溯源广度）
- 即 edge 进 packed 对**答案质量增益有限**，且维持每 query 3 SQL 召回成本 + 占 budget 替换 baseline chunk（REQ-033 packed_overlap 5-6/8）。

## 3. 禁用通道可行性

| 维度 | 评估 |
|------|------|
| 机制 | `edge_retriever=None` 已存在（`_safe_retrieve_edge` 直接 return []）；生产禁用 = `ai_router._build_evidence_service` 不注入 `PgEdgeRetriever()` 或 config 门控。**代码改动小** |
| REQ-018 影响 | 验收点「4 通道 graph_edge 召回能力」——禁用即生产降为 3 通道，验收需重判；但 `PgEdgeRecallChannel` 召回能力代码保留，仅生产未启用 |
| REQ-025 影响 | REQ-034 已补「生产默认 0.5 下 edge 0 进 prompt」说明，禁用与之一致，**不引入新回归**；需重跑真 LLM 验收确认 baseline 答案质量不退步 |
| 测试覆盖 | `test_pg_edge_retriever.py` 测召回能力本身，禁用生产注入不影响单测；`test_ai_chat_service.py` / `test_context_packer.py` 部分 scenario 注入 edge 需复核 |

## 4. 上调权重可行性

| 维度 | 评估 |
|------|------|
| 机制 | 改 `_RRF_DEFAULT_WEIGHTS['graph_edge']` 0.5 → ≥1.2，或文档建议生产设 `RRF_CHANNEL_WEIGHTS` env。**配置改动** |
| 收益 | weight sweep：1.2 下 Metric A 0%→50%。但 REQ-033 证即使进 packed，Metric B=10%、跨文档=0%——**对答案质量增益有限** |
| 成本 | 维持每 query 3 SQL 召回成本；且 edge 进 packed 占 budget 替换 baseline chunk |
| REQ-018/025 影响 | 通道保留，REQ-018 不受影响；REQ-025 edge 进 prompt 样例 0→50%，需重跑真 LLM 验收 |

## 5. 决策

**决策：禁用 graph_edge 通道（省召回成本）**

依据：

- **成本侧确定**：生产默认 0.5 下召回完全无效，纯浪费每 query 3 SQL。禁用机制已存在（`edge_retriever=None`），代码改动小。
- **收益侧上限有限**：即使 boosting（w=1.2）使 edge 进 packed 50%，REQ-033 证跨 section 扩展仅 10%、跨文档 grounding 0%——对答案质量增益有限，且维持召回成本。
- **禁用是占优选项**：禁用消除纯浪费且产出与现状相同（0 进 packed，因默认本就惰性）；上调需维持成本换取有限增益，性价比低。

## 6. 建议动作

| 动作 | 说明 | 归属 |
|------|------|------|
| 禁用 graph_edge 通道 | 生产 `edge_retriever` 经 config 门控不注入；保留 `PgEdgeRecallChannel` 代码可随时重新启用 | 独立实现需求 |
| 重跑 REQ-025 真 LLM 验收 | 确认 baseline（3 通道）答案质量不退步 | 独立实现需求 |
| REQ-018 验收基线降级说明 | 4 通道 → 3 通道生产 + edge 通道保留可启用 | REQ-018 Delivery Record |
| 登记实现需求 | (1) config 门控 `edge_retriever` 注入；(2) 重跑 REQ-025；(3) REQ-018 基线降级 | 候选区 |

## 7. 非目标（确认未做）

- 未修改 RRFFusion / ContextPacker / AIChatService / recall_service / PgEdgeRecallChannel / ai_router 主链路代码
- 未重跑 REQ-025 真 LLM 验收
- 未实施任何通道禁用/权重上调代码变更（仅决策 + 建议）

## 8. 数据可复现

```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out <report.md> --json-out <data.json> \
  --report-title "REQ-035 graph_edge 通道去留决策 (dry-run)"
```

REQ-035 章节在报告末尾，含成本/收益对照 + 禁用/上调可行性 + 决策判定。dry-run 不调 LLM。
