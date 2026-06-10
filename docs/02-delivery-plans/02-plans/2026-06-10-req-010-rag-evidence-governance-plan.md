# REQ-010 P1 真实 RAG 证据治理与 AI Chat 溯源体验 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan slice-by-slice. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 用户执行偏好：inline（逐个执行），不使用 subagent-driven 模式（见 `~/.claude/memory/user-preferences.md`）。本 plan 保持 inline-friendly：每个 slice 都是一个独立小 PR，agent 在同一个会话里逐个推进即可。

**Goal:** 把 AI Chat 升级为真实 RAG：EvidenceItem 统一证据模型 + retriever adapter 可替换 + chunk / KG / metadata 多源召回 + LLM 上下文以原文为主 + 前端来源可点击跳文件 + 历史数据幂等回填。

**Architecture:**
- 后端：保留 `RecallChannel` Protocol（node-shaped 旧契约）；新增 `EvidenceItem` + `ChunkRetriever` / `GraphRetriever` / `MetadataFilter` / `EvidenceFusion` 4 个 Protocol；P1 用 PostgreSQL adapter 实现；`ai_router` 改注入新接口。
- 前端：升级 `AiChatView` 来源渲染 + 跳转；`FileDetailView` 接受 `?chunk=` 锚点；services 层 DTO 升级到 `EvidenceItem`。
- 工具：3 个 `backfill_*` 管理命令 + `evidence_coverage_report.py` 覆盖率脚本。
- 依赖：国内 LLM（Qwen / DeepSeek）+ DashScope embedding（已就位）。

**Tech Stack:** Python 3.11+ / FastAPI + SQLAlchemy 2 / PostgreSQL + pgvector / tsvector / Alembic / Vue 3 + TypeScript / Tailwind CSS 4 / Vitest。

**Spec:** [`docs/02-delivery-plans/01-specs/2026-06-10-req-010-rag-evidence-governance.md`](../01-specs/2026-06-10-req-010-rag-evidence-governance.md)

**Working dirs:**
- Backend: `packages/server-python`
- Frontend: `packages/web`
- Scripts: `scripts/ai/`

**Branching:**
- 塑形：`feature/req-010-rag-evidence-shaping`（当前）
- 实现：每个 Slice 一个独立分支 `feature/req-010-slice-N-...`；或合并到 `feature/req-010-rag-evidence` 单分支（按 PR 大小决定 — 建议至少 Slice 1-3 同 PR，Slice 4 / 5 / 6 / 7 各自独立 PR，Slice 8 收口 PR）

---

## Slice 0 — 塑形收口（已完成，作为基线）

> 已在 `feature/req-010-rag-evidence-shaping` 完成。

- [x] 写 spec `docs/02-delivery-plans/01-specs/2026-06-10-req-010-rag-evidence-governance.md`
- [x] 写 plan（本文件）
- [x] `current-work.md` 把 REQ-010 从"下一批候选任务"移到"当前进行中"，状态 🟣 Shaping → 🔵 就绪
- [x] user 确认 3 项关键决策（Q1 / Q2 / Q3 + Q4）

## Slice 1 — 证据模型 + 诊断日志

> 目标：定义 `EvidenceItem` + `EvidenceFusion` Protocol + Simple 实现 + 诊断日志。**不**接入 ai_router，只放新代码。
> 范围：仅 backend。**AC 覆盖：AC-3 / AC-6**

**Files:**
- Create: `packages/server-python/app/contexts/knowledge/domain/evidence.py`
- Create: `packages/server-python/app/contexts/knowledge/application/evidence_fusion.py`
- Create: `packages/server-python/tests/contexts/knowledge/test_evidence_model.py`
- Create: `packages/server-python/tests/contexts/knowledge/test_evidence_fusion.py`

- [ ] **Step 1.1 — EvidenceItem dataclass + source_type 枚举**
  - 字段：`evidence_id` / `source_type` (`Literal["chunk","knowledge_node","knowledge_edge","structured_field"]`) / `file_id` / `chunk_id` / `node_id` / `edge_id` / `structured_path` / `title` / `content` / `snippet` / `metadata` (dict) / `score` / `channels` (list[str])
  - `evidence_id` 派生规则：f`{source_type}:{file_id}:{chunk_id or node_id or edge_id or structured_path}"`
  - unit test：`test_evidence_id_is_deterministic`、`test_chunk_evidence_round_trip`

