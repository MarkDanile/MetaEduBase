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

| 任务 | 状态 | 优先级 | 领域 | 当前进展 | 下一步 | 验证 |
|------|------|--------|------|----------|--------|------|
| REQ-022 登录页品牌氛围与工作区画布白灰层级优化 | 🟡 进行中 | P1 | Frontend / Theme / Design System | 分支 `req-022-login-workspace-polish`；登录页浅蓝渐变、细网格、能力标签和柔和白灰工作区画布已实现；设计规则已同步 | 提交 PR 并合并；合并后回填 Done / work-log / 最近完成 | typecheck / lint / build / check-engineering-docs / diff check 通过；`/login` light 浏览器 smoke 通过 |
| REQ-018 P2 4 通道并行召回与图谱关系召回 | 🟢 完成 | P0 | RAG / Graph / AI Chat | Slice 1+2+3 PR #333/#334/#335 已合并：PgEdgeRetriever骨架 + 4通道注入 + trace/dedup 验证通过；Slice 4 待 dev DB knowledge_edges 数据 | Slice 4：真实PG验收报告（依赖 dev DB 有边数据） | — |
| REQ-017 RRF / Weighted RRF 融合排序收口 | 🟡 进行中 | P0 | RAG / Ranking / AI Chat | Slice 1-3 PR #325 已合并：配置入口 + fusion diagnostics + 通道降级。Slice 4（真实 PG 样例 RRF 排序分析）待 REQ-015 PG 环境 backfill | Slice 4：RRF 排序分析脚本；依赖 REQ-015 真实 PG 环境 | 待 REQ-015 backfill |

## 下一批候选任务

