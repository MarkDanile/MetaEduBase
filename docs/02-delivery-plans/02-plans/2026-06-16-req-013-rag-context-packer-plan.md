# REQ-013 RAG Context Packer 与回答 grounding 增强 — Plan

> Spec: `docs/02-delivery-plans/01-specs/2026-06-16-req-013-rag-context-packer.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-013-rag-context-packer-and-grounded-answering.md`

## Scope

本 plan 实现 P2 阶段的 RAG Context Packer。它承接 REQ-012 的多路 evidence 结果，不替代 P2-SEARCH、P2-RRF 或 BUG-007。

建议分支：

```text
feat/req-013-rag-context-packer
```

## Slice 1 — 现状 trace 与失败样例锁定

目标：

- 先证明“Python 基本数据类型”失败时，最终 prompt 里到底是什么。
- 避免直接写 packer 后仍不知道质量是否提升。

建议动作：

- 增加测试级 trace helper 或日志断言，能观察：
  - channel results 数量。
  - fusion 后 evidence 顺序。
  - prompt context 摘要。
  - evidence 的 `file_id` / `chunk_id` / `chunk_index` / `section_title`。
- 用 fixture 构造“目录 chunk 高分 + 正文 chunk 存在”的失败场景。

验收：

- 有测试能复现“只给目录时应判定上下文不足”。
- 有测试能证明后续 packer 会把正文 chunk 带入 prompt。

## Slice 2 — Context Packer 模块与 neighbor expansion

目标：

- 新增独立 packer。
- 命中 chunk 后拉取相邻 chunk，组成连续上下文。

建议动作：

- 新建 `app/contexts/knowledge/application/context_packer.py`。
- 定义 `ContextPackingOptions`、`PackedContext`、`PackedContextBlock`。
- 支持按 `file_id + chunk_index` 批量查邻居 chunk。
- 默认窗口建议先用 `neighbor_window=1`。
- 去重：同一 `file_id + chunk_id` 只进入一次 packed context。

验收：

- 单测：命中 chunk 52 时，packer 拉取 51 / 52 / 53。
- 单测：边界 chunk 0 不请求负 index。
- 单测：重复 evidence 命中同一 chunk 时只出现一次。

## Slice 3 — section fallback 与 graph-to-chunk packing

目标：

- section metadata 可用时聚合同 section。
- graph evidence 回源 chunk 后走同一套 packing。
- section metadata 不可信时不拖垮回答。

建议动作：

- 对 `section_title` / `section_path` 都存在且一致的 chunk，允许在预算内补同 section chunk。
- 对 `knowledge_node` evidence，优先使用 `source_chunk_id` 或 `chunk_id` 回查 chunk。
- 若 `section_path` 为空或异常，只用 chunk_index 邻居。
- 不在本任务修复 BUG-007，但要让 packer 对坏 metadata 有兜底。

验收：

- 单测：graph evidence 带 `source_chunk_id` 时，packed block content 来自 `document_chunks.content`。
- 单测：section_path 为空时仍能通过 chunk_index 邻居扩展。
- 单测：section_path 错乱不会跨文件扩展。

## Slice 4 — TOC guard 与 prompt builder 接入

目标：

- 目录 / 简介 / TOC chunk 不再作为唯一主上下文。
- `AIChatService` 的 prompt 使用 packed context。

建议动作：

- 增加轻量 `is_toc_like_chunk` 规则：
  - 标题或正文含“目录 / Table of Contents”。
  - 大量短行 + 页码样式。
  - 内容主要是章节标题列表且缺少解释性正文。
- 目录 chunk 可以保留 evidence，但 packing 时正文 chunk 优先。
- 修改 `_build_prompt_context` 入参或新增 prompt builder，使其消费 `PackedContext.blocks`。
- 保留现有 `DocumentSource` 聚合。

验收：

- 单测：目录 chunk 分数最高但正文 chunk 存在时，prompt 主体包含正文 chunk。
- 单测：prompt 中不再只出现 `content[:200]`。
- 单测：packed block 超预算时按非目录、score、channels 裁剪。

## Slice 5 — 真实样例验收与数据初始化说明

目标：

- 用真实或接近真实的样例证明回答质量改善。
- 如果数据库数据不满足策略，明确 reinitialize / backfill 方式。

建议动作：

- 有 PG 环境时跑：
  - “python 的基本数据类型有哪些？”
  - “Python 的数据类型和变量怎么理解？”
  - “智能制造专业需要哪些技能？”
- 记录：
  - topN evidence。
  - packed context 摘要。
  - 最终回答是否有用。
  - 文档级来源和 chunk 定位是否正常。
- 如果样例文件 chunk metadata 缺失，记录需要重跑 parse / chunk / embed / index 的文件范围。

验收：

- 真实样例或 fixture 样例能证明 prompt 含正文上下文。
- 若真实 PG 不可用，必须写明环境阻塞，并保留 mock / fixture 行为级测试。

## Files To Inspect First

- `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`
- `packages/server-python/app/contexts/knowledge/application/evidence_fusion.py`
- `packages/server-python/app/contexts/knowledge/domain/evidence.py`
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_vector_retriever.py`
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_keyword_retriever.py`
- `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_graph_retriever.py`
- `packages/server-python/app/shared/parsing/chunker.py`
- `packages/server-python/tests/contexts/knowledge/test_ai_chat_service.py`
- `packages/server-python/tests/e2e/test_p1_rag_evidence_e2e.py`

## Required Checks

- `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/knowledge/test_ai_chat_service.py -q`
- 新增 context packer 测试文件对应的 pytest 命令。
- 若改 AI Chat API 或前端引用 UI：
  - `pnpm --filter @metaedu/web test`
  - `pnpm --filter @metaedu/web lint`
  - `pnpm --filter @metaedu/web typecheck`
- 有 PG 环境时运行真实 `/api/v1/ai/chat/evidence` 样例。
- `scripts/check-engineering-docs`
- `git diff --check`

## Documentation Closure

完成实现后必须同步：

- `docs/01-product-planning/04-backlog.md`：REQ-013 状态。
- `docs/01-product-planning/05-requirements/REQ-013-rag-context-packer-and-grounded-answering.md`：交付记录。
- `docs/01-product-planning/02-milestones/02-growth-phase.md`：P2 open item 状态。
- `docs/03-engineering-governance/current-work.md`：候选 / 进行中 / 最近完成。
- `docs/03-engineering-governance/work-log.md`：一行式索引。

如发现独立缺口：

- 真实 bug：登记 `BUG-xxx`。
- 可维护性或测试债：登记 `TD-xxx`。
- 流程或文档问题：登记 `DOC-xxx`。
