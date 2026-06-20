# REQ-035: P2 graph_edge 通道去留决策

Status: 🟢 完成
Priority: P2
Milestone: P2
Source: REQ-034 follow-up（生产默认权重 0.5 下 graph_edge 惰性，登记决策候选）
Related: REQ-018 / REQ-025 / REQ-033 / REQ-034 / TD-068 / TD-069

## 背景

REQ-034 weight sweep 证实在**生产默认权重 0.5**（`ai_router._RRF_DEFAULT_WEIGHTS`，未设 `RRF_CHANNEL_WEIGHTS` env）下，graph_edge 每样例召回约 8 chunks 但 **0 进 fusion_topN / packed**——edge 通道在生产默认配置下是惰性死权重，仅付出召回成本无任何产出。仅在校验脚本 boosting 用的 w=1.2（非生产配置）下 edge 才进 packed（50%）。

当前架构事实（已 codegraph 确认）：

- **召回串行**：`AIChatService._retrieve` 因 SQLAlchemy AsyncSession 禁止并发操作，`chunk_results` → `graph_results` → `edge_results` 顺序执行。edge 召回成本完全叠加在每个 query 上。
- **edge 通道成本**：`PgEdgeRecallChannel.recall` 每次 query 跑 3 条 SQL（ILIKE 种子节点 → `knowledge_edges` 遍历 → 关联节点 hydrate），无论是否有 edge 进 fusion。
- **禁用机制已存在**：`AIChatService` 构造接受 `edge_retriever=PgEdgeRetriever() if use_graph_edge else None`；`_safe_retrieve_edge` 在 `edge_retriever is None` 时直接 `return []`，零成本。生产禁用 = 移除 `PgEdgeRetriever()` 注入或经 config 门控。
- **REQ-033 已证**：即使 edge 进 packed（w=1.2 boosting），Metric B（跨 section 扩展）= 1/10、跨文档 grounding = 0/10，对答案质量增益有限。

## 目标

基于 REQ-033/034 既有证据 + 召回成本分析，给出 graph_edge 通道去留的明确决策。**不改主链路代码。**

决策二选一：

1. **禁用 graph_edge 通道**（省召回成本）：将生产 `edge_retriever` 注入改为 None / config 门控，消除每 query 3 条 SQL 的无效召回成本。
2. **上调默认权重使 edge 实际贡献**：将 `_RRF_DEFAULT_WEIGHTS["graph_edge"]` 从 0.5 上调到 ≥1.2 使 edge 进 fusion/packed。

## 非目标

- 不修改主链路代码（RRFFusion / ContextPacker / AIChatService / recall_service / PgEdgeRecallChannel / ai_router）
- 不重跑 REQ-025 真 LLM 验收（若决策为变更，由后续实现需求承接）
- 不强行让任何指标达标
- 不在本任务实施代码变更——仅评估 + 决策

## 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 报告新增 "REQ-035" 章节：成本侧量化（每 query 3 条 SQL / 召回 chunk 数 / 0 进 fusion）+ 收益侧量化（即使 w=1.2 boosting 的 Metric A/B/跨文档） | 报告章节 |
| AC-2 | 章节含「禁用」可行性分析：禁用机制（`edge_retriever=None` 已存在）+ 影响面（REQ-018 通道验收 / REQ-025 进 prompt 验收 / 测试覆盖） | 报告章节 |
| AC-3 | 章节含「上调权重」可行性分析：从 0.5 → ≥1.2 的收益（Metric A 0→50%）+ 成本（edge 同文档不扩展 grounding，REQ-033 已证收益有限） | 报告章节 |
| AC-4 | 给出明确决策（禁用 / 上调 / 维持现状）+ 实现需求归属（若变更，登记独立实现需求） | 报告结论 |
| AC-5 | dry-run 可复跑；成本/收益数据来自既有 REQ-028 v3 dry-run（不调 LLM） | CLI 行为 |
| AC-6 | 不修改主链路代码；仅新增脚本报告章节 | 代码 diff |

## 事实源

- REQ-034 评估报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation-report.md`
- REQ-034 requirement: `docs/01-product-planning/05-requirements/REQ-034-p2-graph-edge-rrf-weight-strategy-evaluation.md`
- REQ-033 评估报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation-report.md`
- REQ-018: `docs/01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md`
- REQ-025: `docs/01-product-planning/05-requirements/REQ-025-p2-graph-edge-prompt-impact-and-real-llm-validation.md`
- 召回编排: `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`（`_retrieve` / `_safe_retrieve_edge`）
- RRF 权重配置: `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`（`_RRF_DEFAULT_WEIGHTS`）
- edge 召回: `packages/server-python/app/contexts/knowledge/application/recall_service.py`（`PgEdgeRecallChannel`）
- 基线脚本: `scripts/validate_req024_p2_real_validation.py`（拆分后 `scripts/rag_validation/` 包）

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-20 | 登记 | REQ-034 证生产默认 0.5 下 edge 惰性（召回成本无产出），登记本决策候选。本任务接力 |
| 2026-06-20 | 脚本改造 | `scripts/rag_validation/report_decision.py` 新增 `_render_req035_section`（成本/收益对照 + 禁用可行性 + 上调可行性 + 决策判定）；`report.py` 挂载章节。新增 `report_decision.py` 模块（从 `report_chain.py` 拆出，保持每文件 ≤500 行） |
| 2026-06-20 | dry-run 决策 | 成本侧：生产默认 0.5 下每 query ~8 chunks 召回（3 SQL）0 进 fusion/packed（纯无效）。收益侧上限：boosting w=1.2 使 edge 进 packed 50%，但 REQ-033 证跨 section 扩展仅 10%、跨文档 0%——对答案质量增益有限 |
| 2026-06-20 | 决策收口 | **决策：禁用 graph_edge 通道**。禁用机制已存在（`edge_retriever=None`），消除纯浪费且产出与现状相同；上调需维持成本换有限增益，性价比低。登记实现需求承接 config 门控 + 重跑 REQ-025 真 LLM 验收 + REQ-018 基线降级。REQ-035 翻 🟢 完成 |
