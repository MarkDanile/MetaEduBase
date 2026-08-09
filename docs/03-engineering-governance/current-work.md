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

### TASK-REQ041-047-S4D-B: R1-S4-D-B Ledger Resolve + Activation

状态：🟡 进行中（Draft risk-targeted）
类型：实现（TD-092 Draft + `Backend iteration`）
领域：R1-S4-D Transport Participants（ledger resolve + registry 激活）
最近接手工具：Claude Code
分支：`feat/req041-047-r1-s4d-ledger-resolve`

需求来源：
- Plan: [R1-S4-D 契约细化 §D-B-1/D-B-2/D-B-3/D-Act-1](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#r1-s4-d-transport-participant-契约细化)
- 技术债：TD-092（高风险 PR 收敛治理，Draft risk-targeted）

当前进展：
- 落点对账完成；共享 ledger service（`agent_transport_ledger_service.py`）+ resolve + gate 查询 + registry 激活已实现。
- backfill/consumer 两侧改共享层（消除导入 backfill 私有）；S4-D-A 矩阵删 `_transport_owners_active` fixture、capability gate 测试翻转为放行断言（52 passed 不变）。
- 三面首轮复审完成（P0=1/P1=8/P2=8/P3=5，归 5 根因族）→ **5 族一次返修完成**（集合锁前置修 P0 AB-BA、gate expected_revision=None + 集成测试、replay/consumed 反例、CAS 0 行、口径修正）。

下一步：
- 返修批次提交 → 一次定向复核 → P0/P1 清零后 Ready + 唯一一次 Backend full。

验证状态：
- S4-D-B 矩阵 24 passed + 邻近（S4-D-A 52 + backfill 44 + registry 10）= 130 passed（专项小集合）；ruff 0；mypy 0。
- **CI 口径（族 5 修正）**：Draft `Backend iteration` risk-targeted 实际 **613 passed / 4m45s**（run 31286310836）——非专项 149；Ready 后 Backend full 以最新 HEAD 为准。
- **batch3 顺序污染记录失效**（族 5）：现 main 单独跑 batch3 10 passed 全绿、与 S4-D-A 同跑 62 passed 全绿——原「既有 main 污染」在当前 main 不可复现，已修正记录。

交接备注：
- 只 resolve `conversation_scope` 行；`tenant_scope`/`orphan` 不 resolve（留 S5/运维）。
- ledger `resolved` 不代替 S4-C Tx2 精确终态（重放三分支保持）。
- 不扩入 S4-E/F、migration 041、S5 scheduler、S6、external/runtime owner；不自动合并。

## 下一批候选任务

按"建议执行顺序"排序；候选区只保留近期 1 到 3 个入口，完整任务池回 `docs/01-product-planning/04-backlog.md` / `docs/03-engineering-governance/technical-debt.md`。

| 优先级 | 任务 | 状态 | 建议下一步 | 事实源 |
|--------|------|------|------------|--------|
| P1-P | REQ-042 Agent Workspace 塑形 | 🔵 Ready for Docs Only | 可并行塑形 Conversation/Run/Event UI 契约；完整代码实现等待 R1/C1 | [Requirement](../01-product-planning/05-requirements/REQ-042-agent-workspace-three-pane-experience.md) |
| P1 | REQ-047 C1 Durable Core 总验收 | ⚫ Blocked by R1-S1..S6 | R1 全部验收后执行联合 conformance 与文档收口 | [Joint Plan](../02-delivery-plans/02-plans/2026-07-24-req-041-047-conversation-run-contract-plan.md#slice-c1durable-core-总验收与文档收口) |

## 最近完成

最近完成区默认最多保留 20 行（按 `docs/03-engineering-governance/01-rules/workbench.md#保留策略` 强约束）。超过 20 行时，必须一次性批量归档，只保留最新 12 行；第 13 行及以后全部移出。不得每次只移动 1 行。本表只承担"近期完成窗口"的角色，详细验证、行为变化、PR 描述和复盘见 `docs/03-engineering-governance/work-log.md`、对应技术债总账、plan 或 PR。

按"最近优先"（最新任务在最上）排序：

| 日期 | 任务 | 状态 | 摘要 | 事实源 |
|------|------|------|------|--------|
| 2026-08-09 | R1-S4-D-A Transport Participant Core（workspace/execution transport eraser） | 🟢 完成 | 共享基类（S2-D/S3-D 管道收敛）+ 两 participant + S4-C tombstone 互操作；三面 5 根因族 → 定向 → 轻量 → 最终核对 P0/P1=0，评分 93；Backend full 三路 CI 全绿；registry 保持 False | [PR #542](https://github.com/MarkDanile/MetaEduBase/pull/542)（squash merge `5fc5c33b`）/ [Plan §R1-S4-D](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) / [score 93](04-retrospectives/review-score-log.md) |
| 2026-08-07 | R1-S4-D 契约细化（transport participant 拆分） | 🟢 完成 | 冻结 S4-D-A Core / S4-D-B Resolve+Activation 两 PR 拆分；S4-D-A 不翻 registry、S4-D-B 统一翻（merged-boundary）；两类 gate 区分（conversation_scope 内嵌 fail closed / tenant_scope 共享查询）；集合锁免取条件冻结；三面 0/8/10/9 → 5 根因族 → 定向复核 0/0/3/2 | [PR #541](https://github.com/MarkDanile/MetaEduBase/pull/541)（squash merge `51a12df6`）/ [Plan §R1-S4-D](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-08-07 | R1-S4-C 实现 PR-B（Claim/consumer CAS + deterministic terminalization） | 🟢 完成 | 六元 CAS + unknown/stale 双事务协议 + C1 第 4 跳 + allowlist + C8 项 11；round-1 三面 3 根因族返修 + round-2 定向复核 P0/P1 清零，评分 90；Draft iteration + Ready Backend full 三路 CI 全绿 | [PR #539](https://github.com/MarkDanile/MetaEduBase/pull/539)（squash merge `8f184935`）/ [Plan §R1-S4-C](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) / [score 90](04-retrospectives/review-score-log.md) |
| 2026-08-07 | R1-S4-C 实现 PR-A（Producer propagation + replay/catch-up） | 🟢 完成 | writer 真实 scope/epoch + COMPLETED 非 NULL epoch 守卫 + existing 校验 + replay 不重写 + catch-up 收敛；round-1 三面 4 根因族返修 + round-2 P0/P1 清零，评分 89；Backend full 绿 | [PR #537](https://github.com/MarkDanile/MetaEduBase/pull/537)（squash merge `2e70c1df`）/ [Plan §R1-S4-C](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-08-07 | R1-S4-C Writer/Claim Scope + Epoch Fence 契约冻结 | 🟢 完成 | 冻结 scope/epoch 四跳传播链、六元 CAS（turn/output 三源）、claim 短事务 + 锁序矩阵、unknown/stale 双事务协议状态表（具名 code + digest envelope + 重放精确终态三分支）、C6 11 反例 + C8 11 项验收矩阵；10 轮收敛终审 0/0/0/0，评分 87；契约 PR 恢复纯文档 | [PR #535](https://github.com/MarkDanile/MetaEduBase/pull/535)（squash merge `c2e1af42`）/ [Plan §R1-S4 C1-C9](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-08-06 | TD-092 高风险 PR CI 反馈周期与复审收敛治理 | 🟢 完成 | Draft risk-targeted `2m44s / 297 passed`，Ready 最新 HEAD 保留 Backend full；三面首轮复审、根因族返修、连续两轮新 P1 升级与单风险域 PR 规则落地；独立复核 0/0/0/0，评分 93 | [PR #532](https://github.com/MarkDanile/MetaEduBase/pull/532)（squash merge `fb6058ac`）/ [TD-092](technical-debt.md#td-092-高风险-pr-ci-反馈周期与复审收敛治理) / [work-log](work-log.md) |
| 2026-08-06 | R1-S4-B Transport/External Schema + Backfill 实现 | 🟢 完成 | migration 040（四表 scope 列 + 两 ledger + inbox tombstone）+ 五维 verify backfill（scope/epoch/external-ref/投影/scope-vs-来源）+ CLI；十二轮独立复审 0/0/0/0（含 epoch-only 收敛、表↔issue 绑定、external ref 绑定 heal、B2 类型裁决共用 expected）；全量 2103 passed | [PR #530](https://github.com/MarkDanile/MetaEduBase/pull/530)（squash merge `0fb43ccb`）/ [Plan §R1-S4](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-08-04 | R1-S4-B Transport/External Schema + Backfill 契约冻结 | 🟢 完成 | 冻结 migration 040 schema（四表 scope 列 + 两 ledger + inbox tombstone）+ 回填矩阵 + 三态 reconcile（advisory lock 集合锁入 D8）+ external 空 allowlist + 041 guard 冻结 + scope/epoch 双维 verify；七轮复审 0/0/0/1 | [PR #528](https://github.com/MarkDanile/MetaEduBase/pull/528)（squash merge `b2020d4c`）/ [Plan §R1-S4](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-08-04 | R1-S4-A Transport/External/Late-write 契约冻结 | 🟢 完成 | 盘点 4 张 inbox/outbox 与 transport owner 映射；冻结 D1-D8（结构化 owner scope、epoch 传播链 + 六元组 CAS、历史不确定行三态 reconcile、tombstone 留 digest、external ref ledger 全覆盖、部分 ACK 不标 completed、runtime fake 仅证明协议、claim/Guard 顺序）；三轮复审 0/0/0/0 | [PR #526](https://github.com/MarkDanile/MetaEduBase/pull/526)（squash merge `cf4c8374`）/ [Plan §R1-S4](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-08-04 | R1-S3-E Dispatch、竞态与收口 | 🟢 完成 | dispatch_output deterministic late-write 终态化（幂等原语 + claim CAS）+ purge-fenced projection/read 重分类 deterministic + race/幂等真实 PG 反例 + backfill 钉住 execution.core.v1 + no-bypass 守卫；三轮复审 0/0/0/0；变异逐项 KILLED；三路 CI 全绿 | [PR #524](https://github.com/MarkDanile/MetaEduBase/pull/524)（squash merge `916699db`）/ [work-log](work-log.md) / [Plan §R1-S3](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) |
| 2026-08-03 | R1-S3-D ExecutionErasureParticipant（execution.core.v1 正文清除 + final scan + ACK fencing） | 🟢 完成 | migration 039 行级守卫白名单 + 正文清除 + final scan + 完整 fencing + blocked 三方一致 + 真实计数 ACK digest；四轮复审 0/0/0/0；变异逐项 KILLED；erase_available 翻 True；Backend 2016 passed / 0 failed；三路 CI 全绿 | [PR #522](https://github.com/MarkDanile/MetaEduBase/pull/522)（squash merge `99142f15`）/ [work-log](work-log.md) / [Plan §R1-S3](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) |
| 2026-08-02 | R1-S3-C Writer fence（13 接线 + 9 writer 矩阵 + 锁链修复 + 真 e2e） | 🟢 完成 | composition-owned FencedExecutionPort + 9 writer wrapper + 13 call site；锁链全路径 Spec §6.1 与 S3-D 同序无 AB-BA；verdict 内建 + Run 归属绑定 + 跨边界 Protocol；变异 2 组 + 真 e2e 6 组；复审 0/0/0；Backend 1951 passed | [PR #519](https://github.com/MarkDanile/MetaEduBase/pull/519)（merge `eb911b9a`）/ [work-log](work-log.md) / [score 88](04-retrospectives/review-score-log.md) |
| 2026-07-31 | R1-S3-B Schema 与基础契约（actor tombstone + shared digest + per-owner source key） | 🟢 完成 |  migration 038 + shared digest helper + per-owner source key + tombstone 契约（6 处 fail-closed guard + `DirectRagTerminalReplayError` 透传）；6 轮 max 复审收口 0/0/0；23 文件 / 1689 增；三路 CI 全绿（Backend 8m52s） |
| 2026-07-30 | R1-S3-A Execution owner 契约注记/plan delta（先于代码冻结） | 🟢 完成 | 纯文档冻结 execution.core.v1 participant 设计（fenced port + 9 writer 矩阵 + migration 038 actor tombstone + per-owner source key + event 计数器 + S3/S6 拆分）；两轮 max 复审 + 轻量复核 0/0/0；S3-A~E PR 拆分冻结；三路 CI 全绿 | [PR #515](https://github.com/MarkDanile/MetaEduBase/pull/515)（merge `2d4f8091`）/ [Plan §R1-S3](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-30 | R1-S2-D/E workspace 正文清除 + participant ACK + final body scan | 🟢 完成 | workspace.core.v1 participant 正文清除 + body scan + ACK；V1 冻结契约（fingerprint 持久化 migration 037 + 构造器禁覆盖 + placeholder denylist）；7 轮 max 复审 P0/P1/P2=0/0/0；全量 1908 passed；三路 CI 全绿 | [PR #513](https://github.com/MarkDanile/MetaEduBase/pull/513)（merge `5db40361`）/ [Plan §R1-S2](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-29 | R1-S2-C ingress checkpoint source key + title/create fence + backfill 锁序 | 🟢 完成 | ingress 真实 source key + verdict/advance 拆分 + title/create 接 fence + backfill 消 AB-BA + deleted 410/redacted envelope + migration 036 归一；四轮 max 复审清零；全量 1849 passed；三路 CI 全绿 | [PR #511](https://github.com/MarkDanile/MetaEduBase/pull/511)（merge `2ceaffd0`）/ [Plan §R1-S2](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-28 | R1-S1 Fence/Hold/Purge schema 基座 | 🟢 完成 | owner key 锁 + owner registry + 四协调表 + tombstone + fence 状态机（16 边）+ backfill 恢复契约；六轮 max 复审 P0/P1/P2=0/0/0；全量 1777 passed；dev 已 reset 到 034 head | [PR #506](https://github.com/MarkDanile/MetaEduBase/pull/506)（merge `b8cbdf14`）/ [Plan §R1-S1](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-27 | REQ-060 Slice 4 移动端 + a11y + Playwright + 收口 | 🟢 完成 | useMobileDrawer + LayoutView 重构（30 新增 vitest）+ Playwright 3 组 spec（55/55）；326/326 vitest；三路 CI 全绿；六轮复审 P0/P1/P2=0/0/0；评分 95 | [PR #503](https://github.com/MarkDanile/MetaEduBase/pull/503)（）/ [Plan §Slice 4](../02-delivery-plans/02-plans/2026-07-23-req060-console-ia-nav-rbac-plan.md) / [work-log](work-log.md) / [scorecard](04-retrospectives/review-score-log.md) |
