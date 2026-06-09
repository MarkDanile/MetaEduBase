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
| REQ-006 P1 知识资产处理链路最终演示验收 | 🟣 Shaping | P1 | Product / Document / AI / Testing | 已建 spec / plan 骨架（`feat/req-006-p1-final-demo` 分支）；Backlog 状态 `⚫ Candidate` → `🟣 Shaping`；`metaedu_test` 已恢复（W23 复核 4 文件 34 passed in 9.86s）；Stage 1 待实施（端到端脚本 + UI 手册）。 | Stage 1：探查现有 fixture → 写 `tests/e2e/test_p1_demo.py` 6 步串联 → 写 `req-006-p1-final-demo-ui.md` 手册 → ruff + 门禁 + commit。Stage 2：轨道 B / W23 / Backlog / current-work / work-log 文档回填。 | `scripts/check-engineering-docs` 退出码 0（塑形已收口） |

## 下一批候选任务

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/03-engineering-governance/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| 暂无（REQ-006 已在当前进行中区） | - | - | - | 从工作台或用户指定任务开工。 |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时再批量归档最旧记录，建议一次性压回 12 到 15 行左右；不要每完成一个任务就做单条搬运。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-09 | DOC-050 优化 current-work 最近完成窗口与评分总账排序 | 🟢 完成 | 最近完成窗口从 5 行改为 20 行，超过后批量归档到 12-15 行；评分总账明确最新评审置顶；文档门禁脚本和测试同步。 | [Work Log](work-log.md) / [Workbench](01-rules/workbench.md#保留策略) / [Review Score Log](04-retrospectives/review-score-log.md) |
| 2026-06-09 | TD-035 收口 REQ-005 新增测试文件 ruff 质量门禁 | 🟢 完成 | `ruff check --fix` 自动修 1 个 I001 + 3 个 SIM300（assertion 顺序翻转 + 1 行多余空行）；pytest 11 passed 不变；ruff app/ tests/ 全过。 | [TD-035 Delivery Record](technical-debt.md#td-035) |
| 2026-06-09 | DOC-049 收口结构化抽取完成态占位与验证声明漂移 | 🟢 完成 | 修正 REQ-005 spec AC-8 浅拷贝口径 / AC-10 失败条件 / `TD-???` → TD-034；plan 提交占位 TBD 补 `4773741` / 11 条用例真实计数；评估把完成态占位扫描以候选形式登记到 `quality-gates.md#脚本门禁候选清单`（推迟）。0 业务代码改动。 | [Backlog](../01-product-planning/04-backlog.md) / [Spec](../02-delivery-plans/01-specs/2026-W23-req-005-structured-extraction-regression.md) / [Quality Gates](01-rules/quality-gates.md#脚本门禁候选清单) |
| 2026-06-09 | REQ-005 结构化抽取嵌套结构稳定性验收 | 🟢 完成 | 为 `extract_template_prompts` 补 11 条 object / array / table 嵌套回归用例；锁定 `build_fields_desc` 嵌套描述 / `try_parse` 嵌套 JSON 与 think 剥离 / `_merge_template_structured_data` 浅拷贝契约；轨道 B 翻结论。0 业务代码改动。 | [Spec](../02-delivery-plans/01-specs/2026-W23-req-005-structured-extraction-regression.md) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-005-structured-extraction-regression-plan.md) |
| 2026-06-09 | BUG-002 修复登录后主面板外边距巨大、内容显示容器过小 | 🟢 完成 | 移除 `ui-page-shell` 的 `max-width: 1120px; margin: 0 auto`，保留 width/padding/background；消除与各 View 自带 max-w 嵌套冲突。`pnpm typecheck / lint / build` 退出 0；`check-engineering-docs` passed。 | [Work Log](work-log.md) / [Backlog](../01-product-planning/04-backlog.md) / [PR #107](https://github.com/MarkDanile/MetaEduBase/pull/107) (`76fe2d2`) |
| 2026-06-09 | DOC-045 修正 TD-033 CSS 拆分交付声明与追踪证据 | 🟢 完成 | 弱化 TD-033 任务卡 4 处"零 CSS 字节变化 / build output identical"过强声明；6 处事实源补 `PR #103` / `25ca165` 追踪；显式登记 TD-033 未建 spec / plan 的处置方式（事后不补建）。docs-only，`check-engineering-docs` 退出码 0。 | [Work Log](work-log.md) / [TD-033 Delivery Record](technical-debt.md#td-033) / [PR #106](https://github.com/MarkDanile/MetaEduBase/pull/106) |
| 2026-06-09 | DOC-048 增加评审高分质量校准规则 | 🟢 完成 | 最近 5 条评审平均分 >92 时，阶段复盘必须抽查评分是否偏宽；发现问题需在评分总账标记并登记 follow-up。 | [Review Scorecard](01-rules/review-scorecard.md#高分质量校准) / [Retrospectives](04-retrospectives/README.md) |
| 2026-06-09 | DOC-047 建立评审评分总账与落盘规则 | 🟢 完成 | 新增评审评分总账，回填 TD-033 评分 81；复杂评审后必须把总分、follow-up、流程扣分点和规则改进结论落盘。 | [Review Score Log](04-retrospectives/review-score-log.md) / [Review Scorecard](01-rules/review-scorecard.md) |
