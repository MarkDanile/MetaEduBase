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
| REQ-008 收口 REQ-004 验收证据与质量门禁缺口 | 🟡 进行中 | P1 | Product / Document / Testing | 修 5 项 ruff 失败（E501/UP035/I001）+ 4 分支 `template.select layer=...` caplog 断言 + 2 条 L3 解析失败 / 空响应用例。 | [Spec](../02-delivery-plans/01-specs/2026-W23-req-008-req-004-quality-follow-up.md) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-008-req-004-quality-follow-up-plan.md) / [Requirement](../01-product-planning/05-requirements/REQ-008-req-004-template-selection-quality-follow-up.md) |

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
| 2026-06-08 | DOC-033 开发前分支门禁前移与产品规划状态可视化 | 🟢 完成 | 将“会改文件先切任务分支”前移到开工入口；产品规划状态统一为颜色图标，并新增脚本门禁防止裸状态回退。 | [Git Workflow](01-rules/git-workflow.md) / [Workflow](workflow.md) / [Backlog](../01-product-planning/04-backlog.md) / [Script](../../scripts/engineering/check_engineering_docs.py) |
| 2026-06-08 | REQ-004 模板匹配可解释化收口 | 🟢 完成 | 抽 `select_template` 纯函数 + 9 条分支回归 + 4 分支统一 `template.select` 日志；行为不变：3 层优先级 / 阈值 0.7 保持。详细验证摘要见 work-log 索引行。 | [PR #77](https://github.com/MarkDanile/MetaEduBase/pull/77) / `docs/02-delivery-plans/01-specs/2026-W23-req-004-template-match-explainability.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-004-template-match-explainability-plan.md` / `docs/01-product-planning/02-milestones/01-validation-phase.md` |
| 2026-06-08 | DOC-031 补强 REQ follow-up 分流与跨事实源状态门禁 | 🟢 完成 | 增加 follow-up 类型分流规则，完成门禁明确 REQ 状态组回查，脚本检查 Backlog / Requirement / Iteration / Milestone / current-work 状态漂移、最近完成 work-log 索引和交付占位。 | [Rules](task-modes.md) / [Quality Gates](01-rules/quality-gates.md) / [Script](../../scripts/engineering/check_engineering_docs.py) |
| 2026-06-08 | REQ-007 收口 REQ-003 RAG 质量链路验收缺口 | 🟢 完成 | 5 AC 全部收口（行为级测试 / 状态同步 / 过度声明 / e2e 死代码 / 验证声明真实）。详细验证摘要与本地环境 vs Codex 集成环境差异见 work-log 索引行。 | [PR #75](https://github.com/MarkDanile/MetaEduBase/pull/75) / [Requirement](../01-product-planning/05-requirements/REQ-007-req-003-rag-quality-gate-follow-up.md) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-007-rag-quality-gate-follow-up-plan.md) / [P1](../01-product-planning/02-milestones/01-validation-phase.md) |
| 2026-06-08 | REQ-003 P1 RAG 质量链路验收与回归测试 | 🟢 完成 | 4 个新测试文件（24 用例）覆盖 NER / 融合 / 3 通道契约 / ai_chat e2e；轨道 B 4 行翻结论；Backlog REQ-003 推 Done；Protocol-vs-concrete drift 入账 TD-030。 | [PR #74](https://github.com/MarkDanile/MetaEduBase/pull/74) / [Spec](../02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-003-rag-quality-gate-plan.md) / [P1](../01-product-planning/02-milestones/01-validation-phase.md) |
