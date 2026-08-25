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

### TASK-R1-S6-I3-TD106: settlement SUCCESS ledger/binding 收口（TD-106 方案 A 实现，stacked on #590）

状态：🟡 进行中（Draft PR #592；三面评审 P0=0/P1=2 已按用户裁决修复并验证，保持 Draft 待独立复审；TD-106 仍 P1 open）
最新交接（2026-08-25）：方案 A 实现落地（`settlement._close_window_ledger` 态 1 同事务逐 ref/binding 落 receipt+清源 ref；participant Tx2 清除逻辑提取模块级唯一写入路径 B2/E-5-2；`_aggregate_window` 态 1 携带 per-ref `ref_closures`+空 evidence fail-closed）。**三面评审**（diff `aa889db8..34e1672c`）面一 P0=0/P1=0/P2=1/P3=3 + 面二 P0=0/P1=1/P2=1/P3=4 + 面三 P0=0/P1=1/P2=1/P3=4，曾转 Ready 后因 P1≠0 `gh pr ready 592 --undo` 回 Draft。**2 项 P1 已按用户裁决修复（本批）**：(P1-A) 空冻结窗口合法 no-op SUCCESS——`_close_window_ledger` 改严格计数守卫（`len(closures) != len(t1.plan)` → fail closed；plan 空+closures 空 → no-op return），不调 adapter/不伪造 receipt/不写 ledger/不清 source，保留 aggregate 空计划确定性 ack digest，仅收敛 fence erased+checkpoint acked；新增 `test_external/runtime_empty_window_noop_success`（零 adapter 调用+合法 ack digest+零 ledger/binding 写+重放幂等）+ 防混淆守卫 `test_non_empty_plan_missing_closure_fail_closed`/`test_empty_plan_stray_closure_fail_closed`（均 fail closed 整体零写）。(P1-B) 补齐冻结矩阵第(5)项两具名 mutation——**M8 缺集合锁**（lock-acquisition sentinel 替换 `acquire_transport_aggregate_lock`，断言任何 ledger/source/fence/checkpoint 写之前必调用，external+runtime 两载体）+ **M9 败者 raise**（真实 PG stale-CAS：helper identity read 后、UPDATE 前第二连接并发合法收口，rowcount=0→raise+T2 整事务回滚无 partial fence/checkpoint ACK，external+runtime 两载体）。mutation 脚本重构支持多 edit/多测试，**9/9 全真红**。验证：TD-106 专项 20（含新增 8）+ composition 全量 781 passed/1 skipped（F10 skip 保持）+ migration roundtrip 10/10 + ruff/mypy baseline(0 reg)/git diff --check/engineering-docs 全绿。**P2 保留未关**：runtime per-binding receipt 算出即丢弃（receipt_digest 语义=ACK 证据链输入，不加列）；settlement↔participant 跨入口双写者并发用例（M9 shared-helper stale-CAS 不冒充全覆盖）；M4 receipt 复用深度。
类型：REQ-041/047 R1-S6-I3 TD-106 方案 A 实现（技术债收口；#591 = 裁决载体纯文档 Draft）
分支：feature/req041-047-r1-s6-i3-td106-settlement-ledger-closure（自 #590 head aa889db8 切出）

下一步：保持 #592 OPEN/Draft，等独立复审确认 2 项 P1 修复闭合（TD-106 仍 P1 open）；复审通过前不转 Ready、不评分、不合并、不建 closeout；不触碰 #590/#591/migration 043/schema/enum/CHECK/门禁脚本/KNOWN_ISSUES/CI；不启动 PR-D/E/C1/S5 production wiring/registry capability 翻转。

