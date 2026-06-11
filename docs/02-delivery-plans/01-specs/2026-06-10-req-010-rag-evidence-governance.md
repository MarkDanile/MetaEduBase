# REQ-010 P1 真实 RAG 证据治理与 AI Chat 溯源体验 — Spec

> Spec 入口：REQ-010（需求塑形 2026-06-10）。本文件是验收口径与边界的事实源；实施拆分见 [`2026-06-10-req-010-rag-evidence-governance-plan.md`](../02-plans/2026-06-10-req-010-rag-evidence-governance-plan.md)。
> 需求正文：[`docs/01-product-planning/05-requirements/REQ-010-p1-rag-evidence-governance.md`](../../01-product-planning/05-requirements/REQ-010-p1-rag-evidence-governance.md)

## 目标

把 AI Chat 问答从"知识点标题扩写"升级为"基于原文切片 + 结构化字段 + 可追溯知识关系"的真实 RAG 回答：

- 召回统一到 `EvidenceItem`，可按 `file_id` / `chunk_id` / `node_id` / `structured_path` 排序与溯源。
- LLM prompt 上下文以 `document_chunks.content` 为主证据，节点标题 / 描述降级为补充。
- 前端回答中的 `[1]` / `[2]` 引用能跳到具体文件 + chunk 锚点。
- 接口与基础设施解耦：P1 PostgreSQL + pgvector / tsvector / SQL 知识图谱；P2 / P3 可替换为 Milvus / Qdrant / Elasticsearch / Neo4j / GraphRAG 而不改 AI Chat 业务编排。
- 历史数据可一次性回填，覆盖 `node→chunk` 关联、chunk embedding / tsvector、metadata 可用率。

## 决策记录（2026-06-10 塑形澄清）

> 用户在 REQ-010 塑形阶段确认 3 项关键决策；后续 spec / plan 不得偏离。

- **Q1 — node→chunk 关联治理走法**：
  KG 抽取按 chunk 切片（推荐）。`extract_knowledge_graph` 改为"先扫 chunk，按 chunk 分组请求 LLM"，保证每条 entity 都能挂上 `source_chunk_id`；历史数据回填阶段对存量 node 做"同名 + 同一文件 + 最近 chunk"模糊匹配。
- **Q2 — 前端来源跳转目标**：
  跳文件详情页 + chunk 锚点（推荐）。新建路由 `/resource/files/:fileId?chunk=:chunkId`，`FileDetailView` 监听 query 自动滚到对应 chunk 并高亮 3s。
- **Q3 — P1 adapter 抽象边界**：
  同步约束 MCP / KG 视图（接口 + 业务代码同步迁）。P1 期间把 MCP / 知识图谱展示 / AI Chat 三处 RAG 消费方统一迁到 `ChunkRetriever` / `GraphRetriever` / `MetadataFilter` / `EvidenceFusion` 接口。`FrequencyFusion` 改为接口实现 `SimpleFrequencyFusion`（保持现状），同时新增 `RRFFusion` 占位实现。
- **Q4 — 「同步约束 MCP / KG 视图」落地范围**：
  接口 + 业务代码同步迁。但限制为：MCP / KG 视图只迁检索路径（replacement 完成），不重写其展示 / 工具层；新接口与现状行为对齐（保持简单 SQL + 节点回放），后续 P2 / P3 替换基础设施时再统一升级 adapter。

> 另外 4 个待澄清项已从需求正文与代码现状推导完成，不需要再次询问：
> - **P1 样例文档**：以"智能制造专业需要哪些技能？"相关课程资料作为首个验收样例（与 AiChatView quickQuestions 第 3 题一致）。
> - **structured_data 召回优先级**：同时支持（a）作为 metadata filter 缩小候选范围；（b）作为结构化证据进入 prompt 上下文。P1 同时落 a 和 b；b 走"非空 template 字段 + matched_type 路径"。
> - **问答 trace 记录**：AI Chat 端点增加 `x-request-id` 日志字段，记录 query / NER / 候选数 / 融合结果 / 候选 ids / 最终 prompt 摘要；不单独建 trace 表，避免越界。
> - **无法定位 chunk 的历史 node**：允许只回填到 `source_file_id`，并标记 `node_source_resolution = "file_only"` 后续人工细化。

