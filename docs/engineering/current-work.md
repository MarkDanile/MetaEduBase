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

最近完成区最多保留 5 行（按 `docs/engineering/rules/workbench.md#保留策略` 强约束）。超出 5 行的已完成任务应归档到 `docs/engineering/work-log.md` 单行索引 + 段落归档，本表只承担"最近 5 个工作窗口"的角色。详细验证、行为变化、PR 描述和复盘见 `docs/engineering/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-05 | DOC-013 工程文档门禁增强与 UI 迁移事实源收口 | 🟢 完成 | `scripts/check-engineering-docs` 增加技术债状态一致性、完成交付记录和工作台摘要长度检查；同步收口 TD-027 与 UI 迁移文档。 | `scripts/engineering/check_engineering_docs.py` |
| 2026-06-05 | TD-028 业务视图与共享组件的 `liquid-input` / `liquid-btn-*` / `liquid-tag-*` / `liquid-dialog*` 存量替换 | 🟢 完成 | 12 文件 119 处原子控件类迁到 `ui-*`，保留 `main.css` 中 `liquid-*` 兼容别名；详情见设计系统段落归档。 | [PR #61](https://github.com/MarkDanile/MetaEduBase/pull/61) |
| 2026-06-05 | TD-027 补 `ui-input` / `ui-btn-*` / `ui-tag-*` / `ui-dialog` 共享类（设计系统扩展） | 🟢 完成 | `main.css` 新增 12 个 token 化 `ui-*` 原子控件类，并补 `--overlay-bg` / `--btn-ripple` 主题 token。 | [PR #59](https://github.com/MarkDanile/MetaEduBase/pull/59) |
| 2026-06-05 | TD-026 共享组件 `liquid-card` 残留验证 | 🟢 完成 | 4 个共享组件严格 `rg "liquid-card"` 均为 0；原残留量为任务卡快照误计，后续拆为 TD-027 / TD-028。 | `docs/engineering/technical-debt.md#td-026` |
| 2026-06-05 | TD-025 业务页面 `liquid-card` 容器统一迁移到 `ui-panel`（业务视图部分完成） | 🟢 完成 | 3 个切片完成 7 个业务页面 20 处 `liquid-card` → `ui-panel`；例外和视觉变化见技术债卡片与 PR。 | `docs/engineering/technical-debt.md#td-025` |
