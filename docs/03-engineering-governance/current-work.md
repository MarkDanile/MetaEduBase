# 当前开发工作台

本文件是所有 AI IDE、插件和人工协作的当前任务入口。开始任何开发任务前，先阅读本文件，再按任务卡片中的链接渐进式读取相关 spec、plan、技术债或架构约束。

不同任务类型的开工条件、必读文档和完成标准见 `docs/03-engineering-governance/task-modes.md`。

## 使用规则

- 本文件只保留当前任务、近期候选和少量最近完成任务；任何修改本文件或任务状态前，必须先读 `docs/03-engineering-governance/01-rules/workbench.md`。
- 开发前确认本次任务卡片，并按卡片链接渐进式读取 spec、plan、技术债或架构约束。
- 涉及跨文件开发、计划接力、状态交接或后续继续开发时，必须登记或更新任务卡片。
- 代码、验证或 Git 阶段变化后，必须同步任务状态、当前进展、下一步和验证结果。
- 提交、PR、合并或声明完成前，运行 `scripts/check-engineering-docs` 并执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`；门禁主实现位于 `scripts/engineering/check_engineering_docs.py`。

## 当前进行中

### TASK-R1-S6-I3-D-GOV: 工作台精简 + PR-D 剩余边界重定基（pure-docs）

状态：🟡 进行中（2026-09-01）
分支：`docs/req041-047-r1-s6-i3-d-workbench-prd-rebaseline`（base = main `4b92b980`，D2 closeout 之后）
当前执行模式：pure-docs governance（仅 3 文件：current-work.md + plan §S6-14 + fact-audit.md）
最近接手工具：Claude Code
类型 / 领域：REQ-041/047 R1-S6-I3-D 治理收口 / docs-only / 工作台 + 计划层 + 事实审计
需求来源：用户裁决（D2 squash merge 入 main `ae7f3c98` + closeout `4b92b980` 完成后下达）
当前进展：
- slim TASK-R1-S6-I3-D → GOV 卡片（本卡，≤12 行）；候选 1-3 项冻结顺序（PR-D → F-matrix → PR-E，PR-E 标 PR-D 前置依赖）
- plan §S6-14 APPEND post-D2 supersede 注解（D1a/D1b/D2 = #598/#600/#602 已合 main；PR-D remaining = production-neutral 4 项；exclude scheduler caller/S5-D1b-D2 wiring/capability flip/六 erase 入口生产可达）；原 §S6-14 冻结顺序保留为历史事实不覆盖
- fact-audit §17.7 顶部补 D2 merged-boundary 标注 + 改"PR-D 未启动"→"PR-D 剩余 operational closeout 未启动" + §18 删 PR-D 基线 aff54883
下一步：用户裁决 Ready → 评分 → squash merge → closeout；**不启动 PR-D 实现 / F-matrix / PR-E / C1 / S5 wiring / capability flip / 六 erase 入口生产可达**
验证状态：`git diff --check` clean / `scripts/check-engineering-docs --full` 全绿 / 仅 3 允许文件改动 / `rg` 复核 Round-1..8 mutation/CI 链/评分链仅在 fact-audit §17.7 + plan merged-boundary 历史标注内
事实源：[work-log](work-log.md) / [fact-audit §17.7](04-retrospectives/r1-s6-i3-d-fact-audit.md) / [Score Log](04-retrospectives/review-score-log.md) / [plan §S6-14](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [PR #598](https://github.com/MarkDanile/MetaEduBase/pull/598) / [PR #600](https://github.com/MarkDanile/MetaEduBase/pull/600) / [PR #602](https://github.com/MarkDanile/MetaEduBase/pull/602) / [PR #603](https://github.com/MarkDanile/MetaEduBase/pull/603)

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P1 | R1-S6 PR-D **剩余交付**（production-neutral 边界，按 plan §S6-14 post-D2 rebaseline 注解） | ⚫ 待办，独立后续 PR | 仅包含：(1) production-neutral continuous ledger export/archive orchestration entry；(2) restore-before-open runbook；(3) D1a→D1b→D2→gate cross-layer safety drill / contract verification；(4) crash/retry、post-snapshot purge、manual reconcile ops 步骤。**禁止**：scheduler production caller、S5/D1b/D2 production wiring、capability flip、六 erase 入口生产可达。详见 plan §S6-14 post-D2 supersede/rebaseline 注解 | [Plan §S6-14](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) post-D2 rebaseline 注解 / [fact-audit §17.7](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| P1 | R1-S6 F-matrix 7/12 + F10 M6 test contract 增强 | ⚫ 待办，独立后续 PR | F-matrix 7/12 mutation NOT-RED（M-F2/F3/F4/F5/F6/F8/F12）+ F10 M6（completed 绕过最终扫描）判别载体补齐；M6 真实 PG 路径需 G1/G2/G3 cleared + 所有 owner acked + final scan 非零 → blocked (scan reason) 的测试矩阵 | [TD-105](technical-debt.md#td-105-r1-s6-f10-实现承接契约纠偏后解除-skip--真实-pg-判别) closeout note / F-matrix #590 mutation follow-up |
| P2 | R1-S6 PR-E release drill 五阶段 canary（真实 PG / 备份 / 流量开关） | ⚫ 待办，独立后续 PR；**前置依赖 = PR-D 剩余交付**，**禁止在 PR-D 之前启动** | 本地无法执行（无生产基础设施 + 无备份保留 runbook 执行环境）——按 R1-AC12 字面降级为 contract-tested 验证；登记生产门禁；待 PR-D 剩余交付的 runbook / 编排 / 跨层 drill 落地后再启动 | [Plan §S6-7](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|------|
| 2026-09-01 | R1-S6-I3-D D2 restore replay executor + restore-before-open gate（M 类；Round-8/8.1 三面复审 P0/P1/P2/P3=0 + squash merge 入 main） | 🟢 完成（D2 子阶段；TASK-R1-S6-I3-D 仍 🟡 进行中——PR-D 未启动） | PR #602 squash mergeCommit `ae7f3c98`；评分 92 Original；108 D2 专项 + 992 composition + 21/21 mutation；D2 wiring / PR-D / PR-E / C1 / S5 wiring / capability flip / 六 erase 未启动 | [PR #602](https://github.com/MarkDanile/MetaEduBase/pull/602)（mergeCommit `ae7f3c98`）/ [work-log](work-log.md) / [score 92](04-retrospectives/review-score-log.md) / [fact-audit](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-08-28 | R1-S6-I3-D D1b 专用 MinIO ledger archive sink + 不可变 commit-graph 发布协议（两阶段 API 拆分；三面 P1 修复闭环 + squash merge 入 main） | 🟢 完成（D1b 子阶段；TASK-R1-S6-I3-D 仍 🟡 进行中） | PR #600 squash mergeCommit `01c84f7c`；评分 94 Original；47/47 composition + 6/6 opt-in real MinIO + 11/11 mutation；D1b wiring / D2 / PR-D / PR-E / C1 / S5 wiring / capability flip / 六 erase 未启动 | [PR #600](https://github.com/MarkDanile/MetaEduBase/pull/600)（mergeCommit `01c84f7c`）/ [work-log](work-log.md) / [score 94](04-retrospectives/review-score-log.md) / [fact-audit](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-08-28 | R1-S6-I3-D D1a bounded read-only ledger snapshot codec（三轮 P1 治理闭环 + squash merge 入 main） | 🟢 完成（D1a 子阶段；TASK-R1-S6-I3-D 仍 🟡 进行中） | PR #598 squash mergeCommit `5868831e`；评分 97 Original；57/57 D1a + 828 composition + 20/20 mutation；D1a 已并入 main，D1b/D2/PR-D 未启动 | [PR #598](https://github.com/MarkDanile/MetaEduBase/pull/598)（mergeCommit `5868831e`）/ [work-log](work-log.md) / [score 97](04-retrospectives/review-score-log.md) / [fact-audit](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-08-26 | R1-S6-I3-F10 settlement T1/T2 hold 推进故障矩阵真实 PG 判别 + TD-105 实现承接 | 🟢 完成 | PR #596（squash `c0ec008d`）；评分 97 Original；8 项 PG 测试 + 7/8 mutation 真红（M6 NOT-RED）；净 diff 3 文件 1005+/23- 无生产代码；**TD-105 已完成并关闭**；F10 不直接 completed；PR-D/E/C1/S5 wiring 未启动 | [PR #596](https://github.com/MarkDanile/MetaEduBase/pull/596)（squash `c0ec008d`）/ [work-log](work-log.md) / [score 97](04-retrospectives/review-score-log.md) |
| 2026-08-26 | R1-S6-I3 root bounded integration: S6-F1..F14 故障矩阵 + TD-106 方案 A + scope 收敛 + main closeout | 🟢 完成 | root PR #586（squash `68fafd81`）+ main closeout；评分 94 Original；scope = F1-F14 故障矩阵 + TD-106 方案 A bounded integration；PR-D/E scaffold 已撤回；**TD-106 已完成并关闭**；F10 仍 skip（TD-105 承接）+ PR-D/PR-E/C1/S5 wiring/capability flip 均未启动 | [PR #586](https://github.com/MarkDanile/MetaEduBase/pull/586)（squash `68fafd81`）/ [work-log](work-log.md) / [score 94](04-retrospectives/review-score-log.md) |
| 2026-08-25 | R1-S6-I3-F10 S6-F10 契约核对纠偏 + TD-106 决策门禁（contract-first，纯文档） | 🟢 完成 | PR #591（squash `738be6f9`）；评分 89（Original）；§S6-15 冻结入 main；**TD-106 实现已随 #586 入 main 完成**（详细见 work-log + [TD-106](technical-debt.md#td-106-r1-s6-settlement-success-不写-ledgerbinding实现-vs-s5-c-1-冻结契约缺口pre-existing)） | [PR #591](https://github.com/MarkDanile/MetaEduBase/pull/591)（squash `738be6f9`）/ [work-log](work-log.md) / [score 89](04-retrospectives/review-score-log.md) |
| 2026-08-24 | R1-S6-I3-A schema/test alignment bounded repair（squash 入 #586） | 🟢 完成 | squash 入 #586；评分 92（Original）；幽灵列对齐真实 schema + acked fixture 合法化 + 独立 CHECK 负例 + F3 补种；fresh PG 043 24/24 + composition 750；**#586 已合 main**；TD-104 保持承接 | [PR #589](https://github.com/MarkDanile/MetaEduBase/pull/589)（squash `f6062466`）/ [work-log](work-log.md) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-24 | R1-S6-I3-B restore replay 持久状态域契约纠偏（contract-first，纯文档） | 🟢 完成 | PR #587（squash `66674f23`）；评分 85；三层 CHECK 闭集 + replay 路由表 + 判定方式冻结；**#586 已合 main**；TD-104 + REQ-047 | [PR #587](https://github.com/MarkDanile/MetaEduBase/pull/587)（squash `66674f23`）/ [work-log](work-log.md) / [score 85](04-retrospectives/review-score-log.md) |
| 2026-08-20 | R1-S6-I2 Writer conformance suite + body/ref orphan inspection | 🟢 完成 | PR #584（merge `ad7ac3e5`）；评分 88；3 writer spec + 六类 verify 巡检 + Run 行锁；21 项专项 + 726 composition；TD-100~103 + REQ-047；S6-I3/C1/S5 wiring 未启动 | [PR #584](https://github.com/MarkDanile/MetaEduBase/pull/584)（merge `ad7ac3e5`）/ [work-log](work-log.md) / [score 88](04-retrospectives/review-score-log.md) |
| 2026-08-19 | R1-S6-I1 Retention workers（run_event_retention + run_audit_retention + migration 043） | 🟢 完成 | PR #582（squash `f5072ec6`）；评分 87（基线 `d1427567`）；两 worker + 043 guard + 两处 S5 修复落地；三面返修+决 A 测试兼容升级后 P0/P1=0；Backend 2649/1/4/0 + mutation 18/18 + 043 往返稳定；S6-I2/I3/C1/S5 wiring 未启动；TD-097/098/099 + REQ-047 | [PR #582](https://github.com/MarkDanile/MetaEduBase/pull/582)（squash `f5072ec6`）/ [work-log](work-log.md) / [score 87](04-retrospectives/review-score-log.md) |
| 2026-08-19 | R1-S5 Root Integration: settlement idempotency key 对齐 + B/C/D 联合组合根 | 🟢 完成 | root PR #577（squash `636fc425`）合并；评分 92（基线 `995aa223`）；126 专项 + composition 665 + mutation 8 组 + Backend 2600/1/4 + Frontend 326+55；production erase 入口仍不可达；follow-up REQ-047 + TD-093/095/096 + td-032 | [PR #577](https://github.com/MarkDanile/MetaEduBase/pull/577)（squash `636fc425`）/ [work-log](work-log.md) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-19 | R1-S5 SCH-D: Settlement & Retry-Reconcile（squash 入 root） | 🟢 完成 | 已 squash 入 root PR #577（`5033efc5`）并随 root 合并（`636fc425`）；child 正式评分 92（Original）；23 专项 + 12/12 mutation kill + composition 646 passed | [PR #579](https://github.com/MarkDanile/MetaEduBase/pull/579) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-19 | R1-S5 SCH-C: Rebuild & Seeding（squash 入 root） | 🟢 完成 | 已 squash 入 root PR #577（`a8f4d561`）并随 root 合并（`636fc425`）；child 正式评分 92（Original）；40 专项 + 27/27 mutation kill + composition 623 passed | [PR #578](https://github.com/MarkDanile/MetaEduBase/pull/578) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-17 | R1-S5 SCH-A Claim & Lease 实现（migration 042 + ConversationPurgeScheduler） | 🟢 完成 | migration 042 + claim/lease 服务（四转移 expected-epoch CAS、tenant 上限 4、takeover 后强制聚合）；评分 93（最终 P0/P1/P2=0）；29 专项 + 13/13 mutation kill + Backend 2504/1/4；**SCH-A 完成不代表 Scheduler 已启用**；follow-up REQ-047 | [PR #575](https://github.com/MarkDanile/MetaEduBase/pull/575)（squash merge `36d091a4`）/ [work-log](work-log.md) / [score 93](04-retrospectives/review-score-log.md) |
| 2026-08-17 | R1-S5-D-A SCH-A Lease Carrier 契约纠偏（contract-first，纯文档） | 🟢 完成 | durable lease carrier 契约已纠偏：`updated_at` 退出租约事实源、migration 042 冻结（SCH-A 落地）、三态×四转移 epoch CAS 全函数、owner entry 门禁、SCH-9..16（反例矩阵 53→61 冻结验收载体）；评分 90（最终 P0/P1=0）；**纠偏完成不代表 migration 042 或 SCH-A 已实现**；follow-up REQ-047 | [PR #573](https://github.com/MarkDanile/MetaEduBase/pull/573)（squash merge `3438c53b`）/ [work-log](work-log.md) / [score 90](04-retrospectives/review-score-log.md) |
| 2026-08-16 | R1-S5-D Scheduler 契约冻结（contract-first，纯文档） | 🟢 完成 | S5-SCH-0..5 全卷（状态机/锁序/写者矩阵/四 slice 拆分/53 项反例映射/REQ-047 分流）；评分 87（最终 P0/P1=0）；**契约完成不代表 Scheduler 实现完成**；SCH-A/B/C/D 未开工，B/C/D 联合 merged-boundary | [PR #571](https://github.com/MarkDanile/MetaEduBase/pull/571)（squash merge `253e53e4`）/ [work-log](work-log.md) / [score 87](04-retrospectives/review-score-log.md) |