## 范围

### 包含 — Backend

- **证据模型**：
  - 新建 `EvidenceItem`（pydantic BaseModel）：`evidence_id` / `source_type` (`chunk` / `knowledge_node` / `knowledge_edge` / `structured_field`) / `file_id` / `chunk_id` / `node_id` / `edge_id` / `structured_path` / `title` / `content` / `snippet` / `metadata` (dict) / `score` / `channels` (list[str]) / `source_chunk_id` (uuid.UUID | None, 默认 None; 仅 `source_type=="knowledge_node"` 时与 `chunk_id` 同值, 其余 source_type 必须 None; 不参与 `evidence_id` 派生; 详见 §3.1 末尾「AC-3 解读说明」)。
  - 新建 `EvidenceFusion` Protocol + `SimpleFrequencyFusion` 实现 + `RRFFusion` 占位实现。
  - 现有 `RecallResult` / `RecallChannel` 保留为"knowledge node-shaped" 旧契约；新增 `ChunkRecallChannel` / `KeywordChunkRecallChannel` / `MetadataFileRecallChannel` 三个 PostgreSQL adapter；adapter 内部把 chunk / metadata 命中映射成 `EvidenceItem`。`RecallResult` 内部扩展 `source_file_id` / `source_chunk_id` 字段（与 `EvidenceItem` 字段一一对应；`RecallChannel` Protocol 形参不变）。
- **retriever 抽象**：
  - 新建 `ChunkRetriever` Protocol：P1 由 `PgChunkVectorRetriever` / `PgChunkKeywordRetriever` 实现。
  - 新建 `GraphRetriever` Protocol：P1 由 `PgGraphRetriever` 实现，节点结果尽量回填 `source_chunk_id` / `source_file_id`。
  - 新建 `MetadataFilter` Protocol：P1 由 `PgMetadataFilter` 实现，读 `files.doc_type` / `files.tags` / `files.structured_data` 顶层 key。
  - `ai_router` 改为依赖接口 + 注入 PostgreSQL adapter（默认）；测试可通过 fake retriever 验证编排。
- **AI Chat 编排层升级**：
  - `ai_router` prompt 上下文从"知识节点 title/description"升级为"EvidenceItem 列表"，每条至少包含 `file_id` / `chunk_id` / `content` 片段 / 命中通道。
  - LLM prompt 模板要求引用编号 `[1]` / `[2]` 对应 evidence 顺序。
  - `ChatResponse.sources` 升级为 `EvidenceItem[]`（保留旧字段到 deprecation period）。
  - 新增诊断日志：query / NER / 候选数 / 融合结果 / 候选 ids / prompt 摘要。
- **KG 抽取按 chunk 切片**：
  - `extract_knowledge_graph` 改为"按 chunk 分组请求 LLM"，每条 entity 写入时同时记录 `source_chunk_id`（来自本组 chunk）和 `source_file_id`。
  - 抽取 prompt 模板要求 entity 标注所在 chunk_index。
  - 删除"按整段 document 拼 prompt"路径。
- **node→chunk 回填任务**：
  - 新建 `backfill_knowledge_node_source` 管理命令：扫描历史 `knowledge_nodes` 缺 `source_chunk_id` 的记录，按"name + 同一 source_file_id + chunk 内容关键词子串"模糊匹配；无法确定的标记 `node_source_resolution = "file_only"`。
  - 新建 `backfill_chunk_embedding` 管理命令：扫描 `document_chunks` 缺 `embedding` / `content_tsvector` 的记录，补齐 + 输出覆盖率统计。
  - 新建 `backfill_file_metadata` 管理命令：扫描 `files` 缺 `doc_type` / `tags` / `structured_data` 的记录，按 file_type + filename 启发式补 `doc_type`；统计 metadata 可用率。
  - 3 个命令必须幂等（重复执行不产生重复节点 / 边 / 来源记录），并输出 `scanned / updated / skipped / failed` 统计。
- **adapter 迁移 — MCP**：
  - 找到 MCP 当前对知识 / 文件的检索入口，迁到 `ChunkRetriever` / `GraphRetriever` 接口；行为保持现状（先保证接口稳定）。
