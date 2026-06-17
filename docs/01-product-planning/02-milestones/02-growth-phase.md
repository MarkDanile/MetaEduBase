# P2: 阶段二 — 增长期

Status: ⚫ Candidate
Current: No
External:

## Goal

在不引入过早复杂度的前提下，提升召回质量、抽取质量与系统稳定性。阶段二不以“替换所有基础设施”为目标，而是在阶段一产品链路成立后，对真实瓶颈做有边界的增强。

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
| P2-SEARCH | 🟡 Shaping | PostgreSQL tsvector + 中文分词搜索增强 | 技术债入口 [TD-047](../../03-engineering-governance/technical-debt.md#td-047) 已收口（PR #192）：metaedu/postgres-zhparser:pg16 镜像 + chinese_zh 文本搜索配置 + plainto_tsquery，dev 库真跑 backfill 覆盖率 74.95% → 81.91%（+6.96 pct）。剩 182 个 file_only 节点属 REQ-012 后续 embedding 召回范围。基础设施 Ready，召回链路集成 pending → Shaping 中间态。 |
| REQ-013 | 🟢 完成 | RAG Context Packer 与回答 grounding 增强 | PR #305 squash merge：context_packer.py 新建、neighbor/section/graph expansion、TOC guard、prompt builder 接入；17 mock tests 100% pass。Slice 5 真实 PG 样例待 backfill。 | [Requirement](../05-requirements/REQ-013-rag-context-packer-and-grounded-answering.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-16-req-013-rag-context-packer.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-16-req-013-rag-context-packer-plan.md) / [PR #305](https://github.com/MarkDanile/MetaEduBase/pull/305) |
| BUG-007 | 🟢 完成 | pdf_parser sections path 错乱 | PR #303 squash merge：docling counters 算法 + 非标题黑名单。 | [BUG-007](../05-requirements/BUG-007-pdf-parser-section-path-inconsistency.md) / [PR #303](https://github.com/MarkDanile/MetaEduBase/pull/303) |
| REQ-014 | 🟢 Done | RAG 真实 PG 样例、数据回填与回答 grounding 验收 | PR #308 squash merge：spec + plan + 一次性验收脚本 + 占位报告 + 跨事实源同步。follow-up：下个 PR 跑真 PG（dev 库 + LLM key）→ 报告填充 + BUG-006/007 "真 PG 复测"字段；验收中发现真问题另开 BUG-xxx。 | [Requirement](../05-requirements/REQ-014-rag-real-pg-grounding-and-data-backfill-validation.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-16-req-014-rag-real-pg-grounding-validation-plan.md) / [PR #308](https://github.com/MarkDanile/MetaEduBase/pull/308) (merge `86f2f05`) |
| REQ-015 | 🟣 待验证 | RAG 生产链路 grounding 与真实验收收口 | Context Packer / RRF / trace diagnostics / 真实 PG 验收脚本已接到生产默认链路；待真 PG 样例和 LLM 回答报告确认质量目标。 | [Requirement](../05-requirements/REQ-015-rag-production-grounding-closure.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-17-req-015-rag-production-grounding-closure.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-17-req-015-rag-production-grounding-closure-plan.md) |
| P2-NER | ⚫ Candidate | LLM 混合 NER | 待进入 backlog |
| P2-RRF | ⚫ Candidate | RRF 融合排序 | 待进入 backlog |
| P2-INFRA | ⚫ Candidate | Redis 缓存 / RabbitMQ / LiteLLM / MinIO 集群按瓶颈择一推进 | 待进入 backlog |

## Evidence

- 历史规划：`git show bf6429c:ARCHITECTURE.md`
- 模板结构抽取历史设计：`docs/90-compat-legacy/superpowers/specs/2026-05-27-structured-template-design.md`
- 模板 AI 上下文历史设计：`docs/90-compat-legacy/superpowers/specs/2026-06-28-template-ai-context-design.md`
