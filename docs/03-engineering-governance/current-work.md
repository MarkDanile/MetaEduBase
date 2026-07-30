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

### TASK: REQ-041/047 R1-S3 Execution owner + RunEvent payload + compatibility output

状态：🟡 进行中
类型：新需求开发（R1 分 Slice）
领域：agent_execution / erasure coordination
当前执行模式：superpower / plan-do（契约注记先于代码冻结）
最近接手工具：Claude Code (Opus 4.8)
分支：feat/req041-047-r1-s3-execution-owner

需求来源：
- Spec: [R1 专项契约](../02-delivery-plans/01-specs/2026-07-27-req-041-047-r1-retention-purge-recovery.md)
- Plan: [R1 Plan §R1-S3](../02-delivery-plans/02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md)
- 架构约束：Spec §4.1 execution.core.v1、§6.1/§6.2 锁序/writer fence、§7.2 Execution 清除语义

当前进展：S3 契约注记 round-2 复审返修完成（P0=0/P1=4/P2=3 全部闭合）：① `erase_available` 时序（S3-B 保持 False，S3-D 与 participant 同 commit 翻 True）② create_run 真实入口 `consume_turn_requested`（非 `submit_turn`，后者只写 workspace outbox）③ `terminal_code` 也裁剪（任意 1-100 字符，非受控）④ migration 038 应用层 tombstone 契约（创建强制 UUID / domain 允许 erased / 需 actor 命令 fail closed / API 不暴露 digest / purge 后负向测试）⑤ event 计数器持久化于 fence checkpoint + baseline 0 + writer `created` 标志 ⑥ 提取 composition/shared actor digest helper（双 participant 共用，不复用 workspace 私有）⑦ migration 038 downgrade 边界（redacted 行 fail closed/forward-fix，不伪造 UUID）。
下一步：PR #515 round-2 修订待轻量只读复核 -> 通过后合并 S3-A -> 启动 S3-B（schema/contract PR：migration 038 + 应用层 tombstone 契约 + owner/source key 映射 + registry 增 actor_identity（erase_available 保持 False）+ shared digest helper + backfill）。
验证状态：docs gate passed + `git diff --check` 干净（round-2 修订后）。
交接备注：S3-A 纯文档；S3-B 起新增 migration 038（不改 034-037）；不进 S4；不启用 purge scheduler。S2-D/E 已合并（PR #513 merge `5db40361`）。

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
| 2026-07-24 | Conversation/Run 联合核心契约塑形 | 🟢 完成 | 冻结 16 项核心决策与 8 Slice plan；四轮独立 `max` 反例审查 P0/P1 从 9 -> 4 -> 1 -> 0；纯文档，无代码/迁移/API/UI | [PR #477](https://github.com/MarkDanile/MetaEduBase/pull/477)（`265f59c7`） |
| 2026-07-24 | REQ-059 企业级可控 Agent 平台源码研究与控制面塑形 | 🟢 完成 | 八项 Architecture Gate 决策、AI Delivery Matrix、园区应用顺序和 12 仓库固定源码导航完成；文档门禁、路径核验、独立复审和用户签字通过 | [PR #475](https://github.com/MarkDanile/MetaEduBase/pull/475)（`132730a0`）/ [Requirement](../01-product-planning/05-requirements/REQ-059-enterprise-agent-platform-kernel.md) |
| 2026-07-23 | TD-084 GitHub Actions Node 24 与 hermetic 测试分类收口 | 🟢 完成 | 6 类 Action 升级 Node 24；slow marker 移除，CI 统一排除 external_network；PR/main/manual 三层全绿，Backend 约 5m，无 Node 20 警告 | [PR #472](https://github.com/MarkDanile/MetaEduBase/pull/472)（`beb7c6fd`）/ [Tech Debt](technical-debt.md#td-084-github-actions-node-24-与-hermetic-测试分类收口) |
| 2026-07-23 | TD-083 后端风险分级测试选择与性能专项治理 | 🟢 完成 | PR targeted / main full-not-slow / nightly full；默认禁外网 + 外部依赖 mock；not-slow 1365 pass/2m41s；resource 探针 15 pass/4.22s | [PR #469](https://github.com/MarkDanile/MetaEduBase/pull/469)（`cccb3ff6`）/ [Tech Debt](technical-debt.md#td-083-后端风险分级测试选择与性能专项治理) |
| 2026-07-23 | TD-082 分层质量门禁与 CI 提速 | 🟢 完成 | scope-aware CI + 秒级 hooks + MCP lock + 前端构建去重；不可靠分片已撤销，后端专项由 TD-083 接力 | [PR #467](https://github.com/MarkDanile/MetaEduBase/pull/467)（`754ca109`）/ [Tech Debt](technical-debt.md#td-082-分层质量门禁与-ci-提速) |
| 2026-07-23 | REQ-060 企业 Agent 控制台信息架构与权限化导航（初版 shaping） | 🟢 初版完成 | PR #491 冻结目标 IA；2026-07-25 复审发现 4 P1/2 P2，已由当前 R1 修订 activeNav、原子路由、移动端边界并正式登记 TD-087 | [PR #491](https://github.com/MarkDanile/MetaEduBase/pull/491)（`efe126af`）/ [Spec R1](../02-delivery-plans/01-specs/2026-07-23-req060-console-ia-nav-rbac.md#11-r1-review-corrections2026-07-25) |
| 2026-07-23 | TD-081 CI、Git hooks 与 mypy 可执行基线 | 🟢 完成 | 三路 GitHub CI + fresh PostgreSQL/zhparser + fail-closed hooks + 可递减 mypy baseline；main required checks 对管理员生效。Backend 1368 pass/5 skip，三路 CI 全绿 | [PR #465](https://github.com/MarkDanile/MetaEduBase/pull/465)（`a37a7e51`）/ [Tech Debt](technical-debt.md#td-081-ci-git-hooks-与-mypy-可执行基线缺失) |
| 2026-07-22 | TD-080 后端全量测试顺序污染与 coroutine 未 await warning | 🟢 完成 | alembic fileConfig 传 disable_existing_loggers=False 治本（不再污染已存在 logger）+ 12 document asyncio.run mock 改 side_effect close coroutine + slow marker 优化 dev 循环（-m 'not slow' 6:33→~5min）。全量 0 fail；1 回归测试防回退 | [PR #464](https://github.com/MarkDanile/MetaEduBase/pull/464)（`a20f3ee1`）/ [work-log](work-log.md) |
| 2026-07-22 | REQ-058 企业背调生产级 RBAC、制审分离与多租户配置 | 🟢 完成 | DD 权限矩阵+maker-checker+任务可见性+tenant_scoped_config 表+配置审计+平台 status only。7 AC；5 Slice（#459~#463）；43 测试；全量 1364 pass/3 pre-existing；ruff 0/docs gate 0 | [PR #463](https://github.com/MarkDanile/MetaEduBase/pull/463)（`d2c3b752`）/ [work-log](work-log.md) |
