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

### TASK-R1-S6-I3-F10: S6-F10 契约核对纠偏（contract-first，纯文档）

状态：🟡 进行中（Draft PR #591 = OPEN/Draft，base = main，独立分支非 stacked；§S6-15 冻结：读法甲 + 唯一可执行路由表 + TD-106 方案 A 决策材料；**TD-106 方案 A 实现已通过 PR #592 squash 入 #590 parent（mergeCommit `e345c429`，评分 92 Original 已落入 Score Log）；#590 仍 OPEN/Draft、整体未完成，本 PR #591 不承载代码实现、保持 Draft**）
最新交接（2026-08-25）：F10 契约只读核对完成 + 契约纠偏段 §S6-15 冻结 + **独立三面+对抗质疑者复评审完成**：三面（数据/状态机 / 并发/锁序 / 文档一致性）+ 1 个对抗质疑者从 6 个攻击角度独立取证。**读法甲本身三面+对抗质疑者一致确认成立**（前 4 环：T2 单向放行 → fence erased + checkpoint acked → G2 blocked → rebuild HOLD_GATED，逐环代码验证通过）。但复评发现两处文档级错误须纯文档修正：**§S6-15.2 论证支柱 "participant Tx2 不 ack / 只由 settlement 落账" 被证伪**（external participant Tx2 原子写 fence ERASED + checkpoint acked + refs erased，单 commit `external_ref_erasure_participant.py:824-858`，orchestrator 明文「participant 自记 blocked/acked」`owner_execution_orchestrator.py:399-401`）——改挂三证据链：(1) 裁决二 plan:2136 显式命名 + 明文判别；(2) F10 注入前提（hold 推进）下 participant 等值检查在到达 ACK 写之前即 fail-closed；(3) 期望结果文本与 S5-C-1 frozen snapshot 验收三处锁定。**§S6-15.3 前置行不可达**（refs erased + checkpoint/fence 仍 erasing 经真实 participant 不可达）——改 "Tx1 已提交 + Tx2 未落账 → refs 仍 registered"。**对抗质疑者额外发现** settlement SUCCESS 不写 ledger/binding（pre-existing 实现 vs S5-C-1 冻结契约缺口）：任何带 external ref/binding 的 settlement recovery 完成后 final scan 非零 → 优先级 3 永久死锁；登记 §S6-15.5 + TD-106/P1（影响一切 settlement recovery 路径，与 F10 路由正交）。§S6-15 冻结：两套 hold-drift 路径事实基线（Tx1/Tx2 真锚点 = `transport_erasure_participant.py:356` 基线，§S6-15.1）+ 三证据链读法锁定 + 唯一可执行路由表（含可达前置 / 禁止构造状态 / → completed 链尾条件式）+ 待裁决项 4 项 + §S6-15.5 settlement SUCCESS ledger 写缺口。**TD-106 决策门禁（2026-08-25）**：方案 A 已用户批准；实现由独立 stacked PR #592 承载（base = #590 分支），已 squash 入 #590 parent（mergeCommit `e345c429`，评分 92 Original 落入 Score Log）。**实现证据（2026-08-25 治理归位，plan §S6-15.5 追加）**：方案 A 实现落地（`_close_window_ledger` 严格计数守卫 + 空窗口合法 no-op SUCCESS + per-ref/binding 落 receipt+清源 ref + D8 集合锁 + B2 唯一清除路径）+ M8/M9 mutation 补齐冻结矩阵第 (5) 项 + 9/9 全真红 + 20 项 TD-106 专项 + composition 781 passed/1 skipped + P1-A/P1-B 定向复核 P0/P1=0；TD-106 状态改为"实现与评审已闭合并入 integration parent，待 #590/main merged-boundary"，**本登记不标记完成、不关闭**。**P2 三项保留未关**：(P2-1) runtime per-binding receipt 形参零使用（语义=ACK 证据链输入，不加列）；(P2-2) settlement↔participant 跨入口双写者并发用例（M9 shared-helper stale-CAS 不冒充全覆盖 = 裁决项 2a）；(P2-3) M4 receipt 复用深度。**F10 路由四环状态**：F10 测试仍未解除 skip（#590 `test_f10_contract_conflict_not_implemented` 保持 skip）；#590 整体未完成（F10 + M-F3/M-F5/M-F8 + PR-D/E + C1 + S5 production wiring + registry capability 翻转 仍未处理）；四环路由（T2 单向放行 → fence erased/checkpoint acked → G2 hold-drift 投影 → rebuild G3 HOLD_GATED）冻结不变。
类型：REQ-041/047 R1-S6-I3-F10（S6-F10 契约纠偏；参照 I3-B PR #587 先例）
分支：docs/req041-047-r1-s6-i3-f10-contract

下一步：本 PR #591 仅追加治理文档（§S6-15.5 实现证据 + technical-debt TD-106 状态更新 + current-work 同步），保持 Draft 不转 Ready/不评分/不合并；最终复核 P0/P1=0 后转 Ready → 三路 required checks 全绿 → 评分（`scripts/check-review-score-submit --base FINAL_IMPL_HEAD --pr 591`，新增唯一 `#591 Original` 行，Metrics unchanged）。本轮不合并；TD-105（F10 实现承接）阻塞于 #590/main merged-boundary；不启动 PR-D/E/C1/S5 production wiring/registry capability 翻转。

交接备注：F10 当前 skip（#590 `test_f10_contract_conflict_not_implemented`）；本纠偏不带入 #590 任何代码/测试；#590 = OPEN/Draft head=`733f1b2b`（PR #592 squash mergeCommit `e345c429` + parent 治理同步），stacked on #586 `a2e30fed`；main 保持 `b28f84ab`。验证：check-engineering-docs --full + git diff --check + Draft 三路 checks。若发现需代码/schema/S5 契约修改，立即保持 Draft 并报告，不自行裁决。follow-up TD-104 + TD-105 + TD-106 + REQ-047。

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
