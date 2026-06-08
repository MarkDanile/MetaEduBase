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
| REQ-007 REQ-003 复盘缺口的 RAG 质量链路收口 | 🔵 进行中 | P1 | AI / Testing / Docs | 已建 `2026-W23-req-007-rag-quality-gate-follow-up-plan.md`；Task 1 行为级测试文件 `test_recall_channels_behavior.py` 已提交（9 用例）；Task 2 e2e 死代码清理已完成；Task 3 状态同步（本次提交）已完成。 | Task 4 Step 1-2 修正 P1 轨道 B 4 行”验证结论”列过度声明；Task 4 Step 3-4 全量验证（4 测试文件 + ruff + docs gate）。 | `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/{test_rule_based_ner,test_frequency_fusion,test_recall_channels_contract,test_recall_channels_behavior,test_ai_chat_rag_e2e}.py -q` |

## 下一批候选任务

按风险和接力价值，本区只保留近期 1 到 3 个候选；完整技术债余量仍以 `docs/03-engineering-governance/technical-debt.md` 为准。

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| REQ-004 模板匹配可解释化收口 | ⚫ 候选 | P1 | Product / Document / AI | 用真实业务文档验证三层模板匹配和日志表现。 |
| REQ-005 结构化抽取嵌套结构稳定性验收 | ⚫ 候选 | P1 | Product / Document / Contract | 建立 object / array / table 抽取结果样例回归。 |
| REQ-006 P1 知识资产处理链路最终演示验收 | ⚫ 候选 | P1 | Product / Document / AI / Testing | 先修复本机 `metaedu_test` 连通性，再组织上传/解析/抽取/图谱/RAG 问答/来源展示的端到端演示。 |

## 最近完成

最近完成区最多保留 5 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超出 5 行的已完成任务应归档到 `docs/03-engineering-governance/work-log.md` 单行索引 + 段落归档，本表只承担"最近 5 个工作窗口"的角色。详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-06-08 | REQ-003 P1 RAG 质量链路验收与回归测试 | 🟢 完成 | 4 个新测试文件（24 用例）覆盖 NER / 融合 / 3 通道契约 / ai_chat e2e；轨道 B 4 行翻结论；Backlog REQ-003 推 Done；Protocol-vs-concrete drift 入账 TD-030。 | [PR #74](https://github.com/MarkDanile/MetaEduBase/pull/74) / [Spec](../02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md) / [Plan](../02-delivery-plans/02-plans/2026-W23-req-003-rag-quality-gate-plan.md) / [P1](../01-product-planning/02-milestones/01-validation-phase.md) |
| 2026-06-07 | DOC-030 建立真实 AI 应用组合轻量规划入口 | 🟢 完成 | 新增 `06-ai-applications` 记录四个学校真实 AI 应用，明确应用组合与 P1/P2/P3 底座路线双轴协同；Backlog 增加 APP-001 到 APP-004。 | [AI Applications](../01-product-planning/06-ai-applications/README.md) / [Backlog](../01-product-planning/04-backlog.md) |
| 2026-06-07 | DOC-029 明确 P1/P2/P3 检索架构演进边界 | 🟢 完成 | P1 三通道明确为 PostgreSQL 内 vector / keyword / metadata；P2 写清 PostgreSQL 增强和第 4 图谱关系通道；P3 再进入向量库 / 图数据库 / ES 多引擎形态。 | [P1](../01-product-planning/02-milestones/01-validation-phase.md) / [P2](../01-product-planning/02-milestones/02-growth-phase.md) / [P3](../01-product-planning/02-milestones/03-scale-phase.md) |
| 2026-06-07 | DOC-028 复核 P1 验证期并建立最终查漏补缺迭代 | 🟢 完成 | 轨道 B 改为实现事实 / 验证证据分栏；新增 REQ-003 到 REQ-006，并建立 P1 final gap closure 迭代。 | [P1](../01-product-planning/02-milestones/01-validation-phase.md) / [Iteration](../01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md) |
| 2026-06-07 | DOC-027 恢复产品规划三阶段里程碑结构 | 🟢 完成 | `01-roadmap.md` 收敛为阶段一/二/三；`02-milestones` 增加三阶段详情，并按产品能力 / 检索与抽取质量 / 基础设施三轨道组织。 | [Roadmap](../01-product-planning/01-roadmap.md) / [Milestones](../01-product-planning/02-milestones/README.md) |
