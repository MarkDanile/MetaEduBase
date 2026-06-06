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
| 暂无 | ⚫ 待办 | - | - | 当前没有已开工任务。 | 从“下一批候选任务”或用户指定任务开工。 | - |

## 下一批候选任务

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/03-engineering-governance/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| 暂无 | ⚫ 待办 | - | - | 当前没有近期候选任务。 |

## 最近完成

最近完成区最多保留 5 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超出 5 行的已完成任务应归档到 `docs/03-engineering-governance/work-log.md` 单行索引 + 段落归档，本表只承担"最近 5 个工作窗口"的角色。详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-07 | DOC-023 补齐 Claude / Trae 流程级跳转入口 | 🟢 完成 | `.claude/rules` 与 `.trae/rules` 增加 currentWork、workflow、taskModes、technicalDebt、productPlanning、deliveryPlans 轻量入口，仍不复制规则正文。 | [Workflow](workflow.md) / [Docs Rules](01-rules/docs.md) |
| 2026-06-07 | DOC-022 复核技术债到交付闭环与插件输出门禁 | 🟢 完成 | 补强 TD 到 spec/plan 的判定、规划层与交付层边界、superpower/插件输出路径规则，并让文档门禁阻断旧 docs 路径复活。 | [Workflow](workflow.md) / [Quality Gates](01-rules/quality-gates.md) |
| 2026-06-07 | DOC-021 docs 子层目录编号排序 | 🟢 完成 | 规划层、交付层和工程治理子目录按阅读顺序编号；核心工程入口文件保持稳定名称。 | [Docs](../README.md) / [Planning](../01-product-planning/README.md) |
| 2026-06-07 | DOC-020 docs 分层目录完全迁移 | 🟢 完成 | `docs/` 改为语义编号四层目录，迁移旧文档路径并更新 AI 入口、规则索引和文档门禁。 | [Docs](../README.md) / [Rules](01-rules/docs.md) |
| 2026-06-07 | DOC-019 建立产品规划层与复盘入口 | 🟢 完成 | 新增 `docs/01-product-planning/*` 四层规划入口与 `retrospectives` 复盘入口，并同步工作流、任务模式和文档门禁。 | [Product](../01-product-planning/README.md) / [Retro](03-retrospectives/README.md) |
