# 当前开发工作台

本文件是所有 AI IDE、插件和人工协作的当前任务入口。开始任何开发任务前，先阅读本文件，再按任务卡片中的链接渐进式读取相关 spec、plan、技术债或架构约束。

不同任务类型的开工条件、必读文档和完成标准见 `docs/engineering/task-modes.md`。

## 使用规则

- 本文件只保留当前任务、近期候选和少量最近完成任务；详细规则见 `docs/engineering/rules/workbench.md`。
- 开发前确认本次任务卡片，并按卡片链接渐进式读取 spec、plan、技术债或架构约束。
- 涉及跨文件开发、计划接力、状态交接或后续继续开发时，必须登记或更新任务卡片。
- 代码、验证或 Git 阶段变化后，必须同步任务状态、当前进展、下一步和验证结果。
- 提交、PR、合并或声明完成前，运行 `scripts/check-engineering-docs` 并执行 `docs/engineering/rules/quality-gates.md#完成门禁`；门禁主实现位于 `scripts/engineering/check_engineering_docs.py`。

## 当前进行中

当前无进行中任务。

## 下一批候选任务

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/engineering/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| TD-023 收口 TD-020 文档一致性、断链与归档索引 | 🔵 就绪 | P2 | Docs / 工程流程 / 跨 AI 交接 | 修正 TD-020 spec 行为描述、plan 断链、work-log DOC-011 索引丢失和全量 pytest 声明证据不足；按 `technical-debt.md#td-023` 验证。 |

## 最近完成

最近完成区只保留摘要，详细验证、行为变化、PR 描述和复盘见 `docs/engineering/work-log.md`、对应技术债总账、plan 或 PR。

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-05 | DOC-012 工程文档自动门禁与工作台瘦身 | 🟢 完成 | 新增工程文档门禁，主实现收敛到 `scripts/engineering/check_engineering_docs.py`，`scripts/check-engineering-docs` 保留稳定兼容入口；工作台详细规则迁入 `rules/workbench.md`；首次运行修复 TD-004 历史 plan 断链。 | [Spec](../specs/2026-06-05-doc-012-engineering-doc-gates-and-workbench-slimming.md) / [Plan](../plans/2026-06-05-doc-012-engineering-doc-gates-and-workbench-slimming-plan.md) |
| 2026-06-05 | TD-020 统一 LLM provider resolver 与 factory 优先级事实源 | 🟢 完成 | `factory` 暴露 `RESOLVER_PROVIDER_NAMES` + `resolver_default_provider()`；`provider_resolver` 改为薄壳复用 factory 事实源；新增 `tests/shared/test_factory.py` 与 2 个 resolver 用例；零业务行为变化。 | [docs/engineering/technical-debt.md#td-020-统一-llm-provider-resolver-与-factory-优先级事实源](technical-debt.md) / [PR #46](https://github.com/MarkDanile/MetaEduBase/pull/46) |
| 2026-06-05 | DOC-011 技术债总账结构化展示优化 | 🟢 完成 | `technical-debt.md` 增加任务总览表和结构化任务卡片；长 `备注` 压缩为交付记录、事实源和验证摘要，降低扫视成本。 | `docs/engineering/technical-debt.md` |
| 2026-06-05 | DOC-010 收敛完成门禁并瘦身重复流程规则 | 🟢 完成 | 将通用收尾检查集中到 `quality-gates.md#完成门禁` 6 项；`workflow.md`、`task-modes.md`、`git-workflow.md` 和 AI 入口文件改为引用，减少重复规则和 token 开销。 | `docs/engineering/rules/quality-gates.md#完成门禁` |
| 2026-06-05 | TD-022 收口早期已完成计划文件的活动式未勾选项 | 🟢 完成 | 5 个早期 plan（TD-004/005/006/007/015）顶部补交付历史段，154 行 `- [ ]` → `- [x]`，与 TD-021 收口 TD-016/017/018/019 模式一致。 | `docs/engineering/technical-debt.md#td-022-收口早期已完成计划文件的活动式未勾选项` / [PR #44](https://github.com/MarkDanile/MetaEduBase/pull/44) |
