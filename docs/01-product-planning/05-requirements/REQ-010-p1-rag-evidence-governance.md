# REQ-010: P1 真实 RAG 证据治理与 AI Chat 溯源体验

Status: 🟣 Shaping
Priority: P1
Milestone: P1
Source: AI Chat 问答质量复核 / P1 RAG 链路目标校准

## 背景

P1 阶段的核心目标是验证 RAG 问答链路：

```text
用户提问 -> 多源召回 -> 融合排序 -> LLM 回答
```

复核当前实现后发现，现有 AI Chat 链路已经具备 NER、3 通道召回、融合排序和 sources 返回，但召回对象主要是 `knowledge_nodes`，LLM 上下文主要由知识节点的 `title` / `description` 拼接而成，没有把 `document_chunks.content` 作为主要证据交给大模型。

这会导致回答质量更像“知识点标题扩写”，而不是真正基于原文切片、结构化数据和可追溯来源的 RAG 回答。

## 核心判断

无论阶段内采用哪种召回技术，最终目标都应是找到和问题最相关、可作为回答依据的证据内容：

| 召回源 | P1 / 后续形态 | 最终应落到 |
|--------|---------------|------------|
| 向量召回 | P1 可继续使用 PostgreSQL + pgvector | 相关 `document_chunks.content` |
| 全文检索 | P1 可使用 PostgreSQL `tsvector` 或轻量关键词召回；P2/P3 再考虑 ES | 相关 `document_chunks.content` |
| 知识图谱 | P1 可用 `knowledge_nodes` / `knowledge_edges` 替代图数据库；后续可参考 GraphRAG 思路增强 | 能回到 `source_chunk_id` / `source_file_id` 的实体、关系和原文证据 |
| 元数据过滤 | P1 可使用 `doc_type` / `tags` / `structured_data` / NER 过滤或加权 | 缩小 chunk / 文件 / 结构化字段候选范围，而不是替代原文证据 |
| 结构化抽取结果 | P1 已有 `files.structured_data` | 可作为结构化证据或过滤条件进入问答上下文 |

核心原则：**知识图谱、全文检索、向量检索和元数据过滤都服务于 evidence retrieval，不能用孤立知识点替代原文证据。**

## 目标

建立 P1 最小真实 RAG 证据闭环，让 AI Chat 至少满足：

1. 用户问题能够召回相关原文 chunk。
2. 多路召回结果统一为可排序、可溯源的证据单元。
3. LLM 上下文包含足够的原文片段、结构化字段或知识关系，而不是只有知识点标题。
4. 回答中的来源编号可以追溯到具体文件、chunk 或结构化字段。
5. 前端能够展示回答下方的参考文件 / 来源列表。
6. 历史数据在结构升级后可通过初始化 / 回填任务补齐，不要求人工重新上传全部资料。
7. P1 的 PostgreSQL 单引擎实现必须通过接口隔离，保证 P4 替换 Neo4j、Milvus / Qdrant、Elasticsearch 等基础设施时不改 AI Chat 业务编排。

## 建议证据模型

后续可设计统一的 `EvidenceItem` 或等价 DTO，避免各通道直接返回彼此不兼容的对象。

建议字段：

| 字段 | 说明 |
|------|------|
| `evidence_id` | 证据唯一 ID，可由 source type + source id 派生 |
| `source_type` | `chunk` / `knowledge_node` / `knowledge_edge` / `structured_field` |
| `file_id` | 来源文件 |
| `chunk_id` | 来源 chunk，可为空但应尽量补齐 |
| `node_id` | 来源知识节点 |
| `structured_path` | 结构化字段路径，如 `template.basic_info.course_name` |
| `title` | 用于展示的标题 |
| `content` | 给 LLM 的主要证据文本 |
| `snippet` | 前端展示用摘要或高亮片段 |
| `metadata` | `doc_type` / `tags` / section / page / channel 等补充信息 |
| `score` | 归一化或融合后的分数 |
| `channels` | 命中的召回通道，如 `vector` / `keyword` / `metadata` / `graph` |

## 范围

### Backend

- 建立召回抽象边界，避免 AI Chat 直接依赖具体存储实现：
  - `ChunkRetriever` 或等价接口：P1/P2 由 PostgreSQL + pgvector / tsvector 实现，P4 可按指标替换为 Milvus / Qdrant / Elasticsearch。
  - `GraphRetriever` 或等价接口：P1 可由 `knowledge_nodes` / `knowledge_edges` + SQL 查询实现，后续可替换 Neo4j 或 GraphRAG 风格索引。
  - `MetadataFilter` 或等价接口：P1 可读 `files.doc_type` / `tags` / `structured_data`，后续可接入更完整的标签服务或画像服务。
  - `EvidenceFusion` 或等价接口：融合排序只处理统一 evidence，不关心底层通道来自 PostgreSQL、ES、向量库还是图数据库。
