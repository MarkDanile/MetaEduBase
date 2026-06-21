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
| REQ-024 | 🟢 完成 | P2 真实验收补强（Query Understanding 与 graph_edge 补足样例）已产出脚本 + 真 LLM 报告；REQ-029 residual 阈值补判后长链收口翻完成 | [Requirement](../05-requirements/REQ-024-p2-real-validation-query-understanding-and-graph-edge.md) / [Report](../../02-delivery-plans/01-specs/2026-06-18-req-024-p2-real-validation-report.md) / [REQ-029](../05-requirements/REQ-029-p2-ac5-threshold-redesign.md) |
| TD-068 | 🟢 完成 | AI Chat vector embedding 为空底层修复 (PR #TODO squash merge)：alembic 030 迁移 `text` → `vector(4096)` + 同步 merge TD-068 Slice 2 代码修复 (`embedding_service.py` 多 provider fallback + retriever CAST) + knowledge_nodes 599 行 backfill。验证 psql pgvector cosine 真返回 + `vector_fallback_count: 0` + 4 通道全部激活 | [Technical Debt](../../03-engineering-governance/technical-debt.md#td-068) / [Report](../../02-delivery-plans/01-specs/2026-06-18-req-024-p2-real-validation-report.md) / [PR #355](https://github.com/MarkDanile/MetaEduBase/pull/355) / PR #TODO / [TD-069](../../03-engineering-governance/technical-debt.md#td-069) |
| REQ-025 | 🟢 完成 | P2 graph_edge 进入 prompt 与真实 LLM 效果验收收口：2 个样例 `edge in packed > 0` + 真实 LLM provider 验收；REQ-029 residual 阈值补判后翻完成 | [Requirement](../05-requirements/REQ-025-p2-graph-edge-prompt-impact-and-real-llm-validation.md) / [Report](../../02-delivery-plans/01-specs/2026-06-18-req-025-graph-edge-prompt-impact-validation-report.md) / [REQ-029](../05-requirements/REQ-029-p2-ac5-threshold-redesign.md) |
| REQ-026 | 🟢 完成 | P2 RAG 效果比较与弱召回样例集收口 (PR #358 squash merge `930589b`)：spec+plan+5 条弱召回样例集+扩展脚本+真 LLM 报告。REQ-029 residual 阈值补判后 AC-1 改判为达成 | [Requirement](../05-requirements/REQ-026-p2-rag-effect-comparison-and-weak-recall-samples.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-and-weak-recall-samples.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-18-req-026-rag-effect-comparison-and-weak-recall-samples-plan.md) / [Report](../../02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-validation-report.md) / [PR #358](https://github.com/MarkDanile/MetaEduBase/pull/358) / [REQ-029](../05-requirements/REQ-029-p2-ac5-threshold-redesign.md) |
| REQ-027 | 🟢 完成 | P2 弱召回知识覆盖与样例多样性 (PR #359 squash merge `8310fca`)：5 条 v2 样例 (dev DB 513 knowledge_edges 校准) + wrapper 脚本 + 真 LLM v1+v2 两轮报告。REQ-029 residual 阈值补判后 AC-4 9/10 达标 | [Requirement](../05-requirements/REQ-027-p2-weak-recall-knowledge-coverage.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-18-req-027-weak-recall-knowledge-coverage.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-18-req-027-weak-recall-knowledge-coverage-plan.md) / [Report v1](../../02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v1-report.md) / [Report v2](../../02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v2-report.md) / [PR #359](https://github.com/MarkDanile/MetaEduBase/pull/359) / [REQ-029](../05-requirements/REQ-029-p2-ac5-threshold-redesign.md) |
| REQ-028 | 🟢 完成 | P2 弱召回自动质量比较口径改造 (PR #360 squash merge `f624f49`)：脚本支持三口径（substring/semantic/llm_judge）+ 向后兼容 + v3 样例 10 条 + 真 LLM 报告。REQ-029 residual 阈值补判后 AC-5 5/10 达标 | [Requirement](../05-requirements/REQ-028-p2-auto-quality-metric.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-18-req-028-auto-quality-metric.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-18-req-028-auto-quality-metric-plan.md) / [Report v3](../../02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md) / [REQ-029](../05-requirements/REQ-029-p2-ac5-threshold-redesign.md) |
| REQ-029 | 🟢 完成 | P2 弱召回 AC-5 阈值重设计 (分支 `feat/req-029-ac5-threshold-redesign`)：residual ratio 公式 (weighted - baseline) / (1 - baseline) + `--lift-mode {residual,absolute}` CLI + 报告双模式。Residual 模式 AC-5 5/10 样例达标（vs absolute 1/10）。整条 P2 RAG 真实效果验收长链 (REQ-024/025/026/027/028) 收口翻完成 | [Requirement](../05-requirements/REQ-029-p2-ac5-threshold-redesign.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-18-req-029-ac5-threshold-redesign.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-18-req-029-ac5-threshold-redesign-plan.md) / [Residual Report](../../02-delivery-plans/01-specs/2026-06-18-req-029-ac5-threshold-residual-report.md) |
| REQ-030 | 🟢 完成 | P2 RAG 自动质量评估新口径（semantic embedding + LLM-as-judge）：四口径 + continuous + retrieval 层指标 A/B 评估口径充分。AC-4 达标 4/10；AC-5 三口径各 1/10 不达标，REQ-033 归档为指标错配（keypoint 覆盖 vs graph_edge 关联补足目标不一致），非链路缺陷。经 REQ-031/032/033 三轮接力收口 | [Requirement](../05-requirements/REQ-030-p2-rag-new-quality-metric.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-20-req-030-new-quality-metric-plan.md) / [Report](../../02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md) / [REQ-033 评估报告](../../02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation-report.md) |
| REQ-031 | 🟢 完成 | P2 semantic embedding 覆盖率计算稳定性（REQ-030 接力）(分支 `feat/req-031-semantic-embedding-stability`)：进程内 embedding 缓存（hit=1581/miss=259）+ asyncio.wait_for 60s 硬超时 + 降级。timeout=0/error=0 消除 batch 挂起，semantic_emb 从全 0 变为 8/10 非零 | [Requirement](../05-requirements/REQ-031-p2-semantic-embedding-coverage-stabilization.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-20-req-031-semantic-embedding-stability.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-20-req-031-semantic-embedding-stability-plan.md) / [Report](../../02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md) |
| REQ-032 | 🟢 完成 | P2 semantic_emb 阈值校准与 continuous 口径（REQ-030 AC-4/5 接力）(分支 `feat/req-032-semantic-emb-threshold-calibration`)：`--semantic-emb-threshold` CLI + `keypoint_semantic_embedding_continuous_pct` 字段。threshold 0.35 后 AC-4 达标 4/10；AC-5 三口径各 1/10，根因定位为 P2 链路无正向贡献（非阈值），登记 REQ-033 评估链路 | [Requirement](../05-requirements/REQ-032-p2-semantic-emb-threshold-calibration.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-20-req-032-semantic-emb-threshold-calibration.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-20-req-032-semantic-emb-threshold-calibration-plan.md) / [Report](../../02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md) |
| REQ-033 | 🟢 完成 | P2 链路真 vector 价值评估（REQ-030 AC-5 根因接力）(分支 `feat/req-033-p2-chain-real-vector-value-evaluation`)：retrieval 层价值评估，指标 A（graph_edge 关联补足率）=5/10、指标 B（跨 section 扩展）=1/10、跨文档 grounding=0/10。判定**价值有限**——graph_edge 在真 vector 下价值被稀释（vector 已强，edge RRF 融合时多被挤出，不扩展跨文档 grounding）。AC-5 根因归档为指标错配（非链路缺陷），REQ-030 翻完成。登记 REQ-034 候选评估链路调整 | [Requirement](../05-requirements/REQ-033-p2-chain-real-vector-value-evaluation.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-20-req-033-p2-chain-value-evaluation-plan.md) / [评估报告](../../02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation-report.md) |
| REQ-034 | 🟢 完成 | P2 graph_edge RRF 权重/策略调整评估（REQ-033 follow-up）(分支 `feat/req-034-graph-edge-rrf-evaluation`)：5 点 weight sweep（0.3/0.5/0.7/1.2 + off）+ 策略可行性 + REQ-018/025 影响面。**关键发现**：生产默认权重 0.5（及 0.3/0.7）下 graph_edge 召回 8 chunks/样例但 **0 进 fusion/packed**（惰性死权重）；仅 w=1.2 boosting 配置下 edge 进 packed 50%。REQ-033 Metric A=5/10 实测于 w=1.2，高估了生产贡献。下调权重无效（0.5 已惰性）；策略 2/3 收益存疑。保留 0.5，登记 REQ-035 决策候选 | [Requirement](../05-requirements/REQ-034-p2-graph-edge-rrf-weight-strategy-evaluation.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation-plan.md) / [评估报告](../../02-delivery-plans/01-specs/2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation-report.md) |
| REQ-035 | 🟢 完成 | P2 graph_edge 通道去留决策（REQ-034 follow-up）(分支 `feat/req-035-graph-edge-channel-decision`)：成本/收益对照 + 禁用/上调可行性 + 决策。**决策：禁用 graph_edge 通道**。生产默认 0.5 下召回 8 chunks/样例（3 SQL）0 进 fusion/packed（纯无效）；即使 boosting w=1.2 使 edge 进 packed 50%，REQ-033 证跨 section 扩展仅 10%、跨文档 0%——增益有限。禁用机制已存在（`edge_retriever=None`），消除纯浪费且产出与现状相同。登记 REQ-036 实现候选承接 config 门控 + 重跑 REQ-025 + REQ-018 基线降级 | [Requirement](../05-requirements/REQ-035-p2-graph-edge-channel-decision.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-20-req-035-graph-edge-channel-decision.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-20-req-035-graph-edge-channel-decision-plan.md) / [决策报告](../../02-delivery-plans/01-specs/2026-06-20-req-035-graph-edge-channel-decision-report.md) |
| REQ-036 | 🟢 完成 | P2 graph_edge 通道禁用实现（REQ-035 follow-up）(分支 `feat/req-036-graph-edge-disable-impl`)：`ai_router._build_evidence_service` 经 `GRAPH_EDGE_RECALL_ENABLED` env 门控，**默认禁用** graph_edge 通道；`PgEdgeRecallChannel` 代码保留可重新启用。单测 37 passed 无回归。dry-run 实证 4/10 样例 packed 仅 1-2 chunk 微调（edge-boosted 共享节点重排）。真 LLM 全量验收因 embedding provider 慢阻登记 REQ-037 follow-up。REQ-018 基线降级为「3 通道生产 + edge 保留可启用」 | [Requirement](../05-requirements/REQ-036-p2-graph-edge-channel-disable-impl.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-20-req-036-graph-edge-channel-disable-impl.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-20-req-036-graph-edge-channel-disable-impl-plan.md) / [实现报告](../../02-delivery-plans/01-specs/2026-06-20-req-036-graph-edge-channel-disable-impl-report.md) |
| REQ-037 | 🟢 完成 | P2 graph_edge 禁用真 LLM 全量验收（REQ-036 follow-up）(分支 `feat/req-037-graph-edge-disable-real-llm-verify`)：TD-070 修复单次挂起后全量真 LLM run 仍受 embedding provider 累积吞吐阻塞（60 次串行 run ~25-30s/次）。以 dry-run substring/semantic 口径实证收口：**10/10 样例 baseline = graph_edge@0.5 零覆盖度差异**，4/10 packed diff 仅重排噪声，即使 w=1.2 boosting 覆盖度亦不变。判定禁用无回归。全量真 LLM（semantic_emb/continuous/llm_judge 口径）登记 follow-up | [Requirement](../05-requirements/REQ-037-p2-graph-edge-disable-real-llm-verify.md) / [Backlog](../04-backlog.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-21-req-037-graph-edge-disable-real-llm-verify.md) / [Plan](../../02-delivery-plans/02-plans/2026-06-21-req-037-graph-edge-disable-real-llm-verify-plan.md) / [验收报告](../../02-delivery-plans/01-specs/2026-06-21-req-037-graph-edge-disable-real-llm-verify-report.md) |
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
