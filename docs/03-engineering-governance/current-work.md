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

### TASK-R1-S6-C1: R1-S6 C1 Durable Core 联合契约/conformance 总验收（Phase 1：B 类 test 补强 + 已落地架构事实修正）

状态：🟡 进行中
类型：new-requirement acceptance（Durable Core 总验收；B 类 test-only 补强 + C 类已落地架构事实修正）
领域：engineering / agent_workspace / agent_execution / composition
当前执行模式：单人顺序执行（active-card commit → 5 项 B 类 test 补强 + ARCHITECTURE.md 修正 → 逐项定向 + 分层验证 + 全量回归 + 11 mutation harness 重跑 → OPEN/Draft PR → 等三路 CI → 停止待评审）
最近接手工具：Claude Code
分支：feature/req041-047-r1-s6-c1-durable-core-acceptance

需求来源：
- Spec: `docs/02-delivery-plans/01-specs/2026-07-24-req-041-047-conversation-run-contract.md` §14 + `docs/02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md` §10/§11/§12
- Plan: `docs/02-delivery-plans/02-plans/2026-07-24-req-041-047-conversation-run-contract-plan.md` Slice C1 + §6 全局矩阵 + `docs/02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md` §S6
- 技术债：不关闭/不重开 TD-104/TD-032/TD-105/TD-106
- 架构约束：C1 = Durable Core 联合契约/conformance 总验收，**不等于** production erase/release enable

