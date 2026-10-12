# REQ-042 WS-S2 phase-A：公共 Submit Turn API 契约（contract freeze 候选）

> Status: 🟣 Contract Proposal（本 PR 合并后视为 phase-A 契约冻结；评审期发现冲突以本文修订为准，不静默改写）
> Created: 2026-10-12
> Owner Requirement: [REQ-042](../../01-product-planning/05-requirements/REQ-042-agent-workspace-three-pane-experience.md)（整体仍 ⚫ Candidate，本 spec 不代表 REQ-042 进入 Ready / Planned / Done）
> 上级计划：[WS-S2 / WS-S3 contract-shaping 计划](../02-plans/2026-09-09-req-042-ws-s2-ws-s3-contract-shaping.md) §WS-S2 phase-A
> 依赖契约：[REQ-041/047 联合核心契约](2026-07-24-req-041-047-conversation-run-contract.md)（Durable Core，🟢 Done）
> 明确排除：REQ-043 Runtime conformance / Tool Gateway spec、REQ-047 Extended 三组 spec、WS-S2 phase-B/C/D/E、WS-S3 全部

## 0. 本 spec 的边界声明

- 本 spec 只冻结**公共 submit API 契约**（WS-S2 phase-A）。它描述的是「契约是什么」，**不声称端点已实现**：截至本 spec 撰写，`agent_workspace` 公共 router 无任何 `/turns` 端点，`submit_turn()` 仅为 internal application contract（`agent_workspace/application/bridge.py` + `composition/agent_control_plane.py`）。
- 本 spec **不定义、不重新定义** REQ-047 Extended 三组持久化契约（HumanInput/Approval、ToolCall/ToolGrant/Snapshot、Artifact/Evidence）；所有相关字段只作为后续依赖引用。
- 本 spec 不裁定 WS-S2 计划内 phase-B 前置依赖表述冲突（phase 表要求 REQ-047 Extended 三组 spec 冻结、推荐顺序叙述称 Extended 不阻塞 phase-B）；该冲突在 phase-B 开工前另行裁决。
- WS-S2 不变禁止项在本 spec 层面同样成立：不接 `AgentTurnLoopRuntime`、不接 SSE / EventSource、不实现 cancel / stop / steer、不做 frontend wire-up（均属后续 phase / WS-S3）。

## 1. 端点契约

| 项 | 冻结值 |
|----|--------|
| Method / Path | `POST /api/v1/agent-workspace/conversations/{conversation_id}/turns` |
| Router 归属 | `agent_workspace` 公共 router（既有前缀 `/api/v1/agent-workspace/conversations`） |
| 鉴权 | 与既有会话端点同一 `get_current_user` 依赖；`tenant_id` / `actor_id` 只能从鉴权上下文派生，**禁止**作为请求字段 |
| 成功响应 | 首次接受 `201 Created`；幂等重放 `200 OK` 且 `idempotent_replay=true` |
| Content-Type | `application/json`；未知顶层字段一律 `422`（严格 schema，fail-closed） |

## 2. 会话状态可提交性矩阵

| Conversation 状态 | 可提交 | 响应 |
|---|---|---|
| `active` | ✅ | 正常接受 |
| `archived` | ❌ | `409 conversation_not_active`（先 restore 再提交） |
| `deleted` | ❌ | `404 conversation_not_found`（删除后不泄露存在性） |

依据：内部 repo 层 `reserve_user_turn` 以 `include_deleted=False` 取行（deleted → not found），且 `state != active` 直接拒绝（`InvalidConversationStateError`，"new turns require an active conversation"）。本 spec 将该内部语义公开化为稳定错误码，不改变行为。

## 3. `SubmitTurnRequest`（前端可提交字段）