- **adapter 迁移 — KG 视图**：
  - `KnowledgeBaseView` / `FileDetailView` 中"按文件查节点 / 边"路径迁到 `GraphRetriever` 接口。

### 包含 — Frontend

- **AI Chat 回答渲染**：
  - 回答 markdown 中的 `[1]` / `[2]` 渲染为可点击引用编号，hover 弹出对应 evidence 摘要，点击跳 `/resource/files/:fileId?chunk=:chunkId`。
  - 回答下方"参考来源"列表升级为多行卡片：标题 / 通道标签 / 分数 / 文件名 + chunk_index / "查看源文件"按钮。
  - 同一文件多个 chunk 合并展示（折叠），可展开查看具体片段。
  - 当无可靠证据时，UI 顶部显示 banner "参考资料不足，本次回答未引用证据"；sources 为空时 LLM 兜底文案必须显式说明。
- **FileDetailView chunk 锚点**：
  - 监听 `route.query.chunk`，自动滚到对应 chunk 行 + 高亮 3s（不要无限常亮）。
  - chunk 行 ID 规则 `chunk-{chunkId}`。
- **adapter 无关的 DTO 变化**：
  - 前端 services 层的 chat DTO 升级 `sources` 字段类型到 `EvidenceItem[]`；保留旧字段到下个迭代再删。

### 包含 — 数据初始化 / 回填

- 见上文 3 个 `backfill_*` 管理命令。
- 验证脚本 `scripts/ai/evidence_coverage_report.py`：输出 `node_source_chunk` / `chunk_embedding` / `chunk_tsvector` / `file_metadata` 覆盖率。

### AC-3 解读说明（TD-050 收口时同步）

> 本节由 TD-050 spec [§3.1](../01-specs/2026-06-11-td-050-evidence-item-source-chunk-id-pass-through.md) 引出；本 spec L40 字段清单已按本节规则更新。

- `EvidenceItem.source_chunk_id` 字段仅在 `source_type == "knowledge_node"` 时填充（与 `chunk_id` 同值；`chunk_id` 字段承载该 node 的 `knowledge_nodes.source_chunk_id` 引用，详见 plan Step 3.1）。
- `source_type == "chunk"` / `"knowledge_edge"` / `"structured_field"` 时 `source_chunk_id` **必须**为 `None`（不与"该 evidence 指向原文切片"的语义混淆）。
- `source_chunk_id` **不**参与 `evidence_id` 派生（`_derive_evidence_id` 不引用 `source_chunk_id`；避免同一 chunk 被多条 `knowledge_node` 共享时 `evidence_id` 冲突）。
- 与 `RecallResult.source_chunk_id` 字段一一对应：`RecallResult` 内部加 `source_file_id` / `source_chunk_id` 字段（`source_file_id` **不**进 `EvidenceItem` model，仅在 `RecallResult` 与 `PgGraphRetriever` 内部用，最终写入 `EvidenceItem.file_id`）。
- `evidence_id` 派生规则（4 类 `source_type`）保持稳定；`source_chunk_id` 是"附加溯源"信息，不影响 `evidence_id` 唯一性。
- P2 / P3 升级到 Neo4j / GraphRAG 时复用本节规则；`source_chunk_id` 字段名是稳定契约（详见 TD-050 spec §3.2 / §4 路线 A2 理由）。

### 不包含

- 不强制引入 Elasticsearch、Milvus / Qdrant、Neo4j、GraphRAG 框架；只在接口层留出替换点。
- 不重写整个文档处理流水线；`extract_knowledge_graph` 改 chunk 切片是 P1 范围。
- 不把 AI Chat 做成多智能体编排。
- 不重写 MCP 工具层 / 知识图谱展示层 UI；只迁检索路径到新接口。
- 不引入新的 trace 持久化表 / 服务；只用结构化日志。
- 不替换 LLM provider；evidence 模型升级不动 chat 协议。

## 验收标准

> AC 编号与 REQ-010 需求正文 AC 编号一一对应；以下为可执行验收口径。

