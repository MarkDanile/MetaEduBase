# 当前开发工作台

本文件是所有 AI IDE、插件和人工协作的当前任务入口。开始任何开发任务前，先阅读本文件，再按任务卡片中的链接渐进式读取相关 spec、plan、技术债或架构约束。

不同任务类型的开工条件、必读文档和完成标准见 `docs/03-engineering-governance/task-modes.md`。

## 使用规则

- 本文件只保留当前任务、近期候选和少量最近完成任务；详细规则见 `docs/03-engineering-governance/01-rules/workbench.md`。
- 开发前确认本次任务卡片，并按卡片链接渐进式读取 spec、plan、技术债或架构约束。
- 涉及跨文件开发、计划接力、状态交接或后续继续开发时，必须登记或更新任务卡片。
- 代码、验证或 Git 阶段变化后，必须同步任务状态、当前进展、下一步和验证结果。
- 提交、PR、合并或声明完成前，运行 `scripts/check-engineering-docs` 并执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`；门禁主实现位于 `scripts/engineering/check_engineering_docs.py`。

## 当前进行中

| 任务 | 状态 | 优先级 | 领域 | 当前进展 | 下一步 | 验证 |
|------|------|--------|------|----------|--------|------|
| BUG-002 修复登录后主面板外边距巨大、内容区过小 | 🟡 进行中 | P1 | Frontend | TD-008 引入的 `ui-page-shell`（max-width 1120px + margin auto）在 LayoutView 包裹 RouterView，与各 View 自带 max-w 嵌套冲突，导致大屏巨大外边距、宽屏 1600 视图被卡到 1120。修复：移除 max-width: 1120px; margin: 0 auto，保留 width/padding/background。`pnpm typecheck` / `pnpm lint` / `pnpm build` 退出 0；产物 CSS 确认 `ui-page-shell{width:100%;padding:var(--spacing-page);background:var(--color-bg-base)}`。 | 创建 PR、合并到 main、回填工作日志 | 见 [Backlog](../01-product-planning/04-backlog.md) |

## 下一批候选任务

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/03-engineering-governance/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| REQ-005 结构化抽取嵌套结构稳定性验收 | ⚫ 候选 | P1 | Product / Document / Contract | 建立 object / array / table 抽取结果样例回归。 |
| REQ-006 P1 知识资产处理链路最终演示验收 | ⚫ 候选 | P1 | Product / Document / AI / Testing | 先修复本机 `metaedu_test` 连通性，再组织上传/解析/抽取/图谱/RAG 问答/来源展示的端到端演示。 |

## 最近完成

最近完成区最多保留 5 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超出 5 行的已完成任务应归档到 `docs/03-engineering-governance/work-log.md` 单行索引 + 段落归档，本表只承担"最近 5 个工作窗口"的角色。详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-09 | DOC-045 修正 TD-033 CSS 拆分交付声明与追踪证据 | 🟢 完成 | 弱化 TD-033 任务卡 4 处"零 CSS 字节变化 / build output identical"过强声明；6 处事实源补 `PR #103` / `25ca165` 追踪；显式登记 TD-033 未建 spec / plan 的处置方式（事后不补建）。docs-only，`check-engineering-docs` 退出码 0。 | [Work Log](work-log.md) / [TD-033 Delivery Record](technical-debt.md#td-033) / [PR #106](https://github.com/MarkDanile/MetaEduBase/pull/106) |
| 2026-06-09 | DOC-048 增加评审高分质量校准规则 | 🟢 完成 | 最近 5 条评审平均分 >92 时，阶段复盘必须抽查评分是否偏宽；发现问题需在评分总账标记并登记 follow-up。 | [Review Scorecard](01-rules/review-scorecard.md#高分质量校准) / [Retrospectives](04-retrospectives/README.md) |
| 2026-06-09 | DOC-047 建立评审评分总账与落盘规则 | 🟢 完成 | 新增评审评分总账，回填 TD-033 评分 81；复杂评审后必须把总分、follow-up、流程扣分点和规则改进结论落盘。 | [Review Score Log](04-retrospectives/review-score-log.md) / [Review Scorecard](01-rules/review-scorecard.md) |
| 2026-06-09 | DOC-046 修正 P1 轨道 B 检索 / 抽取质量展示 | 🟢 完成 | 给轨道 B 增加可视化状态列，保留“实现事实 / 验证结论”证据分栏；不改变真实验收结论。 | [P1 Milestone](../01-product-planning/02-milestones/01-validation-phase.md#轨道-b检索--抽取质量) |
| 2026-06-09 | TD-033 拆分 `main.css` 设计系统级 CSS 模块 | 🟢 完成 | 纯机械拆分：`main.css` 1343 → 9 行（`@import` 入口）+ 8 个模块文件（≤500 行/个）；以 `pnpm typecheck / lint / build` 退出码 0 + `git diff --check` 退出码 0 为依据（Vite 产物未做 hash / diff 对比）。`check-engineering-docs` 通过。 | [Technical Debt](technical-debt.md#td-033) / [TD-032 Baseline](02-baselines/td-032-source-file-sizes.md) / [PR #103](https://github.com/MarkDanile/MetaEduBase/pull/103) (`25ca165`) |