- 增加 chunk 级向量召回：基于 `document_chunks.embedding` 返回相关 chunk。
- 增加 chunk 级全文 / 关键词召回：基于 `document_chunks.content_tsvector` 或 `content` 返回相关 chunk。
- 保留 knowledge node 召回，但节点必须尽量回到 `source_chunk_id` / `source_file_id`。
- 让知识图谱抽取写入更完整的来源信息：
  - `source_chunk_id`
  - `source_file_id`
  - `description`
  - 合理的 `domain` / `level`
  - 必要时补 `embedding`
- 元数据过滤不只依赖 NER 的 `domain` / `level`，还应评估：
  - `files.doc_type`
  - `files.tags`
  - `files.structured_data`
  - template 抽取结果中的业务字段
- LLM prompt 组装从“相关知识点”升级为“参考证据”，至少包含：
  - chunk 原文片段
  - 来源文件名 / 章节 / chunk 序号
  - 命中通道
  - 结构化字段或知识关系补充

### 数据初始化 / 回填

若 REQ-010 引入新的证据字段、索引字段或关联字段，必须提供可重复执行的初始化 / 回填路径。不能只支持新上传数据。

需要覆盖：

- 历史 `knowledge_nodes` 与 `document_chunks` 的关联补齐：
  - 能确定来源 chunk 的节点补 `source_chunk_id`。
  - 只能确定来源文件的节点至少保留 `source_file_id`，并标记待人工或后续算法细化。
- 历史 `knowledge_nodes` 的 `description` / `domain` / `level` / `embedding` 补齐策略。
- 历史 `document_chunks.content_tsvector` / `embedding` 的重建和校验。
- 历史 `files.tags` / `doc_type` / `structured_data` 可用于 metadata filter 的字段识别和回填策略。
- 回填任务必须具备幂等性：重复执行不产生重复节点、重复边或重复来源记录。
- 回填任务需要输出统计结果：扫描数、更新数、跳过数、失败数和失败原因样例。

建议形式：

| 类型 | 建议实现 |
|------|----------|
| 本地运维命令 | `scripts/...` 或后端管理命令，用于一次性 backfill / reindex |
| 异步任务 | 数据量较大时使用 Celery task 分批处理 |
| 验证脚本 | 输出 chunk / node / metadata / embedding / tsvector 覆盖率 |

### Frontend

- 回答正文中的来源标注支持 `[1]` / `[2]` / `[3]` 等编号。
- 来源编号可以点击，定位到对应参考来源详情。
- 回答结果下方展示“参考来源”列表，至少包含：
  - 文件名或知识节点标题
  - chunk / 章节摘要
  - 命中通道
  - 分数或相关度提示
  - 查看源文件 / 查看片段入口
- 来源列表需要去重：同一文件多个 chunk 可合并展示，但仍能展开查看具体片段。
- 当没有检索到可靠证据时，前端应能展示“未找到足够参考来源”，而不是把空 sources 当成正常回答。

## 行业最佳实践建议

- **Evidence first**：回答必须先有证据，再由 LLM 组织语言。
- **Citation grounded**：每条关键结论尽量引用来源编号；没有来源的内容应明显区分为推断或建议。
- **Source inspectability**：用户能从回答跳回文件、chunk 或结构化字段。
- **Hybrid retrieval**：向量召回负责语义相似，全文召回负责术语精确命中，元数据负责范围过滤，知识图谱负责关系扩展。
- **Late fusion**：多路候选先统一成证据项，再做融合排序，避免通道之间各自为政。
- **No-evidence fallback**：上下文不足时明确说明缺少资料，而不是输出泛化答案。
- **Observability**：记录每次问答的 query、NER 结果、各通道候选、融合结果、最终 prompt 摘要，便于排查质量问题。
- **Replaceable infrastructure**：业务编排依赖接口，不依赖 PostgreSQL / Neo4j / Milvus / ES 等具体实现；阶段升级只替换模块内部 adapter。
- **Backfill before claim**：数据结构升级后，必须先完成历史数据初始化和覆盖率验证，才能声明 RAG 质量链路已收口。

## 架构可替换性要求

P1 可以继续使用 PostgreSQL 单引擎，但实现时必须为 P2 / P3 技术演进保留替换点。