- **AC-1**：给定真实文档样例（智能制造专业课程材料），`POST /api/v1/ai/chat` 的 `sources` 至少包含 1 条 `source_type=chunk` 的 `EvidenceItem`。
- **AC-2**：LLM prompt 上下文拼接后能 grep 到至少 1 条 `document_chunks.content` 文本（≥80 字符）；不再只拼 `knowledge_nodes.title` / `description`。
- **AC-3**：`EvidenceItem` 返回字段包含 `file_id` / `chunk_id`（chunk 类型）或 `node_id` + `source_chunk_id`（node 类型）；老 `SourceItem` 字段保留到 deprecation period。
- **AC-4**：回答正文中 `[1]` / `[2]` 引用编号与 `sources` 列表顺序一一对应。
- **AC-5**：`AiChatView` 渲染"参考来源"列表 + 点击跳文件详情；`FileDetailView` 收到 `?chunk=` 自动滚到对应 chunk 并高亮 3s。
- **AC-6**：当候选为空或全部 score < 阈值（0.3）时，回答明确写"未找到足够参考来源"，UI banner 显示对应提示。
- **AC-7**：测试覆盖（每条独立 pytest 用例）：
  - chunk vector recall
  - chunk keyword recall
  - node-to-chunk 追溯（fuzzy 匹配）
  - 融合排序后 sources shape
  - `RRFFusion` 占位实现
  - 3 个 `backfill_*` 命令的幂等性
- **AC-8**：`docs/01-product-planning/01-roadmap.md` / `04-backlog.md` / `02-milestones/01-validation-phase.md` / `current-work.md` / `work-log.md` / `technical-debt.md` 状态一致；新增 follow-up（若有）登记。
- **AC-9**：`scripts/ai/evidence_coverage_report.py` 输出 node→chunk / chunk embedding / chunk tsvector / file metadata 覆盖率；3 个回填命令各输出 scanned / updated / skipped / failed 统计。
- **AC-10**：3 个回填命令重复执行不产生重复节点 / 边 / evidence 来源。
- **AC-11**：`ai_router` 依赖注入 `ChunkRetriever` / `GraphRetriever` / `MetadataFilter` / `EvidenceFusion` 抽象；测试可通过 fake 实现验证编排（不依赖 PostgreSQL / pgvector / tsvector / 图谱 SQL）。
- **AC-12**：spec / plan 显式说明 P1 PostgreSQL adapter 与 P2 / P3 替换边界（Neo4j / Milvus / Qdrant / Elasticsearch）。
- **AC-13**（Q3 / Q4 衍生）：MCP RAG 消费入口 + `KnowledgeBaseView` 节点查询路径已迁到 `ChunkRetriever` / `GraphRetriever` 接口；现有行为不变（断点验证：`pytest -k "mcp_rag" not failing"` + `npm run test:unit -- -t "knowledge"`）。
- **AC-14**（Q1 衍生）：`extract_knowledge_graph` 改 chunk 切片后，e2e `test_p1_demo` 仍通过；新写一条 `test_extract_kg_writes_source_chunk_id` 验证每条 entity 都有 `source_chunk_id`。
- **AC-15**（Q2 衍生）：`FileDetailView` 新增 `?chunk=` query 处理；新写一条 `vitest` 覆盖 chunk 滚动 + 高亮。

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| P1 直接引入 chunk 召回会拉大 LLM 上下文，token 成本上升 | `context_window` 限制；`Snippet` 只取前 200 字符给 LLM，原始 `content` 给 sources |
| chunk 切分粒度不适配问答（500 字偏长 / 偏短） | P1 沿用现有 chunk 切分；不顺带改 chunker；如出现证据缺失问题登记为 follow-up |
| KG 抽取按 chunk 切片后调用次数上升（每个 chunk 一次 LLM 调用） | 复用现有 `extract_knowledge_graph` 任务；后续按 CELERY 并行 / batch 优化登记为 follow-up |
| 同步迁 MCP / KG 视图会放大 PR 范围 | 拆分为 Spec + Plan 中的独立 slice（Slice 4 拆为 4a 知识图谱展示 + 4b MCP），每个独立 PR；AC-13 验证只在检索路径层面 |
| 历史数据回填产生重复节点 / 边 | 3 个 backfill 命令都用 `INSERT ... ON CONFLICT DO NOTHING` 或先 SELECT 校验；AC-10 覆盖 |
| `source_chunk_id` 模糊匹配可能错配 | 记录 `node_source_resolution` 字段；"file_only" 状态对外可查，UI 显式标"来源待细化" |
| Frontend `v-html` 渲染 markdown 时把 `[1]` 改坏 | 用 marked tokenizer 自定义 link / reference rule；用 unit test 覆盖 |

