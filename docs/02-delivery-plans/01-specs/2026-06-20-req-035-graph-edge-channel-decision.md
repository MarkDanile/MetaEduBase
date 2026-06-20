# REQ-035 Spec: P2 graph_edge 通道去留决策

> Status: 🟢 完成
> Created: 2026-06-20
> Source: REQ-034 follow-up（生产默认权重 0.5 下 graph_edge 惰性）
> Requirement: `docs/01-product-planning/05-requirements/REQ-035-p2-graph-edge-channel-decision.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-035-graph-edge-channel-decision-plan.md`

## 1. Problem Statement

REQ-034 weight sweep 证实在生产默认权重 0.5 下 graph_edge 每样例召回约 8 chunks 但 0 进 fusion/packed（惰性死权重），仅付出召回成本无产出。REQ-034 结论之一：登记 REQ-035 决策候选评估「禁用 graph_edge 通道省召回成本」vs「上调默认权重使 edge 实际贡献」。本任务完成该决策，不改主链路代码。

当前架构事实（已 codegraph 确认）：

- `AIChatService._retrieve` 串行执行 `chunk_results` → `graph_results` → `edge_results`（SQLAlchemy AsyncSession 禁止并发），edge 召回成本完全叠加。
- `PgEdgeRecallChannel.recall` 每次 query 跑 3 条 SQL：ILIKE 种子节点 → `knowledge_edges` 遍历（`ORDER BY e.weight DESC`）→ 关联节点 hydrate。
- `_safe_retrieve_edge` 在 `self.edge_retriever is None` 时直接 `return []`——禁用机制已存在，生产禁用 = 移除 `PgEdgeRetriever()` 注入或 config 门控。
- 默认权重 `{vector: 1.0, keyword: 1.0, graph_node: 0.5, graph_edge: 0.5}`（`ai_router._RRF_DEFAULT_WEIGHTS`），可经 `RRF_CHANNEL_WEIGHTS` env 覆盖。

## 2. Goal

基于 REQ-033/034 既有证据 + 召回成本分析，给出 graph_edge 通道去留明确决策。**不改主链路代码。**

## 3. Non-Goals

- 不改 RRFFusion / ContextPacker / AIChatService / recall_service / PgEdgeRecallChannel / ai_router
- 不重跑 REQ-025 真 LLM 验收（若决策为变更，由后续实现需求承接）
- 不强行让任何指标达标
- 不在本任务实施代码变更

## 4. Acceptance Criteria

见 requirement AC-1 ~ AC-6。

## 5. Architecture

### 5.1 成本侧量化（脚本新增章节）

基于既有 REQ-028 v3 dry-run 数据（不需重跑），新增 `_render_req035_section`：

- **召回成本**：per sample graph_edge 召回 chunk 数（8/样例）× 3 SQL/召回 = 每 query ~3 条无效 SQL
- **产出**：生产默认 0.5 下 0/10 进 fusion、0/10 进 packed（REQ-034 weight sweep）
- **对比**：禁用后召回成本 = 0；上调到 1.2 后 edge 进 packed 5/10 但 Metric B/跨文档仍 ~0（REQ-033）

### 5.2 禁用可行性

| 维度 | 评估 |
|------|------|
| 机制 | `edge_retriever=None` 已存在（`_safe_retrieve_edge` 直接 return []）。生产禁用 = `ai_router._build_evidence_service` 不注入 `PgEdgeRetriever()` 或 config 门控。**代码改动小**。 |
| REQ-018 影响 | REQ-018 验收点「4 通道 graph_edge 召回能力」——禁用即 4 通道降 3 通道，**验收需重判或降级**。但通道召回能力本身（PgEdgeRecallChannel）保留，仅生产未启用。 |
| REQ-025 影响 | REQ-025 验收点「graph_edge 进 prompt + 真 LLM 验收」——REQ-034 已补「生产默认 0.5 下 edge 0 进 prompt」说明，禁用与之一致，**不引入新回归**。需重跑真 LLM 验收确认 baseline 答案质量不退步。 |
| 测试覆盖 | `tests/contexts/knowledge/retrievers/test_pg_edge_retriever.py` 测的是 PgEdgeRetriever 召回能力本身，禁用生产注入不影响单元测试。`test_ai_chat_service.py` / `test_context_packer.py` 部分 scenario 注入 edge，需复核。 |

### 5.3 上调权重可行性

| 维度 | 评估 |
|------|------|
| 机制 | 改 `_RRF_DEFAULT_WEIGHTS["graph_edge"]` 0.5 → ≥1.2，或文档建议生产设 `RRF_CHANNEL_WEIGHTS` env。**配置改动**。 |
| 收益 | weight sweep：1.2 下 Metric A 0%→50%（edge 进 packed）。但 REQ-033 证即使进 packed，Metric B（跨 section 扩展）=1/10、跨文档 grounding=0/10——**对答案质量增益有限**。 |
| 成本 | 维持每 query 3 条 SQL 召回成本；且 edge 进 packed 会占用 budget 替换 baseline chunk（REQ-033 packed_overlap 分析）。 |
| REQ-018 影响 | 通道保留，**不受影响**。 |
| REQ-025 影响 | edge 进 prompt 样例数从 0→50%，**需重跑真 LLM 验收**确认是否改善答案。 |

### 5.4 决策框架

| 条件 | 决策 |
|------|------|
| 成本（每 query 3 SQL 无产出）> 收益（即使 boosting 亦不改善 Metric B/跨文档） | 禁用 graph_edge 通道，登记实现需求做 config 门控 + 重跑 REQ-025 真 LLM 验收 |
| 收益（w=1.2 下 edge 进 packed 改善答案质量，需真 LLM 验证）> 成本 | 上调默认权重到 ≥1.2，登记实现需求 + 重跑 REQ-025 真 LLM 验收 |
| 两者收益均不确定 / 成本可接受 | 维持现状（0.5 惰性），接受无效召回成本，后续随 vector 召回增强再评估 |

## 6. Risks

- **禁用被误读为「放弃 graph_edge 能力」**：PgEdgeRecallChannel 召回能力代码保留，仅生产未启用；后续若 vector 召回退化或图谱扩充，可经 config 重新启用。
- **决策需要真 LLM 验证支撑但本任务不跑 LLM**：成本侧证据充分（0 进 fusion 是确定事实）；收益侧「上调权重是否改善答案」需真 LLM 验证，但 REQ-033 已证即使进 packed 亦不改善 Metric B/跨文档，收益上限有限。决策可在不跑 LLM 的前提下给出。
- **禁用触发 REQ-018/025 重判**：若决策为禁用，需独立实现需求承接 config 门控 + 真验收重判，不在本任务做。

## 7. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | `_render_req035_section` 成本/收益量化 + 禁用可行性 + 上调可行性 + 决策框架 | — |
| Slice 2 | dry-run 验证机制 + 章节渲染 | Slice 1 |
| Slice 3 | 决策 + 结论 + 报告 | Slice 2 |
| Slice 4 | 文档收口 + commit + push + PR | Slice 3 |

## 8. References

- REQ-034 评估报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation-report.md`
- REQ-033 评估报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation-report.md`
- REQ-018: `docs/01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md`
- REQ-025: `docs/01-product-planning/05-requirements/REQ-025-p2-graph-edge-prompt-impact-and-real-llm-validation.md`
- 基线脚本: `scripts/validate_req024_p2_real_validation.py`（拆分后 `scripts/rag_validation/` 包）
