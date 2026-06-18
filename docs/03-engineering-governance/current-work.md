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
| REQ-027 P2 弱召回知识覆盖与样例多样性 | 🟡 部分收口 | P0 | RAG / P2 / Real Validation / Data | 分支 `feat/req-027-weak-recall-knowledge-coverage`；requirement + spec + plan + 5 条 v2 样例（dev DB 校准：513 knowledge_edges 抽样职业面向链）+ wrapper 脚本 + 真 LLM v1+v2 两轮报告均已生成。质量层 P2 提升 ≥30% 仅 1/10 (10%)，AC-4 未达成；问题在自动覆盖度口径（子串匹配 + 真实 LLM 长答案同义改写），不在数据缺口（Q8 baseline 已 0.80） | REQ-028 接力自动质量比较口径改造（语义匹配 / LLM-as-judge 兜底）；本任务不翻完成 | wrapper 脚本 dry-run 两轮 exit 0；v1 复跑 1/5 与第一轮一致；v2 10 样例 4 scenario 全部跑通 |
| REQ-024 P2 真实验收补强：Query Understanding 与 graph_edge 补足样例 | 🔴 阻塞 | P0 | RAG / P2 / Real Validation | 分支 `codex/req-024-p2-real-validation`；TD-068 已澄清 vector fallback；REQ-025 / REQ-026 / REQ-027 已接力，但质量层真实改善证据仍不足 | REQ-028 接力自动质量比较口径；本任务不翻完成 | REQ-024 / REQ-025 / REQ-026 / REQ-027 real LLM 报告均已生成；真实效果仍未通过 |
| REQ-025 P2 graph_edge 进入 prompt 与真实 LLM 效果验收收口 | 🟣 待验证 | P0 | RAG / P2 / Real Validation | 分支 `feature/req-025-graph-edge-prompt-validation`；已让 `knowledge_edge` 回源 chunk 并保底进入 packed context；真实 LLM provider 已跑 | 完成本 PR 的代码与报告闭环；效果改善不足由 REQ-026 / REQ-027 / REQ-028 承接，不在本任务夸大完成 | 24 个相关 pytest 通过；ruff 指定文件通过；`--allow-llm` report 已生成，External LLM enabled |

## 下一批候选任务

