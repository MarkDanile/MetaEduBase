# REQ-012: RAG 多路召回与知识图谱证据链收口

Status: 🔵 Ready
Priority: P1
Milestone: P1 / P2
Parent: REQ-010
Alias: REQ-010 质量 follow-up
Source: AI Chat 问答质量复核 / TD-046 数据回填结果 / TD-047 / TD-050 / P2-SEARCH 规划校准

## 背景

REQ-010 已建立 evidence-aware AI Chat 骨架：前端默认请求 `/ai/chat/evidence`，后端通过 `AIChatService` 把候选证据融合后交给 LLM，并在前端展示 `[1]` / `[2]` 引用和参考来源。

复核发现，该骨架仍未完全达到“用户提问 -> 多路召回 -> 融合排序 -> 高相关原文切片 / 结构化证据 / 图谱证据 -> LLM 回答”的目标：

- evidence 路径当前主要接入 chunk vector + graph 两路；chunk keyword retriever 已存在但未注入线上 service。
- `MetadataFilter.filter(...)` 返回值未被接住，过滤 / 加权结果没有真正参与候选集。
- 知识图谱召回仍可能退化为 `knowledge_nodes.description`，未稳定回到 `source_chunk_id` / 原文 chunk。
- prompt context 使用 `snippet or content`，当前 chunk retriever 的 snippet 为 `content[:200]`，上下文可能偏薄。
- TD-046 回填后 `node_source_chunk` 为 754 / 1006 (74.95%)，仍有 252 个 `file_only` 节点；其中中文分词 / ILIKE 限制已拆为 [TD-047](../../03-engineering-governance/technical-debt.md#td-047)。
- 2026-06-12 复核发现，`AiChatView` 中 `[N]` 点击仍从“最近一条 assistant 消息”取 sources，历史回答点击会错位。
- 2026-06-12 复核确认，底部“参考来源”仍直接渲染 `EvidenceItem[]`，一级来源是 chunk / knowledge_node 等证据条目，不是用户期望的文档级引用来源。

本需求承接 REQ-010 的质量 follow-up，聚焦 AI Chat 的真实回答质量，不替代 TD-047 / TD-048：

| 任务 | 边界 |
|------|------|
| REQ-012 | 多路召回、证据链、prompt 证据上下文、文档级参考来源、端到端问答质量收口 |
| TD-047 | 中文分词 / PostgreSQL tsvector 搜索增强，已完成，是 REQ-012 的底层检索能力依赖之一 |
| TD-050 | `EvidenceItem.source_chunk_id` 字段与 RecallResult 透传，已完成，是 graph evidence 回源 chunk 的前置依赖 |
| TD-048 | 旧 `/ai/chat` node-shaped 契约 deprecation，已完成，不再作为 REQ-012 阻塞项 |

## 设计决策

- 回答正文里的 `[1]` / `[2]` / `[3]` 仍绑定具体 evidence / chunk，用于标注某句话参考了哪段证据。
- 回答底部的“参考来源”一级对象必须是文档，不是切片、知识节点或单条 evidence。
- chunk 只能作为文档下的“命中片段”展示，可折叠 / 展开；点击文档标题进入文件详情，点击片段进入文件详情并定位到 chunk。
- graph / structured evidence 可以参与 LLM 上下文，但只有能归因到 `file_id` 的证据才能进入文档级参考来源；无法归因的证据只能作为“知识图谱补充证据 / 来源待细化”展示，不得伪装为文档引用。

## 目标

- 让 AI Chat evidence 路径真正使用 chunk 级多路召回，而不是只依赖向量和知识节点摘要。
- 让 metadata filter 的结果进入融合前候选治理。
- 让 graph evidence 能追溯到 file / chunk，优先给 LLM 原文证据，而不是孤立知识点。
- 在 token budget 内组装足够的原文 chunk / 结构化字段 / 关系证据，提升回答 grounding。
- 让底部“参考来源”按文档聚合展示，并支持展开查看命中片段。
- 让回答正文 `[N]` 点击绑定当前消息的证据，不被后续回答覆盖或错位。
- 建立可复现验收：用真实样例问题验证 sources、prompt context、回答引用和覆盖率指标。

## 非目标

- 不在本需求内引入 Elasticsearch、Neo4j、Milvus / Qdrant 或完整 GraphRAG 基础设施。
- 不直接实现 TD-047 的中文分词方案；本需求只依赖或引用其结果。
- 不删除旧 `/ai/chat` 契约；该事项由 TD-048 独立处理。
- 不重写整个文档处理流水线。

## 范围

### Backend

- 将 chunk keyword / 全文召回接入 `AIChatService` 的 evidence 路径。
- 修复 metadata filter 返回值未参与候选集的问题。
- 增强 graph retriever：命中 `knowledge_node` 后尽量回到 `source_chunk_id` / `source_file_id`，必要时扩展取相关 chunk。
- 检查并修复 KG 抽取节点写入分支，确保新抽取节点稳定写入 `source_file_id`、`source_chunk_id`、`node_source_resolution`。
- 改进 prompt context 组装：从固定 200 字 snippet 过渡到 token budget 下的证据打包策略。
- 保持 retriever / fusion / prompt 组装可替换边界，不把 PostgreSQL SQL 细节泄漏到 AI Chat 编排层。

### Data

- 基于 TD-046 后的覆盖率作为起点：`node_source_chunk` 74.95%、`chunk_embedding` 100%、`chunk_tsvector` 100%、`file_metadata` 100%。
- 对 `file_only` 节点做分布分析，区分：
  - 缺 `source_file_id` 的历史 / seed 节点。
  - 有 `source_file_id` 但未定位 chunk 的节点。
- 若代码修复后需要重跑数据，优先选择性 backfill / reinitialize 关键文件，不默认全量重跑。

### Frontend

- 修复 `[N]` 点击使用“最近一条 assistant sources”的错位问题，改为绑定当前消息 sources。
- 将底部参考来源从逐条 `EvidenceItem` 卡片改为文档级来源列表。
- 每个文档来源展示文档标题、来源类型 / 标签、最高相关度、命中通道、命中片段数量和“查看文档”入口。
- 文档来源下可展开 chunk 命中片段；片段可点击定位到文件详情页的 chunk 锚点。
- 无法归因到文档的 graph / structured evidence 不进入文档来源列表；如确需展示，放到“补充证据 / 来源待细化”区域。

## 验收标准

- AC-1：`/ai/chat/evidence` 的候选通道至少包含 chunk vector、chunk keyword / full-text、graph evidence 三类来源或明确降级日志。
- AC-2：metadata filter 的返回结果实际影响融合前候选集，并有测试覆盖。
- AC-3：graph evidence 至少在可解析场景中回到 `file_id` / `chunk_id`，LLM prompt 中优先使用对应 chunk 原文。
- AC-4：prompt context 包含真实 chunk 内容，不能只包含 `knowledge_nodes.title` / `description`。
- AC-5：回答中的 `[N]` 引用编号不越界，且与当前 assistant 消息的 evidence 顺序一致；点击历史回答里的 `[N]` 不得跳到最新回答的来源。
- AC-6：底部“参考来源”一级按文档聚合，不按 chunk / knowledge_node / EvidenceItem 逐条展示。
- AC-7：文档级来源可展开命中片段；点击文档进入文件详情页，点击片段进入文件详情页并定位 chunk。
- AC-8：无法归因到文档的 graph / structured evidence 不伪装为文档引用，UI 明确显示“来源待细化”或不进入参考文档列表。
- AC-9：用“Python 的基本数据类型和变量有哪些？”或等价真实样例跑通端到端验收，记录文档级参考来源、命中片段、召回通道、prompt 摘要和回答质量结论。
- AC-10：用“智能制造专业需要哪些技能？”或等价真实样例跑通端到端验收，记录 sources、召回通道、prompt 摘要和回答质量结论。
- AC-11：重跑 `scripts/ai/evidence_coverage_report.py`，记录 REQ-012 前后覆盖率变化。
- AC-12：不把 TD-047 / TD-048 / TD-050 的独立边界重复合并进本需求；它们只作为已完成前置依赖引用。

## 验证建议

- `pytest tests/contexts/knowledge/test_ai_chat_service.py -q`
- 新增或扩展 chunk keyword / metadata filter / graph-to-chunk 的单元测试。
- 新增或扩展前端测试，覆盖当前消息 `[N]` 点击、文档级来源聚合和 chunk 展开。
- 有 PG 环境时运行 `/api/v1/ai/chat/evidence` 真实样例测试，至少覆盖 Python 操作指南相关问题和智能制造样例问题。
- `python scripts/ai/evidence_coverage_report.py`
- `scripts/check-engineering-docs`
- `git diff --check`

## 后续入口

- Spec: `docs/02-delivery-plans/01-specs/2026-06-12-req-012-rag-retrieval-document-sources.md`
- Plan: `docs/02-delivery-plans/02-plans/2026-06-12-req-012-rag-retrieval-document-sources-plan.md`
- 开发建议按后端证据链、文档级来源 DTO、前端引用 UI、真实样例验收 4 段切片推进。
