# REQ-041/047 实施 Plan：Conversation、Message、Run、Event Durable Core

> **Status**: 🔵 Ready for sliced implementation
> **Requirement**: [REQ-041](../../01-product-planning/05-requirements/REQ-041-ai-workspace-conversation-persistence.md) / [REQ-047](../../01-product-planning/05-requirements/REQ-047-agent-run-artifact-approval-center.md)
> **Spec**: [Conversation/Message/Run/Event 联合核心契约](../01-specs/2026-07-24-req-041-047-conversation-run-contract.md)
> **Parent**: [REQ-059](../../01-product-planning/05-requirements/REQ-059-enterprise-agent-platform-kernel.md)
> **Scope**: 只授权 REQ-041 全范围与 REQ-047 Durable Core；不授权 Pi、Agent Loop、Tool Gateway、Approval/Artifact/Evidence 完整实现

## 1. 交付目标

在不等待 Pi Worker 的前提下，先建立 MetaEduBase 自己拥有的 durable control plane 基线：

1. `agent_workspace` 持久化产品 Conversation、用户级 pin 状态、Message 与 MessagePart。
2. `agent_execution` 持久化最小 Agent/Runtime profile identity、AgentRun、TurnInput 与 append-only RunEvent。
3. submit-turn、Run 终态与 assistant Message 使用双向 outbox/inbox，崩溃和重投不重复也不永久丢失。
4. 浏览器可按 `run_id + after_seq` 恢复事件，并通过 GET Run 独立确认终态。
5. Direct RAG 成为首个 compatibility producer，证明控制面不依赖 Pi 才能工作。
6. Conversation 删除、Run 启动、pending dispatch 与 retention 有明确并发和故障语义。

本 plan 完成后：REQ-041 可以关闭；REQ-047 只能声明 Durable Core 完成，完整 REQ-047 仍需 HumanInput/Approval、Tool/Grant/Snapshot、Artifact/Evidence 三组独立 spec/plan。

## 2. AI Delivery Profile

- Complexity: 极高。虽然 REQ-041 单独为高，但联合实现包含跨上下文 outbox、单调 seq、SSE replay、并发 lease、删除协调和故障恢复。
- Risk: 多租户正文权限、迁移、幂等、跨上下文一致性、并发、流式重连、保留/删除、敏感 payload。
- Lead: 契约、E0/E1/B1/R1 使用 `S-XH`，即 Codex + GPT-5.6 Sol `xhigh`；W1/D1 普通实现可用 `S-H`。开工时记录实际 model id 与 effort。
- Delegable: W1 的普通 Repository/API/DTO/单元测试可交 `G-H`；D1 compatibility adapter 和无并发展示 DTO 可交 `G-M/G-H`。不得让其他模型独立改变 CR-1/2/4/5/6/9/10/13/14/15/16、迁移顺序、状态机、删除协调或 SSE gap 语义。
- Independent Review: E1/B1/R1 完成后由 Claude Code + GLM-5.2 `max` 做只读反例审查；不可用时用另一独立 Harness 的 frontier model `max` 复审并如实记录，不得写成双模型已满足。
- Human Gate: 平台架构负责人在 W1 开工前签字确认 CR-1..16、owner-private 权限、30/90/365 天默认保留和 `ConversationExecutionCoordinator/Guard`；安全/数据负责人在 R1 合并前确认正文删除、legal hold 与 super_admin 边界。
- Validation: 每个 Slice 运行相关 pytest、Ruff、mypy baseline、Alembic upgrade；B1/R1 必须执行 crash/concurrency fault matrix，SSE 必须执行 replay/live handoff 与权限撤销集成测试。

编码模型分工只约束开发过程，不写入生产 `RuntimeProfile` 或 `ModelGrant`。

## 3. 命名与目录

代码实现沿用仓库 bounded context 骨架，不新增万能 `agent` context：

```text
packages/server-python/app/contexts/agent_workspace/
  application/        # commands, DTO, WorkspaceReadPort implementation
  domain/             # Conversation, Message, policy, repository ports
  infrastructure/     # ORM, repository, workspace inbox/outbox
  interfaces/api/     # conversation/message/turn router

packages/server-python/app/contexts/agent_execution/
  application/        # RunCoordinator, integration handlers, read ports
  domain/             # AgentRun, TurnInput, RunEvent, transition rules
  infrastructure/     # ORM, repository, execution inbox/outbox, SSE ledger source
  interfaces/api/     # run query/cancel/events router

packages/server-python/app/shared/schemas/
  agent_integration.py  # versioned DTO/event envelope only; no ORM/domain service

packages/server-python/app/composition/
  agent_control_plane.py  # Coordinator + Guard wiring; only application ports, no domain rows
```

