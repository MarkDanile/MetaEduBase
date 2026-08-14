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

### R1-S5-C: Settlement-only Adapter Recovery 契约（contract-first，拆分自 #564）

状态：🟡 进行中
类型：契约冻结（contract-first，纯文档，stacked PR）
领域：R1 保留/清除（settlement / adapter recovery）
当前执行模式：plan-do（文档契约）
最近接手工具：Claude Code
分支：docs/req041-047-r1-s5c-settlement-adapter-recovery-contract（stacked 于 #564 scope-cleanup 后 HEAD `da57b947`；PR #565 Draft）

需求来源：
- Spec: [R1 §4.2/§5.2/§8](../02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md)
- Plan: [R1-S5-C 契约段（本 PR 新增）](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) + #564 S5-B-11 七族 P1（拆分源）
- 架构约束: [architecture.md](../03-engineering-governance/01-rules/architecture.md)

当前进展：拆分归一化完成——#564 落地 scope-cleanup commit（S5-B-1/S5-B-7 具体 settlement/adapter 裁决移除，只留「rebuild 输入必须已满足 S5-C settlement terminal contract」依赖接口；S5-B-9 行 14/19/20/24 编号占位移交；第三轮计数与拆分记录保留不覆盖），#564 新 HEAD `da57b947` 已推送；S5-C stacked 于该 HEAD，净 diff 仅 S5-C 契约 + 工作台状态。契约正文按「先冻结状态机」组织：S5-C-1 输入/输出态全函数（六输出态 + 已落账/failed 收敛 + fence 收敛规则）、S5-C-2 写域与 drift 绕过（frozen-snapshot 基准六条 + 禁新 Tx1 作用域限定）、S5-C-3/4/5/6 四项单独裁决（旧 adapter 身份 = 历史 resolver + fail closed / 自动恢复期限有界载体 / receipt 语义三态 / replay-only 收敛）、S5-C-7 并发与写者（锁序逐方法核对含 runtime/transport repair、互斥机制两层重写、erasing→blocked 边写者登记 + CAS token、ACK-lost 第三路径）、S5-C-8 反例矩阵 16 行、S5-C-9 接口与变更登记（S4-F 两项变更 + S5-A 补登记绑定 S5-B-8 回填载体第 9/10/11 项）。**首轮全新三面完成：P0=1/P1=7/P2=15/P3=4（27 findings）→ 去重 11 根因族 → 一次统一返修落地**；**Ready 前事实载体纠偏批次已落地**（RecoveryDescriptor 六字段 + 强不变量、deadline 进入点判定、输出态 3/5/6 独立 reason code、lookup 可重放、反例行 14/15/16）——（S5-C-10 记录）。
下一步：**Ready 前事实载体纠偏批次闭环**——独立定向复核 P0=0/P1=2/P2=3/P3=3（行 8 残留 + 例外条款偏函数，均事实载体级）→ 补正清零（复核员判定不触发上层架构裁决）；docs gate 后停下汇报。不转 Ready、不评分、不合并、不回 #564 处理 E/F。
验证状态：docs gate exit 0（返修后重跑）；首轮三面 P0=1/P1=7/P2=15/P3=4（27 findings）→ 11 根因族一次返修 + 定向复核闭环（S5-C-10 记录）。
交接备注：Draft；不回 #563（保持 `efde24e4`）、不处理 S5-B 族 E/F、不转 Ready、不评分、不合并、不启动实现或 migration。S5-B 状态见下。

### R1-S5-B: Purge Revision Rebuild & Evidence Seeding 契约（stacked contract-first，Option D）

状态：🔴 阻塞（Draft paused/blocked by S5-C）
类型：契约冻结（contract-first，纯文档，stacked PR）
领域：R1 保留/清除（rebuild/seeding/lineage）
当前执行模式：plan-do（文档契约）
最近接手工具：Claude Code
分支：docs/req041-047-r1-s5b-rebuild-seeding-contract（#564，HEAD `da57b947`，stacked 于 #563 `efde24e4`）