- [ ] **Step 1.2 — EvidenceFusion Protocol + SimpleFrequencyFusion + RRFFusion 占位**
  - `SimpleFrequencyFusion` 沿用现有 `FrequencyFusion` 行为（搬过来即可，不改算法）
  - `RRFFusion` 实现 `1 / (k + rank)` 公式，k=60 默认；标 `(P2)` 注释说明
  - unit test：`test_simple_fusion_dedupes_evidence`、`test_rrf_fusion_ranks_by_aggregate`

- [ ] **Step 1.3 — ai_router 诊断日志字段（不改行为）**
  - 加 `logger.info("ai_chat: query=%r ner=%r candidates=%d fused=%d prompt_chars=%d evidence_ids=%s")`
  - 不打 LLM 完整 prompt；只打摘要（首 200 字符）

- [ ] **Step 1.4 — pytest 全过 + ruff 全过**
  - `cd packages/server-python && pytest tests/contexts/knowledge/test_evidence_model.py tests/contexts/knowledge/test_evidence_fusion.py -v`
  - `cd packages/server-python && ruff check app/contexts/knowledge/ tests/contexts/knowledge/`

## Slice 2 — retriever adapter 接口

> 目标：定义 `ChunkRetriever` / `GraphRetriever` / `MetadataFilter` Protocol + 1 个 fake 实现 + 1 个 PostgreSQL adapter 占位（不接 ai_router）。
> 范围：仅 backend。**AC 覆盖：AC-11**

**Files:**
- Create: `packages/server-python/app/contexts/knowledge/application/retrievers/__init__.py`
- Create: `packages/server-python/app/contexts/knowledge/application/retrievers/chunk_retriever.py`
- Create: `packages/server-python/app/contexts/knowledge/application/retrievers/graph_retriever.py`
- Create: `packages/server-python/app/contexts/knowledge/application/retrievers/metadata_filter.py`
- Create: `packages/server-python/tests/contexts/knowledge/retrievers/test_chunk_retriever_contract.py`
- Create: `packages/server-python/tests/contexts/knowledge/retrievers/test_graph_retriever_contract.py`
- Create: `packages/server-python/tests/contexts/knowledge/retrievers/test_metadata_filter_contract.py`

- [ ] **Step 2.1 — ChunkRetriever Protocol**
  - 方法 `async def retrieve(query, ner_result, tenant_id, session, *, top_k, file_filter=None) -> list[EvidenceItem]`
  - `file_filter` 是可选的 metadata-derived 预过滤；先 list[str] file_ids
  - fake 实现：`FakeChunkRetriever` 接受预设 `return_value`

- [ ] **Step 2.2 — GraphRetriever Protocol**
  - 方法 `async def retrieve(query, ner_result, tenant_id, session, *, top_k) -> list[EvidenceItem]`
  - 要求 P1 实现尽量回填 `source_chunk_id` / `source_file_id`
  - fake 实现：`FakeGraphRetriever`

- [ ] **Step 2.3 — MetadataFilter Protocol**
  - 方法 `async def filter(ner_result, tenant_id, session, *, candidates) -> list[EvidenceItem]`
  - 设计：filter 收 list[EvidenceItem] + 读 `files.doc_type` / `files.tags` / `files.structured_data` 顶层 key，做打分加权或硬过滤
  - fake 实现：`FakeMetadataFilter`

- [ ] **Step 2.4 — 契约测试（sig.parameters 严格对齐，参考 RecallChannel 协议风格）**
  - 同 Slice 0 / TD-030 风格：sig 必须与 Protocol 完全一致
  - fake 实现 + 1 条回归测试

- [ ] **Step 2.5 — pytest 全过 + ruff 全过**

## Slice 3 — chunk 级召回进入 AI Chat

> 目标：`PgChunkVectorRetriever` / `PgChunkKeywordRetriever` / `PgMetadataFilter` 实现；`ai_router` 改注入新接口 + prompt 升级。
> 范围：仅 backend。**AC 覆盖：AC-1 / AC-2 / AC-4 / AC-11**

**Files:**
- Create: `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_vector_retriever.py`
- Create: `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_chunk_keyword_retriever.py`
- Create: `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_metadata_filter.py`
- Create: `packages/server-python/app/contexts/knowledge/infrastructure/retrievers/pg_graph_retriever.py`
- Modify: `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`
- Modify: `packages/server-python/app/contexts/knowledge/application/recall_service.py`（保留旧 RecallChannel 不动）
- Create: `packages/server-python/tests/contexts/knowledge/test_ai_chat_evidence.py`
- Create: `packages/server-python/tests/e2e/test_p1_rag_evidence.py`

