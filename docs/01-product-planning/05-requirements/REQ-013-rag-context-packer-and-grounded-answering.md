# REQ-013: RAG Context Packer 与回答 grounding 增强

Status: 🟢 Done (PR #305 merged)
Priority: P1
Milestone: P2
Parent: REQ-012
Related: P2-SEARCH / P2-RRF / BUG-007 / TD-054
External:

## Delivery Record

| Date | What | Details |
|------|------|---------|
| 2026-06-16 | Slice 1-4 | PR #305 open：新增 `context_packer.py`（ContextPacker / PackedContext / PackedContextBlock / ContextPackingOptions / is_toc_like_chunk）；`AIChatService` 集成；ChunkRepository 扩展；17 mock tests 100% pass。Slice 5 真实 PG 样例待 backfill。 |

## Problem

REQ-012 已把 AI Chat 从旧的知识点回答路径推进到 evidence-aware RAG：chunk vector、chunk keyword、graph evidence、document sources 和引用 UI 已具备基础形态。但真实问答仍暴露一个关键质量缺口：

> 用户问“python 的基本数据类型有哪些？”时，系统回答“未找到足够参考来源”，理由是提供的证据只包含教程目录和简介，没有列出具体数据类型。

这说明当前问题不只是“有没有召回通道”，而是“召回命中后，是否把足够、连续、可回答的原文上下文交给 LLM”。行业实践通常把召回单位和生成单位分开：小 chunk 用于精准召回，回答前再扩展到相邻 chunk、父章节或同一 section 的连续上下文。

## Users / Scenarios

- 学生在 AI Chat 中基于已上传教材、教程或课程文件提问，希望得到可引用、可追溯的答案。
- 教师上传课程材料后，用 AI Chat 快速验证知识点问答效果。
- 后续 APP-001 / APP-002 / APP-003 / APP-004 依赖同一套 RAG grounding 能力，不能让智能体只拿孤立知识点或目录回答。

核心样例：

- “python 的基本数据类型有哪些？”
- “Python 的数据类型和变量怎么理解？”
- “智能制造专业需要哪些技能？”

## Scope

### Backend

- 在 `AIChatService` 的 fusion 之后、prompt builder 之前新增 Context Packer 层。
- 命中 chunk 后，按 `file_id + chunk_index` 回扩相邻 chunk，默认至少支持 `hit-1 / hit / hit+1`。
- 当 `section_title` / `section_path` 可用时，优先支持同 section 的上下文聚合；当 section 元数据缺失或不可信时，回退到 chunk_index 邻居扩展。
- graph evidence 有 `source_chunk_id` 时，先回源 chunk，再参与 context packing；图谱只做召回线索和关系增强，不替代原文上下文。
- prompt context 使用 packed context，不再直接以 `EvidenceItem.snippet` 作为主要生成上下文。
- 增加目录 / 简介 / TOC 类 chunk 的降权或非主证据策略，避免目录片段压过正文片段。
- 保留 `EvidenceItem[]` 和 `DocumentSource[]` 外部契约；如需新增内部 DTO，应只用于 prompt packing 和测试。

### Data / Initialization

- 本需求不强制新增表结构。
- 若实现依赖 `section_title`、`section_path`、`char_start`、`char_end` 的质量，应记录当前数据质量结论。
- 如果发现已有数据不满足新策略，应提供选择性重建 / reinitialize 指引，优先针对 Python 操作指南等样例文件重跑，而不是默认全量重建。

### Frontend

- 本需求主要是后端 RAG 质量增强。
- 前端只在必要时调整证据预览展示，确保引用仍能点开文档来源和命中片段。

## Non-Goals

- 不引入 Elasticsearch、OpenSearch、Milvus、Qdrant、Neo4j 或完整 GraphRAG 框架。
- 不替代 P2-SEARCH 的 PostgreSQL tsvector / 中文分词增强。
- 不替代 P2-RRF 的融合排序升级；本需求可为 RRF 留接口，但默认先实现 Context Packer。
- 不重写文档解析、chunker 或 KG 抽取全链路；发现独立问题时登记 BUG / TD。
- 不把 AI Chat 改造成 agent 编排。

## Acceptance

- AC-1：新增 Context Packer 或等价模块，位置在 retrieval / fusion 之后、prompt builder / LLM 调用之前。
- AC-2：命中 chunk 后，prompt 中可包含相邻 chunk 或同 section 的连续上下文；不能只给单条 `snippet[:200]`。
- AC-3：graph evidence 带 `source_chunk_id` 时，参与 packing 的内容优先来自对应 `document_chunks.content`。
- AC-4：目录 / 简介 / TOC 类 chunk 不得作为唯一主证据导致回答退化；若只命中目录，应继续尝试正文扩展或明确记录检索失败原因。
- AC-5：`DocumentSource` 仍按文档聚合，回答引用 `[N]` 与 packed context 的来源映射不越界、不漂移。
- AC-6：真实或 fixture 样例“python 的基本数据类型有哪些？”应能把“数据类型和变量”正文上下文送入 prompt，并生成有用回答；若当前数据库没有相关正文，必须在验收记录中明确数据缺口。
- AC-7：保留“证据不足不编造”的系统原则；质量增强的目标是提供更充分证据，不是让 LLM 无依据自由发挥。
- AC-8：新增单元测试覆盖 neighbor expansion、section expansion fallback、TOC 降权、graph-to-chunk packing、token budget 裁剪。
- AC-9：有 PG 环境时补真实链路验证：记录各通道 topN、fusion 后 topN、packed context 摘要和最终回答质量。
- AC-10：文档回填同步 Backlog、P2 里程碑、current-work、Requirement、Spec、Plan；如产生独立 follow-up，按 REQ / BUG / TD 分流。

## Open Questions

- 首版默认邻居窗口用 `±1` 还是 `±2`？建议先 `±1`，由 token budget 控制继续扩展。
- prompt 最大上下文预算用字符数还是 token 估算？建议先字符数常量，后续可替换 token estimator。
- TOC / 目录 chunk 的识别规则放在 packer 还是 retriever ranking？建议 packer 先做保护，P2-RRF 再统一排名策略。

## Delivery Links

- Spec: `docs/02-delivery-plans/01-specs/2026-06-16-req-013-rag-context-packer.md`
- Plan: `docs/02-delivery-plans/02-plans/2026-06-16-req-013-rag-context-packer-plan.md`
- Backlog: `docs/01-product-planning/04-backlog.md`
- Milestone: `docs/01-product-planning/02-milestones/02-growth-phase.md`
- Current Work: `docs/03-engineering-governance/current-work.md`