交接备注：验证基线——ruff 全包 All checks passed；mypy baseline 0 regressions；git diff --check clean；check-engineering-docs --full passed；migration 043/schema/enum/CHECK/Score Log/Metrics/CI 均未触碰（git diff name-only 核对）。mutation 证明矩阵：M1 receipt 写/M2 source 清除/M3 聚合 receipt/M4 单写 CAS（unit 级判别）/M5 空 evidence 守卫/M6 E-1 绑定重验/M7 token 重验（F11 载体）全部 red→green。本地测试库=docker colima `metaedu/postgres-zhparser:pg16`（homebrew pg16 无 zhparser 扩展，不可用）。

### TASK-R1-S6-I3-C: S6-F1..F14 故障矩阵完整批（PR-C，stacked on #586）

状态：🟡 进行中（Draft，stacked base = #586 head `a2e30fed`；本分支未推、待 PR-C Draft 创建）
最新交接（2026-08-24）：F1-F14 真实 PG 故障矩阵实现（详细验证见 PR body 真实 HEAD/映射/验证数字；未推、未转 Ready）。**F9/F11/F13/F14 已落测试 + 真实 PG 实测通过（详见 PR body）**（4 行真实 PG 反例 = 9 项子测试）；F4 crash-replay 多 ref 分步 ACK + F6 seq gap raw DELETE 409/410 + F7 first_available 推进 + SSE 410 稳定 + F12 retention Run 行锁串行；**F10 契约冲突 → 不实现**（Plan §S6-5 F10 自相矛盾；不修 S5、不上 fake；skip 占位 + 待契约裁决 PR 纠偏，类似 I3-B）；**F1/F2/F3/F5/F8** 浅层真实 PG 判别迁移至 `test_s6i3_fault_matrix.py`（worker kill / claim 半提交 / ACK 丢失 / ACK 落账后 crash / outbox claim；真实覆盖分别在既有 test_s4eb2_external_erasure / test_s4f_fault_matrix / test_s5_sch_a_claim_lease / test_s6i1_event_retention 等）。文件拆分（td-032 闭合）：1040 行 → `s6i3_seeds.py`（155，fixture + helper）+ `test_s6i3_fault_matrix.py`（F1/F2/F3/F5/F8，264）+ `test_s6i3_fault_hold.py`（F9+F10，219）+ `test_s6i3_fault_external.py`（F4+F11，331）+ `test_s6i3_fault_events.py`（F6+F7+F12，480）+ `test_s6i3_fault_scheduler.py`（F13+F14，191）+ `test_s6i3_fault_matrix_restore_replay.py`（replay/ledger/drill/serialize，696）——所有文件 < 1000。具名 mutation kill `scripts/s6i3_fault_matrix_mutation_kill.py`（memory backup + try/finally 还原，**不裸 git restore**，避免抹掉本分支未提交源码）；**5/12 mutation 真实 red-then-green**（M-F13/M-F7/M-F9/M-F11/M-F14）；**7/12 注入定义完成但与测试执行路径解耦**（M-F2/M-F3/M-F4/M-F5/M-F6/M-F8/M-F12 注入 production helper 但映射测试用 raw SQL 或浅层断言，注入后测试仍绿——属测试判别力增强范围，归 PR-C 后续或独立测试 contract 增强 PR）。验证：ruff/mypy/git diff/engineering-docs/composition 命令与结果详见 PR body（未推、未转 Ready；本卡不复制完整数字以避免与 PR body 漂移）。**严格停止条件**：mutation 无法稳定转红即报告（本轮 7/12 即此情况）——已据实报告，不冒充。**未实现**：PR-D（ledger export executor + runbook）/ PR-E（release drill 真实 canary）/ C1 / S5 production wiring / registry capability 翻转。
类型：REQ-041/047 R1-S6-I3-C（S6-I3 PR-C 拆分第三批；S6-I3-A/I3-B 已分别 squash 入 #586 / 入 main）
分支：feature/req041-047-r1-s6-i3-c-fault-matrix-completion（新建，**未推**）

