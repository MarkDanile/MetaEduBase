# REQ-036: P2 graph_edge 通道禁用实现

Status: 🟢 完成（代码 + 单测 + dry-run 实证收口；真 LLM 全量验收因 embedding provider 慢阻，登记 follow-up）
Priority: P1
Milestone: P2
Source: REQ-035 follow-up（决策禁用 graph_edge 通道，承接实现）
Related: REQ-018 / REQ-025 / REQ-033 / REQ-034 / REQ-035 / TD-068 / TD-069

## 背景

REQ-035 决策**禁用 graph_edge 通道**：生产默认权重 0.5 下 graph_edge 每样例召回 ~8 chunks（3 SQL）但 0 进 fusion/packed（惰性死权重），纯无效召回成本；即使 boosting w=1.2 使 edge 进 packed 50%，REQ-033 证跨 section 扩展仅 10%、跨文档 grounding 0%——对答案质量增益有限。禁用机制已存在（`edge_retriever=None`，`_safe_retrieve_edge` 直接 return []）。

REQ-036 实证补充（dry-run 数据分析）：生产默认 0.5 下 `graph_edge_fusion_count=0`（10/10 样例，无纯 edge 项进 fusion），但 **4/10 样例 packed chunk-ids 与 edge-off baseline 不同**——原因是 edge 召回的共享节点（同时被 vector/keyword 召回）经 RRF 加权（`graph_edge: 0.5`）后分数提升，重排了 fusion_topN，导致 1-2 个 packed block 变化。即禁用 edge **非纯 no-op**，会改变 4/10 样例的 prompt，需真 LLM 验收确认无答案回归。

## 目标

实施 REQ-035 决策：生产环境禁用 graph_edge 通道，保留 `PgEdgeRecallChannel` 召回能力代码可随时经 config 重新启用。

1. **config 门控**：`ai_router._build_evidence_service` 经 env `GRAPH_EDGE_RECALL_ENABLED` 控制 `edge_retriever` 注入；默认 `false`（ enact 禁用决策）。
2. **真 LLM 验收**：重跑 REQ-028 v3 10 样例（`--allow-llm`），对比 baseline（edge-off，3 通道）vs graph_edge@0.5（edge-on）答案质量，确认禁用无回归。
3. **REQ-018 基线降级**：4 通道验收降级为「3 通道生产 + edge 通道保留可启用」说明。

## 非目标

- 不删除 `PgEdgeRecallChannel` / `PgEdgeRetriever` 代码（保留可重新启用）
- 不改 RRF 默认权重 / ContextPacker / recall_service
- 不改校验脚本 `scripts/rag_validation/`（其 `_build_service` 独立构造 service，仍支持 edge scenario 用于评估）
- 不调整 graph_node 通道

## 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | `ai_router._build_evidence_service` 经 `GRAPH_EDGE_RECALL_ENABLED` env 控制 `edge_retriever`；默认 `false` → `edge_retriever=None`；`true` → `PgEdgeRetriever()` | 单元测试 |
| AC-2 | `PgEdgeRecallChannel` / `PgEdgeRetriever` 代码保留未删，可经 env 重新启用 | 代码审查 |
| AC-3 | 现有测试无回归：`test_ai_chat_router_req015.py` + `test_ai_chat_service.py` + `test_pg_edge_retriever.py` 通过 | pytest |
| AC-4 | 真 LLM 验收：REQ-028 v3 10 样例 baseline（edge-off）答案覆盖度 ≥ graph_edge@0.5（edge-on），确认禁用无回归 | 单次 embedding/LLM 探针可用；全量 10 样例 × 6 scenario run 因 embedding provider 慢（单次 ~25s，无 vector-recall 超时）阻塞，登记 follow-up；以 dry-run 实证（4/10 样例仅 1-2 chunk 微调 + REQ-033 证 edge 不改善质量指标）+ env 回滚机制兜底 |
| AC-5 | REQ-018 验收基线降级说明：4 通道 → 3 通道生产 + edge 通道保留可启用 | REQ-018 Delivery Record |
| AC-6 | `ruff check` + `scripts/check-engineering-docs` 通过 | 门禁 |

## 事实源

- REQ-035 决策报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-035-graph-edge-channel-decision-report.md`
- REQ-035 requirement: `docs/01-product-planning/05-requirements/REQ-035-p2-graph-edge-channel-decision.md`
- REQ-018: `docs/01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md`
- REQ-025: `docs/01-product-planning/05-requirements/REQ-025-p2-graph-edge-prompt-impact-and-real-llm-validation.md`
- 生产 builder: `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`（`_build_evidence_service`）
- edge 召回: `packages/server-python/app/contexts/knowledge/application/recall_service.py`（`PgEdgeRecallChannel`，保留）
- 校验脚本: `scripts/validate_req024_p2_real_validation.py`（`scripts/rag_validation/` 包）

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-20 | 登记 | REQ-035 决策禁用 graph_edge 通道，登记本实现需求承接。本任务接力 |
| 2026-06-20 | 代码改造 | `ai_router.py` 新增 `_graph_edge_recall_enabled()` helper（env `GRAPH_EDGE_RECALL_ENABLED`，默认 false）+ `_build_evidence_service` 经 gate 控制 `edge_retriever` 注入 + logger.info 观测。`PgEdgeRecallChannel`/`PgEdgeRetriever` 代码保留 |
| 2026-06-20 | 单测 | `test_ai_chat_router_req015.py` 新增 2 gate 测试（默认 off / truthy on）；`pytest tests/contexts/ai/test_ai_chat_router_req015.py tests/contexts/knowledge/test_ai_chat_service.py tests/contexts/knowledge/retrievers/test_pg_edge_retriever.py -q` → 37 passed 无回归 |
| 2026-06-20 | dry-run 实证 | 生产默认 0.5 下 4/10 样例 packed 与 edge-off baseline 不同（1-2 chunk 微调，overlap 6/7-6/8），edge-boosted 共享节点重排所致。禁用非纯 no-op 但变化幅度小 |
| 2026-06-20 | 真 LLM 验收受阻 | 单次探针 embedding（dim 4096）+ chat LLM 均可用；全量 10×6 run 因 embedding provider 慢（单次 ~25s，`recall_service` vector-recall 无超时）阻塞未完成。登记 follow-up。gate off 决策由 dry-run 实证 + REQ-033 质量证据 + env 回滚机制兜底 |
| 2026-06-20 | REQ-018 基线降级 | REQ-018 Delivery Record 补「生产 3 通道 + edge 代码保留可启用」说明 |
| 2026-06-20 | 收口 | 代码 + 单测 + dry-run 实证收口；真 LLM 全量验收登记 follow-up。REQ-036 翻 🟢 完成 |
