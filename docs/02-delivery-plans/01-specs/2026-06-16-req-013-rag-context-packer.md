# REQ-013 RAG Context Packer 与回答 grounding 增强 — Spec

> Requirement: `docs/01-product-planning/05-requirements/REQ-013-rag-context-packer-and-grounded-answering.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-16-req-013-rag-context-packer-plan.md`
> Milestone: `docs/01-product-planning/02-milestones/02-growth-phase.md`

## Summary

当前 AI Chat 已具备多路 evidence 召回骨架，但真实问题仍可能只把目录 / 简介 / 单条短 snippet 给到 LLM，导致“资料库里有正文，回答却说证据不足”。本 spec 要求在 fusion 之后新增 Context Packer：用小 chunk 做召回，用相邻 chunk / 同 section / 回源 chunk 组装生成上下文，再交给 LLM。

本任务属于 P2 召回质量增强，不引入新搜索引擎或图数据库。

## Current Findings

| 发现 | 证据 | 影响 |
|------|------|------|
| prompt 当前直接使用 `ev.snippet or ev.content` | `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py` | chunk retriever 的 200 字 snippet 会截断正文上下文。 |
| chunk retriever 构造 snippet 为 `content[:200]` | `pg_chunk_vector_retriever.py` / `pg_chunk_keyword_retriever.py` | 即使命中正文 chunk，LLM 也可能只看到片段开头。 |
| graph evidence 已可回源 chunk | `AIChatService._hydrate_graph_chunks` | 方向正确，但仍缺统一 packing 与上下文预算。 |
| chunker 已声明 neighbor expansion / parent-child chunk 延后 | `packages/server-python/app/shared/parsing/chunker.py` | 当前没有“召回小 chunk，生成大上下文”的正式实现。 |
| 真实问题仍出现目录证据不足 | 用户反馈“python 的基本数据类型有哪些？” | 排序和上下文包装尚未达到可用质量。 |

## Goals

- 在 AI Chat 编排中明确 `retrieval -> fusion -> context packing -> prompt -> LLM` 的边界。
- 命中 chunk 后，把相邻 chunk 或同 section 内容组装为可回答上下文。
- graph evidence 回源 chunk 后参与同一套 context packing。
- 降低目录 / 简介 / TOC chunk 对最终 prompt 的伤害。
- 保持现有 `/ai/chat/evidence` 响应契约稳定。
- 为 P2-RRF / reranker / ES / Neo4j 等后续升级保留清晰接口。

## Non-Goals

- 不新增外部搜索或向量基础设施。
- 不重写 `EvidenceItem` / `DocumentSource` 对外 shape。
- 不修改 AI Chat 页面主交互，除非引用预览必须适配 packed context。
- 不用 prompt 诱导 LLM 脱离证据回答。
- 不把 BUG-007 的 PDF section path 问题塞进本任务；本任务只要求 packer 对 section 元数据缺失有 fallback。

## Proposed Design

### 1. Context Packer Boundary

建议新增独立模块，例如：

```text
packages/server-python/app/contexts/knowledge/application/context_packer.py
```

核心接口可保持简单：

```text
ContextPacker.pack(
    fused: list[EvidenceItem],
    tenant_id: str,
    session: AsyncSession,
    options: ContextPackingOptions,
) -> PackedContext
```

`AIChatService.chat()` 中的顺序变为：

```text
retrieve()
-> fusion.fuse()
-> hydrate graph chunks
-> context_packer.pack()
-> build_document_sources()
-> prompt_builder / _build_prompt_context()
-> LLM
```

### 2. Packed Context Model

内部 DTO 可包含：

```text
PackedContext
- blocks: list[PackedContextBlock]
- evidence: list[EvidenceItem]
- diagnostics: dict

PackedContextBlock
- evidence_index
- file_id
- chunk_ids
- source_type
- title
- section_title
- section_path
- content
- channels
- score
```

`blocks[].content` 是给 LLM 的生成上下文；`EvidenceItem[]` 仍是对外引用序列。

### 3. Expansion Strategy

首版优先级：

1. **Direct chunk**：保留命中的 chunk。
2. **Neighbor expansion**：按同一 `file_id` + `chunk_index` 拉取 `index-1 / index / index+1`。
3. **Section expansion**：当 `section_path` 或 `section_title` 稳定时，补同 section 的连续 chunk，受预算约束。
4. **Graph source expansion**：graph evidence 先通过 `source_chunk_id` 回到 chunk，再走同一扩展逻辑。
5. **Fallback**：section 元数据缺失或错乱时，只使用 chunk_index 邻居，避免依赖坏 metadata。