- [ ] **Step 3.1 — PgChunkVectorRetriever**
  - SQL：`SELECT c.id, c.file_id, c.chunk_index, c.content, c.section_title, c.section_path, 1 - (c.embedding <=> :vec::vector) AS score FROM metaedu.document_chunks c WHERE c.tenant_id = :tid AND c.embedding IS NOT NULL ORDER BY c.embedding <=> :vec::vector LIMIT :lim`
  - 把每行映射成 `EvidenceItem(source_type="chunk", file_id=row["file_id"], chunk_id=row["id"], content=row["content"], snippet=row["content"][:200], score=..., channels=["vector"], title=row["section_title"] or f"Chunk {chunk_index}", metadata={"section_path": row["section_path"]})`

- [ ] **Step 3.2 — PgChunkKeywordRetriever**
  - 复刻现有 `PgKeywordRecallChannel` 的关键词分词策略；查 `document_chunks.content` + `section_title`
  - 关键差异：返回 `EvidenceItem(source_type="chunk")`

- [ ] **Step 3.3 — PgMetadataFilter**
  - 读 `files.doc_type` / `files.tags` / `files.structured_data` 顶层 key；对 candidate EvidenceItem 的 `file_id` 做 IN 过滤
  - P1：硬过滤（不含匹配 doc_type 的 evidence 直接 drop）；同时把 `doc_type` / `tags` 写入 `metadata` 字段

- [ ] **Step 3.4 — PgGraphRetriever**
  - 沿用现有 `PgVectorRecallChannel` / `PgKeywordRecallChannel`（knowledge_nodes 视角），但返回 `EvidenceItem(source_type="knowledge_node", file_id=node.source_file_id, chunk_id=node.source_chunk_id, ...)`
  - 关键：INSERT 时已写 `source_chunk_id`（Slice 5），所以这里能直接读

- [ ] **Step 3.5 — ai_router 接入新接口**
  - 依赖注入：构造函数接受 `chunk_retriever: ChunkRetriever` / `graph_retriever: GraphRetriever` / `metadata_filter: MetadataFilter` / `evidence_fusion: EvidenceFusion`
  - 默认实例：PostgreSQL adapters
  - 测试可通过 fake 注入
  - prompt 模板升级：
    ```text
    你是 MetaEduBase AI 助手。请基于提供的「参考证据」回答，并按引用编号 [1]、[2] 标注。
    证据来源可能来自原文切片（chunk）、结构化字段或知识节点。
    如果证据不足，请直接说"未找到足够参考来源"，不要编造。

    参考证据：
    [1] 来源: chunk | 文件: {filename} | 章节: {section} | 命中: vector
    {content_snippet}
    [2] 来源: knowledge_node | 节点: {title} | 关联文件: {file_id} | 关联 chunk: {chunk_id}
    {content_snippet}
    ```
  - `ChatResponse.sources` 升级为 `list[EvidenceItem]`；保留 `SourceItem` 字段到下个迭代再删（用 `response_model_exclude_none` 兼容）

- [ ] **Step 3.6 — 测试**
  - unit：`test_ai_chat_returns_chunk_evidence` / `test_ai_chat_prompt_contains_chunk_content` / `test_ai_chat_no_evidence_returns_fallback`
  - fake retriever 验证编排（不依赖 PostgreSQL）
  - e2e：`test_p1_rag_evidence` 跑真实 LLM（如果环境不可用，skip with reason）

- [ ] **Step 3.7 — pytest + ruff + check-engineering-docs 全过**

## Slice 4a — KG 视图迁到 GraphRetriever

> 目标：`KnowledgeBaseView` / `FileDetailView` 节点查询路径迁到 `GraphRetriever` 接口。
> 范围：仅 frontend（按需调整 services.ts）。**AC 覆盖：AC-13**

**Files:**
- Modify: `packages/web/src/services/knowledge.ts`
- Modify: `packages/web/src/views/knowledge/KnowledgeBaseView.vue`（仅当 services 改 API）
- Modify: `packages/web/src/views/resource/queries.ts`（FileDetailView 用）