固定命名：`Conversation`、`ConversationUserState`、`Message`、`MessagePart`、`AgentRun`、`TurnInput`、`RunEvent`、`ConversationExecutionCoordinator`、`ConversationExecutionGuard`、`WorkspaceReadPort`、`ExecutionRunReadPort`。禁止使用含义模糊的 `Session` 代替产品 Conversation；Runtime 私有会话统一叫 `RuntimeSessionBinding`。

源码参考继续使用 REQ-059 固定 commit 导航，重点是 Codex Thread/Turn/Item、OpenClaw EventLedger、OpenCode per-session serialization 和 Open Design Conversation/Runtime identity 分离；只借鉴契约，不复制 local-first 存储。

## 4. PR/Slice 顺序

每个 Slice 单独 PR；后一个 Slice 只依赖已经合并的前置契约。不同模型不得并发修改同一 migration、状态机或 shared integration schema。

### Slice W1：Workspace durable store

**复杂度/执行**：高，`S-H`；Repository/DTO/普通 API 测试可交 `G-H`，删除与幂等由 `S-XH` Review。

**实施状态**：🟢 已由 [PR #479](https://github.com/MarkDanile/MetaEduBase/pull/479) 合并；只完成本 Slice，REQ-041 全需求继续保持 Doing。

交付：

- 建立 `agent_workspace` context 骨架和 `Conversation/ConversationUserState/Message/MessagePart` domain model。
- 独立 migration 创建四张业务表与 workspace inbox/outbox infrastructure 表；tenant-first unique/index 与 partial unique 必须落数据库。
- 实现 Conversation/Message repository、Message/run queue seq 行锁分配、完整 command digest 与 owner-private policy。
- 实现 create/get/list/search/rename/pin/archive/restore/history；delete 字段和 repository 先落地，DELETE endpoint 等 B1 Guard 可用后再开放。
- route 未完整接通前不把菜单改名为 Agent Workspace，不声明页面刷新能力已交付。

退出条件：

- 相同 Message idempotency key + 完整 command digest 返回同一对象/run id/queue seq，不同 digest 409。
- 50 个并发 Message 写入得到无重复、无 gap 的 1..50 seq。
- tenant/actor 矩阵、keyset cursor、搜索正文权限、auto-title/user-title CAS 与 user-scoped pin 测试通过。
- migration upgrade/downgrade/upgrade 通过，且没有跨 context FK。

### Slice E0：Execution identity、Binding 与 Snapshot contract

**复杂度/执行**：极高，`S-XH`；profile DTO 可下放，Binding epoch/ACK cursor 不可下放。

**实施状态**：🟡 分支 `codex/req-047-e0-execution-identity` 实现与验证已完成，正在走 Git 闭环；严格止于本 Slice，未引入 Run/Event 或 Runtime 调用。专项 21 passed、全量 1411 passed / 4 deselected；独立 `max` 反例审查最终 P0/P1=0。

交付：

- 创建最小 `AgentDefinitionVersion/RuntimeProfile/RuntimeSessionBinding` 与 versioned capability/config/context snapshot schema。
- migration 建立 profile catalog 与 Binding ingest cursor；不引入 Pi SDK、Worker 进程或 Runtime 私有 checkpoint。
- 提供 tenant-scoped、幂等的 `system.direct_rag.v1` / `compat.direct_rag.v1` bootstrap；compat profile 只给旧入口，能力固定 `resume/steer/native_tools=false`。
- 冻结 binding epoch fencing、单活动 ingest stream、`next_expected_runtime_seq/acked_through` 和 runtime provenance 全空/全有约束。

退出条件：profile digest 发布后不可改；跨 tenant/binding/run/epoch 事件被拒；5 先于 4 不落库、不 ACK through 5；重复 seq 同 digest 返回累计 ACK、不同 digest fail closed。

### Slice E1：Execution durable core

**复杂度/执行**：极高，`S-XH`；第二 Harness 只读检查状态机和并发反例。

交付：

- 建立 `agent_execution` context 骨架和 `AgentRun/TurnInput/RunEvent` domain model，引用已合并 E0 identity/snapshot。
- 独立 migration 创建 run/input/event 与 execution inbox/outbox 表；建立 FIFO queue、one-active partial unique lease、canonical/runtime seq unique 和 recovery index。
- Run 固化 bounded capability/config/budget snapshot 与 context ref/digest。
- 使用表驱动状态机实现 spec 允许迁移与终态 guard。E1 只启动 capability snapshot 明确 `tool/input/approval=false` 的 compatibility/read-only profile；其他 profile 在对应 durable store 未安装时 fail closed。测试通过 GuardStatePort fake 覆盖 pending/unknown 反例，不把 fake 当生产实现。
- 实现 RunEvent append、Runtime ingest dedupe、canonical terminal event 与 AgentRun 终态同事务。
- `runtime.terminal_observed` 只能作为 observation；不得直接等同 canonical terminal。

退出条件：

- 全状态迁移表、非法迁移、CAS race、FIFO/projection barrier、queued start race 和 one-active lease 测试通过。
- 100 个并发 append 得到无重复、无 gap 的 1..100 canonical seq；runtime ACK 只推进同事务提交的连续前缀。
- completed 缺 output digest/message id、存在 pending guard 或冲突 terminal digest 时 fail closed。

### Slice B1：Workspace/Execution bridge 与并发 Guard

**复杂度/执行**：极高，`S-XH`；不得下放一致性算法。

交付：

- 在 shared schema 中冻结 `turn.requested.v1`、`assistant_message.publish_requested.v1` 与 inbox ACK DTO；共享文件只含 schema。
- 实现 submit-turn：Guard -> Conversation row -> user Message/Part + preallocated run id + workspace outbox 同事务。
- execution consumer 在单事务内完成 inbox receipt claim/digest 校验、相同 run id 的 root TurnInput/queued AgentRun、receipt consumed；commit 后才 ACK workspace outbox。
- Run completed 时同事务预分配 terminal message id、写 terminal result/event 与 publish outbox；workspace consumer 以预分配 id 幂等投影 assistant Message。
- user Message 投影 `pending/accepted/dead_letter/abandoned` dispatch 状态，completed Run 投影 `pending/published/dead_letter/suppressed` output publish 状态；transport 发送成功不能代替 consumer ACK。
- 在 `app/composition` 实现 `ConversationExecutionCoordinator/Guard`，两个 context 只暴露 application port；submit/dispatch/start/projection/delete/purge 全部遵守固定锁顺序和 authoritative read 禁缓存。
- scheduler 只启动最小未放弃 queue seq，且所有 predecessor output 已 `published/not_required/suppressed`。
- 提供 dead-letter retry/abandon 命令；abandon 必须在 Guard 内证明 execution 无 receipt/run，再停用原 outbox。
- 提供 output projection retry/reconcile/suppress 命令；suppress 只用于 terminal object 永久不可读，必须以预分配 Message id 写 redacted tombstone/system notice并记录 actor/reason/digest。
- dispatcher claim 与 ACK 只用独立短事务；释放 outbox 行锁后才获取 Guard/调用 consumer，禁止持 row lease 进入业务锁链。
- 开放 Conversation DELETE：有未 ACK turn 或任意非终态 Run 返回 409；Execution port 不可用返回 503。

故障矩阵：

| 崩溃/竞争点 | 断言 |
|-------------|------|
| Message/outbox commit 后、dispatch 前退出 | 后台创建同一 run id |
| execution commit 后、ACK 前退出 | 重投不生成第二个 Run/TurnInput |
| inbox receipt claim 后、领域写前退出 | 同事务回滚，重投继续而不是跳过 |
| terminal commit 后、assistant publish 前退出 | GET Run 已终态，后台只投影一个 Message |
| assistant Message commit 后、ACK 前退出 | 预分配 id/origin unique 返回同一 Message |
| delete 与 pending dispatch 竞争 | delete 409 或 dispatch 先完成；不存在 deleted 后新 Run |
| 两 scheduler 同时 start | 只有一个取得 lease，另一个保持 queued/retry |
| queue seq 2 先入 execution、seq 1 仍在 outbox | seq 2 不启动，直到 workspace barrier 确认 1 resolved |
| predecessor terminal、assistant projection pending | 下一 Run 不启动，projection 稳定后才释放 barrier |
| terminal 后 publish 与 delete 竞争 | Message 可投影但在 deleted Conversation 下保持隐藏 |
| outbox 重试耗尽 | 原 event/run/message id 进入可观察 dead-letter；具名重放后恢复且不重复业务对象 |
| terminal object 永久不可读 | 授权 suppress 写 tombstone并释放 FIFO；不伪造正常 assistant output |
| dispatcher claim 与 purge 并发 | 无 outbox-row/Guard 锁反转；真实 PostgreSQL deadlock 测试无环 |

### Slice A1：Run query 与 SSE replay

**复杂度/执行**：高，`S-H` 主导；replay/live handoff 与权限撤销由 `S-XH` Review。

交付：

- 实现 GET Run、cancel intent 和 `GET /events?after_seq=N`。
- SSE 使用 Authorization fetch stream，`id=seq`、exclusive after_seq、comment heartbeat 和 versioned audience DTO；无权事件返回同 seq 的 `event.redacted`。
- replay/live handoff 使用同一个 ledger boundary；数据库通知只作唤醒，遗漏通知时仍从 PostgreSQL seq 补读。
- 实现 retention 410、内部 gap 409、cursor ahead 409、Last-Event-ID 冲突 400 和终态后正常结束。
- 每批/heartbeat 重查短期 access decision；权限撤销关闭流。

退出条件：断线重连无丢失/重复、replay 与 live 交界无窗口、相同 seq/同 audience 不同 delivery digest fail closed、混合 visibility 仍连续、跨 tenant/actor 与 URL token 均拒绝。

### Slice D1：旧 Direct RAG compatibility recording

**复杂度/执行**：高，`S-H` 或 `G-M`，`S-H` Review。

交付：

- 现有 `/ai/chat/evidence` 行为保持兼容，并在旧入口内部通过 CompatibilityRunAdapter 写同一 Conversation/Run/Event/terminal contract；它不消费新 Workspace submit-turn。
- 输出最小事件族：queued/started、phase、evidence summary、usage/error summary、canonical terminal；不伪造 ToolCall 或 RuntimeSessionBinding。
- existing RAG source 只转为受权限裁剪的 Evidence summary/ref，不把 diagnostics 原文整体复制到 Message。
- 使用 deterministic fake LLM + 真实 PostgreSQL 验证 persistence/replay；真实 LLM 只作为产品效果验收，不是 durable contract 通过前提。
- 新 Workspace submit route 保持 feature-disabled，直到 REQ-043 至少一个 AgentTurnLoopRuntime profile 通过 conformance；测试可用 fake Runtime 验证命令契约，不在生产把 Direct RAG 冒充 Agent Loop。

退出条件：重新认证后通过 API 恢复旧入口记录的 user Message、Run、events、assistant Message；原 `/ai/chat/evidence` 回归不变；同一输入重试不重复回答。页面刷新/断线体验归 REQ-042。

### Slice R1：Retention、purge 与恢复收口

**复杂度/执行**：极高，`S-XH`；GLM-5.2 `max` 隐私/故障反审，人工数据负责人签字。

交付：

- 实现 30 天 Conversation recovery、Run/Event 90/365 天基线、payload tombstone 与 envelope bounds。
- `ConversationExecutionCoordinator` 驱动固定 owner 集合的 durable purge saga；各 owner 在首次正文写事务预建 active ErasureFence，writer/purge 共用 owner-scoped transaction lock，并在同事务完成 revision 校验、write/erasure、ingress watermark 和 digest ACK。
- legal hold、`outcome_unknown`、未解决审批或业务保留时延后 purge，并记录 reason code。
- execution ACK 前 suppress 未投影 output、撤销 publish outbox、清除 terminal output ref；Runtime/business/inbox/outbox/external-object 所有迟到写先查 owner fence，purged 后只能拒绝或写无正文 tombstone并安全推进水位。
- legal hold 与 purge 用 hold/purge revision CAS 排序；purge 不等待 outbox row lease，通过 fence/cancellation CAS 收口在途 delivery。
- 外置对象先写隔离 staging object，只在 owner fence transaction 内发布引用；定期清理无引用 staging，不能用“对象写成功”冒充数据库引用已提交。
- Guard/owner advisory lock key 使用唯一共享的稳定 64-bit 派生函数，记录等待时间、超时和碰撞诊断；各 Adapter 不得自行 hash。
- owner registry 是 purge revision 的输入；新增/未知 owner 或 fence capability 未安装时 fail closed，不得提前 ACK。
- purge 分步 checkpoint、幂等重试、部分失败可观察；固定 owner 全 ACK 且最终正文扫描为零后才写 `purged_at`。
- 补一致性巡检：opaque ref tenant mismatch、Message/terminal digest conflict、event seq gap、orphan external payload。

退出条件：冻结时间测试覆盖 30/90/365 天；payload expired 不制造 seq gap；envelope 裁剪正确推进 first available；active/pending/queued/projection 并发删除、hold/purge race、dispatcher deadlock、writer fence-check 后暂停再与 purge 竞争、旧 Worker spool/业务 outbox 迟到写、部分失败和 purge 后投影测试通过。

### Slice C1：Durable Core 总验收与文档收口

**复杂度/执行**：高，`S-H` 集成，`S-XH` 最终 Review。

- 运行联合契约 conformance/fault suite 和完整相关后端回归。
- 更新 `ARCHITECTURE.md`：只在两个 context 的代码、迁移和组合根真实落地后登记，不在此前预写。
- 更新 REQ-041 为 Done；REQ-047 只标 Durable Core 完成，不关闭完整 Requirement。
- 记录真实 model id/effort、第二评审缺陷、返工和 CI 尝试。
- 不在本 Slice 顺手实现 REQ-042 UI、REQ-043 Runtime 或 REQ-047 extended entities。

## 5. REQ-047 后续塑形门禁

以下对象仅在本 spec 中冻结所有权、引用和 terminal guard，未获得本 plan 的实现授权：

| 后续契约 | 必须先回答 | 推荐强度 |
|----------|------------|----------|
| HumanInputRequest + ApprovalRequest | audience、first-answer-wins、expiry、revision/epoch、审批过期与 Tool 原子取消 | `S-XH` + 独立 `G-M` 反例审查 |
| ToolCall + ToolGrant + Snapshot | prepare/reserve/execute/reconcile/settle、预算、幂等、unknown outcome、secret 边界 | `S-XH`，人工安全签字 |
| Artifact + EvidenceItem | 版本、业务 ownership、下载授权、retention、证据血缘和 DD compatibility | `S-H` 主修，领域/数据负责人验收 |

这三组契约可以在 E1 Durable Core 后塑形，但生产 L3 写操作必须等待前两组完成。

## 6. 全局验证命令

每个实现 PR 按变更范围执行最小相关套件，C1 至少执行：

```bash
cd packages/server-python
uv run pytest tests/contexts/agent_workspace tests/contexts/agent_execution -q --tb=line
uv run pytest -q -m 'not external_network' --tb=line
uv run ruff check app/ tests/
uv run python scripts/check_mypy_baseline.py
uv run alembic upgrade head
cd ../..
scripts/check-engineering-docs --full
git diff --check
```

另需以测试或故障注入脚本固定以下矩阵：50 并发 Message seq、100 并发 RunEvent seq、双 scheduler lease、每个 outbox/inbox crash point、SSE replay/live handoff、permission revoke、output suppress、30/90/365 retention、legal hold、erasure fence 迟到写与 delete/dispatch/start/purge race。锁序和 fence 用真实 PostgreSQL 验证；只跑 mock 不得宣称真实 LLM 效果或 Pi Runtime 已完成。

## 7. 回滚与发布

- migration 只新增表/索引，不改旧 `/ai/chat/evidence` 数据；每个 migration 可独立 downgrade。
- 新路径在 REQ-042/043 验收前不进入主菜单；submit route 在 AgentTurnLoopRuntime profile conformance 通过前保持关闭，旧 Direct RAG 继续服务。
- 已写入的 Run/Message 审计不通过回滚删除；回滚代码后保留表，使用向前修复处理 schema/数据。
- inbox/outbox consumer 使用版本化事件；发布顺序为 consumer first、producer second，回滚顺序相反。
- 不用 Redis/Kafka 作为 V1 正确性前提；未来只替换 fanout/dispatch transport，不替换 PostgreSQL 企业事实源。
