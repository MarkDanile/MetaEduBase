# REQ-041/047 Spec: Conversation、Message、Run、Event 联合核心契约

> **Status**: 🔵 Core Ready（REQ-041 全范围 + REQ-047 Conversation/Message/Run/Event Core）
> **Requirements**: REQ-041 / REQ-047
> **Parent**: REQ-059
> **Scope**: Contract-first shaping only；本 spec 不代表数据库、API、SSE 或 UI 已实现
> **Research baseline**: 2026-07-24

---

## 1. 结论先行

V1 建立两个独立 bounded context：

- `agent_workspace` 拥有产品级 `Conversation`、`ConversationUserState`、`Message` 与 `MessagePart`。
- `agent_execution` 拥有 `AgentRun`、`TurnInput`、`RunEvent`、Runtime Binding、Tool、Input、Approval、Artifact、Evidence 和运行 Snapshot。

两个上下文只交换稳定 UUID、版本化 integration event 和 application port DTO：

- 不共享 ORM model、repository 或 SQLAlchemy relationship。
- 不建立跨上下文数据库外键。
- 不通过 ORM cascade 删除执行审计。
- 不把 Run、Tool、Approval、Artifact 或 Evidence 正文复制进 Message JSON。
- 跨上下文写入使用 transactional outbox/inbox 和幂等消费者，不依赖双写碰巧成功。

新 Workspace 的用户输入经一个产品命令提交：

```text
POST /api/v1/agent-workspace/conversations/{conversation_id}/turns
  -> workspace transaction
       user Message + MessagePart
       preallocated run_id
       turn.requested outbox event
  -> synchronous best-effort dispatch after commit
  -> execution inbox (dedupe)
       TurnInput(root) + AgentRun(queued)
  -> background outbox retry makes delivery durable
       exhausted delivery remains replayable dead-letter + alert
```

Run 终态与 assistant Message 的关系采用反向 outbox：

```text
Runtime terminal result observed
  -> execution transaction
       RunResult ref/digest
       preallocated terminal_message_id (completed only)
       AgentRun canonical terminal state
       canonical terminal RunEvent
       assistant_message.publish_requested outbox event (completed with user-visible output only)
  -> workspace inbox (dedupe)
       final assistant Message + MessagePart using terminal_message_id
       unique(origin_run_id, output_ordinal)
```

因此浏览器断线、API 进程退出、outbox 重投或消费者重复执行都不会生成重复用户消息、Run、终态事件或 assistant Message。持续性下游故障不会被写成“已投递”：事件保留在可告警、可具名重放的 dead-letter，恢复后仍复用原 event/run/message id。

## 2. 当前源码事实

当前仓库事实：

- `knowledge/interfaces/api/ai_router.py` 的 `/ai/chat/evidence` 是一次请求/一次完整响应，没有产品 Conversation、Message 或浏览器 SSE。
- 后端使用 PostgreSQL `metaedu` schema、SQLAlchemy async session、UUID 主键与显式 `tenant_id`。
- Resource、Skill、MCP、Due Diligence 已形成 tenant-scoped repository、软删除、审计 digest 和业务报告独立所有权模式。
- 现有 MCP SSE 代码只解析第三方 MCP transport，不是可复用的产品 RunEvent 协议。
- 现有列表大多使用 offset；Agent Workspace 新增 keyset/seq cursor，不延续大历史 offset 的漂移风险。

源码参考：