下一步：创建 Draft PR（base = #586 分支 = `a2e30fed`，非 main），本地核对 local == origin == PR head + 干净工作树，停 Draft 不转 Ready/不评分/不合并/不创建 closeout；不启动 PR-D/E/C1/S5 production wiring；mutation 7/12 NOT-RED 的部分在 PR body 列明 + 留作 PR-C 后续或独立测试 contract 增强 PR；F10 契约冲突上报待契约裁决 PR 纠偏（不自行架构裁决）。

交接备注：根 PR #586 = OPEN/Draft integration root，head=`a2e30fed`（I3-A + base sync merge），本 PR stacked on `#586` 分支 → squash merge 落地入 `#586`。main 保持 `b28f84ab`。S6-5 冻结契约未改；migration 043 未触碰；CHECK / enum / Score Log / Metrics / 门禁脚本 / KNOWN_ISSUES / CI 配置或阈值均未触碰。F10 契约冲突判定见 test_s6i3_fault_hold.py `test_f10_contract_conflict_not_implemented` skip 注释。S6I2_PENDING_WRITERS 中 restore_replay_executor 仍仅 pending。

### TASK-R1-S6-I3: S6-F1..F14 真实故障矩阵 + 发布演练 + restore replay 机制与 runbook

状态：🟡 进行中（OPEN / Draft integration root；head=`f6062466` + parent base sync merge）
最新交接（2026-08-24）：stacked child #589（R1-S6-I3-A schema/test alignment，评分 92）已 squash 并入（mergeCommit `f6062466`），alignment 红灯已闭合（fresh PG head=043 24/24 + 同树 CI 三路全绿）；main@`b28f84ab` 已普通 merge 同步（Score Log 冲突按事实源解决：#589/#587 各恰一行，Metrics 未变）；**整体未完成**——F6-F14、PR-C/D/E、C1、S5 production wiring、registry capability 翻转均未启动；TD-104/REQ-047 与既有 follow-up 不关闭。
类型：REQ-041/047 R1-S6-I3（R1-S6 最后一片实现；S6-I1/I2 已合并并 closeout）
领域：scheduler / retention / purge-recovery / fault-matrix / release-drill / restore-replay
当前执行模式：实现（contract-first S6-5/S6-7/S6-8 已随 PR #581 冻结并入 main；本 PR 仅实现 S6-I3 业务代码与测试）
最近接手工具：Claude Code
分支：feature/req041-047-r1-s6-i3-fault-matrix-restore-replay

需求来源：
- Spec: [R1 Retention/Purge/恢复专项契约 §10/§11](../02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md)
- Plan: [R1 分 Slice 实施计划 §R1-S6-5/§R1-S6-7/§R1-S6-8/§R1-S6-9/§R1-S6-10](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md)（S6 契约冻结经 PR #581 并入 main `01524667`；S6-I1 经 PR #582 squash `f5072ec6`；S6-I2 经 PR #584 merge `ad7ac3e5` + closeout PR #585 merge `96ddc014`）