### 4. TOC / Directory Guard

首版不要求训练分类器，但必须有基本保护：

- 识别标题 / 内容中明显的“目录”“Table of Contents”“第 X 章 ... 页码列表”等目录型 chunk。
- 目录型 chunk 可以保留为导航 evidence，但不能作为唯一主上下文。
- 如果高分 evidence 全是目录型 chunk，应尝试同文件正文邻居或更低排名正文 chunk；仍失败时在 diagnostics 记录原因。

### 5. Prompt Building

`_build_prompt_context()` 不应再直接选择 `ev.snippet or ev.content` 作为唯一上下文来源。它应使用 packed blocks，例如：

```text
[1] 来源: chunk | 文件: Python教程.pdf | 章节: 数据类型和变量 | 命中: vector,keyword
...连续上下文...
```

回答仍按 `[1]` / `[2]` 引用 evidence 序列。若多个 packed block 来自同一文档，可继续由 `DocumentSource` 聚合到底部来源。

### 6. Diagnostics

首版至少在日志或测试可访问对象中记录：

- 原始 channel topN 数量。
- fusion 后 evidence 数量。
- packed block 数量。
- 每个 block 的 `file_id`、`chunk_ids`、字符数、是否目录型。
- 是否触发 section fallback。

不要求做前端可视化 trace，但测试必须能断言 packer 行为。

## Acceptance Criteria

- AC-1：存在独立 Context Packer 或等价独立函数，`AIChatService` 的 prompt 上下文来自 packed context。
- AC-2：chunk evidence 的 prompt 内容不再被固定 200 字 snippet 限制；默认能包含命中 chunk 的相邻 chunk。
- AC-3：graph evidence 带 `source_chunk_id` 时，packer 拉取对应 chunk 并可扩展邻居。
- AC-4：section 元数据可用时支持同 section 聚合；不可用时回退 chunk_index 邻居，不抛错。
- AC-5：目录 / TOC chunk 不得作为唯一主上下文；测试覆盖目录 chunk 高分但正文 chunk 存在的场景。
- AC-6：packed context 有预算控制，超预算时按 score / channel / 非目录优先级裁剪。
- AC-7：`DocumentSource` 仍以文档为一级来源，`evidence_indices` 与回答 `[N]` 顺序一致。
- AC-8：真实或 fixture 样例“python 的基本数据类型有哪些？”的最终 prompt 包含正文上下文，不只包含教程目录。
- AC-9：保留证据不足兜底：如果检索和 packing 后仍没有正文证据，回答可拒绝，但 diagnostics 必须能说明原因。
- AC-10：完成后同步 Backlog、Requirement、P2 Milestone、current-work、work-log；如有独立缺口，登记 BUG / TD / REQ，不扩大本 PR。

## Validation

- Backend:
  - 新增 `tests/contexts/knowledge/test_context_packer.py` 或同等测试。
  - 扩展 `tests/contexts/knowledge/test_ai_chat_service.py`，断言 prompt 使用 packed context。
  - 覆盖 graph-to-chunk、neighbor expansion、section fallback、TOC guard、budget 裁剪。
- Integration:
  - 有 PG 环境时对 `/api/v1/ai/chat/evidence` 跑“python 的基本数据类型有哪些？”。
  - 记录各通道 topN、fusion 后 topN、packed context 摘要、最终回答。
  - 如数据缺失，记录需要 reinitialize 的文件和命令，不伪装通过。
- Frontend:
  - 若未改 UI，可只跑现有 AI Chat / evidence 相关测试。
  - 若改引用展示，补对应 frontend test。
- Required:
  - `scripts/check-engineering-docs`
  - `git diff --check`

## Risks

| 风险 | 缓解 |
|------|------|
| context 过长导致 prompt 成本上升 | 设置字符预算、文档数上限、block 数上限。 |
| 坏 section metadata 误扩展 | section 扩展必须有 chunk_index fallback。 |
| 目录 chunk 高分挤掉正文 | TOC guard + 非目录正文优先。 |
| evidence 编号和 packed block 混淆 | `EvidenceItem[]` 仍是引用序列，packed block 只负责 prompt。 |
| 与 P2-RRF 边界重叠 | 本任务只做 packing 和轻量 guard，不重写 fusion 算法。 |