当前进展：Phase 0 contract-to-test audit 已完成（REQ-041 6 满足/2 部分[AC-3/AC-6]；REQ-047 Core 9 满足/1 部分-缺口[R-AC5 extended entities]；R1-AC 11 满足/1 部分[AC-9 hold 写侧未接线]；全局矩阵 14/15[permission revoke 部分]）；Phase 1 开工，active-card commit 先行
下一步：5 项 B 类 test 补强（AC-3 re-auth / AC-6 CoT sentinel / permission-revoke unused_grants / R1-AC1 时间边界 / R1-AC10 日志指标 sentinel）+ ARCHITECTURE.md 已落地事实修正（§4/§5.5/§6）
验证状态：未运行（实现后按 §验证顺序执行：定向 → contexts → composition → 全量后端 → ruff/mypy/alembic → 11 mutation harness → docs gate）
交接备注：C1 = Durable Core contract/conformance 完成（非生产 erase/release enable）；REQ-041/REQ-047/TASK 完成态留待 post-merge 独立 closeout（已批准裁决：C1 合并后 REQ-041 翻 Done、REQ-047 仅标 Durable Core 完成保持 Shaping、R1-S6 关闭为 Durable Core 完成；S5 wiring/capability flip/六 erase/hold 管理 API/生产门禁/完整 REQ-047 保持独立未启动）；allowed files 仅 current-work + ARCHITECTURE + 5 个 test 文件；external/runtime 保持 erase_available=False，fake 仅 contract-tested；真实 pg_dump/多实例 canary/旧 writer 进程保持生产门禁未执行；测试库仅 metaedu_test；任一测试暴露 production 缺陷即停止（不越界改 app/）

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|------|
| 2026-09-08 | TASK-R1-S6-SCH-D-MUTATION-HARNESS-MAINTENANCE：sch_d mutation harness stale anchor 重锚维护（settlement.py #586 重构漂移）+ 独立 pure-docs closeout | 🟢 完成（sch_d harness 维护子任务；REQ-041/047 完成态与 C1 总验收不受此影响、仍按各自边界推进） | PR #615 squash mergeCommit `6a804a1d`；评分 94 Original；sch_d 6 stale anchor 重锚当前 settlement.py + sch_d 12/12 mutation-level KILLED；合并后 main 11 harness 串行全绿；零生产/测试改动；G-1 顺序偏差 + all(...) limitation 两 P3 真实保留未消除 | [PR #615](https://github.com/MarkDanile/MetaEduBase/pull/615)（mergeCommit `6a804a1d`）/ [work-log](work-log.md) / [score 94](04-retrospectives/review-score-log.md) / [fact-audit §17.13](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-09-07 | R1-S6 PR-E release drill 五阶段 fail-closed canary contract（pure test harness）+ 独立 closeout 治理收口（TASK-R1-S6-I3-D-PR-E-CLOSEOUT 子卡） | 🟢 完成（PR-E 子阶段 + CLOSEOUT 子卡；TASK-R1-S6-I3-D 整体仍 🟡 进行中——C1/S5 wiring/capability flip/六 erase/REQ-047 未启动） | PR #612 squash mergeCommit `25aefc74`；score 95 Original；PR-E 15/15 + composition 1014/6；P3×2 闭环 follow-up=无；PR-E=production-neutral contract-tested test harness 非生产 release enable；真实 pg_dump/多实例 canary 保持生产门禁未执行 | [PR #612](https://github.com/MarkDanile/MetaEduBase/pull/612)（mergeCommit `25aefc74`）/ [work-log](work-log.md) / [score 95](04-retrospectives/review-score-log.md) / [fact-audit §17.12](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-09-06 | R1-S6 F-matrix M-F8 单独判别（test-contract / shared-observation gap 闭合）+ 独立 closeout 治理收口（TASK-R1-S6-FMATRIX-MF8-CLOSEOUT 子卡） | 🟢 完成（F-matrix M-F8 单独判别 + CLOSEOUT 子卡；TASK-R1-S6-I3-D 整体仍 🟡 进行中——PR-E/C1/S5/capability flip/六 erase/REQ-047 未启动） | PR #610 squash mergeCommit `b8daa934`；score 95；F-matrix 12/12 + F10 8/8 = 20/20 KILLED（PR #608 19/20 口径保持）；跨变独立性双证明；G-1 [P3] 真实保留 | [PR #610](https://github.com/MarkDanile/MetaEduBase/pull/610)（mergeCommit `b8daa934`）/ [work-log](work-log.md) / [score 95](04-retrospectives/review-score-log.md) / [fact-audit §17.11](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-09-04 | R1-S6 F-matrix + F10 M6 test contract 增强（独立后续 PR；Phase 0 审计修正 3 项 M-F3/M-F5 错映射 + F10 M6 不可达路径解除；5 文件 pure test contract + mutation harness 修正） | 🟢 完成（F-matrix + F10 M6 子阶段；TASK-R1-S6-I3-D 整体仍 🟡 进行中——F-matrix M-F8 NOT-RED test-contract/shared-observation gap / PR-E/C1/S5/capability flip/六 erase/REQ-047 未启动） | PR #608 squash mergeCommit `e07c601b`；评分 94 Original；**F-matrix 11/12 KILLED + F10 8/8 KILLED = 19/20**（M-F8 NOT-RED 真实 harness issue 不冒充 KILLED）；zero-touch；TD-104/TD-032 保持登记 | [PR #608](https://github.com/MarkDanile/MetaEduBase/pull/608)（mergeCommit `e07c601b`）/ [work-log](work-log.md) / [score 94](04-retrospectives/review-score-log.md) / [fact-audit §17.10](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-09-03 | R1-S6-I3-D PR-D 剩余 operational closeout（production-neutral 4 项：orchestration entry + restore-before-open runbook + D1a→D1b→D2→gate cross-layer safety drill + crash/retry/post-snapshot purge/M-class/blocked-manual reconcile ops） | 🟢 完成（PR-D 子阶段；TASK-R1-S6-I3-D 整体仍 🟡 进行中——F-matrix/PR-E/C1/S5/capability flip/六 erase 未启动） | PR #606 squash mergeCommit `d196d7f0`；评分 95 Original；4 文件净 diff 851 insertions(+)/1(-)；zero-touch（无 migration/schema/CHECK/CI）；TD-104 保持 ⚫ 待办 / TD-032 保持 🟢 待拆分不关闭 | [PR #606](https://github.com/MarkDanile/MetaEduBase/pull/606)（mergeCommit `d196d7f0`）/ [work-log](work-log.md) / [score 95](04-retrospectives/review-score-log.md) / [fact-audit §17.9](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
| 2026-09-02 | R1-S6-I3-D 工作台精简 + PR-D 剩余边界重定基 GOV closeout（pure-docs；TASK-R1-S6-I3-D-GOV 子卡） | 🟢 完成（GOV 子卡；TASK-R1-S6-I3-D 整体仍 🟡 进行中——PR-D/PR-E/C1/S5/capability flip 未启动） | PR #604 squash mergeCommit `e37561fe`；评分 91 Original；pure-docs 3 文件（current-work slim + plan §S6-14 APPEND + fact-audit 4 处过期修复）；P3=5 non-blocking；TASK-R1-S6-I3-D 整体仍 🟡（PR-D/PR-E/C1/S5/capability flip 未启动）；零业务代码改动 | [PR #604](https://github.com/MarkDanile/MetaEduBase/pull/604)（mergeCommit `e37561fe`）/ [work-log](work-log.md) / [score 91](04-retrospectives/review-score-log.md) / [fact-audit](04-retrospectives/r1-s6-i3-d-fact-audit.md) |
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
