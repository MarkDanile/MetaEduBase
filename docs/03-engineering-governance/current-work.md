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

### TASK-R1-S4C-DELTA: R1-S4-C Writer/Claim Scope + Epoch Fence 契约冻结

状态：🟡 进行中（Docs Only 阶段）
类型：新需求开发（Slice contract delta，先于代码冻结）
领域：Backend（composition / agent_workspace / agent_execution writer+claim+consumer 接线）
当前执行模式：superpower / plan-do
最近接手工具：Claude Code
分支：docs/req041-047-r1-s4c-contract-delta

需求来源：
- Spec: docs/02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md（§5.2/§6/§7 owner 边界、external ref、迟到写）
- Plan: docs/02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md#r1-s4transport-ownerexternal-payload-与迟到写（§S4-A D1-D8 + §S4-B B1-B8 契约冻结块 + 本轮 S4-C delta）
- 技术债：docs/03-engineering-governance/technical-debt.md（TD-092 解除 S4-C 暂停，三轮收敛/连续两轮新 P1 拆分为后续验证任务）
- 架构约束：docs/03-engineering-governance/01-rules/architecture.md

当前进展：本轮只提交纯文档 S4-C contract/plan delta，不写业务代码、不改 migration 040、`erase_available` 保持 False。契约冻结范围：Conversation snapshot → outbox metadata → claim envelope → inbox metadata 的 scope/epoch 传播链；writer 写真实 `conversation_id` 与 `producer_purge_revision`（禁拿当前 revision 伪造历史 epoch）；consumer 在 Guard 内执行六元组 CAS（event_id / digest / attempt / claimant / conversation_id / producer_purge_revision）；claim 独立短事务；锁序 Guard → Conversation → owner → fence → 集合 advisory lock（最内层）；S4-B catch-up 自 tenant 起点、不保留跨调用 UUID 游标、verify 不豁免 NULL 行；stale epoch/跨 tenant/scope mismatch/unknown epoch/orphan/takeover/重放/purge-win 反例。
下一步：round-1 三面首轮复审（P0/P1/P2/P3=3/12/11/4）按根因族 R1-R6 一次返修；round-2 落点修正；round-3（0/3/4/0）S1 turn 三源 CAS、S2 双事务协议、S3 orphan 可达性；round-4（0/3/1/0）S2 重写为状态表；round-5（0/3/0/0）三项定向修正；round-6（0/1/1/0）重放锁后检查 outbox 精确终态三分支；round-7（0/1/0/1）精确终态谓词冻结；round-8（0/1/0/0）具名 code + decision_digest envelope 冻结；round-9（0/0/1/1）allowlist 源码改动回退到第二实现 PR（配参数化回归测试，C8 项 11），契约 PR 恢复纯文档（round-9 曾误判回退成功，round-10 核对 git diff main...HEAD 发现 round-8 提交仍含源码，已真正 restore --source=main 并提交 revert）。契约 P0/P1 清零达成，待最终合并确认后开实现 PR（冻结为 producer propagation + replay/catch-up 与 claim/consumer CAS + deterministic terminalization 两 PR）。
验证状态：纯文档——`scripts/check-engineering-docs` + `git diff --check` 通过；PR #535 最新 HEAD 三路 required checks SUCCESS、PR OPEN（此前 CANCELLED 为基建/取消重跑所致，非测试失败，已重跑复绿）；不实现 migration 041、不启用 S5 scheduler。
交接备注：实现阶段保持 Draft、`Backend iteration` risk-targeted；代码稳定后转 Ready 最新 HEAD 执行 Backend full；收敛目标 2-3 轮，连续两轮新 P1 立即回契约或拆分/重构。round-1 三面复审结果须在实现 PR 前记入 work-log。

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
