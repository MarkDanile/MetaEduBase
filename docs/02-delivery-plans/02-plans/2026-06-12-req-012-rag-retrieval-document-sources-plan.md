# REQ-012 RAG 多路召回与文档级参考来源收口 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-12-req-012-rag-retrieval-document-sources.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-012-rag-retrieval-and-kg-evidence-chain-follow-up.md`

## Scope

本 plan 只处理 `REQ-012`，不实现新的技术栈替换。TD-047 / TD-048 / TD-050 均视为已完成前置依赖。

## Slice 1 — Backend evidence 通道收口

目标：
- 将 chunk keyword / full-text 召回接入 `/ai/chat/evidence`。
- 修复 metadata filter 返回值未使用的问题。

建议实现：
- 在 `AIChatService` 中支持多 chunk retriever，或新增 `CompositeChunkRetriever` / `PgHybridChunkRetriever` 包装 vector + keyword。
- `AIChatService._retrieve()` 必须接住 `metadata_filter.filter(...)` 返回值，并用过滤后的候选构造 `channel_results`。
- 保留降级日志：vector / keyword / graph 任一失败时不拖垮整个回答。

验证：
- 单元测试断言 keyword retriever 被调用并进入 fusion。
- 单元测试断言 metadata filter drop / enrich 后的结果影响 fusion 输入。

## Slice 2 — graph evidence 回源 chunk 与 prompt 打包

目标：
- graph evidence 有 `source_chunk_id` 时，LLM prompt 使用 chunk 原文。
- prompt context 不只给 200 字 snippet，而是在预算内给足够原文证据。

建议实现：
- 对 `knowledge_node` evidence，如果存在 `source_chunk_id`，补查 `document_chunks.content` / `chunk_index` / `section_title`。
- 将补查后的 chunk 原文写入 evidence content 或 prompt context 的 evidence block。
- 增加 prompt budget，例如按文档 / 片段分配最大字符数，避免单个片段撑爆上下文。

验证：
- 单元测试：graph evidence 带 `source_chunk_id` 时，prompt 中能 grep 到 chunk 原文。
- 单元测试：graph evidence 缺 file/chunk 时，不被放入文档级来源。

## Slice 3 — 文档级来源模型

目标：
- 底部参考来源一级为文档，不是 chunk / evidence。

建议实现：
- 新增 `DocumentSource` / `DocumentSourceChunk` DTO。
- 从 fused `EvidenceItem[]` 聚合：
  - `file_id` 分组。
  - `best_score = max(score)`。
  - `channels = union(channels)`。
  - `chunks = 同文档下可定位 chunk 的 evidence`。
  - `evidence_indices = 该文档参与正文引用的 evidence 序号`。
- `/ai/chat/evidence` 返回 `reply`、`sources`、`document_sources`。

验证：
- 聚合测试：同一文件多个 chunk 合并成 1 个 DocumentSource。
- 聚合测试：无 `file_id` evidence 不进入 `document_sources`。

## Slice 4 — Frontend 引用点击与来源 UI

目标：
- `[N]` 点击绑定当前消息 sources。
- 参考来源 UI 改为文档级引用列表。

建议实现：
- 给 assistant message 生成稳定 id，`renderMarkdown` 注入 `data-message-id` 或局部 click handler。
- `openEvidenceFileByIndex` 改为接收当前消息 / sources，而不是读取最新 assistant。
- 新增 `DocumentSourceList` 或重构 `EvidenceCard`：
  - 文档标题作为一级卡片。
  - 展示“来自 N 个片段 / 命中通道 / 最高相关度”。
  - “查看文档”按钮进入文件详情。
  - 展开后显示 chunk snippets，点击片段定位 chunk。
- 无文档归因的证据进入“补充证据 / 来源待细化”区域，或暂不展示。

验证：
- 前端测试：两条 assistant 消息各有 `[1]`，点击第一条不会跳第二条 sources。
- 前端测试：两个 evidence 同 file_id 时，只渲染 1 个文档级来源。
- 前端测试：chunk 点击构造 `/resource/files/:fileId?chunk=:chunkId`。

## Slice 5 — 真实样例验收与状态回填

目标：
- 用真实问题证明回答质量和引用体验改善。

验收样例：
- “Python 的基本数据类型和变量有哪些？”
- “智能制造专业需要哪些技能？”

验收记录：
- sources 数量、document_sources 数量。
- 召回通道命中情况。
- prompt 摘要是否包含真实 chunk 原文。
- 回答是否包含有效 `[N]` 引用。
- 文档级来源是否可点击，片段是否可定位。
- `scripts/ai/evidence_coverage_report.py` 前后变化。

收尾：
- 更新 `current-work.md`、Backlog、Requirement、spec、plan、work-log。
- 如发现独立技术债，按 `TD-xxx` 入账，不在 REQ-012 内顺手扩大范围。

## Suggested Branch / PR Strategy

- `feat/req-012-rag-retrieval-document-sources`
- 如果一次 PR 过大，按 slice 拆小 PR：
  - PR 1: backend retrieval + metadata filter
  - PR 2: document source DTO / aggregation
  - PR 3: frontend引用与文档级来源 UI
  - PR 4: real sample validation + docs closure

## Required Checks

- `pytest tests/contexts/knowledge/test_ai_chat_service.py -q`
- 新增后端测试对应的 pytest 文件。
- `pnpm --filter @metaedu/web lint`
- `pnpm --filter @metaedu/web typecheck`
- 有 PG 环境时运行真实 `/api/v1/ai/chat/evidence` 样例。
- `python scripts/ai/evidence_coverage_report.py`
- `scripts/check-engineering-docs`
- `git diff --check`
