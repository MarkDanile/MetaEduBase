# REQ-041/047 R1：Retention、Purge 与恢复专项契约

> Status: Draft for Architecture Review
> Date: 2026-07-27
> Parent Requirement: [REQ-041](../../01-product-planning/05-requirements/REQ-041-ai-workspace-conversation-persistence.md) / [REQ-047](../../01-product-planning/05-requirements/REQ-047-agent-run-artifact-approval-center.md)
> Parent Contract: [Conversation/Message/Run/Event 联合核心契约](2026-07-24-req-041-047-conversation-run-contract.md)
> Implementation Plan: [R1 分 Slice 实施计划](../02-plans/2026-07-27-req-041-047-r1-retention-purge-recovery-plan.md)

## 1. 目标与边界

R1 只解决 Conversation 删除后的恢复、正文清除、审计保留、法律 hold、迟到写和 purge 故障恢复。它不新增 Agent Workspace 页面、不开放新 `/turns` 入口、不实现 Pi Worker，也不提前实现 Approval、ToolCall、Artifact 或 Evidence 的完整领域模型。

本专项细化联合契约 CR-10、CR-13、CR-16，不改变以下已冻结前提：

- 产品 Conversation 与 Runtime 私有 Session 分离。
- `agent_workspace` 与 `agent_execution` 不共享 ORM、repository 或跨上下文外键。
- Conversation 删除不得通过 ORM cascade 删除 Run 审计。
- 原始 Chain-of-Thought、secret、数据库连接和未裁剪 Tool Result 不得进入持久化正文或 purge 日志。
- PostgreSQL 是 V1 的企业事实源；Redis、内存状态或 Worker 本地 spool 不能决定 purge 是否完成。

## 2. 当前源码事实

截至 `main@643131cd`：

- `ConversationExecutionCoordinator.delete_conversation()` 已在 Guard 内检查未 ACK turn 和非终态 Run，并设置 `purge_after = deleted_at + 30 days`。
- `acquire_purge_preflight()` 只建立 `Guard -> Conversation` 锁序，明确没有执行 R1 清除。
- `agent_conversations` 已有 `purge_state / purge_revision / purged_at`，但没有 ErasureFence、legal hold、owner ACK 或 durable purge operation。
- `RunEvent` 已有 `payload_state / expires_at / first_available_event_seq` 所需基础字段，但没有 retention worker。
- D1 已新增 `agent_compatibility_outputs`，其中 `reply_text` 与 `response_envelope` 是 Conversation-owned execution 正文。
- 当前 MessagePart、completed AgentRun、CompatibilityOutput 和 inbox/outbox 的 CHECK/NOT NULL 约束不能表达“正文已清、envelope/digest 保留”；R1 必须先扩展 tombstone schema，不能用占位字符串或空 JSON 冒充已清除。
- Workspace/Execution inbox 仅存 digest，但 inbox/outbox 并非全部具有显式 `conversation_id`，不能靠解析任意 JSON 判断 owner。
- Pi/ACP/LangGraph Runtime 尚未安装；当前不存在可被声明为已验收的 Worker spool 清除实现。

当前实现锚点：

| 事实 | 源码路径 |
|------|----------|
| Guard、delete/restore 与 purge preflight | [`packages/server-python/app/composition/agent_control_plane.py`](../../../packages/server-python/app/composition/agent_control_plane.py) |
| Conversation/Message/Part 与 transport ORM | [`packages/server-python/app/contexts/agent_workspace/infrastructure/models.py`](../../../packages/server-python/app/contexts/agent_workspace/infrastructure/models.py) |
| Workspace submit/projection/迟到写入口 | [`packages/server-python/app/contexts/agent_workspace/application/bridge.py`](../../../packages/server-python/app/contexts/agent_workspace/application/bridge.py) / [`infrastructure/bridge_repository.py`](../../../packages/server-python/app/contexts/agent_workspace/infrastructure/bridge_repository.py) |
| Binding/Run/CompatibilityOutput/Event 与 transport ORM | [`packages/server-python/app/contexts/agent_execution/infrastructure/models.py`](../../../packages/server-python/app/contexts/agent_execution/infrastructure/models.py) |
| Run 状态与 Runtime ingest | [`packages/server-python/app/contexts/agent_execution/application/run_coordinator.py`](../../../packages/server-python/app/contexts/agent_execution/application/run_coordinator.py) / [`infrastructure/execution_repository.py`](../../../packages/server-python/app/contexts/agent_execution/infrastructure/execution_repository.py) |
| D1 正文 staging 与 terminal/output projection | [`packages/server-python/app/composition/direct_rag_compatibility.py`](../../../packages/server-python/app/composition/direct_rag_compatibility.py) / [`application/compatibility_output_service.py`](../../../packages/server-python/app/contexts/agent_execution/application/compatibility_output_service.py) |