下一步：实现（A）S6-F1..F14 真实 PG 故障矩阵 14 项测试（逐行映射真实 test nodeid、注入机制、持久状态结果、零写/单写判别、必要 mutation；F1 lease takeover 双连接 gather / F2 SQL 篡改半提交 / F3 checkpoint 退回 + ack_digest 清重放 / F4 单 owner 分步 ACK 多 ref 逐 ref 注入 / F5 ACK 落账后聚合前 crash / F6 seq gap 测试事务内 `DISABLE TRIGGER ALL` 隔离窗口 raw DELETE / F7 first_available_event_seq + SSE 410 稳定 / F8 outbox claim 短事务 crash + SKIP LOCKED 重入 / F9 hold create vs entry 真并发双连接 gather / F10 T1/T2 间 hold 推进 + 后续 `blocked_hold_revision_changed` G2 门禁 / F11 mutate-during-lookup T2 重验 `checkpoint.state == 'erasing'` 判别载体 / F12 writer/purge pause race + retention 与 writer Run 行锁串行 / F13 进程级 kill 等价注入 = 租约过期+中途 raise+双连接，仅证 DB 状态转移等价，登记生产门禁 / F14 跨 tenant/伪造 ACK/旧 revision 重放 fail closed）+ （B）发布演练脚本 expand → writer capability → batched backfill → verify → canary enable 五阶段 fail-closed 判别（不新增 migration，复用 034..043；writer capability = registry owner_version + conformance 事实承载；canary 仅测试环境/tenant 演练；external/runtime `erase_available=False` 保持不变）+ （C）restore replay 三件套（独立 ledger export 受控快照格式：仅计数/ID/digest/owner/version/受控状态，绝不输出正文/payload/ref 原值/Runtime session ref/自由文本 reason；replay executor M 类集合锁 + 与 retention/audit jobs 互斥 + 已完成 purge 按 ledger receipt/ack_digest 标记不重复 adapter 调用 + 进行中 operation 本地重放 + external/runtime 未 ACK → blocked+reconcile 不冒充已 erase + digest/version 失配 fail closed 转 runbook 人工处置；restore-before-open runbook：恢复后服务保持不可读写 → 导入/校验独立 ledger → replay → S5 六 owner body/ref scan + S6-I2 verify → 扫描为零且门禁通过才开放流量）+ 真实 PG 独立 fresh PG 数据库 + 双连接 `NullPool`/`asyncio.gather` + AC10 sentinel 全 substring 不泄露 + 具名 mutation kill 先红后绿 try/finally 恢复 零残留。**仅当**三面复评 P0/P1=0 且决 A 收口后再允许 Ready。

验证状态：待补——三路 required checks（Backend full / Engineering docs / Frontend）+ 独立 fresh PG 全部 14 项 + release drill 5 阶段 + restore replay roundtrip 真实落地。**严格停止条件**：发现 P0/P1、需新 schema/migration、需修改 S5 状态机/锁序/写者矩阵、需翻转任一 registry capability、需 production scheduler wiring 或六 erase 入口可达、需真实生产 canary/backup/restore drill 才能宣称完成、replay 需调用 external/runtime adapter、无法证明旧 ledger owner_version/digest、发现与 S6-5/S6-7/S6-8 冻结语义冲突——立即停止并报告，不自行架构裁决。**禁止修改**：Metrics、Score Log、migration 043、门禁脚本、KNOWN_ISSUES、CI 配置或阈值。**未启动**：C1 Durable Core 总验收、S5 production wiring、registry capability 翻转（external/runtime 保持 `erase_available=False`）、六 erase 入口生产可达。