- [ ] **Step 4a.1 — services.ts 暴露 `retrieveGraphNodes(query, ner_result, top_k)` 调用新接口**
  - 新端点 `POST /api/v1/knowledge/graph/retrieve` 返回 `EvidenceItem[]`
  - 保留 `listNodes` / `listEdges` 旧端点不变

- [ ] **Step 4a.2 — vitest：knowledge 文件夹 test 不退化**

## Slice 4b — MCP 迁到 retriever 接口

> 目标：MCP 工具的 RAG 入口迁到 `ChunkRetriever` / `GraphRetriever` 接口。
> 范围：仅 backend。**AC 覆盖：AC-13**

**Files:**
- Modify: `packages/server-python/app/contexts/.../mcp_*.py`（按实际 MCP 工具路径）
- Create: `tests/mcp/test_rag_retrievers.py`

- [ ] **Step 4b.1 — 找到 MCP 中调用知识图谱 / 文件 chunk 的入口**
  - 用 `codegraph_search` / `codegraph_explore` 定位

- [ ] **Step 4b.2 — 改用新接口**
  - 行为不变；只是依赖注入

- [ ] **Step 4b.3 — 回归测试**
  - 断点验证：`pytest -k "mcp" not failing`

## Slice 5 — KG 抽取按 chunk 切片

> 目标：`extract_knowledge_graph` 改 chunk 切片；每条 entity 写入 `source_chunk_id`。
> 范围：仅 backend。**AC 覆盖：AC-14**

**Files:**
- Modify: `packages/server-python/app/contexts/document/application/tasks/extract_knowledge_graph.py`
- Create: `packages/server-python/tests/contexts/document/test_extract_knowledge_graph_source_chunk.py`

- [ ] **Step 5.1 — 改 chunk 切片**
  - 按 chunk 分组（每组 1 个 chunk 或 2-3 个相邻 chunk），每组单独请求 LLM
  - 抽取 prompt 模板要求 entity 标注所在 chunk_index
  - 限制：单文件总 prompt 长度不变（≤6000 字符）

- [ ] **Step 5.2 — 写 `source_chunk_id`**
  - INSERT `knowledge_nodes` 字段从 `(id, tenant_id, title, description, domain, level, path, source_file_id, created_at, updated_at)` 升级为加 `source_chunk_id`
  - 注意：`knowledge_nodes` 表是否已有 `source_chunk_id` 列？用 codegraph 确认；若没有，新建 Alembic 迁移

- [ ] **Step 5.3 — 删掉"按整段 document 拼 prompt"路径**
  - 行为差异需在 PR 描述中说明

- [ ] **Step 5.4 — 测试**
  - `test_extract_kg_writes_source_chunk_id`：构造 1 个 file + 3 chunk，触发任务，验证 entity 全部有 `source_chunk_id`
  - e2e `test_p1_demo_step4_kg_extract` 仍通过

- [ ] **Step 5.5 — alembic 迁移（如需）**
  - `alembic/versions/YYYYMMDDHHMM_add_knowledge_node_source_chunk_id.py`
  - 含 `node_source_resolution` 字段（VARCHAR(20)，默认 'chunk_resolved'）

## Slice 6 — 历史数据 backfill / reindex

> 目标：3 个 backfill 管理命令 + 1 个覆盖率脚本，全部幂等。
> 范围：仅 backend + scripts。**AC 覆盖：AC-9 / AC-10**

**Files:**
- Create: `packages/server-python/app/contexts/knowledge/application/backfill_node_source_chunk.py`
- Create: `packages/server-python/app/contexts/document/application/backfill_chunk_embedding.py`
- Create: `packages/server-python/app/contexts/document/application/backfill_file_metadata.py`
- Create: `packages/server-python/app/cli/backfill.py`（typer CLI 入口；或放 `scripts/`）
- Create: `scripts/ai/evidence_coverage_report.py`
- Create: `packages/server-python/tests/contexts/knowledge/test_backfill_node_source_chunk.py`
- Create: `packages/server-python/tests/contexts/document/test_backfill_chunk_embedding.py`
- Create: `packages/server-python/tests/contexts/document/test_backfill_file_metadata.py`
- Create: `tests/engineering/test_evidence_coverage_report.py`

