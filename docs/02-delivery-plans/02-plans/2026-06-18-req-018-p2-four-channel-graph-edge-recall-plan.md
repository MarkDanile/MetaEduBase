# REQ-018 P2 4 通道并行召回与图谱关系召回 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-18-req-018-p2-four-channel-graph-edge-recall.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md`

## Scope

本 plan 实现 REQ-018 的 4 通道并行召回，新增 `PgEdgeRetriever` 从 `knowledge_edges` 做图谱关系召回。其他 3 通道（chunk_vector / chunk_keyword / graph_node）不修改，融合排序由 REQ-017 承接。

## Slice 1 — PgEdgeRetriever 骨架 + Channel Contract

**目标：** `PgEdgeRetriever` 骨架完成，`RecallResult` 支持 edge 类型，mock 测试覆盖通道级失败降级。

**文件：**

- `packages/server-python/app/contexts/knowledge/application/recall_service.py`
  - 新增 `PgEdgeRecallChannel`：查询 `knowledge_nodes` 找种子节点，再查 `knowledge_edges` 找关系节点
  - SQL 路径：先 `ILIKE` 匹配 `knowledge_nodes.title`，取 top-k 节点 → 查 `ix_ke_source` / `ix_ke_target` 找关联边 → 回源到 `target_node.source_chunk_id`
  - 实现 try/except per channel，保证 channel-level degradation

- `packages/server-python/app/contexts/knowledge/application/retrievers.py`
  - 确认 `GraphRetriever` Protocol 不变，`PgEdgeRetriever` 满足 Protocol

- `packages/server-python/tests/contexts/knowledge/retrievers/test_pg_edge_retriever.py`（新建）
  - `test_edge_retriever_returns_evidence_items`：返回 `EvidenceItem(source_type=knowledge_node, channels=[graph_edge])`
  - `test_edge_retriever_falls_back_gracefully`：子查询失败返回空列表
  - `test_edge_retriever_satisfies_graph_retriever_protocol`：Protocol 满足

**验收：**
- `pytest tests/contexts/knowledge/retrievers/test_pg_edge_retriever.py -v` 全部通过
- `ruff check app/contexts/knowledge/ --fix`
- `git diff --check`

## Slice 2 — 接入 AIChatService：4 通道并发

**目标：** `ai_router._build_evidence_service()` 注入 `PgEdgeRetriever`，4 通道并行执行。

**文件：**

- `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`
  - `CompositeChunkRetriever`（3 通道）和 `PgEdgeRetriever`（独立）并行调用
  - 或在 `AIChatService._retrieve()` 中把 edge 作为第 4 通道并发

- `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`
  - 确认 `_retrieve()` 并发模型已支持 4 通道（或按需扩展 `_run_channels`）

- `packages/server-python/tests/contexts/knowledge/test_ai_chat_service.py`
  - 新增测试：`test_ai_chat_uses_four_channels_with_edge`

**验收：**
- `pytest tests/contexts/knowledge/test_ai_chat_service.py -q` 全部通过
- `ruff check app/contexts/knowledge/ --fix`

## Slice 3 — Trace 区分 + 去重合并

**目标：** `diagnostics` 能区分 4 个通道来源，重复 evidence 合并 channels。

**建议动作：**
- 检查 `AIChatService._trace_evidence()` 是否已支持 channels 叠加（已有的 `_normalize_candidate_channels` 可能已处理）
- 确认 `PgEdgeRetriever` 的 `evidence_id` 格式与已有 node 通道不冲突
- `diagnostics.retrieval_topn` 新增 `graph_edge` 键

**文件：**
- `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`（若有修改）

**验收：**
- 测试：4 个通道的 `channels` 在 fused evidence 中正确叠加

## Slice 4 — 真实 PG 样例验收

**目标：** 2 个真实样例（课程先导知识 / 跨章节关联）验证关系召回有效性。

**建议动作：**
- 确认 dev DB 中有 `knowledge_edges` 数据的文件
- 在 `scripts/validate_real_pg_rag.py` 或独立脚本中运行：
  1. 课程先导知识问法（如"学习这门课前需要哪些先导知识？"）
  2. 跨章节关联问法（如"Python 函数的参数和返回值有什么关系？"）
- 对比有/无边 edge 通道时的 recall topN 差异

**文件：**
- `docs/02-delivery-plans/01-specs/2026-06-18-req-018-llm-hybrid-ner-validation-report.md`（placeholder）

**验收：**
- edge 通道能召回到其他通道未覆盖的相关 chunk

## Files To Inspect First

- `packages/server-python/app/contexts/knowledge/application/recall_service.py`
- `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`
- `packages/server-python/app/contexts/knowledge/application/composite_retriever.py`
- `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_graph_retriever.py`
- `packages/server-python/tests/contexts/knowledge/retrievers/test_pg_graph_retriever_contract.py`（参考）

## Required Checks

- `cd packages/server-python && pytest tests/contexts/knowledge/retrievers/test_pg_edge_retriever.py tests/contexts/knowledge/test_ai_chat_service.py -q`
- `ruff check app/contexts/knowledge/`
- `scripts/check-engineering-docs`
- `git diff --check`

## Documentation Closure

完成后必须同步：
- `docs/01-product-planning/04-backlog.md`：REQ-018 状态 🔵 Ready
- `docs/01-product-planning/05-requirements/REQ-018-...`：Delivery Record
- `docs/01-product-planning/02-milestones/02-growth-phase.md`：P2 open item 状态
- `docs/03-engineering-governance/current-work.md`：候选 / 进行中 / 最近完成
- `docs/03-engineering-governance/work-log.md`：一行式索引
