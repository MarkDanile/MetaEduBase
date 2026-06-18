# P2: 阶段二 — 增长期

Status: 🟡 Doing
Current: Yes
External:

## Goal

在不引入过早复杂度的前提下，提升召回质量、抽取质量与系统稳定性。阶段二不以“替换所有基础设施”为目标，而是在阶段一产品链路成立后，对真实瓶颈做有边界的增强。

## Phase Entry

2026-06-17 正式进入 P2 增长期。当前阶段优先围绕真实 AI Chat 质量问题推进：先补齐检索理解、4 通道召回、融合排序和上下文组装，再视指标决定是否引入 ES / Milvus / Neo4j 等阶段三能力。

## Retrieval Architecture

阶段二仍以 **PostgreSQL 优先增强** 为默认路线。它不是直接切到“Milvus / Neo4j / Elasticsearch”全套多引擎，而是在阶段一链路稳定后，补齐最影响质量的召回和排序能力。

| 方向 | 阶段一基线 | 阶段二演进 | 技术边界 |
|------|------------|------------|----------|
| 关键词检索 | `ILIKE` 简单兜底 | PostgreSQL `tsvector` + zhparser 中文分词 | 先不引入 Elasticsearch |
| 图谱关系召回 | 无图谱召回通道 | 基于 PostgreSQL `knowledge_edges` 增加第 4 通道 | 先不引入 Neo4j |
| NER | 规则枚举 | 规则未命中时引入 LLM 混合 NER | 不训练专用 NER 模型 |
| 融合排序 | 频次 + 最佳分数 | RRF + 可配置通道权重 | reranker 视真实瓶颈再评估 |
| 抽取结构 | 提示词约束 + JSON 合并 | 抽取 schema 稳定化和样例回归 | 先锁稳定契约，不追求复杂模板平台化 |

阶段二的核心目标是“质量增强但基础设施克制”：优先用 PostgreSQL 能力和已有抽象提升召回质量，只有指标证明单引擎成为瓶颈时，才进入阶段三的多引擎升级。

## Tracks

### 轨道 A：产品能力

| 里程碑项 | 说明 |
|---|---|
| 文档解析增强 | PDF / Word 更高质量结构化提取，提升章节、表格和正文边界识别质量 |
| Whisper 语音转写 | 音频文件 -> 文本 -> Embedding |
| 更多模板类型沉淀 | 扩展教案、课程标准、授课计划等模板族 |
| 模板 AI 辅助配置优化 | 更快模型、更稳定字段结构、更高可编辑性 |

### 轨道 B：检索 / 抽取质量

| 里程碑项 | 说明 |
|---|---|
| PostgreSQL tsvector + zhparser | 中文分词全文搜索，替代 ILIKE |
| LLM 混合 NER | 规则未命中时调用 LLM 提取实体 |
| 4 通道并行召回 | 新增图谱关系召回通道（PostgreSQL `knowledge_edges`） |
| RRF 融合排序 | Reciprocal Rank Fusion + 可配置通道权重 |
| Context Packer / 回答 grounding | 命中 chunk 后回扩相邻 chunk / 同 section，为 LLM 组装足够的原文上下文 |
| 抽取 schema 稳定化 | 让模板字段、嵌套结构、抽取结果更强约束 |

### 轨道 C：基础设施

| 里程碑项 | 说明 |
|---|---|
| Redis 热点缓存 | 向量查询结果缓存 + NER 结果缓存 |
| Celery + RabbitMQ | 替换 Redis 作为消息代理 |
| LiteLLM 统一代理 | 多 LLM 提供商 fallback + Token 计量 |
| MinIO 集群 | 多节点纠删码 |

## Entry Criteria

- 阶段一的 RAG 问答链路和文档抽取链路稳定可演示。
- 至少有一组真实业务文档暴露出召回、抽取或稳定性瓶颈。
- 对应增强项有清晰指标或验收方式，不按技术偏好直接升级。

## Completion Criteria

- 召回覆盖率达到阶段目标，旧规划参考值为 NER 命中率 >= 85%。
- 搜索响应 p99 达到阶段目标，旧规划参考值为 <= 2s。
- 4 通道并行召回具备降级能力，无单通道失败导致整体不可用；第 4 通道默认是 PostgreSQL `knowledge_edges` 图谱关系召回。
- 中文全文检索先由 PostgreSQL `tsvector` + zhparser 承接；Elasticsearch 仍属于阶段三触发式升级。
- 文档 / 模板 / 抽取链路在真实业务文档上稳定可用。