| 字段 | 类型 | 必填 | 来源与约束 |
|------|------|------|------------|
| `client_message_id` | UUID | 是 | 客户端生成的幂等键；作用域见 §5 |
| `parts` | array | 是 | ≥1 个消息片段；片段字段对齐内部 `MessagePartInput`（`type` / `text` / `format` / `resource_id` / `media_type` / `display_name` / `classification`） |
| `agent_definition_version_id` | UUID | 是 | 客户端选择的 Agent 定义版本；服务端校验存在性与启用状态（未知 → `422`，未授权/未启用 → `403 capability_denied`） |
| `client_options` | object | 否 | 默认 `{}`；客户端可控选项，体积有界；**不承载执行权威**，语义由对应 Agent 定义版本与 server-selected launch policy（phase-B）解释 |

## 4. Server-selected 字段（禁止前端提交）

以下字段由服务端在 dispatch 前构造（对应内部 `TurnLaunchSpecV1`，其 docstring 原文为 "Server-selected immutable execution inputs"），**前端提交任一字段即 `422`**：

`tenant_id`、`actor_id`（鉴权派生）、`runtime_profile_id`、`runtime_binding_id`、`runtime_capability_snapshot`、`run_config_snapshot`、`context_snapshot_ref` / `context_snapshot_digest` / `context_snapshot_classification`、`budget_snapshot`、`parent_run_id`、`message seq`、`run_queue_seq`。

- launch policy 的字段选择与 capability gate 输入由 **WS-S2 phase-B** 冻结，本 spec 只冻结「这些字段不可由客户端提供」与 fail-closed 语义。
- 服务端构造的 launch 必须与请求中的 `agent_definition_version_id` 一致（内部 bridge 既有一致性校验）；不一致视为服务端缺陷，不得静默改写客户端选择。

## 5. 幂等重放语义

- 幂等键：`(tenant_id, actor_id, conversation_id, client_message_id)`，仅适用于 `user_input` 类消息（与内部实现一致）。
- 同键 + 同 `turn_request_digest`：返回原 receipt，`200 OK` + `idempotent_replay=true`，不产生新 Message / Run / outbox 事件。
- 同键 + 不同 digest：`409 idempotency_conflict`。
- digest 组成（沿用联合核心契约冻结定义）：tenant、actor、conversation、规范化 parts/resource refs、agent definition version、客户端可控选项；服务端生成的 run/message id 不参与首次请求摘要。
- 客户端可在任意 5xx / 网络失败后以同键安全重试。

## 6. Revision 边界（与既有冻结契约的一致性）

- 联合核心契约已冻结：**submit-turn 不接受 Conversation `If-Match` / expected revision**（auto title、rename 等无关 revision 推进不应让正常发送失败）。本 spec 继承该裁决，**不引入** submit 路径的 expected revision。
- `409 revision_conflict` 保留给会话元数据 CAS 端点（rename / pin / archive / restore / delete），**不属于** turn 提交的错误命名空间。
- turn 提交的 `409` 命名空间仅含：`idempotency_conflict`、`conversation_not_active`。

## 7. `SubmitTurnResponse` / receipt（公共字段）

| 字段 | 类型 | 说明 |
|------|------|------|
| `message_id` | UUID | durable 用户消息 ID（同事务落库） |
| `message_seq` | int | 会话内消息序号 |
| `run_id` | UUID | 本 turn 预留的 Run 稳定标识（`requested_run_id`） |
| `run_queue_seq` | int | Run 排队序号（同会话串行） |
| `dispatch_state` | string | 提交时刻观测值；首次接受恒为 `pending`（含义见 §8），重放返回当前持久值 |
| `idempotent_replay` | bool | 是否幂等重放 |
| `correlation_id` | UUID | 追踪关联 ID |
| `created_at` | datetime | 消息落库时间 |

不暴露：内部 outbox `event_id`（dispatch 内部标识）、`turn_request_digest`、任何 server-selected launch 字段。

## 8. Durable 边界与 dispatch receipt