需求来源：
- Plan: [R1-S5-B 契约段](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md)

当前进展：两轮三面 + Option D（quiesce-and-finalize）架构重写落地；第三轮广域三面 P0=0/P1=10/P2=17/P3=13（去重 9 族）→ 按指令停止并拆分 S5-C；scope-cleanup 落地（S5-B-1/S5-B-7 settlement/adapter 具体裁决移交 S5-C，只留依赖接口；S5-B-9 行 14/19/20/24 编号占位）。
下一步：**暂停等待 S5-C 冻结**；S5-C 冻结后回填「settlement/adapter 契约指向 S5-C」前向指针；族 E/F（seeding/聚合阶段分离、re-added reason 分派）在 S5-B 主体后续返修。
验证状态：docs gate exit 0（scope-cleanup commit pre-commit 通过）。
交接备注：#564 保持 Draft 未合并；不恢复 #563、不启动 I1/I2/S5 实现/S6/C1、不评分不转 Ready。S5-A 状态：Draft #563 冻结在 `efde24e4`。

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
| 2026-08-13 | R1-S4-F Fault Matrix 实现（架构裁决 Option A） | 🟢 完成 | 多轮 P1 触发 TD-092 升级，Option A（聚合归 S5，现写标注临时投影）；18 反例 + expire_all/双门禁；#561 未实现 S5 reducer；最终 P0/P1/P2=0，评分 90，Backend full 2364 | [PR #561](https://github.com/MarkDanile/MetaEduBase/pull/561)（squash merge `bc3234bd`）/ [work-log](work-log.md) / [score 90](04-retrospectives/review-score-log.md) |
| 2026-08-12 | R1-S4-F Fault 矩阵 + S4 收口 契约细化 | 🟢 完成 | 纯文档冻结 S4-F 契约（F-0~F-7：故障点清单 16 项 + 五方状态一致矩阵 + 注入机制 + 互操作回归 + 与 S5/S6 分工 + 反例矩阵 11 项 + S4 收口）；首轮 P0=0/P1=6/P2=9/P3=9，5 根因族返修（含纠正 1 条返修引入新 P1）→ P0/P1=0，评分 92；净 diff 仅 2 纯文档文件；registry 保持 external/runtime False | [PR #559](https://github.com/MarkDanile/MetaEduBase/pull/559)（squash merge `d658f6eb`）/ [work-log](work-log.md) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-12 | R1-S4-E-C Runtime Conformance Fake | 🟢 完成 | `RuntimeErasureParticipant` conformance fake（`runtime.private.v1`）：session destroy 双事务 + 旧 epoch/迟到 seq/unknown outcome/ACK 重放 + E-3a/E-3b；首轮 P0=0/P1=3/P2=9/P3=16，5 根因族返修 + 定向复核 P0/P1/P2=0，评分 92；registry False | [PR #557](https://github.com/MarkDanile/MetaEduBase/pull/557)（squash merge `c31df023`）/ [work-log](work-log.md) / [score 92](04-retrospectives/review-score-log.md) |
| 2026-08-12 | DOC-080 正式评分提交原子边界与 Metrics Snapshot 所有权 | 🟢 完成 | 冻结 finding/返修与正式评分子阶段、Score Log 单行净 diff、工作台 merge 后 closeout 和 Metrics 独立复盘边界；新增基线感知检查器与 21 个 Git fixture；首轮两项 P1 归一根因族返修后 P0/P1=0，评分 91；Ready Backend full 全绿 | [PR #555](https://github.com/MarkDanile/MetaEduBase/pull/555)（squash merge `2b801a60`）/ [DOC-080](technical-debt.md#doc-080-固化正式评分提交原子边界与-metrics-snapshot-所有权) / [work-log](work-log.md) / [score 91](04-retrospectives/review-score-log.md) |
| 2026-08-11 | R1-S4-E-B2 External Erasure Participant | 🟢 完成 | external erasure participant（3 source DB ref 唯一清除者 + 双事务协议 Tx1/Tx2 + E-3a 失败矩阵 + E-3b 查询/reconcile 闭环）；三面 3 根因族 + 判别力增强批次，评分 91；registry 保持 False；Backend full 全绿 | [PR #552](https://github.com/MarkDanile/MetaEduBase/pull/552)（squash merge `a6aee2e7`）/ [Plan §R1-S4-E](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#r1-s4-e-external-payload--runtime-conformance-契约细化) / [work-log](work-log.md) / [score 91](04-retrospectives/review-score-log.md) |
| 2026-08-10 | R1-S4-E-B1 Lifecycle Registration + Adapter Contract | 🟢 完成 | lifecycle registration port（registered 唯一生产者 + promote blocked->registered）+ adapter contract（E-2b 硬前置 + E-3a 分类 + idempotency key/receipt digest）；集合锁 owner 与 backfill 同源；三面 3 根因族 + 独立测试/运维面 P1 清零，评分 90；registry False | [PR #550](https://github.com/MarkDanile/MetaEduBase/pull/550)（squash merge `683d8c06`）/ [Plan §R1-S4-E](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#r1-s4-e-external-payload--runtime-conformance-契约细化) / [work-log](work-log.md) / [score 90](04-retrospectives/review-score-log.md) |
| 2026-08-10 | R1-S4-E-A Ref Tombstone | 🟢 完成 | migration 041 guard 扩展（持 ref 旧状态 -> redacted 无 ref，revision id 缩短避免版本表 DDL）+ transport inline-only 清 / ref-bearing 零修改 blocked；三面 0/2/12/10 → 12 条决策返修 → P0/P1=0，评分 91；Backend full 全绿 | [PR #548](https://github.com/MarkDanile/MetaEduBase/pull/548)（squash merge `0797e70c`）/ [Plan §R1-S4-E](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#r1-s4-e-external-payload--runtime-conformance-契约细化) / [work-log](work-log.md) / [score 91](04-retrospectives/review-score-log.md) |
| 2026-08-09 | R1-S4-E External payload + Runtime conformance 契约细化 | 🟢 完成 | 纯文档冻结 external/runtime 契约（7 根因 + 四 PR 拆分 + 双事务协议 + 验收矩阵）；三面首轮 6/20/12/2 → 8 根因族一次返修 → 定向复核 P0/P1=0；external/runtime registry 全程 False；三路 CI 全绿 | [PR #546](https://github.com/MarkDanile/MetaEduBase/pull/546)（squash merge `c243c36d`）/ [Plan §R1-S4-E](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#r1-s4-e-external-payload--runtime-conformance-契约细化) / [work-log](work-log.md) |
| 2026-08-09 | R1-S4-D-B Ledger Resolve + Activation | 🟢 完成 | 共享 ledger service + epoch_unresolvable evidence/CAS resolve + 两类 gate + registry 激活；三面 5 根因族(含 P0 锁序 AB-BA)一次返修 + 定向复核 P0/P1=0，评分 88；Backend full 三路 CI 全绿 | [PR #544](https://github.com/MarkDanile/MetaEduBase/pull/544)（squash merge `81cf83b8`）/ [Plan §R1-S4-D](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) / [score 88](04-retrospectives/review-score-log.md) |
| 2026-08-09 | R1-S4-D-A Transport Participant Core（workspace/execution transport eraser） | 🟢 完成 | 共享基类（S2-D/S3-D 管道收敛）+ 两 participant + S4-C tombstone 互操作；三面 5 根因族 → 定向 → 轻量 → 最终核对 P0/P1=0，评分 93；Backend full 三路 CI 全绿；registry 保持 False | [PR #542](https://github.com/MarkDanile/MetaEduBase/pull/542)（squash merge `5fc5c33b`）/ [Plan §R1-S4-D](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) / [score 93](04-retrospectives/review-score-log.md) |
| 2026-08-07 | R1-S4-D 契约细化（transport participant 拆分） | 🟢 完成 | 冻结 S4-D-A Core / S4-D-B Resolve+Activation 两 PR 拆分；S4-D-A 不翻 registry、S4-D-B 统一翻（merged-boundary）；两类 gate 区分（conversation_scope 内嵌 fail closed / tenant_scope 共享查询）；集合锁免取条件冻结；三面 0/8/10/9 → 5 根因族 → 定向复核 0/0/3/2 | [PR #541](https://github.com/MarkDanile/MetaEduBase/pull/541)（squash merge `51a12df6`）/ [Plan §R1-S4-D](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-08-07 | R1-S4-C 实现 PR-B（Claim/consumer CAS + deterministic terminalization） | 🟢 完成 | 六元 CAS + unknown/stale 双事务协议 + C1 第 4 跳 + allowlist + C8 项 11；round-1 三面 3 根因族返修 + round-2 定向复核 P0/P1 清零，评分 90；Draft iteration + Ready Backend full 三路 CI 全绿 | [PR #539](https://github.com/MarkDanile/MetaEduBase/pull/539)（squash merge `8f184935`）/ [Plan §R1-S4-C](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) / [score 90](04-retrospectives/review-score-log.md) |
| 2026-08-07 | R1-S4-C 实现 PR-A（Producer propagation + replay/catch-up） | 🟢 完成 | writer 真实 scope/epoch + COMPLETED 非 NULL epoch 守卫 + existing 校验 + replay 不重写 + catch-up 收敛；round-1 三面 4 根因族返修 + round-2 P0/P1 清零，评分 89；Backend full 绿 | [PR #537](https://github.com/MarkDanile/MetaEduBase/pull/537)（squash merge `2e70c1df`）/ [Plan §R1-S4-C](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-08-07 | R1-S4-C Writer/Claim Scope + Epoch Fence 契约冻结 | 🟢 完成 | 冻结 scope/epoch 四跳传播链、六元 CAS（turn/output 三源）、claim 短事务 + 锁序矩阵、unknown/stale 双事务协议状态表（具名 code + digest envelope + 重放精确终态三分支）、C6 11 反例 + C8 11 项验收矩阵；10 轮收敛终审 0/0/0/0，评分 87；契约 PR 恢复纯文档 | [PR #535](https://github.com/MarkDanile/MetaEduBase/pull/535)（squash merge `c2e1af42`）/ [Plan §R1-S4 C1-C9](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-08-06 | TD-092 高风险 PR CI 反馈周期与复审收敛治理 | 🟢 完成 | Draft risk-targeted `2m44s / 297 passed`，Ready 最新 HEAD 保留 Backend full；三面首轮复审、根因族返修、连续两轮新 P1 升级与单风险域 PR 规则落地；独立复核 0/0/0/0，评分 93 | [PR #532](https://github.com/MarkDanile/MetaEduBase/pull/532)（squash merge `fb6058ac`）/ [TD-092](technical-debt.md#td-092-高风险-pr-ci-反馈周期与复审收敛治理) / [work-log](work-log.md) |
| 2026-08-06 | R1-S4-B Transport/External Schema + Backfill 实现 | 🟢 完成 | migration 040（四表 scope 列 + 两 ledger + inbox tombstone）+ 五维 verify backfill（scope/epoch/external-ref/投影/scope-vs-来源）+ CLI；十二轮独立复审 0/0/0/0（含 epoch-only 收敛、表↔issue 绑定、external ref 绑定 heal、B2 类型裁决共用 expected）；全量 2103 passed | [PR #530](https://github.com/MarkDanile/MetaEduBase/pull/530)（squash merge `0fb43ccb`）/ [Plan §R1-S4](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
