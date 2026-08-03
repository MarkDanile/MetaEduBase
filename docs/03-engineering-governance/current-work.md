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

### TASK: REQ-041/047 R1-S3-D ExecutionErasureParticipant

状态：🟡 进行中
类型：新需求开发（R1 分 Slice，S3-D execution erasure participant）
领域：agent_execution / erasure coordination
当前执行模式：superpower / plan-do（S3-A 契约 / S3-B schema+contract / S3-C writer fence 已合并）
最近接手工具：Claude Code (Opus 4.8)
分支：`feat/req041-047-r1-s3d-execution-erasure`

需求来源：
- Spec: [R1 专项契约](../02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md)（§6.1 锁序 / §7.2 Execution 清除语义）
- Plan: [R1 Plan §R1-S3](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md)（S3-D participant）
- 架构约束：S3-C fenced port 已就位（PR #519 merge `eb911b9a`）；migration 038 actor tombstone 契约 + shared `agent_actor_digest` helper 已就位（PR #517）；workspace participant（S2-D/E）作为锁序与 ACK 模式参考

当前进展：S3-D round-1 复审返修已完成（独立 `max` round-1 报 P0/P1/P2/P3 = 0/7/2/0，全部按 [Plan §S3-D round-1 复审修订](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) 落地）。7 项 P1（suppressed terminal 无条件清除 / migration 039 守卫白名单 / binding 直查 / operation FOR UPDATE + 状态白名单 / blocked 三方一致 / 真实清除计数 ACK digest / registry 回归更新）均含变异验证（5/5 KILLED）+ 真实 PostgreSQL 守卫放行矩阵（13/13 passed）。2 项 P2（started_at / reason bump）已对齐 workspace 冻结语义。本地 `pytest -m 'not external_network'` 全量 2010 passed / 1 xfailed / 0 failed；ruff 0 错；mypy 0 错；docs gate 通过。**待独立 codex 只读复审（不合并）**。
必须实现：固定锁序（Conv FOR UPDATE -> execution.core.v1 owner lock -> fence FOR UPDATE -> AgentRun/RunEvent/CompatibilityOutput）+ clock_timestamp 入口不暴露 now + terminal suppressed（清 ref/media type/classification/message id，保留 digest/size）+ terminal code/reason 归一受控 suppression code + 清 Run context snapshot + compatibility output 清 reply/envelope 投影 payload_state=redacted 保留 digest + RunEvent 清 payload_inline 投影 redacted 保持 seq + payload_ref 存在时 purge_owner_unavailable blocked 禁假 ACK + actor 共享版本化 HMAC helper 匿名化 + Runtime binding ref 不清不关闭存在时 blocked + 非终态 Run blocked + final scan 无条件覆盖 + 完整 fencing（conversation/purge revision/lease epoch/registry digest/hold revision/operation revision/owner version/capability digest）+ blocked 正常返回可重试 + erased 幂等重放 + pending checkpoint repair + 三方状态一致 + ACK 只推进 execution.core.v1 checkpoint + ACK digest 仅含 owner/version/revision/清除计数/scan digest + 同 commit 翻 erase_available=True。
明确禁止：不做 S3-E dispatch_output 分类/backfill/收口；不实现 execution transport/external payload/runtime private eraser；不启用 purge scheduler；不实现 Pi/Runtime session destroy；不实现 365 天 Run prune；不改 migration 034-038（**round-1 P1-2 定向解除「不新增」约束：仅允许新增 migration 039 重定义 append-only 守卫，消除运行时 DDL**）；不清 workspace 正文不删 catalog refs；不混入 Approval/Tool/Artifact/Evidence。
下一步：提交返修（migration 039 + participant 7 P1/2 P2 + 4 个新反例测试 + registry 回归更新 + head 断言更新 + TD-032 行数）-> push -> 独立 codex 只读复审 -> 等待三路 CI -> 合并。
验证状态：本地全量 2010 passed / 1 xfailed / 0 failed；GitHub 三路 CI 待跑。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C 已合并（PR #519 merge `eb911b9a`，score 88）；S3-D round-1 返修已完成本地验证（变异 5/5 KILLED、守卫矩阵 13/13、ruff 0、mypy 0、docs gate 0），本轮**新增 migration 039**（不改 034-038）是复审 P1-2 的唯一合规解（运行时 DDL 有死锁与权限缺陷）；不进 S4，不启用 purge scheduler。

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
| 2026-08-03 | R1-S3-D round-1 复审返修（7 P1 + 2 P2） | 🟢 返修完成（待独立 codex 复审） | migration 039 行级守卫白名单 + 7 P1（suppressed envelope / binding 直查 / operation FOR UPDATE+状态白名单 / blocked 三方一致 / 真实清除计数 ACK digest / registry 回归）+ 2 P2；4 反例 + 13 守卫矩阵；变异 5/5 KILLED；Backend 2010 passed / 1 xfailed | [PR #522](https://github.com/MarkDanile/MetaEduBase/pull/522)（返修 commit 待 push）/ [Plan §S3-D round-1 复审修订](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) |
| 2026-08-02 | R1-S3-C Writer fence（13 接线 + 9 writer 矩阵 + 锁链修复 + 真 e2e） | 🟢 完成 | composition-owned FencedExecutionPort + 9 writer wrapper + 13 call site；锁链全路径 Spec §6.1 与 S3-D 同序无 AB-BA；verdict 内建 + Run 归属绑定 + 跨边界 Protocol；变异 2 组 + 真 e2e 6 组；复审 0/0/0；Backend 1951 passed | [PR #519](https://github.com/MarkDanile/MetaEduBase/pull/519)（merge `eb911b9a`）/ [work-log](work-log.md) / [score 88](04-retrospectives/review-score-log.md) |
| 2026-07-31 | R1-S3-B Schema 与基础契约（actor tombstone + shared digest + per-owner source key） | 🟢 完成 |  migration 038 + shared digest helper + per-owner source key + tombstone 契约（6 处 fail-closed guard + `DirectRagTerminalReplayError` 透传）；6 轮 max 复审收口 0/0/0；23 文件 / 1689 增；三路 CI 全绿（Backend 8m52s） |
| 2026-07-30 | R1-S3-A Execution owner 契约注记/plan delta（先于代码冻结） | 🟢 完成 | 纯文档冻结 execution.core.v1 participant 设计（fenced port + 9 writer 矩阵 + migration 038 actor tombstone + per-owner source key + event 计数器 + S3/S6 拆分）；两轮 max 复审 + 轻量复核 0/0/0；S3-A~E PR 拆分冻结；三路 CI 全绿 | [PR #515](https://github.com/MarkDanile/MetaEduBase/pull/515)（merge `2d4f8091`）/ [Plan §R1-S3](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-30 | R1-S2-D/E workspace 正文清除 + participant ACK + final body scan | 🟢 完成 | workspace.core.v1 participant 正文清除 + body scan + ACK；V1 冻结契约（fingerprint 持久化 migration 037 + 构造器禁覆盖 + placeholder denylist）；7 轮 max 复审 P0/P1/P2=0/0/0；全量 1908 passed；三路 CI 全绿 | [PR #513](https://github.com/MarkDanile/MetaEduBase/pull/513)（merge `5db40361`）/ [Plan §R1-S2](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-29 | R1-S2-C ingress checkpoint source key + title/create fence + backfill 锁序 | 🟢 完成 | ingress 真实 source key + verdict/advance 拆分 + title/create 接 fence + backfill 消 AB-BA + deleted 410/redacted envelope + migration 036 归一；四轮 max 复审清零；全量 1849 passed；三路 CI 全绿 | [PR #511](https://github.com/MarkDanile/MetaEduBase/pull/511)（merge `2ceaffd0`）/ [Plan §R1-S2](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-28 | R1-S1 Fence/Hold/Purge schema 基座 | 🟢 完成 | owner key 锁 + owner registry + 四协调表 + tombstone + fence 状态机（16 边）+ backfill 恢复契约；六轮 max 复审 P0/P1/P2=0/0/0；全量 1777 passed；dev 已 reset 到 034 head | [PR #506](https://github.com/MarkDanile/MetaEduBase/pull/506)（merge `b8cbdf14`）/ [Plan §R1-S1](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-27 | REQ-060 Slice 4 移动端 + a11y + Playwright + 收口 | 🟢 完成 | useMobileDrawer + LayoutView 重构（30 新增 vitest）+ Playwright 3 组 spec（55/55）；326/326 vitest；三路 CI 全绿；六轮复审 P0/P1/P2=0/0/0；评分 95 | [PR #503](https://github.com/MarkDanile/MetaEduBase/pull/503)（）/ [Plan §Slice 4](../02-delivery-plans/02-plans/2026-07-23-req060-console-ia-nav-rbac-plan.md) / [work-log](work-log.md) / [scorecard](04-retrospectives/review-score-log.md) |