- 单事务边界：Conversation 行锁 + `ConversationExecutionGuard` 内完成状态检查、erasure fence 检查、Message(+parts) 落库（分配 `seq` / `requested_run_id` / `run_queue_seq`）、outbox `TurnRequestedV1` 写入；**响应只在 durable commit 之后返回**。
- `pending` 语义（沿用联合核心契约冻结定义）：workspace 事务已 durable、execution consumer 尚未 commit/ACK；`pending` **不是失败**，也不等于 `accepted`。
- Run 实体化边界：Run 行由 execution 侧消费 outbox 后创建（既有 B1 bridge，非本 spec 改动面）。因此公共契约为：
  - 提交事实源 = 会话消息查询端点（`GET /api/v1/agent-workspace/conversations/{id}/messages`，同事务 durable，立即可查）；
  - Run 状态查询 = `GET /api/v1/agent-runs/{run_id}`（既有 execution 端点）；execution 消费完成前对该 `run_id` 可返回 `404`，客户端必须容忍并以上一句为提交事实依据；
  - 上述轮询语义由 phase-C 的真实 PG contract tests 固化；SSE 推送不属于 WS-S2（归 WS-S3）。

## 9. Capability gate（fail-closed）

- 服务端在 dispatch 前按 tenant、actor、agent definition、目标能力做门控；**评估失败一律拒绝**（fail-closed），不降级放行。
- 未授权 / 未启用：`403 capability_denied`。
- gate 输入字段（profile 选择、capability 字段、最小 execution profile）由 phase-B 冻结；本 spec 只冻结语义与错误码。

## 10. 错误码表

| 状态码 | 稳定 code | 触发条件 |
|--------|-----------|----------|
| 401 | `unauthenticated` | 无有效会话 |
| 403 | `capability_denied` | capability gate 拒绝（含评估失败 fail-closed） |
| 403 | `resource_access_denied` | `parts` 引用的 resource 未通过服务端访问校验 |
| 404 | `conversation_not_found` | 不存在 / 非 owner / 已删除（反枚举，三者不区分） |
| 409 | `idempotency_conflict` | 同幂等键不同 digest |
| 409 | `conversation_not_active` | 会话为 archived |
| 422 | `validation_error` | schema 校验失败：未知顶层字段、server-selected 字段提交、parts 为空、未知 `agent_definition_version_id` 等 |
| 429 | `rate_limited` | per-actor / per-tenant 提交限流；响应携带 `Retry-After`。当前代码库无既有 429 中间件，实装归 phase-C，本 spec 冻结语义 |
| 500 | `internal_error` | 未预期失败；客户端可凭幂等键安全重试 |

错误响应体沿用仓库既有 error 形状约定；code 字段为上表稳定字符串，客户端只依赖 code 不依赖 message 文本。

## 11. 四层边界对照（防混淆冻结表）

| 层 | 内容 | 本 spec 关系 |
|----|------|--------------|
| 前端可提交字段 | §3 四字段 | 本 spec 冻结 |
| Server-selected 字段 | §4 清单 | 本 spec 冻结「不可客户端提交」；取值 policy 归 phase-B |
| 内部 `submit_turn()` application contract | `TurnCommand` / `TurnLaunchSpecV1` / `SubmitTurnReceipt`（`agent_workspace/application/dto.py`、`bridge.py`、`shared/schemas/agent_integration.py`） | 本 spec 的**事实依据**，不是公共 API；公共契约不 1:1 暴露内部 DTO |
| 公共 API contract | 本文件 | 唯一公共事实源；phase-C 实装必须与本文件一致 |

## 12. 依赖与后续（只引用，不 redefine）

- 输入：REQ-041 W1 + B1、REQ-047 Durable Core（均已 🟢 Done）；内部 `submit_turn()` 已有 application contract。
- 下游：phase-B（server-selected launch policy + 最小 execution profile，需 REQ-043 Spec 冻结情况按 WS-S2 计划另行裁决）、phase-C（backend route + 真实 PG contract tests）、phase-D/E。
- REQ-043 Runtime conformance / Tool Gateway、REQ-047 Extended 三组 spec：后续依赖，本 spec 不定义其任何字段或 schema。

## 13. 验证

本 PR 为 pure-docs 契约冻结，无业务代码 / 测试 / migration / CI 变更。验证以门禁与人工比对为准：`git diff --check`、 `scripts/check-engineering-docs --full`、相对链接存在性、与 WS-S2 计划 phase-A 行一致性人工核验。不声称端点已实现或 submit loop 可运行。