- [ ] **Step 6.1 — backfill_knowledge_node_source**
  - SQL：`SELECT id, title, source_file_id FROM metaedu.knowledge_nodes WHERE tenant_id = :tid AND (source_chunk_id IS NULL OR node_source_resolution IS NULL)`
  - 模糊匹配策略：在同一 `source_file_id` 的 `document_chunks.content` 中找包含 `title`（去除常见停用词）的 chunk；按 `chunk_index` 排序取第一个
  - 写 `source_chunk_id` 或保留 `source_file_id` + `node_source_resolution='file_only'`
  - 幂等：用 `WHERE source_chunk_id IS NULL` 限制；输出 scanned / updated / skipped(file_only) / failed

- [ ] **Step 6.2 — backfill_chunk_embedding**
  - SQL：`SELECT id, file_id, content FROM metaedu.document_chunks WHERE tenant_id = :tid AND (embedding IS NULL OR content_tsvector IS NULL)`
  - 调 `get_embedding`（沿用 `app.contexts.knowledge.application.embedding_service`）
  - 写 `embedding` + `content_tsvector`（用 `to_tsvector('simple', content)`）
  - 幂等：分批 + 写后用 SELECT 校验
  - 输出 scanned / updated / skipped(已存在) / failed

- [ ] **Step 6.3 — backfill_file_metadata**
  - SQL：`SELECT id, filename, file_type, doc_type, tags, structured_data FROM metaedu.files WHERE tenant_id = :tid AND (doc_type IS NULL OR cardinality(tags) = 0 OR structured_data IS NULL)`
  - 启发式：`file_type=pdf → doc_type='document'`；`file_type=md → doc_type='document'`
  - 不擅自动 `structured_data`（可能损业务字段）；只补 `doc_type` + `tags`
  - 幂等：跳过已有非空值的记录

- [ ] **Step 6.4 — CLI 入口**
  - `python -m app.cli.backfill node-source-chunk --tenant <id>` 等
  - 每个命令 dry-run 模式

- [ ] **Step 6.5 — evidence_coverage_report.py**
  - 4 个指标：node→chunk / chunk embedding / chunk tsvector / file metadata
  - 输出 markdown 表 + JSON；CI 可读

- [ ] **Step 6.6 — 幂等性测试（AC-10）**
  - 每个 backfill 命令连续执行 2 次，第 2 次的 `updated` 应为 0
  - 数据库不增长

## Slice 7 — AI Chat 前端溯源体验

> 目标：`AiChatView` [1] 点击 + 来源卡片 + 无证据 banner + `FileDetailView` chunk 锚点。
> 范围：仅 frontend。**AC 覆盖：AC-5 / AC-6 / AC-15**

**Files:**
- Modify: `packages/web/src/services/api.ts`（chat DTO 升级到 EvidenceItem）
- Create: `packages/web/src/types/evidence.ts`
- Modify: `packages/web/src/views/ai-chat/AiChatView.vue`
- Create: `packages/web/src/components/EvidenceCard.vue`
- Create: `packages/web/src/components/EvidenceRefLink.vue`
- Modify: `packages/web/src/views/resource/FileDetailView.vue`
- Create: `packages/web/src/views/resource/__tests__/FileDetailView.chunkAnchor.spec.ts`

- [ ] **Step 7.1 — types/evidence.ts + services DTO 升级**
  - `EvidenceItem` 类型与后端 pydantic 对齐
  - 旧 `SourceItem` 保留到下个迭代再删

- [ ] **Step 7.2 — `renderMarkdown` 自定义 reference 规则**
  - 把 `[1]` / `[2]` 渲染成可点击 link，href = `/resource/files/${fileId}?chunk=${chunkId}`（仅当 sources 存在匹配 id）
  - 用 unit test 覆盖

- [ ] **Step 7.3 — EvidenceCard.vue**
  - 字段：title / channel tag / score / file name + chunk_index / "查看源文件"按钮
  - 折叠 / 展开

- [ ] **Step 7.4 — EvidenceRefLink.vue**
  - 渲染 `[1]` 为 chip，点击跳文件详情

- [ ] **Step 7.5 — AiChatView.vue 升级**
  - 替换"参考知识源" chip 区 → EvidenceCard 列表
  - 加"无证据 banner"

- [ ] **Step 7.6 — FileDetailView `?chunk=` 锚点**
  - 监听 route.query.chunk
  - 自动滚到 `chunk-{id}` 行 + 高亮 3s（用 setTimeout 清除）
  - chunk 行加 `id="chunk-{id}"`

