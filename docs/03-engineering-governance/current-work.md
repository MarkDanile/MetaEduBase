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

### TASK-R1-S6-F-MATRIX-TEST-CONTRACT: F-matrix + F10 M6 test contract 增强（独立后续 PR）

类型: 纯测试契约 + mutation harness 修正（不动 production code）
领域: 后端 / Erasure / Settlement / Restore-Replay / 测试
当前执行模式: Phase 1 实现 + 验证（Phase 0 契约审计已交付并经用户接受）
最近接手工具: Claude Code (Opus 4.8 / 1M)
分支: `feature/req041-047-r1-s6-f-matrix-test-contract-enhancement`（基于 main `4c376373`）

需求来源:
- Spec: §R1-S6-5（[`2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md`](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) plan §R1-S6-5 故障点清单冻结）
- Plan: §S6-5 / §S6-14 / §S6-15 + fact-audit §17.7 9/12 真红 + M-F3/M-F5/M-F8 stop condition 登记保持
- 技术债: TD-104（⚫ 待办，PR-A schema/test alignment 残项）+ TD-032（🟢 完成但 D1b 1052 + D2 1876 双超 1000 待拆分；本任务**不**拆分）
- 既有事实源: `scripts/s6i3_fault_matrix_mutation_kill.py` 12 项 mutation + `scripts/s6i3_f10_mutation_kill.py` 8 项 mutation

Phase 0 契约审计结论（已交付 + 用户接受）：
1. **M-F3**：错映射（`test_f3_lease_ack_lost_replay_no_fork` 仅 raw SQL seed + COUNT(*)断言，**不**调被变异 `_ack_lost_repair`）→ 修正到 `test_s5_sch_d_settlement.py::test_settlement_ack_lost_repair`（真实调 `closeout_erasing` → `_classify_input("ack_lost")` → `_ack_lost_repair`）
2. **M-F5**：错映射 + 不可达（`test_f5_ack_after_operation_pre_aggregation_crash_takeover_safe` 仅 seed + COUNT(*)，**且** seed 用 checkpoint=acked 不进 mutated `erasing` 分支）→ 修正到 `test_s6_td106_settlement_ledger.py::test_external_multi_ref_per_ref_receipt`（真实调 `closeout_erasing` → `_classify_input(fence=erasing, checkpoint=erasing)` → mutated 分支 → `_t1_plan_recovery` → `_apply_window_outcome`）
3. **M-F2 / M-F4 / M-F6 / M-F8 / M-F12**：当前映射均经公开 production entry 调被变异 helper，**已真红**
4. **F10 M6**：不可达路径（既有 F10 测试集全部走 `hold_revision 0→1` → G2 提前 return，**永远到不了 priority 3 scan check**）→ 新增独立真实 PG test `test_f10_m6_completed_bypass_scan_check_blocked`：G1 cleared + G2 cleared（**不**推进 hold_revision）+ G3 cleared（无 active legal hold）+ 6 owner acked + 5-party pass + workspace.core.v1 final scan 非零（title 残留）→ control 期望 `blocked` + 精确 scan reason；mutant（M6 priority 3 折叠）允许 completed → 转红

下一步:
- 修改 `scripts/s6i3_fault_matrix_mutation_kill.py` M-F3 / M-F5 映射 nodeid
- 新增 `tests/composition/s6i3_seeds.py::_seed_6_owner_acked_with_residual_body`（30 行 helper）
- 新增 `tests/composition/test_s6i3_fault_f10.py::test_f10_m6_completed_bypass_scan_check_blocked`（80-120 行）
- 修改 `scripts/s6i3_f10_mutation_kill.py` M6 映射 nodeid → 新 test_f10_m6_*
- M-F4 定向 mutation 实跑验证 post-TD-106 锚点真红（**未完成实跑前不得报告 M-F4 KILLED**）
- 验证 ruff + mypy baseline（0 regression）+ git diff --check + scripts/check-engineering-docs --full + 完整 backend composition 回归 + M-F3/M-F5/M-F4/M6 定向真实 PG mutation + F-matrix mutation 全量 + F10 mutation 全量
- 普通新 commit + push
- 创建 OPEN/Draft PR；等待三路 CI 全 SUCCESS

验证状态:
- Phase 0 审计：8 项 mutation（含 F10 M6）均经实际生产代码 + 公开入口路径验证完成
- 待运行：上述8 项定向 mutation + 全量 mutation kill + composition 回归 + ruff/mypy baseline

交接备注:
- 本任务**只**增强测试契约与 mutation 映射；**不**修改 production code / migration / schema / enum / CHECK / registry / CI / 门禁脚本 / KNOWN_ISSUES
- metaedu_test 独占 + 串行执行（`db_session` + `session_factory` fixture；**禁止** `s6i3_session_factory`）；禁止触碰 metaedu
- TD-104 / TD-032 保持登记不关闭；TD-105 / TD-106 🟢 完成不重开
- 不启动 F-matrix / PR-E / C1 / S5 wiring / capability flip / 六 erase 入口生产可达 / REQ-047 conformance
- **禁止** amend / rebase / force-push
- 完成后停在 OPEN/Draft，**不** Ready / **不**评分 / **不**合并 / **不** closeout
- 旧 `c07c031c` scaffold 禁止 cherry-pick / 恢复 / 复制

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P1 | R1-S6 F-matrix 7/12 + F10 M6 test contract 增强 | ⚫ 待办，独立后续 PR | F-matrix 7/12 mutation NOT-RED（M-F2/F3/F4/F5/F6/F8/F12）+ F10 M6（completed 绕过最终扫描）判别载体补齐；M6 真实 PG 路径需 G1/G2/G3 cleared + 所有 owner acked + final scan 非零 → blocked (scan reason) 的测试矩阵 | [TD-105](technical-debt.md#td-105-r1-s6-f10-实现承接契约纠偏后解除-skip--真实-pg-判别) closeout note / F-matrix #590 mutation follow-up |
| P2 | R1-S6 PR-E release drill 五阶段 canary（真实 PG / 备份 / 流量开关） | ⚫ 待办，独立后续 PR；**前置依赖 = PR-D 剩余交付，已由 PR #606 满足** | 本地无法执行（无生产基础设施 + 无备份保留 runbook 执行环境）——按 R1-AC12 字面降级为 contract-tested 验证；登记生产门禁；PR-D runbook / 编排 / 跨层 drill 已落地（PR #606 mergeCommit `d196d7f0`，source head `ad9a8fd2` + FINAL_IMPL_HEAD `69803364`），可启动 | [Plan §S6-7](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [PR #606](https://github.com/MarkDanile/MetaEduBase/pull/606) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|------|
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