## 与既有事实源的对齐

- `docs/03-engineering-governance/01-rules/contracts.md`：P1 不动 RAG 入口的 OpenAPI schema（保留 `SourceItem` 字段到 deprecation），但内部 DTO 升级；下一迭代再删旧字段。
- `docs/03-engineering-governance/01-rules/architecture.md`：adapter 边界新增 `ChunkRetriever` / `GraphRetriever` / `MetadataFilter` / `EvidenceFusion` 4 个接口；不修改 `RecallChannel` Protocol（保留 node-shaped 旧契约）。
- `docs/03-engineering-governance/01-rules/testing.md`：新增 ≥ 6 条 backend pytest + 1 条 vitest + 1 条 e2e 回归。
- `docs/03-engineering-governance/01-rules/quality-gates.md`：完整门禁 + ruff + vue-tsc + check-engineering-docs。
- `docs/03-engineering-governance/01-rules/git-workflow.md`：开发在 `feature/req-010-rag-evidence-shaping` / 实现时切到 `feature/req-010-rag-evidence` 分支；PR 描述必须包含 Summary / Scope / Validation / Risks / Docs。
- `docs/03-engineering-governance/01-rules/data-integrity.md`：3 个 backfill 命令必须幂等；输出统计；不绕过 `tenant_id` 隔离。
- `docs/03-engineering-governance/01-rules/security.md`：MCP / KG 视图迁移不绕过认证；`get_current_user` 保留。

## 切片汇总（plan 详细拆分见 plan 文件）

| Slice | 名称 | 主要产物 | 关联 AC |
|-------|------|----------|---------|
| Slice 1 | 证据模型 + 诊断日志 | `EvidenceItem` / `EvidenceFusion` Protocol + Simple 实现 / 日志字段 | AC-3 / AC-6 |
| Slice 2 | retriever adapter 接口 | `ChunkRetriever` / `GraphRetriever` / `MetadataFilter` Protocol + fake 实现 + 测试 | AC-11 |
| Slice 3 | chunk 级召回进入 AI Chat | `PgChunkVectorRetriever` / `PgChunkKeywordRetriever` / `PgMetadataFilter` 接入 `ai_router` + prompt 升级 | AC-1 / AC-2 / AC-4 |
| Slice 4a | KG 视图迁到 GraphRetriever | `KnowledgeBaseView` / `FileDetailView` 检索路径迁移 | AC-13 |
| Slice 4b | MCP 迁到 retriever 接口 | MCP RAG 入口迁移 | AC-13 |
| Slice 5 | KG 抽取按 chunk 切片 | `extract_knowledge_graph` 改 chunk 切片 + `source_chunk_id` 写入 | AC-14 |
| Slice 6 | 历史数据 backfill / reindex | 3 个 `backfill_*` 管理命令 + `evidence_coverage_report.py` | AC-9 / AC-10 |
| Slice 7 | AI Chat 前端溯源体验 | `AiChatView` [1] 点击 + 来源卡片 + 无证据 banner + `FileDetailView` chunk 锚点 | AC-5 / AC-6 / AC-15 |
| Slice 8 | 真实样例验收 | 用智能制造专业样例验证问答质量 + e2e 回归 | AC-1 / AC-4 / AC-8 |

## 不属于 REQ-010 的相邻需求

- 不替换 LLM provider（见 [REQ-009 AI 平台基准与适配器策略](../../01-product-planning/05-requirements/REQ-009-ai-platform-benchmark-and-adapter-strategy.md)）。
- 不实现应用注册 / 应用市场（见 [REQ-011 AI 应用广场与应用注册中心](../../01-product-planning/05-requirements/REQ-011-ai-application-marketplace-and-registry.md)）。
- 不重做模板抽取（见 [REQ-002-3 模板抽取结果溯源字段扩展](../01-specs/2026-06-10-req-002-3-template-source-tracking.md)）。
- 不重做知识图谱展示层 UI；只迁检索路径。