- [ ] **Step 7.7 — vitest 覆盖**
  - `AiChatView` evidence 渲染 / 无证据 banner
  - `FileDetailView` chunk 滚动 + 高亮
  - `renderMarkdown` `[1]` 改写

- [ ] **Step 7.8 — `vue-tsc --noEmit` + `npm run test:unit` + lint**

## Slice 8 — 真实样例验收 + 收口

> 目标：用智能制造专业样例验证问答质量；e2e 回归；状态回填。
> 范围：跨 backend + frontend + docs。**AC 覆盖：AC-1 / AC-4 / AC-8**

**Files:**
- Create: `packages/server-python/tests/e2e/test_p1_rag_evidence_e2e.py`
- Create: `packages/web/playwright/ai-chat-evidence.spec.ts`（如启用 Playwright）
- Modify: `docs/03-engineering-governance/current-work.md`
- Modify: `docs/03-engineering-governance/work-log.md`
- Modify: `docs/03-engineering-governance/technical-debt.md`（如有 follow-up）
- Modify: `docs/01-product-planning/04-backlog.md`
- Modify: `docs/01-product-planning/02-milestones/01-validation-phase.md`

- [ ] **Step 8.1 — e2e：智能制造样例**
  - 用 `tests/e2e/fixtures/manufacturing_*.md`（或新建 fixture）
  - 触发：上传 → 抽取 → chat "智能制造专业需要哪些技能？"
  - 断言：sources 含至少 1 条 chunk 证据；prompt 含 chunk content；LLM 回答含 [1] 引用

- [ ] **Step 8.2 — 回填报告（AC-9）**
  - 跑 3 个 backfill + coverage_report
  - 把覆盖率数字写入 `work-log.md`（作为 P1 RAG 证据链路基线）

- [ ] **Step 8.3 — 状态收口**
  - `current-work.md` 状态 → 🟢 完成
  - `work-log.md` 加 1 行（REQ-010）
  - `backlog.md` / `validation-phase.md` 状态同步
  - `technical-debt.md` 登记 follow-up（若有）：chunk 切分粒度 / RRF 调优 / KG 抽取并行 / chunk 锚点 UX 等

- [ ] **Step 8.4 — 完整 Git 闭环**
  - 按 `git-workflow.md`：commit → push → PR → squash merge → 合并后收口
  - 走 `verification-before-completion` skill 验证

---

## 验证矩阵（按 Slice 对照）

| Slice | pytest | ruff | vue-tsc | vitest | e2e | check-engineering-docs | PR size |
|-------|--------|------|---------|--------|-----|------------------------|---------|
| 1 | ✓ | ✓ | — | — | — | ✓ | 小 |
| 2 | ✓ | ✓ | — | — | — | ✓ | 小 |
| 3 | ✓ | ✓ | — | — | ✓ | ✓ | 中 |
| 4a | — | — | ✓ | ✓ | — | ✓ | 小 |
| 4b | ✓ | ✓ | — | — | — | ✓ | 小 |
| 5 | ✓ | ✓ | — | — | ✓ | ✓ | 中（含 alembic） |
| 6 | ✓ | ✓ | — | — | — | ✓ | 中 |
| 7 | — | — | ✓ | ✓ | — | ✓ | 中 |
| 8 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 小（收口） |

## Follow-up（预估，可能在 Slice 8 后登记）

- **FU-A**：chunk 切分粒度不适配问答（500 字偏长 / 偏短）— 登记 TD-xxx，单独 PR
- **FU-B**：`RRFFusion` 调优（k 值 / 通道权重）— 登记 TD-xxx
- **FU-C**：KG 抽取按 chunk 切片后调用次数上升，做 Celery 批量 / 并行优化 — 登记 TD-xxx
- **FU-D**：`source_chunk_id` 模糊匹配的 "file_only" 节点后续人工细化流程 — 登记 OPS-xxx 或文档
- **FU-E**：`SourceItem` 旧字段下个迭代删除（等 MCP / 第三方消费方稳定后再删）

## 完成门禁（按 quality-gates.md）

每次 PR 提交前：
1. `cd packages/server-python && pytest -q` 全部通过
2. `cd packages/server-python && ruff check .` 无 error
3. `cd packages/web && vue-tsc --noEmit && npm run test:unit` 全部通过
4. `scripts/check-engineering-docs` 退出码 0
5. PR 描述包含 Summary / Scope / Validation / Risks / Docs