| 任务 | 状态 | 优先级 | 领域 | 下一步 | 事实源 |
|------|------|--------|------|--------|--------|
| REQ-028 P2 弱召回自动质量比较口径改造 | ⚫ Candidate | P0 | RAG / P2 / Real Validation / Quality Metrics | REQ-027 real LLM v1+v2 报告：质量层 P2 提升 ≥30% 仅 1/10。问题不在数据缺口（Q8 baseline 已 0.80），而在子串匹配 + 真实 LLM 长答案同义改写导致覆盖度低。需引入：语义匹配 / 关键事实分项权重 / LLM-as-judge 兜底（仅作为 secondary signal） | [REQ-027 Report v2](../02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v2-report.md) / [REQ-027 Report v1](../02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v1-report.md) |
| DOC-073 门禁脚本防绕过与规则修改范围校验 | 🔵 Ready | P1 | Governance / Quality Gates / Scripts | 评估并落地最小检查：非门禁治理任务不得修改门禁脚本、`KNOWN_ISSUES`、忽略列表或阈值来绕过当前失败 | [Backlog](../01-product-planning/04-backlog.md) / [Retro](04-retrospectives/2026-06-18-rules-stage-retrospective.md) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-18 | REQ-027 P2 弱召回知识覆盖与样例多样性 | 🟡 部分收口 | PR #359 squash merge `8310fca`：5 条 v2 样例 (dev DB 513 knowledge_edges 校准) + wrapper 脚本 + 真 LLM v1+v2 两轮报告。机制 10/10 ✅；prompt 5/10 ✅；质量 1/10 ❌ (AC-4 未达成)。Q8 baseline 已 0.80 → 数据够；问题在覆盖度口径；登记 REQ-028 接力 | [REQ-027](../01-product-planning/05-requirements/REQ-027-p2-weak-recall-knowledge-coverage.md) / [Report v2](../02-delivery-plans/01-specs/2026-06-18-req-027-rag-effect-comparison-v2-report.md) / [PR #359](https://github.com/MarkDanile/MetaEduBase/pull/359) |
| 2026-06-18 | REQ-026 P2 RAG 效果比较与弱召回样例集收口 | 🟡 部分收口 | PR #358 squash merge `930589b`：5 条弱召回样例集 + 关键事实覆盖度自动比较 + real LLM 报告。机制 5/5 ✅；prompt 3/5 ✅；质量 1/5 ❌ (AC-1 未达成，Q4 退化 -0.60)；登记 REQ-027 接力 | [REQ-026](../01-product-planning/05-requirements/REQ-026-p2-rag-effect-comparison-and-weak-recall-samples.md) / [Report](../02-delivery-plans/01-specs/2026-06-18-req-026-rag-effect-comparison-validation-report.md) / [PR #358](https://github.com/MarkDanile/MetaEduBase/pull/358) |
| 2026-06-18 | TD-068 AI Chat 真实验证中 query embedding 为空导致向量召回有效性不明 | 🟢 完成 | PR #355 squash merge `fdffd60`：确认 vector topN 是 keyword fallback；diagnostics / REQ-024 report 已显式透出 `embedding_fallback` 与 `vector fallback` 计数，REQ-025 后续验收必须据此判断 | [TD-068](technical-debt.md#td-068) / [Report](../02-delivery-plans/01-specs/2026-06-18-req-024-p2-real-validation-report.md) / [PR #355](https://github.com/MarkDanile/MetaEduBase/pull/355) |
| 2026-06-18 | DOC-072 工程规则阶段复盘与 follow-up 登记 | 🟢 完成 | PR #352 squash merge `e776fb6`：复盘 DOC-057~DOC-071 后的规则执行效果，登记 DOC-073 门禁防绕过和 DOC-074 AI/RAG 完成态口径收紧，并放入工作台候选区 | [Retro](04-retrospectives/2026-06-18-rules-stage-retrospective.md) / [PR #352](https://github.com/MarkDanile/MetaEduBase/pull/352) |
| 2026-06-18 | DOC-071 最近完成任务与 P2 里程碑评审收口 | 🟢 完成 | PR #350 squash merge `325ac35`：评审 DOC-069 后近期完成任务，重点复核 P2-SEARCH、BUG-009/010、REQ-016/017/018，修正 P2 状态漂移、补评分总账，并登记 REQ-024 作为 P2 真实验收补强 | [Review](04-retrospectives/2026-06-18-p2-recent-completion-review.md) / [REQ-024](../01-product-planning/05-requirements/REQ-024-p2-real-validation-query-understanding-and-graph-edge.md) / [PR #350](https://github.com/MarkDanile/MetaEduBase/pull/350) |
| 2026-06-18 | REQ-023 登录页左侧品牌面大胆蓝色视觉加强 | 🟢 完成 | PR #345 squash merge `9d02ba6`：登录页左侧由轻浅蓝调整为深浅蓝品牌面，增加网格、斜向光带和底部圆弧层次；右侧表单和登录后工作区未扩散 | [REQ-023](../01-product-planning/05-requirements/REQ-023-bolder-login-brand-panel.md) / [PR #345](https://github.com/MarkDanile/MetaEduBase/pull/345) |
| 2026-06-18 | REQ-022 登录页品牌氛围与工作区画布白灰层级优化 | 🟢 完成 | PR #343 squash merge `4c9d3a8`：登录页左侧增加浅蓝渐变、细网格和能力标签；登录后主工作区画布改为柔和白灰，卡片保持白色层级；前端 typecheck/lint/build + `/login` light smoke 通过 | [REQ-022](../01-product-planning/05-requirements/REQ-022-login-brand-and-workspace-canvas-polish.md) / [PR #343](https://github.com/MarkDanile/MetaEduBase/pull/343) |
| 2026-06-18 | BUG-011 数据要素模板 AI 生成 500 与 chat_with_model_fallback ValueError 处理缺陷 | 🟢 完成 | PR #342 squash merge：DeepSeek Key 已写入 .env；`chat_with_fallback.py` fast attempt 捕获 ValueError 降级至 fallback，fallback 的 ValueError 保持传播；6 fallback tests + 91 template tests 通过；待服务重启后重测 | [BUG-011](../01-product-planning/05-requirements/BUG-011-template-init-by-ai-500-and-valueerror-handling.md) / [PR #342](https://github.com/MarkDanile/MetaEduBase/pull/342) |
| 2026-06-18 | REQ-021 浅色主题加入克制蓝色点缀 | 🟢 完成 | PR #340 squash merge `5a13c3a`：主按钮改克制蓝色语义 token，Logo / 登录页品牌 mark 改中性底 + 蓝色小图标，设计规则明确蓝色为唯一交互点缀；前端 typecheck/lint/build + `/login` light smoke 通过 | [REQ-021](../01-product-planning/05-requirements/REQ-021-blue-accent-visual-polish.md) / [PR #340](https://github.com/MarkDanile/MetaEduBase/pull/340) |
| 2026-06-18 | REQ-020 Codex / Trae-like 中性双主题视觉收敛 | 🟢 完成 | PR #338 squash merge `d4017d2`：收口为 light/dark 双主题，历史主题值迁移到 light，用户菜单提供轻量切换；新增 theme store 回归测试；前端 typecheck/lint/build/theme.spec + 浏览器 smoke 通过 | [REQ-020](../01-product-planning/05-requirements/REQ-020-codex-trae-neutral-dual-theme.md) / [PR #338](https://github.com/MarkDanile/MetaEduBase/pull/338) |
| 2026-06-18 | REQ-019 单主题视觉风格收敛 | 🟢 完成 | PR #336 squash merge `c3d3ab1`：统一为 paper 单主题，移除用户可见主题切换，旧主题入口映射到同一套暖纸墨韵 token；前端 typecheck/lint/build + 浏览器烟测通过 | [REQ-019](../01-product-planning/05-requirements/REQ-019-single-paper-theme-visual-alignment.md) / [PR #336](https://github.com/MarkDanile/MetaEduBase/pull/336) |
| 2026-06-18 | REQ-018 P2 4 通道并行召回收口 | 🟢 完成 | PR #333/#334/#335 squash merge：PgEdgeRetriever骨架 + 4通道注入AIChatService + trace/dedup验证 + 9 mock tests；真实 PG 验收已补，graph_edge 激活且 evidence_id bug 修复；AC-5 弱召回补足样例由 REQ-024 接力 | [REQ-018](../01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md) / [Spec](../02-delivery-plans/01-specs/2026-06-18-req-018-p2-four-channel-graph-edge-recall.md) / [Plan](../02-delivery-plans/02-plans/2026-06-18-req-018-p2-four-channel-graph-edge-recall-plan.md) / [Report](../02-delivery-plans/01-specs/2026-06-18-req-018-four-channel-graph-edge-recall-validation-report.md) / [PR #333](https://github.com/MarkDanile/MetaEduBase/pull/333) / [PR #334](https://github.com/MarkDanile/MetaEduBase/pull/334) / [PR #335](https://github.com/MarkDanile/MetaEduBase/pull/335) |
| 2026-06-17 | REQ-016 P2 LLM 混合 NER / Query Understanding 收口 | 🟢 完成 | PR #328/#329/#330 merge：HybridQueryUnderstandingService（规则优先 + LLM 低置信触发）+ NERResult.expanded_query + AIChatService diagnostics + keyword/vector retrievers 使用 expanded_query；70 tests 0 回归；验收报告 placeholder 已产出 | [REQ-016](../01-product-planning/05-requirements/REQ-016-p2-llm-hybrid-ner-query-understanding.md) / [Spec](../02-delivery-plans/01-specs/2026-06-17-req-016-llm-hybrid-ner.md) / [Plan](../02-delivery-plans/02-plans/2026-06-17-req-016-llm-hybrid-ner-plan.md) |
| 2026-06-17 | DOC-070 AtomAIBase 项目定位与 README 对外介绍升级 | 🟢 完成 | PR #322 squash merge `e72852b`：README 改为 AtomAIBase 开源项目主页结构；根包描述和顶层架构定位同步；对外介绍保持泛行业定位 | [Backlog](../01-product-planning/04-backlog.md) / [PR #322](https://github.com/MarkDanile/MetaEduBase/pull/322) |
| 2026-06-17 | DOC-069 P2 阶段正式启动与重点任务规划 | 🟢 完成 | PR #320 merge `33c132f`：P1 Done、P2 Doing；REQ-016/017/018 入账并完成代码事实校准 | [P2 Milestone](../01-product-planning/02-milestones/02-growth-phase.md) / [PR #320](https://github.com/MarkDanile/MetaEduBase/pull/320) |
| 2026-06-17 | P2-SEARCH PostgreSQL tsvector + 中文分词搜索增强 | 🟢 完成 | PR #318 merge `7d2a826` 收口：TD-047 PR #192（基础设施）+ REQ-012 PR #216（运行时检索切 chinese_zh + plainto_tsquery）+ REQ-014 PR #308 + REQ-015 PR #314（端到端验收） | [Milestone P2](../01-product-planning/02-milestones/02-growth-phase.md) / [TD-047](technical-debt.md#td-047) / [PR #318](https://github.com/MarkDanile/MetaEduBase/pull/318) |
| 2026-06-17 | BUG-010 AI Chat 自然问法未稳定命中函数参数正文 chunk | 🟢 完成 | PR #316 merge `b753d3a`：确定性 query normalizer + 函数参数术语拆分回归已合并，A/B 等价问法共享核心检索词 | [BUG-010](../01-product-planning/05-requirements/BUG-010-ai-chat-query-normalizer-function-parameter-question.md) / [PR #316](https://github.com/MarkDanile/MetaEduBase/pull/316) |
| 2026-06-17 | REQ-015 RAG 生产链路 grounding 与真实验收收口 | 🟢 完成 | PR #314 merge `4d78667`：生产 RAG 默认链路、真实 dev DB、授权 DeepSeek ask 与状态事实源已收口 | [REQ-015](../01-product-planning/05-requirements/REQ-015-rag-production-grounding-closure.md) / [PR #314](https://github.com/MarkDanile/MetaEduBase/pull/314) |
| 2026-06-17 | BUG-009 AI Chat 真实 PG 链路未把相关正文 chunk 送入 prompt | 🟢 完成 | PR #314 merge `4d78667`：修 AsyncSession 顺序检索、RRF 阈值、lexical supplement 排序和 TOC 邻居识别 | [BUG-009](../01-product-planning/05-requirements/BUG-009-ai-chat-rag-retrieval-context-pipeline-real-pg-failure.md) / [PR #314](https://github.com/MarkDanile/MetaEduBase/pull/314) |
| 2026-06-17 | BUG-008 Context Packer 引入 structlog 依赖但 pyproject 未声明 | 🟢 完成 | PR #310 merge `65c67f58`：pyproject + `structlog>=24.1.0`；478 pytest 0 业务代码回归 | [BUG-008](../01-product-planning/05-requirements/BUG-008-context-packer-structlog-dep-missing.md) / [PR #310](https://github.com/MarkDanile/MetaEduBase/pull/310) |
