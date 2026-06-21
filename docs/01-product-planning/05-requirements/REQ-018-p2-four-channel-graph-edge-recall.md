# REQ-018: P2 4 通道并行召回与图谱关系召回

Status: 🟢 完成（Slice 4 已验收，发现evidence_id=\"\" bug已修复）
Priority: P0
Milestone: P2
Source: P2-RECALL-4 Open Item
Related: REQ-012 / REQ-013 / REQ-017

## Goal

在现有 chunk vector / chunk keyword / metadata 或 graph node 召回基础上，新增 PostgreSQL `knowledge_edges` 图谱关系召回通道，形成 P2 的 4 通道并行召回。图谱关系只提供扩展和推理线索，最终 evidence 必须回到 chunk 或 section。

## Current Code Facts

| 能力 | 当前状态 | 证据 |
|------|----------|------|
| chunk vector recall | 已实现 | `PgChunkVectorRetriever` 已作为 `CompositeChunkRetriever` 的通道之一注入 AI Chat。 |
| chunk keyword recall | 已实现 | `PgChunkKeywordRetriever` 已基于 `document_chunks.content_tsvector` / `chinese_zh` 做 chunk 级关键词召回。 |
| graph node recall | 已实现但不是 edge recall | `PgGraphRetriever` 包装 `PgVectorRecallChannel` / `PgKeywordRecallChannel` 查询 `knowledge_nodes`，并把 `source_file_id` / `source_chunk_id` 透传到 `EvidenceItem`。 |
| graph node -> chunk hydration | 已实现 | `AIChatService._hydrate_graph_chunks()` 和 `ContextPacker` 可把 `knowledge_node` 的 `source_chunk_id` 回源到正文 chunk 与邻居 chunk。 |
| PostgreSQL `knowledge_edges` edge recall | 未实现 | 当前未发现独立 graph edge recall adapter；`knowledge_edges` 主要用于 KG 展示、CRUD、kg-bundle 和数据完整性，不参与 AI Chat 召回通道。 |
| 4 通道并行召回 | 已实现 | PR #333/#334/#335 已接入 `PgEdgeRetriever` 第 4 通道，`diagnostics.retrieval_topn.graph_edge` 可见。 |

因此 REQ-018 是 **新增召回通道任务**。已有 graph node 回源 chunk 能作为实现基础，但不能把它等同于 `knowledge_edges` 图谱关系召回。

## Scope

- 明确当前 AI Chat 生产链路的通道边界和降级策略。
- 新增 graph edge recall adapter：从 `knowledge_edges` 关系出发，找到 source / target 节点，再回到 `source_chunk_id` / `source_file_id` 或相邻 chunk / section。
- 关系召回结果必须进入统一 `EvidenceItem`，而不是把 graph node / edge 当作独立最终正文。
- 保留 PostgreSQL 实现边界，不引入 Neo4j。
- 增加真实样例：课程能力图谱、Python 教程问答、文档结构化结果关联问答。

## Non-Goals

- 不做完整 Microsoft GraphRAG 社区发现 / 全局摘要。
- 不引入 Neo4j 或图数据库。
- 不在本任务内实现 RRF；融合排序由 REQ-017 承接。

## Acceptance

- AC-1：AI Chat 生产链路能并行执行 4 个召回通道，任一通道失败可降级。
- AC-2：graph edge 通道命中的关系最终能回源到 chunk / section，并进入 prompt context。
- AC-3：trace 中能看到 graph edge topN、关联节点、回源 chunk 和最终 evidence。
- AC-4：重复 evidence 能与其他通道合并 channels，不重复污染 sources。
- AC-5：至少 2 个真实样例证明关系召回能补足仅靠 keyword/vector 不稳定的问答。
- AC-6：现有 graph node -> chunk hydration 行为不能回归；新增 edge recall 后仍必须复用统一 `EvidenceItem` / ContextPacker / document_sources 链路。

## Delivery Links

- Backlog: `docs/01-product-planning/04-backlog.md`
- Milestone: `docs/01-product-planning/02-milestones/02-growth-phase.md`

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-18 | Shaping 完成 | spec + plan 产出，PR #332 squash merge |
| 2026-06-18 | Shaping 收口 | spec + plan + PR #332 已合并 |
| 2026-06-18 | Slice 1 完成 | PR #333 squash merge `a94c681`：RecallResult.edge_id + PgEdgeRecallChannel（seed→edge→node）+ PgEdgeRetriever + 5 mock tests |
| 2026-06-18 | Slice 2 完成 | PR #334 squash merge `87230ba`：AIChatService edge_retriever 第 4 通道 + _normalize_candidate_channels 处理 knowledge_edge + RRF graph_edge 权重 0.5 + 2 mock tests |
| 2026-06-18 | Slice 3 完成 | PR #335 merge（仅测试）：trace graph_edge 通道已在 diagnostics.retrieval_topn 中可见，EvidenceItem model_validator 自动去重 + 2 mock tests |
| 2026-06-18 | Slice 4 真实PG验收 | 4通道均激活（vector/keyword/graph/graph_edge）；发现并修复evidence_id="" bug（导致RRF dedup异常）；真PG验收报告已产出 |
| 2026-06-18 | 评审收口 | DOC-071 确认通道接入可关闭；AC-5“关系召回补足 keyword/vector 不稳定问答”仍需更强真实样例，由 REQ-024 接力。 |
| 2026-06-20 | 验收基线降级（REQ-036） | REQ-033/034/035 三轮评估证 graph_edge 在真 vector 召回下价值有限：生产默认权重 0.5 下召回 8 chunks/样例但 0 进 fusion/packed（惰性），即使 boosting 亦不改善 Metric B/跨文档。REQ-036 实施 REQ-035 决策：生产 builder 经 `GRAPH_EDGE_RECALL_ENABLED` env 门控，**默认禁用** graph_edge 通道。验收基线降级：**生产环境 3 通道（vector/keyword/graph_node）+ edge 通道代码保留可经 env 重新启用**。`PgEdgeRecallChannel` 召回能力本身（`test_pg_edge_retriever.py`）未退化，仅生产未注入。详见 [REQ-035 决策报告](../../02-delivery-plans/01-specs/2026-06-20-req-035-graph-edge-channel-decision-report.md) / [REQ-036 实现](REQ-036-p2-graph-edge-channel-disable-impl.md)。 |
