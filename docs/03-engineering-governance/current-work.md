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

### TASK: REQ-041/047 R1-S3-C Writer fence

状态：🟡 进行中
类型：新需求开发（R1 分 Slice，S3-C writer fence）
领域：agent_execution / erasure coordination
当前执行模式：superpower / plan-do（契约注记已冻结，S3-A 契约 / S3-B schema+contract 已合并）
最近接手工具：Claude Code (Opus 4.8)
分支：feat/req041-047-r1-s3c-writer-fence

需求来源：
- Spec: [R1 专项契约](../02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md)
- Plan: [R1 Plan §R1-S3](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md)（S3-C PR 拆分：Writer fence）
- 架构约束：Spec §6.2 writer fence 协议；§7.2 Execution 清除语义；migration 038 actor tombstone 契约（execution.core.v1 `actor_identity` capability 已就位）

当前进展：S3-C round-5 revert 已推（commit `a9423134`）并通过三路 CI。回退 round-4 verdict-before-writer（pre_create_callback）方案：Backend CI 30+ 分钟挂起（Guard + Conversation 行锁内再取 owner lock + fence FOR UPDATE，与 backfill Conversation -> owner 形成环路）。回到 round-3 顺序：consume_turn_event 先持 Guard + Conversation 行锁 + commit writer；caller (dispatch_turn) 在 created=True 时调 fenced_create_run 取 owner lock + advance run_context_body=queue_seq。P3 stage 去重保留；erasing fence reject 测试保留（直接验 require_active_fence）；测试改 round-5 顺序断言（ast.unparse 剥离 docstring/comment 误报）。
下一步：等独立 max 只读复核 round-5 revert -> P0/P1 清零后按流程合并 S3-C -> 启动 S3-D（ExecutionErasureParticipant）。
验证状态：ruff passed / mypy baseline 0 回归 / docs gate passed；三路 CI 全绿（Backend 9m35s / Engineering docs 6s / Frontend 5s）。
交接备注：S3-A 已合并（PR #515）；S3-B 已合并（PR #517）；S3-C fenced port 在 composition 层；erase_available 保持 False（S3-D 翻）；不进 S4；不启用 purge scheduler。round-5 方案是 trade-off——verdict-after-writer 不在 writer 前，但同事务内仍由 Guard + Conversation 行锁串行化，避免 owner 环路。

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
| 2026-07-31 | R1-S3-B Schema 与基础契约（actor tombstone + shared digest + per-owner source key） | 🟢 完成 |  migration 038 + shared digest helper + per-owner source key + tombstone 契约（6 处 fail-closed guard + `DirectRagTerminalReplayError` 透传）；6 轮 max 复审收口 0/0/0；23 文件 / 1689 增；三路 CI 全绿（Backend 8m52s） |
| 2026-07-30 | R1-S3-A Execution owner 契约注记/plan delta（先于代码冻结） | 🟢 完成 | 纯文档冻结 execution.core.v1 participant 设计（fenced port + 9 writer 矩阵 + migration 038 actor tombstone + per-owner source key + event 计数器 + S3/S6 拆分）；两轮 max 复审 + 轻量复核 0/0/0；S3-A~E PR 拆分冻结；三路 CI 全绿 | [PR #515](https://github.com/MarkDanile/MetaEduBase/pull/515)（merge `2d4f8091`）/ [Plan §R1-S3](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-30 | R1-S2-D/E workspace 正文清除 + participant ACK + final body scan | 🟢 完成 | workspace.core.v1 participant 正文清除 + body scan + ACK；V1 冻结契约（fingerprint 持久化 migration 037 + 构造器禁覆盖 + placeholder denylist）；7 轮 max 复审 P0/P1/P2=0/0/0；全量 1908 passed；三路 CI 全绿 | [PR #513](https://github.com/MarkDanile/MetaEduBase/pull/513)（merge `5db40361`）/ [Plan §R1-S2](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-29 | R1-S2-C ingress checkpoint source key + title/create fence + backfill 锁序 | 🟢 完成 | ingress 真实 source key + verdict/advance 拆分 + title/create 接 fence + backfill 消 AB-BA + deleted 410/redacted envelope + migration 036 归一；四轮 max 复审清零；全量 1849 passed；三路 CI 全绿 | [PR #511](https://github.com/MarkDanile/MetaEduBase/pull/511)（merge `2ceaffd0`）/ [Plan §R1-S2](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-28 | R1-S1 Fence/Hold/Purge schema 基座 | 🟢 完成 | owner key 锁 + owner registry + 四协调表 + tombstone + fence 状态机（16 边）+ backfill 恢复契约；六轮 max 复审 P0/P1/P2=0/0/0；全量 1777 passed；dev 已 reset 到 034 head | [PR #506](https://github.com/MarkDanile/MetaEduBase/pull/506)（merge `b8cbdf14`）/ [Plan §R1-S1](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md) / [work-log](work-log.md) |
| 2026-07-27 | REQ-060 Slice 4 移动端 + a11y + Playwright + 收口 | 🟢 完成 | useMobileDrawer + LayoutView 重构（30 新增 vitest）+ Playwright 3 组 spec（55/55）；326/326 vitest；三路 CI 全绿；六轮复审 P0/P1/P2=0/0/0；评分 95 | [PR #503](https://github.com/MarkDanile/MetaEduBase/pull/503)（）/ [Plan §Slice 4](../02-delivery-plans/02-plans/2026-07-23-req060-console-ia-nav-rbac-plan.md) / [work-log](work-log.md) / [scorecard](04-retrospectives/review-score-log.md) |
| 2026-07-25 | TD-087 模板管理 API 后端 RBAC | 🟢 完成 | 15 个管理端点统一高权守卫；tenant-local 最小 lookup DTO、403 脱敏与 92 例角色/租户矩阵完成；Template 124、Identity 47、Frontend 175 passed，三路 CI 全绿 | [PR #495](https://github.com/MarkDanile/MetaEduBase/pull/495)（`40a7bf46`）/ [Tech Debt](technical-debt.md#td-087-模板管理-api-缺少后端-rbac) |
| 2026-07-25 | Agent Control Plane D1 Direct RAG compatibility recording | 🟢 完成 | 旧 evidence API 持久化 Conversation/Message/Run/Event/terminal；双向 bridge 恢复、scoped identity、隔离 execution claim 与 `033` staging；全量 1623 passed，三路 CI 与 `max` 复审全绿 | [PR #489](https://github.com/MarkDanile/MetaEduBase/pull/489)（`56de6bf1`） |
| 2026-07-24 | Agent Control Plane A1 Run query 与 SSE replay | 🟢 完成 | owner-private GET Run、持久化幂等 cancel intent、PostgreSQL ledger SSE replay/live polling、权限重验和 gap/retention/cursor 错误；`032` migration；全量 1605 passed，三路 CI 全绿 | [PR #487](https://github.com/MarkDanile/MetaEduBase/pull/487)（`2f91bed8`） |
| 2026-07-24 | Agent Control Plane B1 Workspace/Execution bridge | 🟢 完成 | shared schema/JCS、双向 inbox/outbox、fencing、Guard、真实 FIFO barrier、terminal projection、dead-letter/reconcile、guarded DELETE/restore 与 `031` migration；全量 1587 passed，三路 CI 全绿 | [PR #485](https://github.com/MarkDanile/MetaEduBase/pull/485)（`e113904b`） |
| 2026-07-24 | Agent Execution E1 durable core | 🟢 完成 | `AgentRun/TurnInput/RunEvent`、FIFO/one-active、连续 Runtime ACK、atomic resume、canonical terminal、组合 FK 与 `030` migration；无 B1/API/Pi/extended entity 越界；全量 1562 passed | [PR #483](https://github.com/MarkDanile/MetaEduBase/pull/483)（`d66f50d3`） |
| 2026-07-24 | Agent Execution E0 identity、Binding 与 Snapshot | 🟢 完成 | `agent_execution` 最小 catalog、版本化 Snapshot、Direct RAG compatibility identity、Binding epoch/DB-clock lease/cursor 契约与 `029` migration；无 Run/Event/API/Runtime 越界；全量 1411 passed | [PR #481](https://github.com/MarkDanile/MetaEduBase/pull/481)（`37417149`） |
| 2026-07-24 | Agent Workspace W1 durable store | 🟢 完成 | `agent_workspace` 四业务表 + inbox/outbox、owner-private API、CAS/keyset、双 seq 与完整摘要落地；DELETE/`/turns` 保持关闭；全量 1390 passed | [PR #479](https://github.com/MarkDanile/MetaEduBase/pull/479)（`88bf3c35`） |