| 能力 | P1 当前/建议实现 | P2/P3 可替换方向 | 不应泄漏到业务层的细节 |
|------|------------------|------------------|------------------------|
| 图谱关系 | PostgreSQL `knowledge_nodes` / `knowledge_edges` + SQL 查询 | Neo4j / GraphRAG 风格索引 | 递归 SQL、边表 join 细节 |
| 向量检索 | PostgreSQL + pgvector | Milvus / Qdrant / 其他向量服务 | `<=>` 操作符、向量字段存储格式 |
| 全文检索 | PostgreSQL `tsvector` / 轻量关键词召回 | Elasticsearch / OpenSearch | `to_tsvector`、`ILIKE`、分词策略 |
| 元数据过滤 | `files.doc_type` / `tags` / `structured_data` | 标签服务 / 用户画像 / 学习情境服务 | JSONB path 查询、字段命名细节 |
| 融合排序 | 本地 fusion service | RRF / reranker / learning-to-rank | 通道原始分数尺度 |

AI Chat 编排层只应感知：

```text
query -> retrievers -> evidence candidates -> fusion -> prompt context -> answer + citations
```

不应直接感知：

```text
pgvector SQL / tsvector SQL / Neo4j Cypher / ES DSL / Milvus collection name
```

后续 spec / plan 必须显式说明新增代码放在哪个 adapter / service / DTO 层，避免把阶段一实现写成阶段二重构障碍。

## 非范围

- 不在 P1 强制引入 Elasticsearch、Milvus / Qdrant、Neo4j 或完整 GraphRAG 基础设施。
- 不直接接入 RAGFlow / Dify 等外部平台。
- 不重写整个文档处理流水线。
- 不把 AI Chat 做成多智能体编排。

## 验收标准

- AC-1：给定真实文档样例，`POST /api/v1/ai/chat` 的检索结果至少包含 1 条 `document_chunks` 证据。
- AC-2：LLM prompt 中包含 chunk 原文片段或结构化字段内容，不再只包含 `knowledge_nodes.title` / `description`。
- AC-3：sources 返回可追溯字段，至少能定位到 file 和 chunk；knowledge node 来源若存在，也能回到 file 或 chunk。
- AC-4：回答正文中的 `[1]` / `[2]` 引用能对应到 sources 列表。
- AC-5：前端回答下方展示参考来源列表，并支持打开或定位参考源。
- AC-6：当无可靠证据时，回答和 UI 明确提示“参考资料不足”。
- AC-7：测试覆盖 chunk vector recall、chunk keyword recall、node-to-chunk 追溯、融合排序和 sources shape。
- AC-8：P1 milestone、Backlog、current-work 和相关 spec / plan 在交付后状态一致。
- AC-9：提供历史数据初始化 / 回填方案，并能统计 node-to-chunk、chunk embedding、chunk tsvector、metadata 可用率。
- AC-10：回填过程幂等，重复执行不会产生重复节点、重复边或重复 evidence 来源。
- AC-11：AI Chat 编排层依赖抽象接口或 service，不直接拼 pgvector / tsvector / 图谱 SQL；测试可通过 fake retriever / fake fusion 验证编排。
- AC-12：spec / plan 明确 P1/P2 PostgreSQL adapter 与 P4 Neo4j、Milvus / Qdrant、Elasticsearch 替换边界。

## 建议切片

| 切片 | 目标 | 说明 |
|------|------|------|
| Slice 1 | 后端证据模型与诊断日志 | 定义 EvidenceItem，增加问答链路可观测输出。 |
| Slice 2 | 可替换 retriever adapter | 抽出 chunk / graph / metadata retriever 接口，P1 先接 PostgreSQL adapter。 |
| Slice 3 | chunk 级召回进入 AI Chat | 新增 chunk vector / keyword 通道，LLM prompt 使用 chunk 内容。 |
| Slice 4 | KG / metadata 与 chunk 关联治理 | 修复 KG 抽取来源字段，评估 doc_type / tags / structured_data 过滤。 |
| Slice 5 | 历史数据 backfill / reindex | 补 node-to-chunk、embedding、tsvector、metadata 覆盖率统计与幂等回填。 |
| Slice 6 | AI Chat 前端来源体验 | 正文编号引用 + 回答下方参考来源列表 + 源头跳转。 |
| Slice 7 | 真实样例验收 | 用 P1 课程/专业样例验证问答质量，形成可复现测试或演示脚本。 |

## 待澄清

- P1 样例文档选择：是否以“智能制造专业需要哪些技能？”相关课程资料作为首个验收样例。
- 来源跳转目标：优先跳文件详情页、chunk 锚点，还是弹出来源详情面板。
- `structured_data` 进入召回的优先级：作为 metadata filter、证据内容，还是二者都支持。
- 是否需要单独记录一次问答检索 trace，供调试和复盘使用。
- 历史知识节点无法自动定位 chunk 时，是允许只回填到 file 级来源，还是必须进入人工确认队列。
- P1 adapter 抽象是只覆盖 AI Chat，还是同步约束知识图谱展示、MCP 查询等其他消费方。
