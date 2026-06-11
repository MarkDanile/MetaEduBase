# REQ-012: RAG 多路召回与知识图谱证据链收口

Status: 🟣 Shaping
Priority: P1
Milestone: P1 / P2
Parent: REQ-010
Alias: REQ-010 质量 follow-up
Source: AI Chat 问答质量复核 / TD-046 数据回填结果 / P2-SEARCH 规划校准

## 背景

REQ-010 已建立 evidence-aware AI Chat 骨架：前端默认请求 `/ai/chat/evidence`，后端通过 `AIChatService` 把候选证据融合后交给 LLM，并在前端展示 `[1]` / `[2]` 引用和参考来源。

复核发现，该骨架仍未完全达到“用户提问 -> 多路召回 -> 融合排序 -> 高相关原文切片 / 结构化证据 / 图谱证据 -> LLM 回答”的目标：

- evidence 路径当前主要接入 chunk vector + graph 两路；chunk keyword retriever 已存在但未注入线上 service。
- `MetadataFilter.filter(...)` 返回值未被接住，过滤 / 加权结果没有真正参与候选集。
- 知识图谱召回仍可能退化为 `knowledge_nodes.description`，未稳定回到 `source_chunk_id` / 原文 chunk。
- prompt context 使用 `snippet or content`，当前 chunk retriever 的 snippet 为 `content[:200]`，上下文可能偏薄。
- TD-046 回填后 `node_source_chunk` 为 754 / 1006 (74.95%)，仍有 252 个 `file_only` 节点；其中中文分词 / ILIKE 限制已拆为 [TD-047](../../03-engineering-governance/technical-debt.md#td-047)。

本需求承接 REQ-010 的质量 follow-up，聚焦 AI Chat 的真实回答质量，不替代 TD-047 / TD-048：

| 任务 | 边界 |
|------|------|
| REQ-012 | 多路召回、证据链、prompt 证据上下文、端到端问答质量收口 |
| TD-047 | 中文分词 / PostgreSQL tsvector 搜索增强，是 REQ-012 的底层检索能力依赖之一 |
| TD-048 | 旧 `/ai/chat` node-shaped 契约 deprecation，不阻塞 REQ-012 主链路 |

## 目标

- 让 AI Chat evidence 路径真正使用 chunk 级多路召回，而不是只依赖向量和知识节点摘要。
- 让 metadata filter 的结果进入融合前候选治理。
- 让 graph evidence 能追溯到 file / chunk，优先给 LLM 原文证据，而不是孤立知识点。
- 在 token budget 内组装足够的原文 chunk / 结构化字段 / 关系证据，提升回答 grounding。
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

- 保持现有 `[1]` / `[2]` 引用和参考来源列表。
- 确认 sources 能打开到文件和 chunk；无法定位 chunk 时要有清晰 fallback。
- 不新增复杂检索调试 UI；必要时只补最小的 evidence 展示字段。

## 验收标准

- AC-1：`/ai/chat/evidence` 的候选通道至少包含 chunk vector、chunk keyword / full-text、graph evidence 三类来源或明确降级日志。
- AC-2：metadata filter 的返回结果实际影响融合前候选集，并有测试覆盖。
- AC-3：graph evidence 至少在可解析场景中回到 `file_id` / `chunk_id`，LLM prompt 中优先使用对应 chunk 原文。
- AC-4：prompt context 包含真实 chunk 内容，不能只包含 `knowledge_nodes.title` / `description`。
- AC-5：回答中的 `[N]` 引用编号不越界，且与 `sources` 顺序一致。
- AC-6：用“智能制造专业需要哪些技能？”或等价真实样例跑通端到端验收，记录 sources、召回通道、prompt 摘要和回答质量结论。
- AC-7：重跑 `scripts/ai/evidence_coverage_report.py`，记录 REQ-012 前后覆盖率变化。
- AC-8：不把 TD-047 / TD-048 的独立边界合并进本需求；需要时以依赖或 follow-up 形式引用。

## 验证建议

- `pytest tests/contexts/knowledge/test_ai_chat_service.py -q`
- 新增或扩展 chunk keyword / metadata filter / graph-to-chunk 的单元测试。
- 有 PG 环境时运行 `/api/v1/ai/chat/evidence` 真实样例测试。
- `python scripts/ai/evidence_coverage_report.py`
- `scripts/check-engineering-docs`
- `git diff --check`

## 后续入口

- 开发前应先建立 spec / plan，明确是否把 TD-047 作为前置依赖。
- 若需要分阶段执行，建议先做 Backend 证据链，再做真实样例验收，最后回填工作台和评审评分。