外部源码参考沿用联合契约已固定版本：OpenClaw [`event-ledger.ts`](https://github.com/openclaw/openclaw/blob/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9/src/acp/event-ledger.ts) 的连续事件账本、[`approval-shared.ts`](https://github.com/openclaw/openclaw/blob/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9/src/gateway/server-methods/approval-shared.ts) 的 revision/first-answer-wins，以及 Open Design [`db.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/db.ts) 的产品会话与 Runtime identity 分离。它们用于验证结构思路，不替代 MetaEduBase 的多租户 purge、legal hold 和 PostgreSQL 锁语义。

## 3. 生命周期与时间基线

所有 retention 时钟使用 PostgreSQL UTC 时间；测试可注入 clock，但生产裁决不得依赖 API/Worker 本机时间。

| 对象 | 起算点 | 基线 | 到期行为 |
|------|--------|------|----------|
| Conversation recovery | `deleted_at` | 30 天 | 到期后禁止普通恢复，进入 purge 调度 |
| Conversation-owned 正文 | purge owner ACK | 最晚在 purge 完成前清除 | 只保留最小 tombstone/digest |
| RunEvent 热重放 | `persisted_at` | 90 天 | 先清 payload，再按完整连续前缀裁剪 envelope 并推进 `first_available_event_seq` |
| AgentRun 终态/审计 envelope | `ended_at` | 365 天 | 无 hold 时进入 execution audit prune；正文可能因 Conversation purge 更早清除 |
| legal hold | hold 生效时间 | 至显式解除或 `expires_at` | 阻止相关正文 purge 和 audit prune，不允许恢复已清除正文 |

恢复规则冻结为：

1. 仅 owner 可恢复，且必须满足 `now < purge_after`、`purged_at IS NULL`、无 owner 进入 `erasing/acked`。
2. `purge_state=running|completed` 时拒绝普通恢复；`blocked/failed` 也不能绕过 30 天截止时间。
3. 恢复成功通过 CAS 清除尚未开始的 purge operation，并递增 Conversation revision；旧 purge lease/revision 随后失效。
4. hold 只保留数据，不延长用户恢复窗口。解除 hold 后从原 `purge_after` 判断是否立即重新排队。

上述范围覆盖在线 PostgreSQL、应用 staging/object adapter 和已登记派生存储。数据库 backup、WAL 和快照服从基础设施 retention runbook：备份不能逐 Conversation 原地改写，但必须有加密、访问隔离和最长保留期；从旧备份恢复时，服务保持不可对外读写，先从独立保存的 erasure operation/receipt 账本重放已完成 purge，再开放流量。没有该 restore drill 证据时只能声明“在线数据已清除”，不能声明完整生产擦除闭环。

## 4. Owner Registry

Purge revision 必须固化 owner registry snapshot 和 digest。owner key/version 是协议字段，不得使用 Python 类名、模块路径或运行时随机顺序。

### 4.1 V1 固定 owner

| owner key | 拥有的正文/引用 | purge 后保留 | ACK 前置条件 |
|-----------|-----------------|------------|--------------|
| `workspace.core.v1` | Conversation title；Message/Part text、display name、resource ref；用户级会话状态 | Conversation/Message id、seq、digest、分类、不可逆 actor audit digest、删除审计 | workspace 正文扫描为零，原 actor id 与 user state 已清除或不可逆匿名化 |
| `workspace.transport.v1` | workspace outbox inline/external payload 与未决 delivery | event id/type/version、digest、取消/消费状态 | conversation-scoped outbox 已取消或无正文 tombstone；inbox receipt 可证明旧事件不会复活正文 |
| `execution.core.v1` | Runtime binding 私有 session ref；Run context/output refs、正文型 snapshots/usage；CompatibilityOutput；RunEvent payload | Run/terminal/event 最小 envelope 与 digest，服从 90/365 天时钟 | output 已 suppress、正文引用与 compatibility output 已清除、event payload 已 tombstone |
| `execution.transport.v1` | execution outbox inline/external payload 与未决 projection | event id/type/version、digest、decision/取消状态 | publish outbox 已取消或 suppress，inbox receipt/迟到 projection 只能落 tombstone |
| `external.payload.v1` | 由上述 owner 登记的外置 payload/staging object | ref digest、media type、classification、erase receipt | 所有已发布对象得到适配器删除 ACK；无引用 staging 已清理 |
| `runtime.private.v1` | 外部 Runtime 的私有 session/checkpoint/spool | binding/epoch/session digest 和销毁结果码 | 有 runtime ref 时必须由已安装 Runtime eraser ACK；未安装能力时 blocked |

以下对象明确不随 Conversation purge：

- `AgentDefinitionVersion`、`RuntimeProfile` 是 tenant catalog，不是 Conversation-owned 数据。
- Resource/Knowledge 文档是被引用资产；R1 只清除 Message 中的 `resource_id/display_name` 引用，不删除源资产。
- 当前 Due Diligence task/report/evidence 没有 Conversation ownership 契约，不能因名称相近被 R1 级联删除。
- 未来业务 Artifact/Evidence 必须先登记稳定 business owner key、conversation ownership/ref ledger 和 erasure capability，才允许写入 Conversation-owned 正文。

### 4.2 Registry 变更

- purge operation 开始时保存排序后的 `(owner_key, owner_version, capability_digest)` 列表及 registry digest。
- 新 owner 或 capability 版本变化不得追加到正在运行的旧 snapshot；Coordinator 将旧 operation 标记 `blocked_registry_changed`，以新 purge revision 重建 owner checkpoints。
- 检测到未知 owner key、未知外置 ref scheme、Runtime ref 但无 eraser、或 Conversation-owned 业务引用但无 participant 时 fail closed。
- “没有查到正文”不是隐式 ACK；participant 仍须在 owner lock 下建立 fence，提交带扫描摘要的 `not_applicable/erased` ACK。

## 5. Durable 数据契约

R1 新增的协调数据属于 Control Plane coordination infrastructure，不成为 Message/Run 之外的第三份业务正文事实源。上下文通过 application port 使用它，不直接 import 对方 ORM。

### 5.1 ErasureFence

`agent_erasure_fences` 每个 `(tenant_id, conversation_id, owner_key)` 一行：

| 字段 | 约束/语义 |
|------|-----------|
| owner_key / owner_version | registry identity；不可就地改名 |
| state | `active/erasing/erased/blocked` |
| purge_revision / hold_revision | writer、purge、hold 的 fencing token |
| ingress_checkpoint | 有界 canonical JSON；按 source key 记录 epoch/连续水位，不保存正文 |
| ingress_digest | checkpoint JCS SHA-256 |
| last_body_write_at | 可观察，不作为正确性裁决 |
| ack_digest / acked_at | owner 清除结果；仅 `erased` 可有 |
| revision / updated_at | CAS 与审计 |

所有已有 Conversation 必须在迁移或受控 backfill 中建立当前已安装 owner 的 fence。新正文 writer 在首次写事务中创建缺失 fence；purge 遇到缺失 fence也必须在 owner lock 下创建，不能把缺行解释为安全。

### 5.2 Purge operation 与 owner checkpoint

- `agent_conversation_purges`：每个 `(tenant, conversation, purge_revision)` 一行，保存 registry digest、retention policy snapshot/digest、hold revision snapshot、状态、lease epoch、计划/开始/完成时间、稳定失败码和重试时间。运行中的 operation 不受后续配置漂移影响；策略变更通过新 revision 生效。
- `agent_conversation_purge_owners`：每个 operation/owner 一行，状态为 `pending/erasing/blocked/failed/acked`，保存 attempt、checkpoint digest、ACK digest、非敏感 reason code 和时间。
- `agent_conversations.purge_state` 是产品查询投影；operation/owner rows 是 saga 与重试事实。两者必须在同一 Coordinator transaction 内保持一致。
- 只有 snapshot 中所有 owner 都 `acked`、registry digest 仍匹配、最后正文扫描为零，才写 `purge_state=completed` 与 `purged_at`。

### 5.3 Legal hold

`agent_conversation_legal_holds` 由 `agent_workspace` 拥有 lifecycle envelope：hold id、tenant、conversation、reason code、purpose、actor、active/expired/released、`expires_at`、revision 和审计时间。Conversation 增加单调 `hold_revision` 作为 purge CAS 输入。

- hold reason 只能来自受控枚举；自由文本不得包含正文、案件细节或用户提示词。
- 创建/解除 hold 需要显式 `agent_retention_hold.manage` permission、purpose 和审计 actor；super_admin 角色本身不自动授权。
- active hold 阻止 purge owner 从 `active` 进入 `erasing`，也阻止 90/365 天 prune。
- purge 已 completed 后新增 hold 只能保存审计，不能恢复正文。

### 5.4 Transport owner scope

Conversation-scoped inbox/outbox 必须有结构化 owner scope，不允许在 purge 时解析任意 payload：

- known event types 增加/回填 `conversation_id` 与 producer fence revision（或等价版本化 owner scope）。
- `turn.requested.v1` 从 Message/Workspace outbox 关系回填；`assistant_message.publish_requested.v1` 从 Run/Execution outbox 关系回填；对应 inbox 由 source event id/correlation 解析并校验。
- 新 conversation-scoped event 缺 owner scope 时 producer 拒绝提交；历史无法可靠回填的 row 进入具名 reconcile 队列并阻止 purge。
- transport schema 必须允许 `cancelled/suppressed` envelope 在保留 payload digest 的同时把 `payload_inline/payload_ref` 都置空；不得以 `{}`、空字符串或虚假 ref 绕过现有 payload CHECK。

## 6. 锁序与 Writer Fence

### 6.1 共享锁 key

唯一实现位于 composition/shared coordination module：

```text
conversation_guard_key(v1, tenant_id, conversation_id)
conversation_owner_key(v1, tenant_id, conversation_id, owner_key)
```

使用带版本前缀的 canonical bytes 经 SHA-256 派生 signed 64-bit key。所有 Adapter 必须调用该实现，不得自行 hash。碰撞只会让无关 owner 串行，不得破坏正确性；记录 lock wait、timeout、key version 和 owner key digest，不记录正文。

固定顺序：

```text
ConversationExecutionGuard
  -> Conversation row
  -> owner advisory transaction lock（按 owner_key 字典序，单 owner 操作只取一个）
  -> ErasureFence row FOR UPDATE
  -> owner aggregate rows（AgentRun 在 Message 之前时沿用既有规则）
```

outbox claim/lease 仍使用独立短事务，不得持 outbox row lock 等待 Guard。purge 通过 producer fence revision、cancel/suppress CAS 和 receipt 处理在途 delivery。

### 6.2 正文 writer 协议

每个 Conversation-owned 正文 writer 必须在同一数据库事务执行：

1. 获取 Guard/Conversation（适用时）与 owner lock。
2. `SELECT ... FOR UPDATE` fence；缺失则按 registry 建立 `active` fence。
3. 校验 Conversation state、hold/purge revision、owner version 与 producer fence revision。
4. `active` 才允许写正文，并原子推进 ingress checkpoint；`erasing/erased` 只能拒绝，或按具名 integration contract 写无正文 tombstone/receipt。
5. 正文写、checkpoint 与 receipt 一起 commit；独立 preflight read 不构成授权。

Runtime ingest、business writer、output projection、transport consumer、external object publish 均服从该协议。旧事件缺 producer fence revision 且 purge 已开始时只能 tombstone/reconcile，不能重新创建正文。

## 7. Owner 清除语义

### 7.1 Workspace

- 清除 Conversation `title`，保留 `title_source=none` 或等价 tombstone。
- Message envelope 保留 id/seq/kind/digest/必要运行 opaque id；V1 物理删除 MessagePart 正文行并把 Message 转 redacted tombstone，避免用空正文违反 part-type 约束。若未来必须保留 Part envelope，需另行增加显式 tombstone state。
- `Conversation.created_by`、Message `author_id` 等直接主体标识在 purge 时清除，另存不可逆、tenant-scoped actor audit digest；相关 envelope CHECK/索引必须显式支持 tombstone，不能保留真实 user UUID 冒充匿名化。
- ConversationUserState 物理删除或不可逆匿名化；pin/read 状态不属于审计必需 envelope。
- 搜索、list/history API 不返回 purged 正文；owner 即使知道 UUID 也只能获得稳定 gone/not-found 语义。

### 7.2 Execution

- purge ACK 前将未发布 terminal output 转 `suppressed`，取消对应 outbox，清 `terminal_output_ref` 与正文型 context snapshot ref。
- completed Run 的 terminal schema 必须显式允许 `output_publish_state=suppressed` 时清 `terminal_output_ref/media_type/classification/message_id` 并保留 digest/size tombstone；不能改写 terminal status 或伪造 ref。
- `CompatibilityOutput.reply_text/response_envelope` 必须清除；增加显式 payload state 或独立 tombstone，使 run/output/response digest 可保留，不能用空字符串/空 JSON 通过约束。
- RunEvent 清 `payload_inline/payload_ref` 并设 `expired/redacted`，保留 seq、type、visibility、classification、digest、size 和 provenance envelope，直至 90 天 envelope prune。
- `RuntimeSessionBinding.runtime_session_ref` 先由 `runtime.private.v1` 处理；Execution 只在得到 Runtime ACK 后清本地 ref 并关闭/invalid binding。
- AgentRun 的 catalog refs 可保留至 365 天；正文型 snapshots、usage 细节和 terminal reason 必须按分类裁剪，不能把正文挪入 audit 字段逃避清除。

### 7.3 External payload

- object 必须先写隔离 staging，再在 owner fence transaction 内登记/publish ref；数据库 ref commit 失败时 staging cleaner 可回收。
- purge 只有在 object adapter 返回可验证 erase receipt 后 ACK；网络超时或结果未知保持 `failed/blocked`，不得把“已发删除请求”当完成。
- 当前没有生产 object-store adapter。R1 对未知 scheme 必须 `external_owner_unavailable` fail closed；fake adapter 只能证明契约，不得宣称生产对象已删除。

## 8. Retention worker 与恢复

三个独立 job 共用 bounded claim lease、数据库时钟、幂等 revision 和 tenant 限流：

1. `conversation_purge_scheduler`：claim 到期 deleted Conversation，建立 operation/owner snapshot，逐 owner checkpoint 执行。
2. `run_event_retention`：先把到期 payload 变 tombstone，再只删除完整连续前缀的 envelope，锁 Run 并原子推进 `first_available_event_seq`；不得制造内部 seq gap。
3. `run_audit_retention`：终态 365 天且无 hold/业务保留时清理 execution aggregate；非终态、`outcome_unknown`、未解决审批或 projection reconcile 未完成时 blocked。

Worker kill、lease 过期、ACK 丢失和重复 claim 后必须从 operation/checkpoint 恢复。重试复用同 purge revision 和 owner checkpoint；registry/hold revision 变化才创建新 revision。

Pi Worker spool 不在 R1 源码范围。R1 交付 `RuntimeErasureParticipant` conformance：session destroy、旧 epoch event、迟到 seq、unknown outcome 和 ACK 重放。REQ-043 的每个 Runtime Adapter 在启用前必须通过该 suite。

## 9. API、权限与可观察性

### 9.1 产品与运维入口

- 现有 owner DELETE/restore 保持产品入口；restore 增加 recovery deadline/purge revision 约束。
- legal hold create/release 是独立 data-governance API，不复用 Conversation PATCH。
- purge inspect/retry/reconcile 是内部运维 API，只返回 operation/owner 状态、digest、reason code、时间和 attempt，不返回正文。
- 不提供“强制跳过 owner ACK”或生产 `allow-always`。

### 9.2 稳定错误码

至少覆盖：

```text
conversation_recovery_expired
conversation_purge_in_progress
conversation_already_purged
purge_blocked_by_legal_hold
purge_blocked_by_unresolved_action
purge_owner_unavailable
purge_registry_changed
purge_owner_ack_conflict
late_body_write_rejected
external_erasure_outcome_unknown
retention_envelope_gap
```

### 9.3 指标与审计

记录 purge queue age、owner duration/attempt、blocked reason、lock wait/timeout、late-write reject/tombstone、external staging orphan、event payload/envelope prune 数量和 retention lag。日志不得记录 Message、event payload、object ref 原值、Runtime session ref 或自由文本 reason。

## 10. 发布、回滚与旧版本 Writer

R1 使用 expand/backfill/enforce/enable 顺序，purge scheduler 默认关闭：

1. Expand：先发布只新增/放宽 tombstone 表达的 schema，不删除旧字段或约束语义。
2. Writer fence：所有当前正文 writer 接入 owner fence，并上报稳定 writer capability version；混合旧/新 writer 期间禁止启用 purge execution。
3. Backfill：用可恢复、分批、tenant 限流的命令补 fence、owner scope、policy snapshot 所需数据；无法可靠回填的行进入 reconcile 并阻止对应 Conversation purge。
4. Verify：运行 missing fence/owner scope/unknown ref/body scan，确认所有服务实例均满足 capability digest。
5. Enable：人工签字后按 tenant/canary 开启 scheduler；先观察 blocked/latency/late-write 指标，再扩大范围。
6. Contract：至少一个稳定发布周期后才收紧 NOT NULL/CHECK 或删除兼容路径。

V1 不支持 purge 开启时仍有旧 Writer 进程在线。Docker Compose 采用维护窗口完成 writer 切换；未来 Kubernetes 滚动发布必须有实例 capability/lease 门禁，不能靠“部署大概完成”判断。代码回滚只能关闭 scheduler 和回退 writer 功能，不能恢复已清正文；schema 采用向前修复。

## 11. 验收标准

- R1-AC1：冻结时间覆盖 30/90/365 天边界、时区和数据库时钟；恢复截止后不因 hold/worker 延迟重新开放。
- R1-AC2：owner registry snapshot/digest、未知 owner、版本变化和缺失 capability 均 fail closed。
- R1-AC3：每个正文 writer 与 purge 共用 owner lock/fence transaction；writer 在 fence check 后暂停并与 purge 竞争时，最终正文不复活。
- R1-AC4：Workspace/Execution/transport/external participant 分步 ACK、部分失败、重试、Worker kill 和 lease 接管可恢复。
- R1-AC5：purge 后 title、MessagePart、compatibility output、Run/Event payload、outbox payload 和外置 ref 扫描为零；audit envelope 不含可恢复正文。
- R1-AC6：event payload 到期不制造 seq gap；envelope prune 只删除连续前缀并正确推进 `first_available_event_seq`，SSE 返回稳定 410/409。
- R1-AC7：legal hold 与 purge CAS race、hold release、expired hold、purge completed 后新增 hold 均有真实 PostgreSQL 测试。
- R1-AC8：pending/queued/terminal projection、outbox claim、旧 producer revision、Runtime 迟到 event 和 external erase unknown 均不会盲重试正文写。
- R1-AC9：跨 tenant/actor、无 permission hold、owner scope mismatch、伪造 ACK 和 operation revision 重放被拒绝。
- R1-AC10：无原始 CoT、secret、正文或外部 ref 进入 purge operation、checkpoint、日志和指标。
- R1-AC11：expand/backfill/enforce/enable 演练证明旧 Writer 在线时 scheduler fail closed；无法回填 owner scope 的历史行不会被跳过。
- R1-AC12：从包含待删除正文的旧备份恢复后，在开放流量前重放 erasure ledger，最终 body/ref 扫描为零；未跑 restore drill 时完成声明明确降级。

## 12. 实施门禁

R1-S1 开工前须由用户/架构负责人确认：

1. V1 固定 owner key 与 `agent_workspace` 持有 legal-hold lifecycle envelope。
2. 30/90/365 天作为默认基线；tenant policy 只能延长，缩短需单独数据合规评审。
3. 当前 Due Diligence/Knowledge 资产不因 Conversation 引用被级联删除。
4. 未安装 Runtime/external/business eraser 时 purge fail closed，而不是用人工 ACK 绕过。
5. 备份/WAL 最长保留与 restore-before-open runbook 由生产基础设施负责人承接；R1 不把在线库清除冒充备份物理擦除。

R1 完成不等于完整 REQ-047 完成；Approval/Tool/Artifact/Evidence 仍需独立塑形。
