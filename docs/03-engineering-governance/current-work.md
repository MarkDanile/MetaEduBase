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

### TASK-R1-S6-I3: S6-F1..F14 真实故障矩阵 + 发布演练 + restore replay 机制与 runbook

状态：🟡 进行中
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

### TASK-R1-S6-I3-A: schema/test alignment bounded repair（stacked on #586）

状态：🟡 进行中
类型：REQ-041/047 R1-S6-I3-A（R1-S6-I3-B 契约纠偏（PR #587 squash `66674f23` 已合并）后首个拆分；bounded 修复）
领域：scheduler / purge-recovery / restore-replay / 测试与 schema 事实对齐
当前执行模式：bounded 修复（schema/test alignment；契约已由 PR #587 冻结）
最近接手工具：Claude Code
分支：feature/req041-047-r1-s6-i3-a-schema-test-alignment（stacked base = #586 head `3fb71cc6`）

需求来源：
- Plan: [R1-S6-I3-B §S6-14 PR-A 承接](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md)
- 技术债：TD-104（schema/test alignment 稳定承接项）

范围（严格 bounded）：(1) ledger export reconcile 幽灵列对齐真实 schema（observed_at→created_at、resolution_state→state，migration 040 :153-173 + ORM agent_transport_ledger.py 复核）+ datetime ISO 序列化；(2) 测试 checkpoint SELECT 对齐真实列（capability_digest/reason_code/created_at；无 intent_digest/recorded_at/failure_code/revision——版本事实 = owner_version + attempt）；(3) acked fixture 合法 64-hex + `_seed_checkpoint` 非 acked ⇒ ack_digest NULL（ck_agent_purge_owner_ack 034:567-571）+ 独立 CHECK 拒绝负例 `test_ck_agent_purge_owner_ack_rejects_short_ack_digest`；(4) F3 补种缺失 checkpoint 行使 ACK-丢失 UPDATE 语义可达。**不处理** quiesced/rebuilding enum drift（PR-B 契约已裁决，代码侧归 PR-D）；不实现 F6-F14；不深化 replay executor/ledger export/runbook/release drill。

下一步：Draft checks 三路全绿后停止（不转 Ready、不评分、不合并、不创建 closeout）。

验证状态：fresh PG（重建 metaedu_test，alembic head=043）24/24 S6-I3 专项 + composition 全量 750 passed + ruff clean + mypy clean + git diff --check clean + check-engineering-docs --full passed。**禁止修改**：migration 043 / 任何 schema/enum/CHECK / S5 状态机/锁序/写者矩阵 / Score Log / Metrics / 门禁脚本 / KNOWN_ISSUES / CI 配置或阈值。**未启动**：PR-C/D/E、C1、S5 production wiring、registry capability 翻转；#586 保持 OPEN/Draft 不改写、不 rerun。

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