## Open Items

| ID | 状态 | 说明 | 归属 |
|----|------|------|------|
| REQ-002 | 🔵 Ready | 模板化结构抽取能力的配置与复用体验，阶段一可塑形，阶段二继续沉淀模板族和抽取质量 | [Requirement](../05-requirements/REQ-002-template-config-and-reuse.md) / [Backlog](../04-backlog.md) |
| REQ-002-3 | 🟢 完成 | 模板抽取结果溯源字段扩展（template.{id, version, layer}） | [Spec](../../02-delivery-plans/01-specs/2026-06-10-req-002-3-template-source-tracking.md) / [Backlog](../04-backlog.md) / [PR #153](https://github.com/MarkDanile/MetaEduBase/pull/153) |
| REQ-002-1 | 🟢 完成 | 模板配置效率（编辑器 UX：拖拽三层 / 子树复制 / 撤销 / 大模板浏览） | [Spec](../../02-delivery-plans/01-specs/2026-06-10-req-002-1-template-config-ux.md) / [Backlog](../04-backlog.md) / [PR #158](https://github.com/MarkDanile/MetaEduBase/pull/158) |
| REQ-002-2 | 🟢 完成 | 模板复用机制（同租户复制 / 全量版本快照 / JSON 导入导出） | [Spec](../../02-delivery-plans/01-specs/2026-06-10-req-002-2-template-reuse.md) / [Backlog](../04-backlog.md) / [PR #159](https://github.com/MarkDanile/MetaEduBase/pull/159) |
| REQ-002-4 | 🟢 完成 | 模板可维护性（schema_version 演进 + 容器互转二次确认 + deprecated + 命名规范） | [Spec](../../02-delivery-plans/01-specs/2026-06-10-req-002-4-template-maintainability.md) / [Backlog](../04-backlog.md) / [PR #170](https://github.com/MarkDanile/MetaEduBase/pull/170) |
| P2-SEARCH | 🟢 Done | PostgreSQL tsvector + 中文分词搜索增强 | 完整证据链：(1) 基础设施 [TD-047](../../03-engineering-governance/technical-debt.md#td-047) PR #192 — `metaedu/postgres-zhparser:pg16` 镜像 + `chinese_zh` 文本搜索配置 + alembic 010 + 3 个 tsvector 生产者切换；dev 库 backfill 覆盖率 74.95% → 81.91%（+6.96 pct）。(2) 运行时召回链路集成 — [REQ-012 PR #216](https://github.com/MarkDanile/MetaEduBase/pull/216) 改写 `pg_chunk_keyword_retriever.py` 用 `plainto_tsquery('chinese_zh', :query) @@ c.content_tsvector::tsvector`（从 ILIKE 兜底升级）。(3) 真 PG 端到端验收 — [REQ-014 PR #308](https://github.com/MarkDanile/MetaEduBase/pull/308) 验收脚本 + [REQ-015 PR #314](https://github.com/MarkDanile/MetaEduBase/pull/314) 真实 dev DB 问答 grounding 收口。剩 182 个 `file_only` 节点按规划让给 REQ-012 后续 embedding 召回范围。 | [TD-047](../../03-engineering-governance/technical-debt.md#td-047) / [PR #192](https://github.com/MarkDanile/MetaEduBase/pull/192) / [PR #216](https://github.com/MarkDanile/MetaEduBase/pull/216) / [PR #308](https://github.com/MarkDanile/MetaEduBase/pull/308) / [PR #314](https://github.com/MarkDanile/MetaEduBase/pull/314) |
| REQ-013 | 🟢 完成 | RAG Context Packer 与回答 grounding 增强 | PR #305 squash merge：context_packer.py 新建、neighbor/section/graph expansion、TOC guard、prompt builder 接入；17 mock tests 100% pass。Slice 5 真实 PG 样例待 backfill。 | [Requirement](../05-requirements/REQ-013-rag-context-packer-and-grounded-answering.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-16-req-013-rag-context-packer.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-16-req-013-rag-context-packer-plan.md) / [PR #305](https://github.com/MarkDanile/MetaEduBase/pull/305) |
| BUG-007 | 🟢 完成 | pdf_parser sections path 错乱 | PR #303 squash merge：docling counters 算法 + 非标题黑名单。 | [BUG-007](../05-requirements/BUG-007-pdf-parser-section-path-inconsistency.md) / [PR #303](https://github.com/MarkDanile/MetaEduBase/pull/303) |
| REQ-014 | 🟢 Done | RAG 真实 PG 样例、数据回填与回答 grounding 验收 | PR #308 squash merge：spec + plan + 一次性验收脚本 + 占位报告 + 跨事实源同步。follow-up：下个 PR 跑真 PG（dev 库 + LLM key）→ 报告填充 + BUG-006/007 "真 PG 复测"字段；验收中发现真问题另开 BUG-xxx。 | [Requirement](../05-requirements/REQ-014-rag-real-pg-grounding-and-data-backfill-validation.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-16-req-014-rag-real-pg-grounding-validation-plan.md) / [PR #308](https://github.com/MarkDanile/MetaEduBase/pull/308) (merge `86f2f05`) |
| REQ-015 | 🟢 完成 | RAG 生产链路 grounding 与真实验收收口 | PR #314 squash merge `4d78667`：BUG-009 修复后真 dev DB prompt 前证据链已恢复；用户授权后完整 DeepSeek ask 已通过。 | [Requirement](../05-requirements/REQ-015-rag-production-grounding-closure.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-17-req-015-rag-production-grounding-closure.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-17-req-015-rag-production-grounding-closure-plan.md) / [Report](../../02-delivery-plans/01-specs/2026-06-17-req-015-rag-production-grounding-validation-report.md) / [PR #314](https://github.com/MarkDanile/MetaEduBase/pull/314) |
| BUG-009 | 🟢 完成 | AI Chat 真实 PG 链路未把相关正文 chunk 送入 prompt | PR #314 squash merge `4d78667`：修共享 `AsyncSession` 并发、RRF 阈值、lexical supplement 排序和邻居 TOC 识别；prompt 前和完整 ask 真实验收均通过。 | [Bug](../05-requirements/BUG-009-ai-chat-rag-retrieval-context-pipeline-real-pg-failure.md) / [Backlog](../04-backlog.md) / [PR #314](https://github.com/MarkDanile/MetaEduBase/pull/314) |
| BUG-010 | 🟢 完成 | AI Chat 自然问法未稳定命中函数参数正文 chunk | PR #316 squash merge `b753d3a`：P2-NER 前置确定性切片已收口；LLM 混合 NER / Query Understanding 后续仍保留为 P2 能力演进。 | [Bug](../05-requirements/BUG-010-ai-chat-query-normalizer-function-parameter-question.md) / [Backlog](../04-backlog.md) / [PR #316](https://github.com/MarkDanile/MetaEduBase/pull/316) |
| REQ-016 | 🟢 Done | P2-NER 代码切片完成：PR #328/#329/#330 已合并；HybridQueryUnderstandingService、expanded_query、AIChatService diagnostics 和 retriever 查询扩展已接入。真实 PG + LLM 效果验收由 REQ-024 接力。 | [Requirement](../05-requirements/REQ-016-p2-llm-hybrid-ner-query-understanding.md) / [Backlog](../04-backlog.md) / [REQ-024](../05-requirements/REQ-024-p2-real-validation-query-understanding-and-graph-edge.md) |
| REQ-017 | 🟢 完成 | P2-RRF：Slice 1-3 PR #325 已合并；Slice 4 真实PG验收通过（4通道RRF融合正常，AC-1~7全部通过）。 | [Requirement](../05-requirements/REQ-017-p2-rrf-weighted-fusion.md) / [Backlog](../04-backlog.md) / [验收报告](../../02-delivery-plans/01-specs/2026-06-18-req-017-rrf-weighted-fusion-validation-report.md) |
| REQ-018 | 🟢 完成 | P2-RECALL-4：Slice 1-3 PR #333/#334/#335 已合并；Slice 4 真PG验收通过（4通道激活、evidence_id唯一、bug修复）。AC-5 的“补足弱召回样例”仍由 REQ-024 补强。 | [Requirement](../05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md) / [Backlog](../04-backlog.md) / [验收报告](../../02-delivery-plans/01-specs/2026-06-18-req-018-four-channel-graph-edge-recall-validation-report.md) / [REQ-024](../05-requirements/REQ-024-p2-real-validation-query-understanding-and-graph-edge.md) |
| REQ-024 | 🔴 Blocked | P2 真实验收补强已产出脚本与 dry-run 报告；TD-068 已澄清 vector fallback；REQ-025 已补 graph_edge 进入 packed context 并跑真实 LLM，但最终回答改善证据不足，不能视为最终效果通过。 | [Requirement](../05-requirements/REQ-024-p2-real-validation-query-understanding-and-graph-edge.md) / [Report](../../02-delivery-plans/01-specs/2026-06-18-req-024-p2-real-validation-report.md) / [REQ-025](../05-requirements/REQ-025-p2-graph-edge-prompt-impact-and-real-llm-validation.md) / [REQ-026](../05-requirements/REQ-026-p2-rag-effect-comparison-and-weak-recall-samples.md) |
| TD-068 | 🟢 完成 | PR #355 squash merge `fdffd60`：已确认 query embedding 为空时 vector topN 来自 keyword fallback；AI Chat diagnostics 和 REQ-024 report 已显式标记 `vector fallback`，避免误判为真实语义向量召回。 | [Technical Debt](../../03-engineering-governance/technical-debt.md#td-068) / [Report](../../02-delivery-plans/01-specs/2026-06-18-req-024-p2-real-validation-report.md) / [PR #355](https://github.com/MarkDanile/MetaEduBase/pull/355) |
| REQ-025 | 🟣 待验证 | graph_edge 进入 prompt 与真实 LLM 效果验收收口：2 个样例已满足 `edge in packed > 0`，真实 LLM provider 已跑；但质量改善证据不足，不能关闭 P2 真实效果验收。 | [Requirement](../05-requirements/REQ-025-p2-graph-edge-prompt-impact-and-real-llm-validation.md) / [Report](../../02-delivery-plans/01-specs/2026-06-18-req-025-graph-edge-prompt-impact-validation-report.md) / [Backlog](../04-backlog.md) |
| REQ-026 | 🟡 部分收口 | P2 RAG 效果比较与弱召回样例集收口 (PR #358 squash merge `930589b`)：spec+plan+5 条弱召回样例集+扩展脚本+真 LLM 报告均已落地。机制层 5/5 ✅；prompt 层 graph_edge in packed 3/5 ✅ (REQ-025 AC-2 达成)；质量层 P2 覆盖度提升≥30% 仅 1/5 ❌ (REQ-026 AC-1 未达成)；Q4 出现 -0.60 退化。已登记 REQ-027 接力样例多样性与数据回填 | [Requirement](../05-requirements/REQ-026-p2-rag-effect-comparison-and-weak-recall-samples.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-and-weak-recall-samples.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-18-req-026-rag-effect-comparison-and-weak-recall-samples-plan.md) / [Report](../../02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-validation-report.md) / [PR #358](https://github.com/MarkDanile/MetaEduBase/pull/358) |
| P2-EXTRACT | ⚫ Candidate | 抽取 schema 稳定化：继续沉淀模板字段、嵌套结构、抽取结果契约和真实样例回归；优先承接 REQ-002 及其子任务后的实际缺口。 | [Backlog](../04-backlog.md) |
| P2-INFRA | ⚫ Candidate | Redis 缓存 / RabbitMQ / LiteLLM / MinIO 集群按瓶颈择一推进；只有出现稳定性、成本、吞吐或可观测瓶颈时进入 Backlog。 | 待进入 backlog |

## Suggested Next Focus

| 顺序 | 任务 | 为什么先做 |
|------|------|------------|
| 1 | REQ-018 P2-RECALL-4 | 先补独立 `knowledge_edges` 关系通道，再把四通道并行召回验收清楚。 |
| 2 | REQ-017 P2-RRF | RRF 基础已在生产链路中，等 REQ-018 通道边界明确后收口 weighted 配置和 4 通道排序验收。 |
| 3 | REQ-016 P2-NER | 在有 trace、召回和排序基线后再引入 LLM Query Understanding，更容易判断它解决的是实体理解问题还是召回排序问题。 |

## Evidence

- 历史规划：`git show bf6429c:ARCHITECTURE.md`
- 模板结构抽取历史设计：`docs/90-compat-legacy/superpowers/specs/2026-05-27-structured-template-design.md`
- 模板 AI 上下文历史设计：`docs/90-compat-legacy/superpowers/specs/2026-06-28-template-ai-context-design.md`
