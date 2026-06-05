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
| TD-009 减少前后端契约漂移 | ⚫ 待办 | P2 | API / 类型 | 选高价值契约族（模板字段或任务状态），建共享 schema 检查。 |

## 最近完成

最近完成区只保留摘要，详细验证、行为变化、PR 描述和复盘见 `docs/engineering/work-log.md`、对应技术债总账、plan 或 PR。

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-05 | TD-028 业务视图与共享组件的 `liquid-input` / `liquid-btn-*` / `liquid-tag-*` / `liquid-dialog*` 存量替换 | 🟢 完成 | 12 文件 119 处 `liquid-input` / `liquid-btn*` / `liquid-btn-primary/ghost/danger` / `liquid-tag*` / `liquid-tag-blue/green/amber/purple` / `liquid-dialog*` / `liquid-dialog-overlay` 全部 token-for-token 1:1 替换为 TD-027（PR #59）建立的 `ui-*` 原子控件共享类，含 5 处 `\`liquid-tag-${color}\`` 模板字符串迁移到 `\`ui-tag-${color}\``。`ui-*` 与 `liquid-*` 在 `main.css` 中是 byte-identical 镜像，纯机械替换零视觉/行为变化。`HomeView` / `KGGraph` 0 处 `liquid-*` 残留（历史已清）跳过；`main.css` 中 `liquid-*` 声明保持兼容别名；`LoginView` 品牌背景仍例外保留；`liquid-card` / `liquid-card-scan` 装饰动效仍保留。 | [PR #61](https://github.com/MarkDanile/MetaEduBase/pull/61) |
| 2026-06-05 | TD-026 共享组件 `liquid-card` 残留验证 | 🟢 完成 | 严格 `rg "liquid-card"` 验证 4 个共享组件（`FieldEditor` / `KGDetailPanel` / `ConfirmDialog` / `KGGraph`）全部 0 命中。任务卡线索的"22 处"是 TD-008 完成时把所有 `liquid-*`（含 `liquid-input` / `liquid-btn-*` / `liquid-tag-*` / `liquid-dialog*`）都误计入 `liquid-card` 残留的快照。4 个共享组件里现有的 `liquid-input` / `liquid-btn-*` 等按 TD-008 规则保持兼容，**不**在本债范围；已拆为 TD-027（补 `ui-*` 等价共享类）+ TD-028（业务视图与共享组件存量替换）作为后续接力。 | `docs/engineering/technical-debt.md#td-026` |

## 最近完成

最近完成区只保留摘要，详细验证、行为变化、PR 描述和复盘见 `docs/engineering/work-log.md`、对应技术债总账、plan 或 PR。

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-05 | TD-008 明确从 `liquid-*` 类到语义 UI 层的迁移路径 | 🟢 完成 | `coding-style.md` 设计系统章节新增「迁移说明」段落（明确 `ui-*` 优先、`liquid-*` 兼容、5 个 `ui-*` 共享类用途、第一个迁移目标）；`main.css` 追加 `ui-page-shell / ui-panel / ui-toolbar / ui-interactive-row` 4 个 token 化共享类（不引入硬编码、不删 `liquid-*`）；`LayoutView` 的 `main` 容器切到 `ui-page-shell`；`PageHeader` 去掉 `wet-line` 装饰条 + `stagger-*` 动画 + `lineWidth/stagger` props（公共 API 收窄，调用方 `HomeView` 同步去掉 `:line-width`）；`EmptyState` 加 `ui-panel p-6` 容器，移除 `animate-slide-up stagger-1`。 | `docs/engineering/technical-debt.md#td-008-明确从-liquid--类到语义-ui-层的迁移路径` |

## 最近完成

最近完成区只保留摘要，详细验证、行为变化、PR 描述和复盘见 `docs/engineering/work-log.md`、对应技术债总账、plan 或 PR。

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-05 | TD-024 收口 TD-023 复核发现的副本文件与旧归一化表述 | 🟢 完成 | 删除未跟踪副本 `scripts/engineering/check_engineering_docs 2.py`（与正式实现 SHA-256 一致）；TD-020 spec §3.1/§4.2 改为 resolver 复用 `RESOLVER_PROVIDER_NAMES` + `resolver_default_provider()` 公开事实源且不复用 `factory._normalize_default_provider`；TD-020 plan 范围段与 TASK-1 风险段同步收口"翻译回 qwen / 优先复用 `_normalize_default_provider`"旧表述。 | `docs/engineering/technical-debt.md#td-024-收口-td-023-复核发现的副本文件与旧归一化表述` |
| 2026-06-05 | TD-023 收口 TD-020 文档一致性、断链与归档索引 | 🟢 完成 | 修正 TD-020 spec `dashscope → qwen` 行为描述（4.1/4.3/4.4 节，与 `factory.resolver_default_provider()` 实现和 `test_factory.py` 一致）；修复 plan Spec 断链（同级 → `../specs/`）；恢复 work-log DOC-011 索引；三份文档全量 pytest 声明补充"本地复跑 / `gh pr checks 46` no checks reported"。 | `docs/engineering/technical-debt.md#td-023-收口-td-020-文档一致性-断链与归档索引` |
| 2026-06-05 | DOC-012 工程文档自动门禁与工作台瘦身 | 🟢 完成 | 新增工程文档门禁，主实现收敛到 `scripts/engineering/check_engineering_docs.py`，`scripts/check-engineering-docs` 保留稳定兼容入口；工作台详细规则迁入 `rules/workbench.md`；首次运行修复 TD-004 历史 plan 断链。 | [Spec](../specs/2026-06-05-doc-012-engineering-doc-gates-and-workbench-slimming.md) / [Plan](../plans/2026-06-05-doc-012-engineering-doc-gates-and-workbench-slimming-plan.md) |
| 2026-06-05 | TD-020 统一 LLM provider resolver 与 factory 优先级事实源 | 🟢 完成 | `factory` 暴露 `RESOLVER_PROVIDER_NAMES` + `resolver_default_provider()`；`provider_resolver` 改为薄壳复用 factory 事实源；新增 `tests/shared/test_factory.py` 与 2 个 resolver 用例；零业务行为变化。 | [docs/engineering/technical-debt.md#td-020-统一-llm-provider-resolver-与-factory-优先级事实源](technical-debt.md) / [PR #46](https://github.com/MarkDanile/MetaEduBase/pull/46) |
| 2026-06-05 | DOC-011 技术债总账结构化展示优化 | 🟢 完成 | `technical-debt.md` 增加任务总览表和结构化任务卡片；长 `备注` 压缩为交付记录、事实源和验证摘要，降低扫视成本。 | `docs/engineering/technical-debt.md` |
