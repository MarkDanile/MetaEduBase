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

### TASK-R1-S6-I3: S6-F1..F14 故障矩阵 + TD-106 方案 A bounded integration（scope 已收敛；PR-D ledger export/replay+runbook、PR-E release drill 拆分独立后续 PR）

状态：🟢 已 squash merge 入 main（2026-08-26，**mergeCommit `68fafd81de5b0925be44e935c532cdce898e2935`**，source head `cca892b54b39836cc5e98a5e84e3028ba1ddea04`，FINAL_IMPL_HEAD `1a61ba6f`，评分 94 Original 已落入 Score Log；评审对象 main@`ddcb87ca`..`1a61ba6f`）；scope = F1-F14 故障矩阵 + TD-106 方案 A bounded integration；TD-106 已完成并关闭
最新交接（2026-08-26）：**scope 收敛 + root 三面复审 + Ready + 评分 94 + squash merge 入 main + closeout commit（已完成）**。**集成事实链**：`PR #589` (R1-S6-I3-A schema/test alignment bounded repair, squash 入 #586 mergeCommit `f6062466`, 评分 92 Original) + `PR #590` (R1-S6-I3-C S6-F1..F14 故障矩阵 + TD-106 方案 A 实现, squash 入 #586 mergeCommit `ee53b172`, 评分 94 Original; source head `cd5a437c`, FINAL_IMPL_HEAD `d3a12549`) + `PR #592` (TD-106 方案 A 实现, squash 入 #590 mergeCommit `e345c429`, 评分 92 Original) → `PR #586` (squash merge 入 main `68fafd81`, source head `cca892b5`, FINAL_IMPL_HEAD `1a61ba6f`, 评分 94 Original) → closeout commit（main closeout PR 已 squash merge 入 main）。scope 收敛（commit `9eef73cd`）撤回 PR-D/E scaffold（`s6i3_ledger_export.py` / `s6i3_restore_replay.py` / `s6i3_release_drill.py` / `restore-before-open.md` / `test_s6i3_fault_matrix_restore_replay.py` 18 项 PR-D/E 测试）——**本 root = F1-F14 故障矩阵 + TD-106 方案 A bounded integration；PR-D/E 拆分独立后续 PR**。**三面复审**（#586 root, head=`1a61ba6f`，评审对象 main@`ddcb87ca`..`1a61ba6f`）：面 A 数据/状态/scope + 面 B 并发/锁序/恢复 + 面 C 测试/mutation/ops/docs → 三面 P0=0/P1=0/P2=0/P3=3（不修复）；验证基线——fresh PG head=043 + F1-F14+TD-106 专项 37 passed/1 skipped（F10）+ TD-106 专项 20/20 + composition 全量 763 passed/1 skipped（撤回 18 项 PR-D/E 测试）+ migration roundtrip 10/10 + ruff/mypy baseline(0 reg)/git diff --check/engineering-docs --full 全绿。**TD-106 已完成并关闭**——bounded integration 已并入 main；main 现包含完整实现；migration 043/schema/enum/CHECK/CI/门禁脚本/KNOWN_ISSUES 零改动。**整体仍未完成（不属于本 root 范围）**：F10 仍 skip（`test_f10_contract_conflict_not_implemented`，TD-105 承接——前置 TD-106 现已完成，可启动 F10 实现 PR 解除 skip）；#590 mutation 9/12 真红 + M-F3/M-F5/M-F8 停止条件登记保持；PR-D/PR-E/C1/S5 production wiring/registry capability 翻转（external/runtime 保持 `erase_available=False`）均未启动；TD-104（PR-A schema/test alignment 残项）+ REQ-047（R1-S6 implementation conformance 联合闭环）保持后续承接；F-matrix 7/12 mutation NOT-RED（M-F2/F3/F4/F5/F6/F8/F12）留作独立测试 contract 增强 PR。
类型：REQ-041/047 R1-S6-I3（R1-S6 最后一片实现；S6-I1/I2/I3 已合并并 closeout）
领域：scheduler / retention / purge-recovery / fault-matrix（PR-D ledger export/replay、PR-E release drill 已拆分独立后续 PR，本 root 不含）
当前执行模式：实现（contract-first S6-5/S6-7/S6-8 已随 PR #581 冻结并入 main；本 PR 已实现 S6-I3 业务代码与测试 + 评分 94 Original）
最近接手工具：Claude Code
分支：`feature/req041-047-r1-s6-i3-fault-matrix-restore-replay` 已删除（`gh pr merge 586 --squash --delete-branch`）

需求来源：
- Spec: [R1 Retention/Purge/恢复专项契约 §10/§11](../02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md)
- Plan: [R1 分 Slice 实施计划 §R1-S6-5/§R1-S6-7/§R1-S6-8/§R1-S6-9/§R1-S6-10/§R1-S6-15](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md)（S6 契约冻结经 PR #581 并入 main `01524667`；S6-I1 经 PR #582 squash `f5072ec6`；S6-I2 经 PR #584 merge `ad7ac3e5` + closeout PR #585 merge `96ddc014`；F10 契约纠偏 + TD-106 决策门禁 经 PR #591 squash `738be6f9` + closeout PR #593 squash `ddcb87ca`；TD-106 方案 A 实现经 PR #592 `e345c429` → #590 `ee53b172` → #586 `68fafd81` 入 main；F10 真实 PG 判别 + mutation kill 经 PR #596 squash `c0ec008d` 入 main，main 现 `c0ec008d`）

下一步：root 已合 main，下一步**启动后续 PR**（按建议执行顺序）：(1) **PR-D**（ledger export executor + restore-before-open runbook，plan §S6-8/§S6-12/§S6-13）；(2) **PR-E**（release drill 五阶段 canary，plan §S6-7）；(3) **F-matrix 7/12 + F10 M6 test contract 增强 PR**（独立测试 contract 增强）；(4) **TD-104**（PR-A schema/test alignment 残项）。**F10 已完成（PR #596 已合 main `c0ec008d`）**：TD-105 由 PR #596 承接并关闭；main closeout 已记录 F10 routing 四环 + TD-106 不变式 + 7/8 mutation 真红 + M6 NOT-RED 登记。**本 root 不含、本轮不启动**（已登记为后续 PR）：PR-D / PR-E / C1 Durable Core 总验收 / S5 production wiring / registry capability 翻转（external/runtime 保持 `erase_available=False`）/ 六 erase 入口生产可达 / F-matrix 7/12 + F10 M6 test contract 增强 / TD-104 均未启动。

验证状态：scope 收敛后本地验证（PR #586 合 main 前）——fresh PG head=043 + F1-F14+TD-106 专项 37 passed/1 skipped（F10）+ TD-106 专项 20/20 + composition 全量 763 passed/1 skipped（撤回 18 项 PR-D/E 测试）+ migration roundtrip 10/10 + ruff/mypy baseline(0 reg)/git diff --check/engineering-docs --full 全绿；PR #586 三路 required checks 全 SUCCESS（Backend ~14min `Backend` at 2026-08-26T07:30:48Z + Engineering docs 17s `Engineering docs` at 2026-08-26T07:16:23Z + Frontend 2m14s `Frontend` at 2026-08-26T07:18:36Z）。**严格停止条件**：发现 P0/P1、需新 schema/migration、需修改 S5 状态机/锁序/写者矩阵、需翻转任一 registry capability、需 production scheduler wiring 或六 erase 入口可达、需真实生产 canary/backup/restore drill 才能宣称完成、replay 需调用 external/runtime adapter、无法证明旧 ledger owner_version/digest、发现与 S6-5/S6-7/S6-8 冻结语义冲突——立即停止并报告，不自行架构裁决。**禁止修改**：Metrics、Score Log、migration 043、门禁脚本、KNOWN_ISSUES、CI 配置或阈值。**未启动**：F10 实现 PR（TD-105 承接）/ PR-D（ledger export/replay executor + runbook）/ PR-E（release drill）/ C1 Durable Core 总验收 / S5 production wiring / registry capability 翻转（external/runtime 保持 `erase_available=False`）/ 六 erase 入口生产可达 / F-matrix 7/12 mutation NOT-RED 增强 PR / TD-104。

交接备注：R1-S6-I1/I2 已合并 main `96ddc014`；R1-S6-I3-A 已 squash 入 #586（PR #589 `f6062466` 评分 92）；R1-S6-I3-C 已 squash 入 #586（PR #590 mergeCommit `ee53b172` 评分 94，source head `cd5a437c`、FINAL_IMPL_HEAD `d3a12549`）；TD-106 方案 A 经 #592→#590→#586→main 完整闭合（mergeCommit `68fafd81` 评分 94 Original，source head `cca892b5`、FINAL_IMPL_HEAD `1a61ba6f`，评审对象 main@`ddcb87ca`..`1a61ba6f`）——**TD-106 已完成并关闭**；main closeout PR 已 squash merge 入 main（pure-docs）。**整体 S6-I3 仍未完成**：F10 仍 skip（TD-105 承接）+ PR-D/PR-E/C1/S5 wiring/capability flip 均未启动；TD-104/REQ-047 与既有 follow-up 不关闭；M-F3/M-F5/M-F8 mutation 停止条件登记保持；F-matrix 7/12 mutation NOT-RED（M-F2/F3/F4/F5/F6/F8/F12）留作独立测试 contract 增强 PR；restore_replay_executor 的 PR-D 骨架已随 scope 收敛撤回；S6I2_PENDING_WRITERS 中 restore_replay_executor 仍仅 pending（字符串登记、无 impl），待独立 PR-D 重建后转 registered，不接生产 wiring；TD-097/098/099/100/101/102/103 保持历史和 follow-up 编号，不因本 PR 自动覆盖或关闭；REQ-047 保持后续联合验收归属。后续收口顺序（已完成）：#590→#586（mergeCommit `ee53b172`）→ #586 root 三面复审/Ready/评分 → #586 squash→main（mergeCommit `68fafd81`）→ main closeout PR（squash merge 入 main）— **全流程闭合**。
后续接力：PR #596 已 squash merge 入 main `c0ec008d`（source head `f5cb0b34` / implementation HEAD `7cc732ba`，评分 97 Original）。**F10 已完成**（TD-105 已关闭）——F10 routing 四环 + TD-106 per-ref receipt + source 清除不变式 + 7/8 mutation 真红 + M6 NOT-RED（如实登记为 test contract 增强 follow-up）；后续接力：(1) PR-D / (2) PR-E / (3) F-matrix 7/12 + F10 M6 test contract 增强 PR / (4) TD-104（PR-A schema/test alignment）/ (5) C1 Durable Core 总验收 / (6) S5 production wiring / (7) registry capability 翻转 / (8) 六 erase 入口生产可达。

### TASK-R1-S6-I3-D: 独立 ledger export/archive + restore replay executor + restore-before-open runbook（**事实审计中，尚未实现** — 不宣称 executor/archive/runbook 已交付）

状态：🟡 进行中（2026-08-27，**事实审计阶段 — 仅读事实源 + Draft PR 占位**；**禁止本轮进入业务代码实现 / Ready / 评分 / 合并 / closeout**）
最新交接（2026-08-27）：**任务卡登记 + 独立分支 + Draft PR + 事实审计阶段**。本任务卡严格声明：当前**仅做事实审计 + Draft 验证**，尚未启动 ledger export executor / archive sink / restore replay executor / restore-before-open runbook 的代码实现。Plan §S6-8 / §S6-12 / §S6-13 / §S6-14 已冻结的 ledger export 与 restore replay 路由表 + 判定方式为唯一事实源；旧 PR-D scaffold（`s6i3_ledger_export.py` / `s6i3_restore_replay.py` / `restore-before-open.md` 等）已随 #586 scope 收敛撤回，本任务从冻结契约与当前 main 重新推导，**禁止 cherry-pick / 恢复 / 复制旧 `c07c031c` scaffold**。`S6I2_PENDING_WRITERS` 中 `restore_replay_executor` 仅字符串 pending 登记（PR #584 I3 merge `ad7ac3e5` 后），待独立 PR-D 落地后转 `registered`。
分支：`feature/req041-047-r1-s6-i3-d-ledger-restore-replay`（从 main `aff54883` 创建）
当前执行模式：事实审计（contract-to-code）——冻结契约 + Plan §S6-8/12/13/14 + §S6-15.5 TD-106 收口 + 当前 main 实现能力，逐项输出实现矩阵；**不实现 / 不修改生产代码 / 不修改 schema / 不修改 migration 043 / 不修改 S5 状态机 / 不修改 registry capability / 不修改 CI 配置 / 不修改 Score Log / 不修改 Metrics**
最近接手工具：Claude Code
类型：REQ-041/047 R1-S6-I3-D（PR-D：独立 ledger 连续导出/归档 + restore replay 执行器 + restore-before-open runbook）
领域：scheduler / retention / purge-recovery / restore-replay（M 类维护路径）
需求来源：
- Spec: [R1 Retention/Purge/恢复专项契约 §3 / §10 / §11](../02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md)（§3「从**独立保存**的 erasure operation/receipt 账本重放」字面要求 + §10 发布迁移流程 + §11 R1-AC12 验收标准）
- Plan: [R1 分 Slice 实施计划 §R1-S6-8 / §R1-S6-12 / §R1-S6-13 / §R1-S6-14 / §R1-S6-15](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md)（§S6-8 备份恢复门禁 + §S6-12 replay 状态路由表 + §S6-13 replay 判定方式 + §S6-14 后续拆分）
- 需求: [REQ-047 Agent Run/产物/证据与人工确认中心](../01-product-planning/05-requirements/REQ-047-agent-run-artifact-approval-center.md)（R1-S6 implementation conformance 联合闭环承接）
- 技术债: `S6I2_PENDING_WRITERS` 登记（`restore_replay_executor` 仅 pending）

下一步（本任务卡分两阶段）：
- **第一阶段（任务卡 + Draft PR，本轮已完成）**：从 main `aff54883` 建任务分支 + current-work.md 新增 TASK-R1-S6-I3-D + push + Draft PR（base=main）+ 等三路 Draft checks 全绿后停止
- **第二阶段（只读事实审计，本轮禁止实现）**：逐项输出实现矩阵——ledger 连续导出/归档 / 快照格式与导入校验 / replay operation 六态 / owner 六元组 / 实际执行语义 / M 类维护路径 / restore-before-open / writer-conformance 登记 / 测试与 mutation；重点回答 6 项阻塞问题；audit 完成后停留 Draft 等候用户裁决是否进入实现阶段

验证状态：**本轮暂无验证结果**（仅做事实审计 + Draft 验证；尚未实现任何业务代码）。Draft PR 三路 required checks 状态待 PR 创建后确认（Engineering docs / Backend iteration / Frontend 预计 docs-only + pytest zero change 全 SUCCESS）。**严格停止条件**（事实审计阶段禁止越过）：需要新 schema/migration/enum/CHECK；需要修改 S5 状态机/锁序/写者矩阵；需要原始敏感 ref 才能重放（external/runtime ref_value / runtime_session_ref）；需要调用 external/runtime adapter；缺少独立 archive sink 或维护互斥机制；owner 六元组或 receipt 无法证明；需要 production wiring/capability flip；冻结契约与当前可执行能力冲突；或需越过 specs §10.5「人工签字后按 tenant/canary 开启 scheduler」/§S6-7.1「V1 不支持 purge 开启时仍有旧 Writer 进程在线」——立即停在 Draft 并报告方案，不自行架构裁决。**禁止修改**：Score Log、Metrics、migration 043、schema、registry capability、门禁脚本、KNOWN_ISSUES、CI 配置或阈值；F10/TD-105 已合并内容；C1 / PR-E / S5 production wiring / capability flip 不在本任务范围启动。**数据库硬边界**：禁止 drop / truncate / reseed / 重建开发库 `metaedu`；后续测试只能使用 `metaedu_test`；任何 destructive DB 命令前必须先打印并确认实际 database name，若不是 `metaedu_test` 立即停止。

交接备注：本任务承接 TASK-R1-S6-I3 后续接力序列的 (1) PR-D 入口；从冻结契约 §S6-8/12/13/14 + §S6-15.5 TD-106 收口与当前 main 实现能力出发重新推导，不复制旧 scaffold；S6I2_PENDING_WRITERS `restore_replay_executor` 待本任务完成后转 `registered`；M 类维护路径（replay executor）与 retention/audit jobs 互斥（冻结声明）；external/runtime 未 ACK 项经 replay 保持 `blocked` + reconcile（**不调用 adapter、不冒充已 erase**）。

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P1 | R1-S6 PR-E release drill 五阶段 canary（真实 PG / 备份 / 流量开关） | ⚫ 待办，独立后续 PR | 本地无法执行（无生产基础设施 + 无备份保留 runbook 执行环境）——按 R1-AC12 字面降级为 contract-tested 验证；登记生产门禁 | [Plan §S6-7](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) |
| P1 | R1-S6 F-matrix 7/12 + F10 M6 test contract 增强 | ⚫ 待办，独立后续 PR | F-matrix 7/12 mutation NOT-RED（M-F2/F3/F4/F5/F6/F8/F12）+ F10 M6（completed 绕过最终扫描）判别载体补齐；M6 真实 PG 路径需 G1/G2/G3 cleared + 所有 owner acked + final scan 非零 → blocked (scan reason) 的测试矩阵 | [TD-105](technical-debt.md#td-105-r1-s6-f10-实现承接契约纠偏后解除-skip--真实-pg-判别) closeout note / F-matrix #590 mutation follow-up |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|------|
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