（暂无）

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-18 | REQ-021 浅色主题加入克制蓝色点缀 | 🟢 完成 | PR #340 squash merge `5a13c3a`：主按钮改克制蓝色语义 token，Logo / 登录页品牌 mark 改中性底 + 蓝色小图标，设计规则明确蓝色为唯一交互点缀；前端 typecheck/lint/build + `/login` light smoke 通过 | [REQ-021](../01-product-planning/05-requirements/REQ-021-blue-accent-visual-polish.md) / [PR #340](https://github.com/MarkDanile/MetaEduBase/pull/340) |
| 2026-06-18 | REQ-020 Codex / Trae-like 中性双主题视觉收敛 | 🟢 完成 | PR #338 squash merge `d4017d2`：收口为 light/dark 双主题，历史主题值迁移到 light，用户菜单提供轻量切换；新增 theme store 回归测试；前端 typecheck/lint/build/theme.spec + 浏览器 smoke 通过 | [REQ-020](../01-product-planning/05-requirements/REQ-020-codex-trae-neutral-dual-theme.md) / [PR #338](https://github.com/MarkDanile/MetaEduBase/pull/338) |
| 2026-06-18 | REQ-019 单主题视觉风格收敛 | 🟢 完成 | PR #336 squash merge `c3d3ab1`：统一为 paper 单主题，移除用户可见主题切换，旧主题入口映射到同一套暖纸墨韵 token；前端 typecheck/lint/build + 浏览器烟测通过 | [REQ-019](../01-product-planning/05-requirements/REQ-019-single-paper-theme-visual-alignment.md) / [PR #336](https://github.com/MarkDanile/MetaEduBase/pull/336) |
| 2026-06-18 | REQ-018 P2 4 通道并行召回收口 | 🟢 完成 | PR #333/#334/#335 squash merge：PgEdgeRetriever骨架 + 4通道注入AIChatService + trace/dedup验证 + 9 mock tests；131 knowledge tests 0 回归；验收报告placeholder已产出；Slice 4（真PG）待dev DB边数据 | [REQ-018](../01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md) / [Spec](../02-delivery-plans/01-specs/2026-06-18-req-018-p2-four-channel-graph-edge-recall.md) / [Plan](../02-delivery-plans/02-plans/2026-06-18-req-018-p2-four-channel-graph-edge-recall-plan.md) / [PR #333](https://github.com/MarkDanile/MetaEduBase/pull/333) / [PR #334](https://github.com/MarkDanile/MetaEduBase/pull/334) / [PR #335](https://github.com/MarkDanile/MetaEduBase/pull/335) |
| 2026-06-17 | REQ-016 P2 LLM 混合 NER / Query Understanding 收口 | 🟢 完成 | PR #328/#329/#330 merge：HybridQueryUnderstandingService（规则优先 + LLM 低置信触发）+ NERResult.expanded_query + AIChatService diagnostics + keyword/vector retrievers 使用 expanded_query；70 tests 0 回归；验收报告 placeholder 已产出 | [REQ-016](../01-product-planning/05-requirements/REQ-016-p2-llm-hybrid-ner-query-understanding.md) / [Spec](../02-delivery-plans/01-specs/2026-06-17-req-016-llm-hybrid-ner.md) / [Plan](../02-delivery-plans/02-plans/2026-06-17-req-016-llm-hybrid-ner-plan.md) |
| 2026-06-17 | DOC-070 AtomAIBase 项目定位与 README 对外介绍升级 | 🟢 完成 | PR #322 squash merge `e72852b`：README 改为 AtomAIBase 开源项目主页结构；根包描述和顶层架构定位同步；对外介绍保持泛行业定位 | [Backlog](../01-product-planning/04-backlog.md) / [PR #322](https://github.com/MarkDanile/MetaEduBase/pull/322) |
| 2026-06-17 | DOC-069 P2 阶段正式启动与重点任务规划 | 🟢 完成 | PR #320 merge `33c132f`：P1 Done、P2 Doing；REQ-016/017/018 入账并完成代码事实校准 | [P2 Milestone](../01-product-planning/02-milestones/02-growth-phase.md) / [PR #320](https://github.com/MarkDanile/MetaEduBase/pull/320) |
| 2026-06-17 | P2-SEARCH PostgreSQL tsvector + 中文分词搜索增强 | 🟢 完成 | PR #318 merge `7d2a826` 收口：TD-047 PR #192（基础设施）+ REQ-012 PR #216（运行时检索切 chinese_zh + plainto_tsquery）+ REQ-014 PR #308 + REQ-015 PR #314（端到端验收） | [Milestone P2](../01-product-planning/02-milestones/02-growth-phase.md) / [TD-047](technical-debt.md#td-047) / [PR #318](https://github.com/MarkDanile/MetaEduBase/pull/318) |
| 2026-06-17 | BUG-010 AI Chat 自然问法未稳定命中函数参数正文 chunk | 🟢 完成 | PR #316 merge `b753d3a`：确定性 query normalizer + 函数参数术语拆分回归已合并，A/B 等价问法共享核心检索词 | [BUG-010](../01-product-planning/05-requirements/BUG-010-ai-chat-query-normalizer-function-parameter-question.md) / [PR #316](https://github.com/MarkDanile/MetaEduBase/pull/316) |
| 2026-06-17 | REQ-015 RAG 生产链路 grounding 与真实验收收口 | 🟢 完成 | PR #314 merge `4d78667`：生产 RAG 默认链路、真实 dev DB、授权 DeepSeek ask 与状态事实源已收口 | [REQ-015](../01-product-planning/05-requirements/REQ-015-rag-production-grounding-closure.md) / [PR #314](https://github.com/MarkDanile/MetaEduBase/pull/314) |
| 2026-06-17 | BUG-009 AI Chat 真实 PG 链路未把相关正文 chunk 送入 prompt | 🟢 完成 | PR #314 merge `4d78667`：修 AsyncSession 顺序检索、RRF 阈值、lexical supplement 排序和 TOC 邻居识别 | [BUG-009](../01-product-planning/05-requirements/BUG-009-ai-chat-rag-retrieval-context-pipeline-real-pg-failure.md) / [PR #314](https://github.com/MarkDanile/MetaEduBase/pull/314) |
| 2026-06-17 | BUG-008 Context Packer 引入 structlog 依赖但 pyproject 未声明 | 🟢 完成 | PR #310 merge `65c67f58`：pyproject + `structlog>=24.1.0`；478 pytest 0 业务代码回归 | [BUG-008](../01-product-planning/05-requirements/BUG-008-context-packer-structlog-dep-missing.md) / [PR #310](https://github.com/MarkDanile/MetaEduBase/pull/310) |
