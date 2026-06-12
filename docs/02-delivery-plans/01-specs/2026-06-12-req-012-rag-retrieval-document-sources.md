# REQ-012 RAG 多路召回与文档级参考来源收口 — Spec

> Requirement: `docs/01-product-planning/05-requirements/REQ-012-rag-retrieval-and-kg-evidence-chain-follow-up.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-12-req-012-rag-retrieval-document-sources-plan.md`

## Summary

本需求收口 AI Chat 当前 3 类用户可见问题：

- 用户问题来自真实文档内容时，AI 仍容易回答“未找到足够参考来源”。
- 回答正文中的 `[1]` / `[2]` / `[3]` 不能稳定打开对应文档片段。
- 底部“参考来源”应展示文档级来源，而不是逐条 chunk / knowledge_node。

本次不新建 follow-up，不新建新的 REQ；它是 `REQ-012` 的正式交付范围。

## Current Findings

| 问题 | 当前证据 | 影响 |
|------|----------|------|
| chunk keyword 未接入 evidence service | `ai_router.py` 中 `_evidence_service` 只注入 `PgChunkVectorRetriever()` + `PgGraphRetriever()`。 | Python 操作指南这类关键词明确的问题仍可能召回不到。 |
| metadata filter 返回值未使用 | `AIChatService._retrieve()` 调用 `await self.metadata_filter.filter(...)` 后没有接返回值。 | filter / metadata 治理不影响融合结果。 |
| `[N]` 点击绑定错误 | `AiChatView.openEvidenceFileByIndex()` 从最近一条 assistant 消息取 sources。 | 点击历史回答引用会错位或无效。 |
| 参考来源不是文档级 | `AiChatView` 直接 `v-for="src in msg.sources"` 渲染 `EvidenceCard`。 | UI 把 evidence/chunk/knowledge_node 当一级引用来源，用户无法按文档理解来源。 |
| graph evidence 仍需真实验收 | TD-050 已打通 `source_chunk_id` 透传，但 REQ-012 尚未验证 graph evidence 是否稳定回到 chunk 原文并进入 prompt。 | 有字段不等于真实问答链路已闭环。 |

## Goals

- `/ai/chat/evidence` 真正使用 chunk vector、chunk keyword/full-text、graph evidence 三类来源。
- metadata filter 的返回结果进入融合前候选集。
- graph evidence 优先回源到 chunk 原文；无法回源时不能作为文档级引用伪装展示。
- prompt context 在 token budget 内优先给 LLM 足够的原文 chunk，而不是只给知识节点 title / description。
- 回答正文 `[N]` 引用绑定当前消息的证据片段，点击可定位到文件详情 + chunk。
- 底部“参考来源”一级对象为文档；chunk 作为文档下的命中片段展示。

## Non-Goals

- 不引入 Elasticsearch、Neo4j、Milvus、Qdrant 或 GraphRAG 框架。
- 不重新实现 TD-047 / TD-048 / TD-050；它们都是已完成前置依赖。
- 不重做知识图谱可视化页面。
- 不把 AI Chat 变成多智能体编排。

## Contract

### EvidenceItem

`EvidenceItem[]` 继续作为回答正文 `[N]` 引用的证据序列。它服务于“这句话引用了哪段证据”。

### DocumentSource

新增或派生文档级来源模型，用于底部“参考来源”。

```text
DocumentSource
- file_id
- title / file_name
- doc_type
- tags
- best_score
- channels
- evidence_indices
- chunks[]
```

`chunks[]` 表示该文档下命中的证据片段：

```text
DocumentSourceChunk
- evidence_index
- chunk_id
- chunk_index
- snippet
- score
- channels
```

实现可以选择：

- 后端在 `/ai/chat/evidence` 中返回 `document_sources` 字段，前端直接展示。
- 或前端从 `sources: EvidenceItem[]` 派生 `DocumentSource[]`。若选择前端派生，必须确保 evidence 中有足够 file metadata。

推荐路线：后端返回 `document_sources`，前端只负责展示，避免多个消费方重复聚合逻辑。

## Acceptance Criteria

- AC-1: `/ai/chat/evidence` 候选通道包含 chunk vector、chunk keyword/full-text、graph evidence；任一通道不可用时记录明确降级日志。
- AC-2: `MetadataFilter.filter(...)` 返回结果实际参与融合前候选集。
- AC-3: prompt context 至少包含真实 chunk 内容；不能只包含 `knowledge_nodes.title` / `description`。
- AC-4: graph evidence 有 `source_chunk_id` 时，prompt 优先使用该 chunk 原文。
- AC-5: 回答正文 `[N]` 引用编号与当前 assistant 消息的 evidence 顺序一致，历史回答点击不受最新回答影响。
- AC-6: `[N]` 点击可打开文件详情页；有 chunk 时定位到 chunk 锚点。
- AC-7: 底部“参考来源”一级按文档聚合，不按 `EvidenceItem` / chunk / knowledge_node 逐条展示。
- AC-8: 文档来源可展开命中片段，片段可点击定位到 chunk。
- AC-9: 无 `file_id` 的 graph / structured evidence 不进入文档来源列表；如展示，必须标记为“来源待细化”。
- AC-10: 真实样例“Python 的基本数据类型和变量有哪些？”能返回有用回答，并展示至少 1 个文档级来源。
- AC-11: 真实样例“智能制造专业需要哪些技能？”能返回有用回答，并展示 evidence 通道、文档来源和片段。
- AC-12: `scripts/ai/evidence_coverage_report.py` 记录 REQ-012 前后覆盖率变化。

## Validation

- Backend:
  - `pytest tests/contexts/knowledge/test_ai_chat_service.py -q`
  - 新增 / 扩展 chunk keyword、metadata filter、graph-to-chunk、document source aggregation 测试。
- Frontend:
  - 新增 / 扩展 `AiChatView` 或 helper 测试，覆盖当前消息 `[N]` 点击、文档级来源聚合、chunk 展开。
  - `pnpm --filter @metaedu/web lint`
  - `pnpm --filter @metaedu/web typecheck`
- Integration:
  - 有 PG 环境时对 `/api/v1/ai/chat/evidence` 运行 Python 操作指南样例和智能制造样例。
  - `python scripts/ai/evidence_coverage_report.py`
- Docs:
  - `scripts/check-engineering-docs`
  - `git diff --check`

## Risks

| 风险 | 缓解 |
|------|------|
| keyword / vector / graph 多路结果重复 | 继续用 `EvidenceItem.evidence_id` + fusion 去重。 |
| 文档级来源与 inline evidence 编号混淆 | 明确 `EvidenceItem[]` 服务正文引用，`DocumentSource[]` 服务底部来源。 |
| graph evidence 无 file_id | 不进入文档级来源，显示为补充证据或来源待细化。 |
| token 上下文过长 | 增加 prompt 打包预算，只取高分文档的高分片段。 |
| 前端引用点击历史消息错位 | 将引用 click handler 绑定当前消息 index / message id，而不是全局取最新 assistant。 |