交接备注：R1-S6-I1/I2 已合并 main `96ddc014`，本 PR 起点 = main `96ddc014`；S6-I3 是 R1-S6 最后一片实现；TD-097/098/099/100/101/102/103 保持历史和 follow-up 编号，不因本 PR 自动覆盖或关闭；REQ-047 保持后续联合验收归属；restore_replay_executor 仅 M 类登记 + 集合锁，不进入生产 wiring；S6I2_PENDING_WRITERS 中 restore_replay_executor 仍仅 pending，落地后转 registered 但不接生产 wiring。

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P1 | REQ-047 C1 Durable Core 总验收 | ⚫ Blocked by R1-S1..S6 | R1 全部验收后执行联合 conformance 与文档收口 | [Joint Plan](../02-delivery-plans/02-plans/2026-07-24-req-041-047-conversation-run-contract-plan.md#slice-c1durable-core-总验收与文档收口) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|------|
| 2026-08-24 | R1-S6-I3-A schema/test alignment bounded repair（squash 入 #586） | 🟢 完成 | squash 入 #586；评分 92（Original）；幽灵列对齐真实 schema + acked fixture 合法化 + 独立 CHECK 负例 + F3 补种；fresh PG 043 24/24 + composition 750；**#586 仍 Draft 整体未完成**（F6-F14/PR-C/D/E/C1/wiring/capability 未启动）；TD-104 保持承接 | [PR #589](https://github.com/MarkDanile/MetaEduBase/pull/589)（squash `f6062466`）/ [work-log](work-log.md) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-24 | R1-S6-I3-B restore replay 持久状态域契约纠偏（contract-first，纯文档） | 🟢 完成 | PR #587（squash `66674f23`）；评分 85；三层 CHECK 闭集 + replay 路由表 + 判定方式冻结；#586 仍 Draft 未修；PR-A/C/D/E、C1、S5 wiring、capability 未启动；TD-104 + REQ-047 | [PR #587](https://github.com/MarkDanile/MetaEduBase/pull/587)（squash `66674f23`）/ [work-log](work-log.md) / [score 85](04-retrospectives/review-score-log.md) |
| 2026-08-20 | R1-S6-I2 Writer conformance suite + body/ref orphan inspection | 🟢 完成 | PR #584（merge `ad7ac3e5`）；评分 88；3 writer spec + 六类 verify 巡检 + Run 行锁；21 项专项 + 726 composition；TD-100~103 + REQ-047；S6-I3/C1/S5 wiring 未启动 | [PR #584](https://github.com/MarkDanile/MetaEduBase/pull/584)（merge `ad7ac3e5`）/ [work-log](work-log.md) / [score 88](04-retrospectives/review-score-log.md) |
| 2026-08-19 | R1-S6-I1 Retention workers（run_event_retention + run_audit_retention + migration 043） | 🟢 完成 | PR #582（squash `f5072ec6`）；评分 87（基线 `d1427567`）；两 worker + 043 guard + 两处 S5 修复落地；三面返修+决 A 测试兼容升级后 P0/P1=0；Backend 2649/1/4/0 + mutation 18/18 + 043 往返稳定；S6-I2/I3/C1/S5 wiring 未启动；TD-097/098/099 + REQ-047 | [PR #582](https://github.com/MarkDanile/MetaEduBase/pull/582)（squash `f5072ec6`）/ [work-log](work-log.md) / [score 87](04-retrospectives/review-score-log.md) |
| 2026-08-19 | R1-S5 Root Integration: settlement idempotency key 对齐 + B/C/D 联合组合根 | 🟢 完成 | root PR #577（squash `636fc425`）合并；评分 92（基线 `995aa223`）；126 专项 + composition 665 + mutation 8 组 + Backend 2600/1/4 + Frontend 326+55；production erase 入口仍不可达；follow-up REQ-047 + TD-093/095/096 + td-032 | [PR #577](https://github.com/MarkDanile/MetaEduBase/pull/577)（squash `636fc425`）/ [work-log](work-log.md) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-19 | R1-S5 SCH-D: Settlement & Retry-Reconcile（squash 入 root） | 🟢 完成 | 已 squash 入 root PR #577（`5033efc5`）并随 root 合并（`636fc425`）；child 正式评分 92（Original）；23 专项 + 12/12 mutation kill + composition 646 passed | [PR #579](https://github.com/MarkDanile/MetaEduBase/pull/579) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-19 | R1-S5 SCH-C: Rebuild & Seeding（squash 入 root） | 🟢 完成 | 已 squash 入 root PR #577（`a8f4d561`）并随 root 合并（`636fc425`）；child 正式评分 92（Original）；40 专项 + 27/27 mutation kill + composition 623 passed | [PR #578](https://github.com/MarkDanile/MetaEduBase/pull/578) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-17 | R1-S5 SCH-A Claim & Lease 实现（migration 042 + ConversationPurgeScheduler） | 🟢 完成 | migration 042 + claim/lease 服务（四转移 expected-epoch CAS、tenant 上限 4、takeover 后强制聚合）；评分 93（最终 P0/P1/P2=0）；29 专项 + 13/13 mutation kill + Backend 2504/1/4；**SCH-A 完成不代表 Scheduler 已启用**；follow-up REQ-047 | [PR #575](https://github.com/MarkDanile/MetaEduBase/pull/575)（squash merge `36d091a4`）/ [work-log](work-log.md) / [score 93](04-retrospectives/review-score-log.md) |
| 2026-08-17 | R1-S5-D-A SCH-A Lease Carrier 契约纠偏（contract-first，纯文档） | 🟢 完成 | durable lease carrier 契约已纠偏：`updated_at` 退出租约事实源、migration 042 冻结（SCH-A 落地）、三态×四转移 epoch CAS 全函数、owner entry 门禁、SCH-9..16（反例矩阵 53→61 冻结验收载体）；评分 90（最终 P0/P1=0）；**纠偏完成不代表 migration 042 或 SCH-A 已实现**；follow-up REQ-047 | [PR #573](https://github.com/MarkDanile/MetaEduBase/pull/573)（squash merge `3438c53b`）/ [work-log](work-log.md) / [score 90](04-retrospectives/review-score-log.md) |
| 2026-08-16 | R1-S5-D Scheduler 契约冻结（contract-first，纯文档） | 🟢 完成 | S5-SCH-0..5 全卷（状态机/锁序/写者矩阵/四 slice 拆分/53 项反例映射/REQ-047 分流）；评分 87（最终 P0/P1=0）；**契约完成不代表 Scheduler 实现完成**；SCH-A/B/C/D 未开工，B/C/D 联合 merged-boundary | [PR #571](https://github.com/MarkDanile/MetaEduBase/pull/571)（squash merge `253e53e4`）/ [work-log](work-log.md) / [score 87](04-retrospectives/review-score-log.md) |
| 2026-08-16 | R1-S5-I2 Owner Aggregation Reducer 原子实现 | 🟢 完成 | calculator + coordinator + 六 owner 去共享写原子落地；评分 88（最终 P0/P1=0）；专项 95 + 22 mutation kill；Backend full 2474 passed/1 skipped/4 deselected；**I2 完成不代表 S5 scheduler 完成**；follow-up REQ-047 | [PR #569](https://github.com/MarkDanile/MetaEduBase/pull/569)（squash merge `ac77d563`）/ [work-log](work-log.md) / [score 88](04-retrospectives/review-score-log.md) |
| 2026-08-15 | R1-S5-I1 Legal Hold Revision Fencing Producer 实现 | 🟢 完成 | create/release producer primitive（Conversation-first FOR UPDATE + 同事务 SQL 原子 bump + tenant-scoped 锁谓词 + fail-closed）；14 真实 PG 用例 + 7 mutation kill；评分 90，Backend full 2379；仅 primitive，不代表 I2/S5 完成 | [PR #567](https://github.com/MarkDanile/MetaEduBase/pull/567)（squash merge `edeabcd0`）/ [work-log](work-log.md) / [score 90](04-retrospectives/review-score-log.md) |
| 2026-08-14 | R1-S5-A/B/C Contract Stack Root 契约冻结（三层 stacked，纯文档） | 🟢 完成 | S5-A reducer + S5-B rebuild（Option D/族 E/F/derived G4/权威公式）+ S5-C settlement（六输出态）冻结并入 main；root 评分 86、子 PR 87/92，P0/P1=0；契约冻结≠S5 实现完成；follow-up REQ-047 | [PR #563](https://github.com/MarkDanile/MetaEduBase/pull/563)（squash merge `6f86f959`）/ [work-log](work-log.md) / [score 86](04-retrospectives/review-score-log.md) |
| 2026-08-13 | R1-S4-F Fault Matrix 实现（架构裁决 Option A） | 🟢 完成 | 多轮 P1 触发 TD-092 升级，Option A（聚合归 S5，现写标注临时投影）；18 反例 + expire_all/双门禁；#561 未实现 S5 reducer；最终 P0/P1/P2=0，评分 90，Backend full 2364 | [PR #561](https://github.com/MarkDanile/MetaEduBase/pull/561)（squash merge `bc3234bd`）/ [work-log](work-log.md) / [score 90](04-retrospectives/review-score-log.md) |
