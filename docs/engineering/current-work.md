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

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| TD-025 业务页面 `liquid-card` 容器统一迁移到 `ui-panel` | 🟡 进行中（切片 1） | P2 | 前端 / 设计系统 | 切片 2：`KnowledgeBaseView` / `FileDetailView` 迁移。切片 3：`TemplateModal` / `TemplateEditorView` / `AiChatView` / `HomeView` + 显式登记 `liquid-btn-*` / `liquid-input` 例外。 |

| 验收 | 内容 |
|------|------|
| 范围（切片 1） | `main.css` 新增 `:root[data-theme="liquid"] .ui-panel` 玻璃感覆盖 + `DatabaseView.vue` / `ResourceView.vue` / `ResourceLibraryView.vue` 3 个页面 12 处 `liquid-card` → `ui-panel` 替换 + `coding-style.md` 业务页面迁移清单扩到切片 1。 |
| 验证（切片 1） | `pnpm --filter @metaedu/web typecheck / lint / build` 全部退出码 0；`scripts/check-engineering-docs` 退出码 0；4 条 `rg` 断言全过（3 个页面 `liquid-card` 0 残留、`ui-panel` 11 处命中、ResourceView `stagger-N` 装饰动效保留、`main.css` 1154 行 `:root[data-theme="liquid"] .ui-panel` 玻璃覆盖存在）。 |
| 事实源 | `docs/engineering/rules/coding-style.md#业务页面迁移清单-td-025`（迁移清单） + `docs/engineering/technical-debt.md#td-025`（任务总账）。 |

## 下一批候选任务

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/engineering/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| TD-009 减少前后端契约漂移 | ⚫ 待办 | P2 | API / 类型 | 选高价值契约族（模板字段或任务状态），建共享 schema 检查。 |

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