- Codex [`app-server/README.md`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/app-server/README.md)：Thread/Turn/Item、start/resume/fork、steer/interrupt 和 terminal turn。
- Codex [`thread_manager.rs`](https://github.com/openai/codex/blob/39a2438d16514d0d6f88105d17b0f747994af487/codex-rs/core/src/thread_manager.rs)：loaded Thread 生命周期不等同持久化事实。
- OpenClaw [`event-ledger.ts`](https://github.com/openclaw/openclaw/blob/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9/src/acp/event-ledger.ts)：单调 seq、重放和完整性标记。
- OpenClaw [`approval-shared.ts`](https://github.com/openclaw/openclaw/blob/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9/src/gateway/server-methods/approval-shared.ts)：revision、runtime epoch 和 first-answer-wins。
- Open Design [`db.ts`](https://github.com/nexu-io/open-design/blob/506c2900b972e6f3a25cfe5fabd7041ec6d869ca/apps/daemon/src/db.ts)：产品 Conversation 与 Runtime Session identity 分离。
- OpenCode [`session/store.ts`](https://github.com/anomalyco/opencode/blob/743f6410f2e5002723fc5e893039ac49fbfe0de8/packages/core/src/session/store.ts)、[`run-coordinator.ts`](https://github.com/anomalyco/opencode/blob/743f6410f2e5002723fc5e893039ac49fbfe0de8/packages/core/src/session/run-coordinator.ts)：Session projection 与 per-key execution serialization。

生产约束仍以 [REQ-059 控制面 spec](2026-07-23-req-059-enterprise-agent-platform-control-plane.md) 为准；上游 local-first 数据模型不能替代 MetaEduBase 多租户控制面。

## 3. 所有权与依赖方向

| 对象 | 所有者 | 可引用 | 禁止 |
|------|--------|--------|------|
| Conversation | `agent_workspace` | tenant、created_by、parent conversation/message | Runtime live handle、Tool 状态 |
| ConversationUserState | `agent_workspace` | conversation、user | 把某用户 pin 变成全局 Conversation 字段 |
| Message / MessagePart | `agent_workspace` | conversation、requested/origin run opaque id | Tool/Approval/Event 正文、原始 CoT |
| AgentRun / TurnInput | `agent_execution` | conversation/input message opaque id | 导入 workspace ORM/repository |
| RunEvent | `agent_execution` | run、runtime provenance、payload ref | 作为 Message 唯一存储 |
| Approval/Tool/Artifact/Evidence | `agent_execution` | run、业务 opaque ref | 被 Conversation cascade 删除 |
| DdReport 等业务状态 | 对应 Agent App | run/artifact/evidence id | 搬入通用 Message/Artifact JSON |

允许依赖：

```text
agent_workspace application
  -> shared integration contract (DTO/event only)

agent_execution application
  -> WorkspaceReadPort (tenant + actor + opaque ids)
  -> shared integration contract (DTO/event only)

composition/agent_control_plane
  -> ConversationExecutionCoordinator
  -> ConversationExecutionGuard
  -> agent_workspace application ports
  -> agent_execution application ports
  -> owns orchestration, but no domain row or repository

outbox dispatcher
  -> invokes registered consumer ports, owns no domain truth
```

`WorkspaceReadPort` 只返回执行所需的不可变快照：conversation id、message id、tenant、actor、content part refs、classification、queue barrier 和 digest。`ExecutionRunReadPort` 只返回 authoritative non-terminal/queue/projection/retention summary。两者不暴露 ORM row，不缓存 Guard 窗口内的裁决结果，也不互相 import 对方 context 的 domain/repository。

## 4. 通用数据规则

### 4.1 ID、时间与租户

- 主键使用 PostgreSQL UUID，V1 延续仓库 UUIDv4 约定；显示顺序不得依赖 UUID。
- 所有表必须有 `tenant_id UUID NOT NULL`，唯一约束和查询索引以 tenant 为首列。
- API 时间使用 RFC 3339 UTC；新迁移使用 `TIMESTAMPTZ`，application 层禁止混用本地时区。
- 跨上下文引用使用 opaque UUID，不建 SQL 外键；写入前经 port 校验 tenant/actor，后台一致性检查发现孤儿引用时告警而不静默删除审计。
- 可变聚合使用单调 `revision BIGINT` 做 optimistic concurrency；命令携带 `If-Match` 或 expected revision。
- integration event 至少携带 `event_id / event_type / schema_version / tenant_id / occurred_at / correlation_id / causation_id`。
- 幂等摘要使用 SHA-256，输入为带 `schema_version` 的 canonical DTO；JSON 采用 RFC 8785/JCS 语义，字符串不做隐式 Unicode normalization，禁止各 Adapter 自行拼接字符串。

### 4.2 内容分类

- Message 正文允许 `internal/restricted`，但 API 必须经过 conversation actor access policy。
- RunEvent 内联 payload 必须 classification 不高于 `internal` 且 UTF-8 JSON `<= 32 KiB`。
- `restricted`、二进制或更大 payload 外置，事件只存 ref、digest、size、media type、classification 和 expiry。
- 原始 Chain-of-Thought、Provider 长期凭证、数据库连接、MCP secret 和未裁剪 Tool Result 不进入任何 Message、RunEvent、日志或 outbox payload。
- plan/phase/tool/evidence/usage/error 只保存可公开或经权限裁剪的摘要。

## 5. `agent_workspace` 数据契约

### 5.1 Conversation

目标表：`metaedu.agent_conversations`。

| 字段 | 类型/约束 | 语义 |
|------|-----------|------|
| id | UUID PK | Conversation 稳定 id |
| tenant_id | UUID, indexed | 租户边界 |
| created_by | UUID | V1 owner；平台管理员不因此获得正文权限 |
| creation_digest | char(64) | 不可变 create command 摘要；同 client conversation id 不同命令返回 409 |
| title | varchar(200) nullable | 首条消息前允许为空 |
| title_source | `none/auto/user` | 用户标题不得被 auto title 覆盖 |
| state | `active/archived/deleted` | 产品生命周期，不反映 Run 状态 |
| parent_conversation_id | UUID nullable | fork 来源，opaque self reference |
| forked_from_message_id | UUID nullable | fork 边界，不要求 V1 UI |
| next_message_seq | bigint, starts 1 | Conversation 内 Message seq 分配器 |
| next_run_queue_seq | bigint, starts 1 | submit-turn 在 workspace 内分配的 FIFO 序号 |
| last_activity_at | timestamptz | 列表排序；只由可见 Message/显式操作更新 |
| archived_at/by | nullable | 归档审计 |
| deleted_at/by | nullable | 软删除与恢复窗口 |
| purge_after | timestamptz nullable | 默认 deleted_at + 30 天，可被 policy/hold 延后 |
| purge_state | `not_scheduled/scheduled/running/blocked/failed/completed` | durable purge saga，不用单次 worker 调用冒充完成 |
| purge_revision | bigint | purge coordinator CAS 与 ACK 集合版本 |
| purged_at | timestamptz nullable | 正文已清除，最小 tombstone 保留 |
| revision | bigint | rename/archive/delete/restore CAS |
| created_at/updated_at | timestamptz | 审计时间 |

约束：

- `parent_conversation_id` 与 `forked_from_message_id` 必须同 tenant，经 application port 校验。
- `state=deleted` 时普通 list/get 返回 404；带 `include_deleted` 的恢复入口仅 owner 和授权数据管理员可见。
- `purged_at IS NOT NULL` 后不可恢复。
- title 去控制字符、最大 200 字符；自动标题异步 CAS，只在 `title_source=none` 时写入。

### 5.2 ConversationUserState

目标表：`metaedu.agent_conversation_user_state`。

| 字段 | 约束 | 语义 |
|------|------|------|
| tenant_id/conversation_id/user_id | composite unique | 用户级视图状态 |
| pinned_at | nullable | pin/unpin；不修改 Conversation 全局状态 |
| last_read_message_seq | bigint default 0 | unread projection，可延后使用 |
| updated_at | timestamptz | 最近状态变更 |

V1 Conversation 为 owner-private；该表仍独立存在，避免未来共享 Conversation 时迁移全局 `pinned_at`。

### 5.3 Message

目标表：`metaedu.agent_messages`。

| 字段 | 类型/约束 | 语义 |
|------|-----------|------|
| id | UUID PK | Message 稳定 id |
| tenant_id/conversation_id | required, indexed | workspace 所有权 |
| seq | bigint | Conversation 内严格递增；unique `(tenant_id, conversation_id, seq)` |
| message_kind | `user_input/assistant_output/system_notice` | Tool/Approval 不伪装成 Message |
| author_type | `user/agent/system` | 作者种类 |
| author_id | UUID nullable | user/agent id；system 可空 |
| client_message_id | UUID nullable | 用户输入幂等键 |
| requested_run_id | UUID nullable | user input 预分配 Run opaque id |
| requested_run_queue_seq | bigint nullable | user input 预分配的 Conversation FIFO 序号 |
| turn_request_digest | char(64) nullable | 完整 submit command 摘要，不只覆盖 Message 正文 |
| turn_dispatch_state | `pending/accepted/dead_letter/abandoned` nullable | 仅 user input；execution ACK 后 accepted，禁止把 transport publish 当 ACK |
| turn_dispatch_error_code/updated_at | nullable | dead-letter/恢复可观察信息，不保存敏感异常 |
| origin_run_id | UUID nullable | assistant output 来源 Run opaque id |
| output_ordinal | int nullable | V1 assistant final output 固定 0 |
| reply_to_message_id | UUID nullable | 语义回复关系 |
| content_state | `visible/redacted/superseded` | 删除/纠正不物理改写历史顺序 |
| content_digest | char(64) | canonical MessagePart digest |
| created_at | timestamptz | seq 是排序事实，时间只审计 |
| redacted_at/reason | nullable | policy 删除或安全清除 |

唯一约束：

- 用户输入：`(tenant_id, conversation_id, author_id, client_message_id)` 与 `(tenant_id, conversation_id, requested_run_queue_seq)` partial unique。
- assistant output：`(tenant_id, origin_run_id, output_ordinal)` unique where origin run not null。
- 同幂等键 + 同 `turn_request_digest` 返回原 Message/Run receipt；同键 + 不同 digest 返回 `409 idempotency_conflict`。摘要至少覆盖 tenant、actor、conversation、规范化 parts/resource refs、agent definition version 和客户端可控选项；服务端生成的 run/message id 不参与首次请求摘要。

Message envelope 创建后不可改 role、author、seq、requested/origin run、queue seq 或 content。唯一内容变化是具名 policy redaction/supersede，必须写审计和新 digest/tombstone；“编辑用户消息”通过新 Message + 新 Run 表达。dispatch projection 只允许 `pending -> accepted|dead_letter|abandoned`、`dead_letter -> pending|abandoned`；abandon 必须在 Guard 内确认 execution 尚无 Run/inbox receipt，并原子停用原 outbox event。

### 5.4 MessagePart

目标表：`metaedu.agent_message_parts`。

| 字段 | 约束 | 语义 |
|------|------|------|
| id | UUID PK | part id |
| tenant_id/message_id | required | 同 tenant；workspace 内可建 FK 到 Message |
| part_seq | int | unique `(tenant_id, message_id, part_seq)` |
| part_type | `text/resource_ref` | V1 只开放两种稳定类型 |
| text_content | text nullable | plain text/Markdown 原文；单 Message 文本合计最大 64 KiB UTF-8 |
| content_format | `plain_text/markdown` nullable | 禁止存未净化 HTML |
| resource_id | UUID nullable | `resource` context opaque ref |
| media_type/display_name | nullable | 展示元数据，不含 storage key |
| digest/classification | required | 完整性与授权 |

Artifact/Evidence 通过 RunEvent 和右侧面板查询，不伪装成 MessagePart。未来新增 image/audio 等 part type 属于契约扩展，必须同步 shared schema 和前端 adapter。

## 6. `agent_execution` 数据契约

### 6.1 AgentDefinitionVersion / RuntimeProfile 最小身份契约

AgentRun 的两个引用在 Core 中均为必填，因此 E1 必须提供最小只读 catalog，不能先写任意 UUID 等待 REQ-043 补表：

| 对象 | 最小字段/约束 | Core 边界 |
|------|---------------|-----------|
| AgentDefinitionVersion | `id/tenant_id/definition_key/version/status/definition_digest/created_by/created_at`；unique `(tenant_id, definition_key, version)`；发布后不可改 digest | 只表达稳定 Agent 身份；Builder、Prompt/Skill 配置和发布流程后置 |
| RuntimeProfile | `id/tenant_id/profile_key/runtime_kind/adapter_key/config_digest/capability_digest/enabled/revision/created_at/updated_at`；unique `(tenant_id, profile_key)` | 不保存 secret/命令行放权参数；完整 resolver、Pi/ACP/LangGraph adapter 归 REQ-043 |

每个使用 Direct RAG compatibility path 的 tenant 通过幂等 bootstrap 获得 `system.direct_rag.v1` AgentDefinitionVersion 和 `compat.direct_rag.v1` RuntimeProfile；能力固定声明 `resume=false / steer=false / native_tools=false`。这只是 control-plane identity，不伪造 Runtime Session，也不表示 Pi 已接入。

### 6.2 RuntimeSessionBinding / RuntimeIngestCursor 最小契约

原生 Runtime 才创建 Binding；Direct RAG/Skill compatibility Run 的 `runtime_binding_id` 为空且不得携带 runtime seq。

| 字段 | 语义 |
|------|------|
| id/tenant_id/conversation_id/runtime_profile_id | Binding identity 与 opaque refs |
| runtime_session_ref | Runtime 私有 session opaque ref；不是产品 Conversation，API 不返回原值 |
| status | `creating/active/resume_required/closed/invalid` |
| current_epoch | 每次创建/恢复执行所有权时单调递增的 fencing epoch |
| next_expected_runtime_seq | 当前 epoch 下一条允许摄取的 seq，初始 1 |
| acked_through_runtime_seq | 已同事务提交的最高连续前缀，初始 0 |
| active_stream_id/stream_lease_expires_at | 同一 binding/epoch 只允许一个活动 ingest stream |
| revision/created_at/updated_at | CAS 与审计 |

Runtime event 的 `binding_id/runtime_epoch/runtime_seq/runtime_event_id` 必须全空或全有；全有时 tenant、run、profile、binding 与当前 epoch 必须一致。摄取只接受以下三种结果：

- `runtime_seq == next_expected`：在同一事务中写 canonical RunEvent、推进 cursor 并提交 `acked_through`，commit 后返回累计 ACK。
- `runtime_seq <= acked_through`：仅当 runtime event id 和 digest 与历史一致时幂等返回当前累计 ACK；冲突 fail closed。
- `runtime_seq > next_expected`：返回稳定 gap，V1 不越序 buffer、不推进 ACK；Worker 保留 spool 并从 `next_expected` 重发。

### 6.3 AgentRun

目标表：`metaedu.agent_runs`。

| 字段 | 类型/约束 | 语义 |
|------|-----------|------|
| id | UUID PK | 可由 submit-turn command 预分配 |
| tenant_id/conversation_id | required, indexed | conversation 是 opaque ref |
| queue_seq | bigint | workspace 预分配的 Conversation FIFO 序号；unique `(tenant_id, conversation_id, queue_seq)` |
| root_input_message_id | UUID | root user Message opaque ref |
| parent_run_id | UUID nullable | regenerate/retry lineage；非 Runtime resume |
| agent_definition_version_id | UUID | 固化 Agent definition |
| runtime_profile_id | UUID | 本 Run 选择的 Runtime profile |
| runtime_binding_id | UUID nullable | Runtime 私有 Session binding |
| status | RunStatus | 见状态机 |
| status_revision | bigint | CAS 状态迁移 |
| next_event_seq | bigint starts 1 | canonical RunEvent seq 分配器 |
| first_available_event_seq | bigint starts 1 | retention 后最早热重放 seq |
| last_event_seq | bigint starts 0 | 当前 canonical 最大 seq |
| event_log_complete | bool default true | 裁剪/损坏必须显式 false |
| queued_at/started_at/ended_at | timestamptz | 生命周期 |
| terminal_reason/code | nullable | 稳定终止语义，不放敏感堆栈 |
| terminal_output_ref | varchar nullable | final assistant output 外置引用 |
| terminal_output_digest/size/media_type/classification | nullable | Message projection 完整性 |
| terminal_message_id | UUID nullable | `completed` 时预分配的 workspace Message opaque id；重投必须复用 |
| output_publish_state | `not_required/pending/published/dead_letter/suppressed` | completed output 到 workspace 的 projection 状态；不改变 Run 终态 |
| created_by | UUID | 提交 actor |
| correlation_id | UUID | 跨 context/Runtime trace |
| runtime_capability_snapshot/run_config_snapshot | JSONB, bounded | 版本化固定 schema；Core 先内联，不存 secret/任意 Provider payload |
| context_snapshot_ref/digest/classification | nullable | 上下文快照外置引用；正文归对应 owner，Run 只持完整性信息 |
| budget_snapshot/usage_summary | JSONB, bounded | 仅固定 schema，不存任意 Provider payload |
| created_at/updated_at | timestamptz | 审计 |

同一 Conversation 允许多个 `queued` Run，但最多一个执行占用者：

```text
UNIQUE (tenant_id, conversation_id)
WHERE status IN (
  'starting', 'running', 'waiting_input', 'waiting_approval',
  'resume_required', 'cancelling'
)
```

`resume_required` 继续持有会话执行租约；尤其存在 `outcome_unknown` 时，后续 queued Run 不得越过它执行。scheduler 在 `ConversationExecutionGuard` 内只能启动 workspace/execution 两侧共同确认的最小未放弃 `queue_seq`，不能因为更早 outbox 延迟而让后提交 Run 插队。

前驱 Run 还必须满足 projection barrier：所有更小 queue seq 已终态，且 `output_publish_state` 为 `published/not_required/suppressed`。`pending/dead_letter` 会阻塞后续 Run，防止 ContextAssembler 在 assistant Message 尚未落 workspace 时遗漏上一轮回答；用户可在新 Conversation/fork 继续，不允许当前 Conversation 静默跳过。

output projection 只允许 `pending -> published|dead_letter|suppressed`、`dead_letter -> pending|published|suppressed`。retry 复用原 outbox/event/message id；reconcile 发现预分配 Message 已存在且 digest 一致时置 published，发现 ref 可读时重排 pending，冲突时 fail closed。只有 terminal object 永久不可读且具名 actor 提供 reason，才允许 suppress：workspace 用预分配 Message id 写 redacted tombstone/system notice，execution 记录 actor/reason/original digest 后释放 FIFO barrier，禁止假装生成过正常回答。

### 6.4 TurnInput

目标表：`metaedu.agent_turn_inputs`。

| 字段 | 语义 |
|------|------|
| id/tenant_id/run_id | 输入记录与 Run |
| ordinal | Run 内输入顺序，root=0 |
| input_kind | `root/steer/human_response` |
| message_id | workspace Message opaque ref |
| request_id | submit/steer/respond 命令幂等键 |
| expected_runtime_epoch | steer/human response 防串 Run |
| context_digest | 从 WorkspaceReadPort 读取的不可变输入摘要 |
| created_by/created_at | actor 审计 |

约束：每个 Run 只有一个 root；`(tenant_id, run_id, ordinal)` 与 `(tenant_id, request_id)` 唯一。普通输入在活动 Run 期间创建新 queued Run；只有显式 steer endpoint 才创建同 Run 的 `steer` input，不自动把普通消息改成 steer。

### 6.5 RunEvent

目标表：`metaedu.agent_run_events`，append-only。

最小字段：

```text
id, tenant_id, conversation_id, run_id, seq,
event_type, schema_version, occurred_at, persisted_at,
visibility, classification, payload_inline|payload_ref,
payload_state, payload_digest, payload_size, media_type, expires_at,
runtime_id, runtime_binding_id, runtime_epoch,
runtime_seq, runtime_event_id,
correlation_id, causation_id
```

约束与序列：

- `(tenant_id, run_id, seq)` unique。
- Runtime 事件有 `(runtime_binding_id, runtime_epoch, runtime_seq)` unique；runtime provenance 四元组必须全空或全有。
- `runtime_seq` 只负责 ingest dedupe/累计 ACK；浏览器永远不看 runtime seq。ACK 只能推进到同事务已提交的最高连续前缀，禁止收到 5 就越过缺失的 4 ACK through 5。
- canonical seq 在同一事务锁 AgentRun row，读取并递增 `next_event_seq`，同时更新 `last_event_seq`。
- 事件 identity/type/seq/digest 等语义 envelope 不更新；只有 retention metadata 可把 `payload_state=inline/external` 迁到 `redacted/expired/archived`。payload 到期只把正文替换为具名 tombstone，不制造 seq gap；只有 envelope 被裁剪时才推进 `first_available_event_seq` 并把 `event_log_complete=false`。
- Worker terminal frame 只写 `runtime.terminal_observed`；唯一 canonical `run.completed/failed/cancelled/expired` 由 RunCoordinator 与 AgentRun 终态同事务提交。

事件族使用 REQ-059 定义；V1 新增 `message.publish_requested/message.published` 仅作为 integration/diagnostic event，不把 assistant Message 正文放入事件。

### 6.6 Inbox / Outbox

两个上下文各自拥有 infrastructure 表：

```text
agent_workspace_outbox / agent_workspace_inbox
agent_execution_outbox / agent_execution_inbox
```

最小字段：event id/type/version、tenant、aggregate id/type、payload ref/digest、correlation/causation、status、attempt count、next attempt、created/published/consumed time、last error code。

- 业务写与 outbox INSERT 必须同事务。
- inbox receipt claim/insert、event type/version/digest 校验、领域写和 receipt `consumed` 必须在消费者自己的同一数据库事务提交；任一步崩溃全部回滚。重复 event 仅在已 consumed 且 payload digest 一致时幂等 ACK；同 event id 不同 digest 进入完整性告警，不能覆盖或跳过。dispatcher 只能在该事务 commit 后收到 ACK。
- dispatcher 只在短事务中用 `FOR UPDATE SKIP LOCKED` claim lease 并立即 commit；释放 outbox 行锁后才调用 consumer，consumer commit/ACK 后再用独立短事务更新 outbox。禁止持 outbox/inbox 行锁获取 ConversationExecutionGuard。指数退避有上限并进入 dead-letter 告警；不得无限热循环。dead-letter 不删除 payload/digest，可由具名运维命令在根因解除后以原 event id 重排，不创建第二个业务命令。
- outbox payload 服从与 RunEvent 相同的敏感裁剪；大正文只传 payload ref/digest。
- “同步 best-effort dispatch”只降低延时，不能成为可靠性前提。

## 7. 状态机

### 7.1 Conversation

```text
active -> archived -> active
active|archived -> deleted -> active (仅 purge 前恢复)
deleted -> purged tombstone (retention worker，不可恢复)
```

- archive 不取消 Run；它只是列表可见性。
- delete 前若存在尚未被 execution ACK 的 turn dispatch，返回 `409 conversation_has_pending_turn`；若存在任意非终态 Run（包括 `queued`），返回 `409 conversation_has_non_terminal_run`，用户先 cancel/resolve。
- deleted Conversation 不接受新 Message/Run。

### 7.2 ConversationExecutionGuard

V1 的 workspace 与 execution 共用 PostgreSQL，但保持独立表和 repository。以下竞争操作必须先按 `(tenant_id, conversation_id)` 获取同一个 transaction-scoped `ConversationExecutionGuard`，再按固定顺序锁聚合行：

- submit-turn 写 Message/outbox；
- execution inbox 接受 `turn.requested`；
- queued Run 竞争 `starting`；
- assistant Message projection；
- turn dispatch replay/abandon；
- Conversation delete/restore/purge。

V1 可用稳定 64-bit key 的 PostgreSQL advisory transaction lock 实现；它只是 composition infrastructure 的并发原语，不成为第三份业务事实源。`composition/agent_control_plane` 的 `ConversationExecutionCoordinator` 持有 Guard 和跨 context 事务编排，两个 context 只实现 application port，不互相 import repository/domain。delete 在 Guard 内同时检查 workspace 未 ACK turn 与 `ExecutionRunReadPort` 返回的非终态 Run；Run 启动在 Guard 内通过 `WorkspaceReadPort` 重查 Conversation、actor grant、最小 queue seq 和 predecessor projection barrier。所有 authoritative read 使用同一事务且禁止缓存；完整锁序固定为“Guard -> Conversation -> owner ErasureFence -> AgentRun/Message”。outbox claim/ACK 是锁链之外的独立短事务，purge 通过 fence/cancellation CAS 处理在途 delivery，不等待或反向锁 outbox row。

这条规则关闭以下竞态：delete 检查后旧 outbox 才创建 queued Run、两个 scheduler 同时取得执行权、queued Run 在 Conversation 删除后启动。未来上下文拆到不同数据库时，必须用 durable coordinator lease/epoch 替换 advisory lock，不得静默降级为先查后写。

### 7.3 AgentRun

允许迁移：

| From | To |
|------|----|
| queued | starting / cancelled / expired |
| starting | running / resume_required / cancelling / failed / expired |
| running | waiting_input / waiting_approval / resume_required / cancelling / completed / failed / expired |
| waiting_input | running / cancelling / expired |
| waiting_approval | running / cancelling / expired |
| resume_required | starting / failed / cancelled |
| cancelling | completed / failed / cancelled / expired / resume_required |

终态：`completed / failed / cancelled / expired`。

全局 guard：

- 终态前不得存在活动 ToolCall、HumanInputRequest 或 ApprovalRequest。
- `executing/reconciling` 写 Tool 未完成时 cancel/timeout 只能进入 `cancelling`。
- 存在 `outcome_unknown` 时 Run 必须为 `resume_required`，不得进入任何终态或释放会话执行租约。
- `resume_required -> starting` 只允许同一 Binding、预期 epoch 的 resume 成功；转 failed/cancelled 前必须确认没有 `outcome_unknown`、撤销未使用 Grant 并关闭恢复意图，不能转 expired。
- queued 直接 cancelled 只适用于尚未创建 Runtime invocation/ToolCall 的 Run；cancelling 的 terminal 转移必须先满足全部终态 guard。
- `completed` 必须有独立 terminal result、可验证 output digest 和 canonical terminal event。
- 状态变化通过 `(id, tenant_id, status_revision, expected_status)` CAS；非法迁移返回稳定冲突，不覆盖当前状态。

## 8. 产品命令与 API

API 前缀：

```text
/api/v1/agent-workspace/*
/api/v1/agent-runs/*
```

### 8.1 Conversation API

| Method | Path | 语义 |
|--------|------|------|
| POST | `/agent-workspace/conversations` | 幂等创建；可接受 client conversation id |
| GET | `/agent-workspace/conversations` | keyset list；active/archived/deleted scope 显式；`q` 搜索可见 title/Message text |
| GET | `/agent-workspace/conversations/{id}` | tenant + actor visibility |
| PATCH | `/agent-workspace/conversations/{id}` | 仅 rename；必须 `If-Match` |
| PUT/DELETE | `/agent-workspace/conversations/{id}/pin` | user-scoped 幂等 pin/unpin |
| POST | `/agent-workspace/conversations/{id}/archive` | CAS archive |
| POST | `/agent-workspace/conversations/{id}/restore` | archive/delete restore；purged 禁止 |
| DELETE | `/agent-workspace/conversations/{id}` | 202 soft delete + purge schedule；pending turn/任意非终态 Run 返回 409 |
| GET | `/agent-workspace/conversations/{id}/messages` | `before_seq` 历史分页或 `after_seq` 前向增量 |
| POST | `/agent-workspace/conversations/{id}/messages/{message_id}/turn-dispatch/retry` | dead-letter 以原 event/run id 具名重排 |
| POST | `/agent-workspace/conversations/{id}/messages/{message_id}/turn-dispatch/abandon` | 确认 execution 未接受后放弃，不生成第二个命令 |

Conversation list cursor 固化 filter/query hash 与 `(pinned_at, last_activity_at, id)` anchor，并以 cursor issued-at 排除列表开始后新建的 Conversation。它保证 keyset 单向遍历而不冒充数据库历史快照：并发 rename/pin/new Message 会让条目重排，客户端在本地产生这些 mutation 后必须失效并重新加载列表。Message 历史默认按 seq descending 取一页、响应按 ascending 展示，不使用 offset。

client conversation id 的重试必须同时匹配不可变 `creation_digest`；摘要覆盖 tenant、actor、conversation id 与规范化初始标题。相同摘要返回原 Conversation，不同摘要返回 `409 idempotency_conflict`，后续 rename 不改变 creation digest。

`q` 去控制字符、长度 2-100，搜索 title 和 actor 有权读取且 `content_state=visible` 的文本 part；返回 Conversation 级结果，默认不回传正文 snippet。搜索 cursor 必须绑定 normalized query hash，换 query 后旧 cursor 返回 400。

### 8.2 Submit Turn

```http
POST /api/v1/agent-workspace/conversations/{conversation_id}/turns
Idempotency-Key: <client_turn_id UUID>
```

请求最小字段：

```json
{
  "parts": [
    {"type": "text", "text": "...", "format": "plain_text"},
    {"type": "resource_ref", "resource_id": "..."}
  ],
  "agent_definition_version_id": "..."
}
```

服务端决定 `run_id`、RuntimeProfile 和 queued/starting；客户端不能用请求参数绕过 Tool、模型或权限策略。响应 `202`：

```json
{
  "conversation_id": "...",
  "message_id": "...",
  "message_seq": 12,
  "run_id": "...",
  "run_queue_seq": 7,
  "dispatch_status": "accepted|pending",
  "run_status": "queued|starting|null",
  "correlation_id": "..."
}
```

`pending` 表示 workspace transaction 已 durable、execution consumer 尚未 commit/ACK；不是失败。transport publish 成功不得返回 `accepted`。相同 key/完整 command digest 返回同一 receipt；不同 digest 为 409。

submit-turn 不使用 Conversation `If-Match`：auto title、rename 或其他无关 revision 不应让正常发送消息失败。命令在 `ConversationExecutionGuard` 与 Conversation row lock 内原子检查 actor/state、分配 Message seq/run queue seq 并写 outbox；delete 与 submit 的先后由锁顺序决定。

retry 只允许 `dead_letter -> pending`，复用原 event/run/message/queue seq 并重验当前 actor/agent policy。abandon 只允许 pending/dead-letter；Coordinator 在 Guard 内同时确认 outbox 未被 consumer claim、execution inbox 无 receipt 且预分配 run id 不存在，才原子停用 outbox 并写 `abandoned`。发现 Run/receipt 时必须 reconcile 为 accepted，不能删除证据。

本 API 是新 Agent Workspace 的产品命令，生产 route 在 REQ-043 至少一个通过 conformance 的 `AgentTurnLoopRuntime` profile 启用前保持关闭。旧 `/ai/chat/evidence` 的 CompatibilityRunAdapter 只能记录旧入口，不得消费本 submit-turn。

### 8.3 Run API

| Method | Path | 语义 |
|--------|------|------|
| GET | `/agent-runs/{run_id}` | 独立终态、usage、ledger bounds、pending input/approval 摘要 |
| GET | `/agent-runs/{run_id}/events` | SSE；exclusive `after_seq` |
| POST | `/agent-runs/{run_id}/cancel` | 幂等 cancel intent，携带 expected revision |
| POST | `/agent-runs/{run_id}/output-projection/retry` | dead-letter 复用原 outbox/event/message id 重排 |
| POST | `/agent-runs/{run_id}/output-projection/reconcile` | 核对 workspace Message/ref/digest 后修正 projection 状态 |
| POST | `/agent-runs/{run_id}/output-projection/suppress` | 永久不可恢复时写 redacted tombstone，需 actor/reason/revision |
| POST | `/agent-runs/{run_id}/steer` | 显式 steer；必须 expected run id/revision/runtime epoch |
| POST | `/agent-runs/{run_id}/input-requests/{id}/responses` | HumanInput response，不复用 Approval endpoint |
| POST | `/agent-runs/{run_id}/approval-requests/{id}/responses` | option whitelist + revision + epoch；first-answer-wins |

错误码至少稳定覆盖：`not_found`、`forbidden`、`revision_conflict`、`idempotency_conflict`、`invalid_state_transition`、`dispatch_already_accepted`、`dispatch_reconcile_required`、`projection_reconcile_required`、`projection_suppress_reason_required`、`conversation_has_pending_turn`、`conversation_has_non_terminal_run`、`event_history_expired`、`event_gap_detected`、`event_cursor_ahead`、`runtime_epoch_mismatch`、`approval_conflict`、`outcome_unknown_requires_reconcile`。

## 9. SSE 与重放契约

```text
GET /api/v1/agent-runs/{run_id}/events?after_seq=N
Accept: text/event-stream
Authorization: Bearer ...
```

- `after_seq` 是 exclusive；第一条事件必须 `seq > after_seq`。
- SSE frame：`id: <seq>`、`event: <event_type>`、`data: <versioned public DTO>`。
- `Last-Event-ID` 可替代 query；两者同时存在且值不同返回 400，禁止猜测。
- heartbeat 是 SSE comment，不分配 RunEvent seq。
- replay 和 live tail 之间必须在同一 ledger boundary 切换，不能先查后订阅造成窗口丢事件。
- 客户端按 `(run_id, seq)` 去重；相同 seq、同 audience 不同 delivery digest 立即停止并报完整性错误。
- V1 不按 visibility 静默过滤 canonical seq。actor 无权查看的事件必须返回同一 seq 的通用 `event.redacted` public envelope，只包含 run/seq/schema、`reason=not_authorized` 和该 audience 的 delivery digest，不暴露原 event type/classification/payload digest；因此 `public 1 / restricted 2 / public 3` 对 owner 仍是连续 1/2/3。
- `after_seq < first_available_event_seq - 1` 返回 410，包含 first available seq、Run terminal status 和 `event_log_complete=false`；不得静默从中间继续。
- `after_seq > last_event_seq` 返回 409 `event_cursor_ahead`；不得长连接等待一个服务端从未签发的 cursor。
- 数据库发现内部 seq gap 返回 409/告警；外部 UI 不把 gap 当正常裁剪。
- 鉴权在连接时校验，并在 heartbeat/批次边界重新检查短期 access decision；权限撤销后关闭流。
- 浏览器使用支持 Authorization header 的 fetch stream；禁止把 JWT 放入 SSE URL。
- Run 进入终态且已发送至 `last_event_seq` 后流可正常结束；浏览器仍以 GET Run 为终态事实。

## 10. 权限与可见性

V1 默认 private Conversation：

- owner 可读写自己的 Conversation/Message，并提交/取消其 Run。
- tenant/actor 两个条件都必须命中；只匹配 tenant 不足以授权正文。
- `super_admin` 默认只看平台运行元数据，不自动获得 Message、Artifact 或 Evidence 正文。
- 合规/数据管理员读取正文需要显式 permission + purpose，不通过角色名隐式放权。
- RunEvent 每条有 visibility；public 事件供 Workspace，internal/restricted 正文只给授权运营/审计入口，其他 actor 只收到保持 seq 的 `event.redacted` envelope。
- SSE、Artifact download、Evidence detail 和 Approval response 每次独立鉴权，不能因用户能看 Conversation 就默认能执行审批。

未来共享 Conversation 通过独立 membership/ACL Requirement 增加，不在 V1 用 `visibility=tenant` 快速放大权限面。

## 11. 删除、保留与法律 hold

### 11.1 默认策略

| 对象 | 用户删除时 | 默认保留 |
|------|------------|----------|
| Conversation | 立即软删除并隐藏 | 30 天可恢复，然后进入 purge |
| Message/Part | delete 期间隐藏 | purge 时正文 redaction，保留最小 id/seq/digest tombstone |
| AgentRun | 不 cascade | 终态/审计摘要默认 365 天 |
| RunEvent payload | 不随 Conversation 立即删 envelope | 热重放 90 天；受 policy 的正文 ref 可提前 purge |
| Approval/ToolCall | 不 cascade | 决策、参数/结果 digest 和 actor 审计默认 365 天 |
| Artifact/Evidence | 不 cascade | 服从业务、tenant、legal hold 与 purpose policy |

### 11.2 删除协调

- Conversation 有未 ACK turn 或任意非终态 Run 时 DELETE 返回 409；不在删除事务中隐式 cancel 外部副作用。检查与状态变化服从 `ConversationExecutionGuard`，Execution 端口不可用时 fail closed 返回 503。
- `ConversationExecutionCoordinator` 驱动 durable purge saga，不由一次 worker 调用跨 context DELETE：进入 `running` 时固化必须响应的 workspace/execution/business owner 集合和 purge revision。每个 owner 在首次可能写正文的同一事务预创建 `ErasureFence(tenant_id, conversation_id, owner_key, purge_revision, hold_revision, state=active, ingress_watermark)`；purge 遇到尚无正文的 owner 也必须在 owner-scoped transaction lock 下创建 fence，禁止以“查不到 row”代表允许写。
- 每个 Runtime/business/inbox/outbox/external-object 正文 writer 与 purge/hold 操作都先获取同一个稳定 `(tenant_id, conversation_id, owner_key)` advisory transaction lock，再 `SELECT ... FOR UPDATE` fence row；fence revision/state 校验与正文写入或 cleanup 必须同一事务。purge 在该锁内执行 `active -> erasing`、清理、推进 ingress watermark 和 ACK；已持锁 writer 要么先 commit 后被 purge 清理，要么在 fence revision/state 变化后失败，不能做独立 preflight read。
- execution owner 的 purge ACK 前必须把未投影 output 转 `suppressed`、撤销对应 publish outbox、清除 `terminal_output_ref`/外置正文并保留最小 digest tombstone；已 published output 也要清除 execution 副本。business owner 按自身 policy 清除 Artifact/Evidence 正文或返回 legal-hold blocked。
- fence 生效后，Runtime ingest、inbox/outbox consumer、Artifact/Evidence 和外置对象写入都必须在上述 owner lock/fence transaction 中裁决：旧事件只能拒绝或消费为无正文 tombstone并推进安全水位，不得重建正文。未实现 transaction fence 的 owner 不得 ACK。
- legal hold、未解决 Approval、`outcome_unknown` 或业务保留要求会延后 `purge_after`，并记录不可敏感化的 hold reason code。legal hold 与 purge 通过同一 `hold_revision/purge_revision` CAS 排序：hold 先成功则 purge blocked；purge completed 后新增 hold 不能恢复已清除正文。
- Message redaction 清除 title、text、display name 和外部正文 ref；保留 digest、classification、seq、actor pseudonymous audit ref。
- Artifact/Evidence 若因法定删除需清除，由其所有者执行并回写 tombstone；Conversation cascade 不拥有该动作。
- purge 失败可按同一 revision/owner 幂等重试；部分完成进入 blocked/failed 并保留 ACK 进度。只有固定 owner 集合全部 ACK、各 ingress watermark 已被 fence 接管且 workspace 最后一次正文扫描为零，才设置 `purge_state=completed/purged_at`。
- Run 已终态但 assistant publish 尚在途时允许软删除；purge 前到达时 Message 保持隐藏且不更新 `last_activity_at`。projection、delete、purge 使用同一 Guard；`purge_state=running|completed` 时 consumer 禁止读取 terminal output ref，只能以预分配 message id 写 redacted tombstone并把 Run projection 置 `suppressed`，正文不得在 purge 后复活。

## 12. 索引与并发基线

最低索引/约束：

```text
agent_conversations:
  (tenant_id, created_by, state, last_activity_at DESC, id)
  (tenant_id, deleted_at) WHERE state='deleted'

agent_conversation_user_state:
  UNIQUE (tenant_id, conversation_id, user_id)
  (tenant_id, user_id, pinned_at DESC)

agent_messages:
  UNIQUE (tenant_id, conversation_id, seq)
  UNIQUE (tenant_id, conversation_id, requested_run_queue_seq) WHERE requested_run_queue_seq IS NOT NULL
  UNIQUE user client_message_id partial index
  UNIQUE assistant origin_run_id/output_ordinal partial index
  (tenant_id, conversation_id, seq DESC)

agent_runs:
  UNIQUE (tenant_id, conversation_id, queue_seq)
  (tenant_id, conversation_id, status, queued_at, id)
  partial UNIQUE active execution lease
  (tenant_id, status, updated_at) for recovery

agent_run_events:
  UNIQUE (tenant_id, run_id, seq)
  UNIQUE (runtime_binding_id, runtime_epoch, runtime_seq) WHERE runtime seq IS NOT NULL
  (tenant_id, run_id, seq)

runtime_session_bindings:
  UNIQUE active stream per (tenant_id, id, current_epoch)
  (tenant_id, status, updated_at) for recovery

inbox/outbox:
  UNIQUE inbox consumer/event
  (status, next_attempt_at, created_at)
```

Message seq 通过锁 Conversation row 分配；RunEvent seq 通过锁 AgentRun row 分配。禁止用 `SELECT max(seq)+1` 无锁写入。

## 13. 故障语义

| 故障点 | 必须结果 |
|--------|----------|
| Message commit 后 API 进程退出 | outbox 后台创建同一个预分配 Run |
| turn.requested 重投 | execution inbox 去重，不生成第二个 Run |
| inbox receipt claim 后、领域写前退出 | 同一事务整体回滚；重投继续处理，不会因“见过 event id”而跳过 |
| delete 与 turn dispatch/queued start 并发 | ConversationExecutionGuard 串行化；有 pending/non-terminal 即 409，删除后 Run 不启动 |
| Run terminal commit 后进程退出 | terminal state/event 已 durable，assistant publish outbox 后台继续 |
| assistant publish 重投 | workspace unique origin key 返回同一 Message |
| outbox 达到重试上限 | projection 状态进入 dead_letter、告警且保留原 id；运维重放后幂等恢复，禁止冒充 dispatched/published |
| runtime seq 5 先于 4 到达 | 不落 5、不推进 ACK；返回 next_expected=4，Worker 保留 spool 顺序重发 |
| SSE 断线 | after_seq 重放，无重复、无静默 gap |
| owner 重放混合 visibility 事件 | 无权事件返回同 seq 的 event.redacted；delivery seq 连续且不泄露原 type/payload digest |
| event payload 外置失败 | 不提交引用事件；Run 保持非终态或稳定失败 |
| Runtime terminal frame 重复/冲突 | 相同 digest 幂等；冲突 fail closed，不覆盖 canonical 终态 |
| active Run cancel 遇到 executing write | 保持 cancelling/resume_required，先 reconcile |
| Conversation purge 遇到 legal hold | 保持 deleted 非 purged，记录 hold code 并重排计划 |

## 14. 验收标准

### 14.1 REQ-041

- C-AC1：Conversation/Message/UserState/Part 字段、唯一约束、cursor 和 actor/tenant policy 有契约测试。
- C-AC2：submit-turn 同 key 同完整 command digest 返回同 Message/Run/queue seq，不同 digest 409。
- C-AC3：Message commit 后任意崩溃点不会永久丢失 Run dispatch。
- C-AC4：重新认证后可通过 rename/pin/archive/restore/delete/search/history API 恢复产品会话，具备稳定 CAS、keyset 和错误语义；页面恢复归 REQ-042。
- C-AC5：30 天恢复、durable purge ACK、redaction、legal hold、pending/queued/projection 并发和跨 context 非 cascade 有故障测试，purged 后正文不能复活。
- C-AC6：assistant output 重投只生成一个 Message，且 digest 与 Run terminal output 一致。
- C-AC7：不保存原始 CoT，Message 不包含 Tool/Approval/Artifact/Evidence 正文。

### 14.2 REQ-047 Core

- R-AC1：Run 状态机、FIFO queue/projection barrier、one-active lease 和所有终态 guard 以表驱动测试覆盖。
- R-AC2：RunEvent canonical/runtime 两套 seq 的唯一性、锁分配、连续前缀 ACK、越序 gap 和重投通过并发测试。
- R-AC3：SSE replay/live handoff、Last-Event-ID、gap、410 retention、混合 visibility redacted envelope 和 terminal query 通过集成测试。
- R-AC4：terminal result、Run CAS、canonical terminal event 和 assistant outbox 同事务。
- R-AC5：cancel/timeout、Approval/Input、executing/reconciling Tool 和 outcome_unknown guard 与 REQ-059 一致。
- R-AC6：跨 tenant、越权 actor、权限中途撤销、restricted payload 和 URL token 均被拒绝。
- R-AC7：Run/Event retention 与 Conversation purge 独立，不产生 ORM cascade 或孤儿敏感 payload。
- R-AC8：ConversationExecutionCoordinator/Guard 下 submit/dispatch/start/projection/delete/purge 的竞争测试证明 FIFO、删除后不启动、purge 后不复活，且锁顺序无死锁回退。
- R-AC9：output projection dead-letter 可 retry/reconcile/suppress；永久坏 ref 通过 tombstone 释放 FIFO，不伪造正常回答。
- R-AC10：每个 owner 的 ErasureFence/ingress watermark 阻止 Runtime/business 迟到正文写；hold/purge CAS 与真实 PostgreSQL dispatcher 锁序测试通过。

## 15. 冻结决策

| ID | 决策 | V1 冻结值 |
|----|------|-----------|
| CR-1 | Context ownership | workspace 拥有 Conversation/Message；execution 拥有 Run/Event，禁止共享 ORM/repository |
| CR-2 | Cross-context consistency | opaque UUID + transactional outbox/inbox；inbox receipt/领域写/consumed 同事务；不做跨 context FK/cascade/双写假设 |
| CR-3 | Submit input | 单一 submit-turn 产品命令；Message 与 outbox 同事务；run id 预分配 |
| CR-4 | Assistant output | canonical Run terminal 后通过 outbox 投影 Message；origin key 幂等；projection 是后续 FIFO barrier 与 purge participant |
| CR-5 | Ordering | Message seq/Run queue seq 与 RunEvent seq 由聚合行锁分配；Run 严格 FIFO + predecessor projection barrier；不依赖 UUID/时间排序 |
| CR-6 | Run serialization | 每 Conversation 最多一个 active execution lease；queued 可多个但不得插队；resume_required 持有 lease |
| CR-7 | Pin semantics | user-scoped ConversationUserState，不放 Conversation 全局字段 |
| CR-8 | Pagination | Conversation keyset snapshot；Message before/after seq；禁止新路径 offset |
| CR-9 | SSE | MetaEduBase Authorization fetch stream，after_seq exclusive，无权事件同 seq redacted，gap/retention 显式失败，Run GET 是终态事实 |
| CR-10 | Delete | 30 天软删除恢复；pending turn/任意非终态 Run 409；purge 需 owner durable ACK，完成/投影竞态不得复活正文 |
| CR-11 | Content | Message text/Resource refs；Tool/Approval/Artifact/Evidence 和 CoT 不进入 Message JSON |
| CR-12 | Access | owner-private 默认；super_admin 无正文默认权；共享 Conversation 后续独立设计 |
| CR-13 | Cross-context concurrency | composition Coordinator + Guard 串行化 submit/dispatch/start/projection/delete/purge；两个 context 只暴露 Port；跨库前替换为 durable coordinator lease |
| CR-14 | Runtime ACK | Binding/epoch 单活动流，只 ACK 同事务提交的最高连续 runtime seq；gap 不 buffer、不越序 ACK |
| CR-15 | Compatibility gate | Direct RAG/Skill adapter 只记录旧入口；新 Workspace submit 在 AgentTurnLoopRuntime profile conformance 通过前关闭 |
| CR-16 | Erasure fence | 每个 owner 首次正文写前建 fence；writer/purge 共用 owner transaction lock，fence 校验与写/清除同事务；outbox claim 不持锁进入 Guard |

改变 CR-1/2/4/5/6/9/10/13/14/15/16 属于破坏性架构变更，必须回到 REQ-041/047 联合评审。

## 16. 明确后置

- Conversation membership、团队共享和委托访问。
- 完整 fork/branch UI；V1 只保留 lineage 字段。
- Redis/Kafka fanout、数据库分区和冷归档实现；由压测/容量指标触发。
- 长期记忆与自动抽取，归 REQ-061。
- Pi/ACP/LangGraph Runtime 实现，归 REQ-043。
- 三栏 Workspace UI，归 REQ-042。
- 业务 Artifact/Evidence 的领域 schema，归对应 Agent App。
