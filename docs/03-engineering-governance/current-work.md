# 当前开发工作台

本文件是所有 AI IDE、插件和人工协作的当前任务入口。开始任何开发任务前，先阅读本文件，再按任务卡片中的链接渐进式读取相关 spec、plan、技术债或架构约束。

不同任务类型的开工条件、必读文档和完成标准见 `docs/03-engineering-governance/task-modes.md`。

## 使用规则

- 本文件只保留当前任务、近期候选和少量最近完成任务；任何修改本文件或任务状态前，必须先读 `docs/03-engineering-governance/01-rules/workbench.md`。
- 开发前确认本次任务卡片，并按卡片链接渐进式读取 spec、plan、技术债或架构约束。
- 涉及跨文件开发、计划接力、状态交接或后续继续开发时，必须登记或更新任务卡片。
- 代码、验证或 Git 阶段变化后，必须同步任务状态、当前进展、下一步和验证结果。
- 提交、PR、合并或声明完成前，运行 `scripts/check-engineering-docs` 并执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`；门禁主实现位于 `scripts/engineering/check_engineering_docs.py`。

## 当前进行中

暂无。

## 下一批候选任务

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| [REQ-018](../01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md) P2 4 通道并行召回与图谱关系召回 | 🟣 Shaping | P0 | RAG / Graph / AI Chat / P2 | 建议下一步优先塑形 spec/plan：确认独立 `knowledge_edges` recall 如何回源 chunk / section。 |
| [REQ-017](../01-product-planning/05-requirements/REQ-017-p2-rrf-weighted-fusion.md) P2 RRF / Weighted RRF 融合排序收口 | 🟣 Shaping | P0 | RAG / Ranking / AI Chat / P2 | RRF 已默认接入；在 REQ-018 边界明确后进入 spec/plan，重点补 weighted 配置、4 通道排序验收和真实样例回归。 |
| [REQ-016](../01-product-planning/05-requirements/REQ-016-p2-llm-hybrid-ner-query-understanding.md) P2 LLM 混合 NER / Query Understanding | 🟣 Shaping | P0 | NER / Query Understanding / AI Chat / P2 | 在 trace / 召回 / 排序基线清楚后推进，优先定义 schema、触发条件和真实问法回归。 |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-17 | DOC-070 AtomAIBase 项目定位与 README 对外介绍升级 | 🟢 完成 | PR #322 squash merge `e72852b`：README 改为 AtomAIBase 开源项目主页结构；根包描述和顶层架构定位同步；对外介绍保持泛行业定位 | [Backlog](../01-product-planning/04-backlog.md) / [PR #322](https://github.com/MarkDanile/MetaEduBase/pull/322) |
| 2026-06-17 | DOC-069 P2 阶段正式启动与重点任务规划 | 🟢 完成 | PR #320 merge `33c132f`：P1 Done、P2 Doing；REQ-016/017/018 入账并完成代码事实校准 | [P2 Milestone](../01-product-planning/02-milestones/02-growth-phase.md) / [PR #320](https://github.com/MarkDanile/MetaEduBase/pull/320) |
| 2026-06-17 | P2-SEARCH PostgreSQL tsvector + 中文分词搜索增强 | 🟢 完成 | PR #318 merge `7d2a826` 收口：TD-047 PR #192（基础设施）+ REQ-012 PR #216（运行时检索切 chinese_zh + plainto_tsquery）+ REQ-014 PR #308 + REQ-015 PR #314（端到端验收） | [Milestone P2](../01-product-planning/02-milestones/02-growth-phase.md) / [TD-047](technical-debt.md#td-047) / [PR #318](https://github.com/MarkDanile/MetaEduBase/pull/318) |
| 2026-06-17 | BUG-010 AI Chat 自然问法未稳定命中函数参数正文 chunk | 🟢 完成 | PR #316 merge `b753d3a`：确定性 query normalizer + 函数参数术语拆分回归已合并，A/B 等价问法共享核心检索词 | [BUG-010](../01-product-planning/05-requirements/BUG-010-ai-chat-query-normalizer-function-parameter-question.md) / [PR #316](https://github.com/MarkDanile/MetaEduBase/pull/316) |
| 2026-06-17 | REQ-015 RAG 生产链路 grounding 与真实验收收口 | 🟢 完成 | PR #314 merge `4d78667`：生产 RAG 默认链路、真实 dev DB、授权 DeepSeek ask 与状态事实源已收口 | [REQ-015](../01-product-planning/05-requirements/REQ-015-rag-production-grounding-closure.md) / [PR #314](https://github.com/MarkDanile/MetaEduBase/pull/314) |
| 2026-06-17 | BUG-009 AI Chat 真实 PG 链路未把相关正文 chunk 送入 prompt | 🟢 完成 | PR #314 merge `4d78667`：修 AsyncSession 顺序检索、RRF 阈值、lexical supplement 排序和 TOC 邻居识别 | [BUG-009](../01-product-planning/05-requirements/BUG-009-ai-chat-rag-retrieval-context-pipeline-real-pg-failure.md) / [PR #314](https://github.com/MarkDanile/MetaEduBase/pull/314) |
| 2026-06-17 | BUG-008 Context Packer 引入 structlog 依赖但 pyproject 未声明 | 🟢 完成 | PR #310 merge `65c67f58`：pyproject + `structlog>=24.1.0`；478 pytest 0 业务代码回归 | [BUG-008](../01-product-planning/05-requirements/BUG-008-context-packer-structlog-dep-missing.md) / [PR #310](https://github.com/MarkDanile/MetaEduBase/pull/310) |
| 2026-06-16 | REQ-014 RAG 真实 PG 样例、数据回填与回答 grounding 验收 | 🟢 完成 | PR #308 merge `86f2f05`：spec + plan + 5-子命令验收脚本 + 占位报告 | [REQ-014](../01-product-planning/05-requirements/REQ-014-rag-real-pg-grounding-and-data-backfill-validation.md) / [PR #308](https://github.com/MarkDanile/MetaEduBase/pull/308) |
| 2026-06-16 | REQ-013 RAG Context Packer 与回答 grounding 增强 | 🟢 完成 | PR #305 squash merge：context_packer.py 新建、neighbor/section/graph expansion、TOC guard、prompt builder 接入；17 mock tests 100% pass。Slice 5 真实 PG 样例待 backfill。 | [REQ-013](../01-product-planning/05-requirements/REQ-013-rag-context-packer-and-grounded-answering.md) / [Spec](../02-delivery-plans/01-specs/2026-06-16-req-013-rag-context-packer.md) / [PR #305](https://github.com/MarkDanile/MetaEduBase/pull/305) |
| 2026-06-16 | BUG-007 pdf_parser sections path 错乱（font-size + 中文正则 level 混用）| 🟢 完成 | PR #303 squash merge：section path 改用 docling counters 算法 + 非标题黑名单补全。mock tests pass。 | [BUG-007](../01-product-planning/05-requirements/BUG-007-pdf-parser-section-path-inconsistency.md) / [PR #303](https://github.com/MarkDanile/MetaEduBase/pull/303) |
| 2026-06-15 | BUG-006 #5 文件详情页返回按钮（router.replace + type=button）| 🟢 完成 | PR #301 squash merge：goBack 改用 router.replace 避免 Vue Query polling 竞态；3 按钮加 type=button。4 vitest + 68/68 frontend 0 回归。 | [BUG-006 #5](../01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md) / [PR #301](https://github.com/MarkDanile/MetaEduBase/pull/301) |
| 2026-06-15 | BUG-006 #3 嵌套 schema 描述 + few-shot 前移 + 截断扩展 | 🟢 完成 | PR #300 squash merge：build_fields_desc 递归 array items children；few-shot 前移到文档内容前；_example 用真实 key + 递归子项；chunks_text 6000→10000。22/22 prompt tests + 439/439 全量 0 回归。 | [BUG-006 #3](../01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md) / [PR #300](https://github.com/MarkDanile/MetaEduBase/pull/300) |
| 2026-06-15 | BUG-006 #2 pdf_parser 中文章节标题（正则 fallback）| 🟢 完成 | PR #299 squash merge：新增 _detect_chinese_heading_level + 5 类正则模式作为 font-size+bold fallback。11/11 新 pytest + 448/448 全量 0 回归。 | [BUG-006 #2](../01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md) / [PR #299](https://github.com/MarkDanile/MetaEduBase/pull/299) |
| 2026-06-15 | BUG-006 #1 模板抽取页面字段名渲染 label（递归 children + keyPath + multi-template）| 🟢 完成 | PR #297 squash merge：抽 getTemplateFieldLabel 到 utils/templateLabels.ts；3 轮迭代。9 vitest + 64/64 frontend 0 回归。 | [BUG-006 #1](../01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md) / [PR #297](https://github.com/MarkDanile/MetaEduBase/pull/297) |
| 2026-06-15 | BUG-006 #4 KG > 50 节点白屏（kg-bundle 原子端点）| 🟢 完成 | PR #295 squash merge：后端新增 GET /api/v1/knowledge/files/{file_id}/kg-bundle。3 PG pytest + 437 mock pytest 0 回归 + 真 PG 复测 3 文件 dangling=0。 | [BUG-006 #4](../01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md) / [PR #295](https://github.com/MarkDanile/MetaEduBase/pull/295) |
| 2026-06-14 | TD-054 chunker 内部 char_offset / local_offset 同步修复（round 2+3）| 🟢 完成 | PR #289 + #290 squash merge：chunker 主循环 + 合并分支 + _split_oversized_chunk pos 同步。10/10 mock pytest + 439 mock pytest 0 业务代码回归。真 PG 复测 28 chunks offset_overlaps 23/28 (82.14%) → 0/28 (0.00%)。 | [TD-054](technical-debt.md#td-054) / [PR #289](https://github.com/MarkDanile/MetaEduBase/pull/289) + [PR #290](https://github.com/MarkDanile/MetaEduBase/pull/290) |
