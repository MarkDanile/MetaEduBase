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

### R1-S5 SCH-B: Owner Execution Orchestrator（B/C/D 联合交付 stack root）

状态：🟡 进行中
类型：实现（反例先行 + 具名 mutation kill）
领域：R1 retention/purge scheduler
当前执行模式：plan-do（TD-092 三面复审）
最近接手工具：Claude Code
分支：feature/req041-047-r1-s5-sch-b-owner-execution-orchestrator

需求来源：
- Plan: ../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md §R1-S5-D S5-SCH-1/2/3

当前进展：开工，未写代码/测试。
下一步：owner 字典序循环 + 每 entry 前 renew lease + 锁内 token 重验（operation revision/lease epoch/expiry/purge revision + Conversation revision/hold + registry digest）+ checkpoint/fence 重读（acked/failed 跳过、erasing 交 settlement port、blocked 白名单重试）+ 每 owner 后 coordinator + takeover 账本恢复 + 显式 `tick()`（1 分钟周期重算，无后台循环）+ retry 预算 3/pre-window 豁免/next_retry_at 仲裁/预算耗尽 failed；窄 settlement port（erasing 收口 + failed-fence 收敛由 port 承担，SCH-B 不写 fence）；owner participant 经显式 port/map 注入（不建生产组合根，六 erase 入口静态守卫仍不可达）。
验证状态：未运行
交接备注：**B/C/D stack root**——后续 SCH-C/SCH-D 将 stacked 进入本 root PR；本 PR 不实现 SCH-C rebuild/seeding、SCH-D settlement、完整 API、指标日志、participant 三键收窄、S6、C1；不转 Ready/评分/合并；不创建 SCH-C/SCH-D 分支、不启用生产 wiring。

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P1 | REQ-047 C1 Durable Core 总验收 | ⚫ Blocked by R1-S1..S6 | R1 全部验收后执行联合 conformance 与文档收口 | [Joint Plan](../02-delivery-plans/02-plans/2026-07-24-req-041-047-conversation-run-contract-plan.md#slice-c1durable-core-总验收与文档收口) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-08-17 | R1-S5 SCH-A Claim & Lease 实现（migration 042 + ConversationPurgeScheduler） | 🟢 完成 | migration 042 + claim/lease 服务（四转移 expected-epoch CAS、tenant 上限 4、takeover 后强制聚合）；评分 93（最终 P0/P1/P2=0）；29 专项 + 13/13 mutation kill + Backend 2504/1/4；**SCH-A 完成不代表 Scheduler 已启用**；follow-up REQ-047 | [PR #575](https://github.com/MarkDanile/MetaEduBase/pull/575)（squash merge `36d091a4`）/ [work-log](work-log.md) / [score 93](04-retrospectives/review-score-log.md) |
| 2026-08-17 | R1-S5-D-A SCH-A Lease Carrier 契约纠偏（contract-first，纯文档） | 🟢 完成 | durable lease carrier 契约已纠偏：`updated_at` 退出租约事实源、migration 042 冻结（SCH-A 落地）、三态×四转移 epoch CAS 全函数、owner entry 门禁、SCH-9..16（反例矩阵 53→61 冻结验收载体）；评分 90（最终 P0/P1=0）；**纠偏完成不代表 migration 042 或 SCH-A 已实现**；follow-up REQ-047 | [PR #573](https://github.com/MarkDanile/MetaEduBase/pull/573)（squash merge `3438c53b`）/ [work-log](work-log.md) / [score 90](04-retrospectives/review-score-log.md) |
| 2026-08-16 | R1-S5-D Scheduler 契约冻结（contract-first，纯文档） | 🟢 完成 | S5-SCH-0..5 全卷（状态机/锁序/写者矩阵/四 slice 拆分/53 项反例映射/REQ-047 分流）；评分 87（最终 P0/P1=0）；**契约完成不代表 Scheduler 实现完成**；SCH-A/B/C/D 未开工，B/C/D 联合 merged-boundary | [PR #571](https://github.com/MarkDanile/MetaEduBase/pull/571)（squash merge `253e53e4`）/ [work-log](work-log.md) / [score 87](04-retrospectives/review-score-log.md) |
| 2026-08-16 | R1-S5-I2 Owner Aggregation Reducer 原子实现 | 🟢 完成 | calculator + coordinator + 六 owner 去共享写原子落地；评分 88（最终 P0/P1=0）；专项 95 + 22 mutation kill；Backend full 2474 passed/1 skipped/4 deselected；**I2 完成不代表 S5 scheduler 完成**；follow-up REQ-047 | [PR #569](https://github.com/MarkDanile/MetaEduBase/pull/569)（squash merge `ac77d563`）/ [work-log](work-log.md) / [score 88](04-retrospectives/review-score-log.md) |
| 2026-08-15 | R1-S5-I1 Legal Hold Revision Fencing Producer 实现 | 🟢 完成 | create/release producer primitive（Conversation-first FOR UPDATE + 同事务 SQL 原子 bump + tenant-scoped 锁谓词 + fail-closed）；14 真实 PG 用例 + 7 mutation kill；评分 90，Backend full 2379；仅 primitive，不代表 I2/S5 完成 | [PR #567](https://github.com/MarkDanile/MetaEduBase/pull/567)（squash merge `edeabcd0`）/ [work-log](work-log.md) / [score 90](04-retrospectives/review-score-log.md) |
| 2026-08-14 | R1-S5-A/B/C Contract Stack Root 契约冻结（三层 stacked，纯文档） | 🟢 完成 | S5-A reducer + S5-B rebuild（Option D/族 E/F/derived G4/权威公式）+ S5-C settlement（六输出态）冻结并入 main；root 评分 86、子 PR 87/92，P0/P1=0；契约冻结≠S5 实现完成；follow-up REQ-047 | [PR #563](https://github.com/MarkDanile/MetaEduBase/pull/563)（squash merge `6f86f959`）/ [work-log](work-log.md) / [score 86](04-retrospectives/review-score-log.md) |
| 2026-08-13 | R1-S4-F Fault Matrix 实现（架构裁决 Option A） | 🟢 完成 | 多轮 P1 触发 TD-092 升级，Option A（聚合归 S5，现写标注临时投影）；18 反例 + expire_all/双门禁；#561 未实现 S5 reducer；最终 P0/P1/P2=0，评分 90，Backend full 2364 | [PR #561](https://github.com/MarkDanile/MetaEduBase/pull/561)（squash merge `bc3234bd`）/ [work-log](work-log.md) / [score 90](04-retrospectives/review-score-log.md) |
| 2026-08-12 | R1-S4-F Fault 矩阵 + S4 收口 契约细化 | 🟢 完成 | 纯文档冻结 S4-F 契约（F-0~F-7：故障点清单 16 项 + 五方状态一致矩阵 + 注入机制 + 互操作回归 + 与 S5/S6 分工 + 反例矩阵 11 项 + S4 收口）；首轮 P0=0/P1=6/P2=9/P3=9，5 根因族返修（含纠正 1 条返修引入新 P1）→ P0/P1=0，评分 92；净 diff 仅 2 纯文档文件；registry 保持 external/runtime False | [PR #559](https://github.com/MarkDanile/MetaEduBase/pull/559)（squash merge `d658f6eb`）/ [work-log](work-log.md) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-12 | R1-S4-E-C Runtime Conformance Fake | 🟢 完成 | `RuntimeErasureParticipant` conformance fake（`runtime.private.v1`）：session destroy 双事务 + 旧 epoch/迟到 seq/unknown outcome/ACK 重放 + E-3a/E-3b；首轮 P0=0/P1=3/P2=9/P3=16，5 根因族返修 + 定向复核 P0/P1/P2=0，评分 92；registry False | [PR #557](https://github.com/MarkDanile/MetaEduBase/pull/557)（squash merge `c31df023`）/ [work-log](work-log.md) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-12 | DOC-080 正式评分提交原子边界与 Metrics Snapshot 所有权 | 🟢 完成 | 冻结 finding/返修与正式评分子阶段、Score Log 单行净 diff、工作台 merge 后 closeout 和 Metrics 独立复盘边界；新增基线感知检查器与 21 个 Git fixture；首轮两项 P1 归一根因族返修后 P0/P1=0，评分 91；Ready Backend full 全绿 | [PR #555](https://github.com/MarkDanile/MetaEduBase/pull/555)（squash merge `2b801a60`）/ [DOC-080](technical-debt.md#doc-080-固化正式评分提交原子边界与-metrics-snapshot-所有权) / [work-log](work-log.md) / [score 91](04-retrospectives/review-score-log.md) |
| 2026-08-11 | R1-S4-E-B2 External Erasure Participant | 🟢 完成 | external erasure participant（3 source DB ref 唯一清除者 + 双事务协议 Tx1/Tx2 + E-3a 失败矩阵 + E-3b 查询/reconcile 闭环）；三面 3 根因族 + 判别力增强批次，评分 91；registry 保持 False；Backend full 全绿 | [PR #552](https://github.com/MarkDanile/MetaEduBase/pull/552)（squash merge `a6aee2e7`）/ [Plan §R1-S4-E](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#r1-s4-e-external-payload--runtime-conformance-契约细化) / [work-log](work-log.md) / [score 91](04-retrospectives/review-score-log.md) |
| 2026-08-10 | R1-S4-E-B1 Lifecycle Registration + Adapter Contract | 🟢 完成 | lifecycle registration port（registered 唯一生产者 + promote blocked->registered）+ adapter contract（E-2b 硬前置 + E-3a 分类 + idempotency key/receipt digest）；集合锁 owner 与 backfill 同源；三面 3 根因族 + 独立测试/运维面 P1 清零，评分 90；registry False | [PR #550](https://github.com/MarkDanile/MetaEduBase/pull/550)（squash merge `683d8c06`）/ [Plan §R1-S4-E](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#r1-s4-e-external-payload--runtime-conformance-契约细化) / [work-log](work-log.md) / [score 90](04-retrospectives/review-score-log.md) |
| 2026-08-10 | R1-S4-E-A Ref Tombstone | 🟢 完成 | migration 041 guard 扩展（持 ref 旧状态 -> redacted 无 ref，revision id 缩短避免版本表 DDL）+ transport inline-only 清 / ref-bearing 零修改 blocked；三面 0/2/12/10 → 12 条决策返修 → P0/P1=0，评分 91；Backend full 全绿 | [PR #548](https://github.com/MarkDanile/MetaEduBase/pull/548)（squash merge `0797e70c`）/ [Plan §R1-S4-E](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#r1-s4-e-external-payload--runtime-conformance-契约细化) / [work-log](work-log.md) / [score 91](04-retrospectives/review-score-log.md) |
