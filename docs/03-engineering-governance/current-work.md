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
| TD-032 baseline 刷新（切片 1-4 收口后回写） | 🟡 进行中 | P3 | 工程治理 | 切片 1-4 全部合并后行数重扫；`td-032-source-file-sizes.md` 已写：合规样例扩展 5 项 / 新增 `FileDetailView.vue` 416 候选 / 新增「切片 5+ 候选清单」段（router 494 + LibraryView 490 + FileDetailView 416 + main.css 1343） | 任务卡登记 → commit + push → backfill 4 处 docs | `scripts/check-engineering-docs` 退出码 0 |

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
| 2026-06-08 | TD-032 4 切片整体收口 | 🟢 完成 | 切片 1-4 全部合并。 | [Technical Debt](technical-debt.md#td-032-治理超大源码文件并建立文件规模拆分原则) |
| 2026-06-08 | DOC-039 增强工程文档脚本门禁 | 🟢 完成 | `scripts/check-engineering-docs` 新增稳定编号、Backlog Done 入账、入口同步和脚本候选清单反查；测试基线迁到新 docs 目录并补 5 个回归用例。 | [Quality Gates](01-rules/quality-gates.md) / `scripts/engineering/check_engineering_docs.py` / `tests/engineering/test_check_engineering_docs.py` / [Backlog](../01-product-planning/04-backlog.md) |
| 2026-06-08 | DOC-038 恢复基础工程原则为单一事实源 | 🟢 完成 | 新增 `engineering-principles.md`，入口和 IDE 兼容规则只保留链接，恢复先想后写、极简主义、手术式改动和目标驱动原则。 | [Engineering Principles](01-rules/engineering-principles.md) / `AGENTS.md` / `CLAUDE.md` / [Backlog](../01-product-planning/04-backlog.md) |
| 2026-06-08 | DOC-037 规则入口瘦身与脚本门禁候选清单整理 | 🟢 完成 | 压缩 `AGENTS.md` / `CLAUDE.md` 为导航入口；确认 `.claude/rules/*` 与 `.trae/rules/*` 保持跳转入口；新增脚本门禁候选清单；不改业务代码。 | `AGENTS.md` / `CLAUDE.md` / [Quality Gates](01-rules/quality-gates.md) / [Backlog](../01-product-planning/04-backlog.md) |
| 2026-06-08 | DOC-036 收口 DOC-034 遗留的 REQ-008 spec 前文旧口径 | 🟢 完成 | 修正 REQ-008 spec 第 21 行 `教案\nabc` 的旧 `layer == "none"` 表述，统一为 `layer == "L3"` + `template is None` + below threshold；不改代码。 | `docs/02-delivery-plans/01-specs/2026-W23-req-008-req-004-quality-follow-up.md` / `docs/01-product-planning/04-backlog.md` |
