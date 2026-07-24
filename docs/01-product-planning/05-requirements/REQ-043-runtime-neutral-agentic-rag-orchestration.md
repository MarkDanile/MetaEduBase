# REQ-043: Runtime 中立的 Agentic RAG 与工具编排

> Status: ⚫ Candidate
> Priority: P0
> Milestone: P3 / Enterprise Agent Platform
> Area: Agent Runtime / Agentic RAG / Tool Gateway / ACP
> Target Context: `agent_execution`（代码与迁移落地后再同步 `ARCHITECTURE.md`）
> Created: 2026-07-23（重塑既有 Backlog 候选）
> Parent: REQ-059
> Related: REQ-041 / REQ-042 / REQ-044 / REQ-045 / REQ-047 / REQ-061 / TD-085
> Architecture Spec: [REQ-059 源码研究与控制面契约](../../02-delivery-plans/01-specs/2026-07-23-req-059-enterprise-agent-platform-control-plane.md)

## Problem

现有 AI Chat 内置一次 `query_internal_data` Tool Calling，SkillRunner 负责固定 SOP，尚无可替换 Runtime、统一工具授权、自主规划、证据评估、多轮重试、取消和恢复。直接把 Pi SDK 或 ACP 接入页面会制造第二套会话、权限和事件事实源。新 Agent Workspace 需要统一 Turn Loop 体验，同时保留旧 AI Chat 和确定性 Workflow 的兼容边界。

## Scope

### Runtime-neutral Control

- 定义 `AgentTurnLoopRuntime`：initialize、create/resume session、start turn（事件流 + 独立 terminal result）、event ACK、input/approval response、steer、cancel、close/discard。
- 建立 `AgentDefinitionVersion / RuntimeProfile / RuntimeSessionBinding`；Pi 是 V1 默认 RuntimeProfile，切换 Runtime 创建新 Binding，不迁移私有 checkpoint。
- 新 Agent Workspace 输入全部进入 `AgentTurnLoopRuntime`；零 ToolCall 最终回答是正常终止。旧 `/ai/chat/evidence` 与确定性 Workflow 使用 compatibility adapter，不定义新 Workspace 的旁路。
- V1 Control Plane -> Worker 使用内部 HTTP/JSON command API + SSE event stream；终态独立查询，浏览器只连接 MetaEduBase API/SSE。command 必须携带 tenant/conversation/run/runtime epoch/idempotency key，SSE 支持 `after_seq` 恢复。
- Runtime 事件映射为 REQ-047 `RunEvent`；事件流与独立终态结果分离。
- Worker 事件先写本地 SQLite spool，按 `runtime_seq` 发送；Control Plane 幂等落 PostgreSQL 后 ACK，PostgreSQL 仍是唯一企业事实源。
- 每 Session 串行 actor queue；Runtime Binding 持久化后才能缓存 handle。
- V1 实现 Pi Worker；后续 ACP、LangGraph 和自研 Adapter 使用同一 Runtime conformance suite。
- `resume_session` 失败必须返回稳定错误；禁止模仿 NuwaClaw 当前产品适配层静默 fallback 到 new session。
- L0/L1 只读任务在文件、网络和资源预算受限时可共享 Worker；写操作、敏感租户、不可信 ACP、自定义文件/网络能力必须进入独立 Runtime Cell，隔离能力不可用时 fail closed。

### Tool Gateway

- Agent 只获得一次 Run 的短期 Tool Grant，不持有真实 MCP 凭证、数据库连接或服务 Token。
- ToolGrant 使用至少 256-bit 熵的 opaque token，服务端只存摘要；默认 TTL 5 分钟、最大 15 分钟，写操作单次使用，并在 Run 终态/取消、runtime epoch 或审批变化、策略失效和预算耗尽时撤销。
- Tool Gateway 按 tenant、actor、agent、run、tool、参数和风险级别校验后，路由到 RAG、MCPInvocationService、SkillRunner、QueryService 或业务 API。
- 工具调用、结果摘要、耗时、预算和错误统一审计；敏感 Payload 按策略裁剪或外置。
- 写工具采用 `prepare -> approval -> reserve -> execute -> reconcile -> settle -> resume`；无法判定外部结果时进入 `outcome_unknown`，禁止盲重试。
- 预算由控制面 reserve，Gateway 按真实 usage 和 reconcile 结果 settle/release；Worker 自报 usage 只作为观测数据。
- 高风险写操作必须经过确定性策略和持久化 Approval，不由 Prompt 自行放行；无幂等键或可靠对账能力时只能生成 L2 草稿。

### Agentic RAG Loop

- `RuntimeProfileResolver` 按 AgentDefinitionVersion、租户策略和自主等级解析 Runtime/模型/工具，不对用户问题做外部简单/复杂分类。
- Agent 可零工具回答，也可制定计划、调用工具、检查证据覆盖与矛盾、有限重试并生成结构化产物。
- 每次 Run 配置最大步骤、墙钟时间、Token、成本、工具调用数和重试数。
- 证据不足时显式降级、追问或交给人工，不循环到预算耗尽。
- 采用 Pi 式统一 Agent Loop；计划保存为 `plan.summary`/Artifact，工具执行经 Tool Gateway，评估拆为 `EvidencePolicy / BudgetPolicy / StopPolicy`，不建立 Planner/Executor/Evaluator 三个平行会话状态机。

### Integration Spikes

- Pi：优先固定 npm 版本的 Node Worker/Sidecar，通过 Adapter 接入；使用 Extension/Hook、自定义 SessionStorage 和 event spool，不 fork 全仓。
- ACP：实现外部 Runtime Adapter，验证 initialize、new/load/resume、prompt/steer、cancel、permission 和 session update。
- OpenClaw：只作为控制面和持久化设计参考，不作为共享多租户后端整体嵌入。
- Open Design：借鉴 `RuntimeAgentDef`、Generic Engine、Run-scoped Tool Token 和 Conversation/Runtime Session 分离；禁用自动审批、自动 confirm 和 allow-all-tools 默认值。
- Codex：借鉴 Thread/Turn/Item、ToolRouter/Registry、Session/TurnContext、Rollout 和 Permission/Sandbox 分层，不假定桌面产品未公开实现。

## Acceptance

- AC-1：同一 Conversation 可切换 RuntimeProfile，产品消息、Run、Artifact 和审批事实源不变；新 Binding 不迁移私有 checkpoint。
- AC-2：新 Agent Workspace 输入统一进入 Turn Loop；零工具回答和工具调用使用同一运行协议，旧 Direct RAG/Skill compatibility path 仍可独立回归。
- AC-3：Runtime 不能绕过 Tool Gateway 直接使用租户凭证；跨租户 Tool Grant 必须失败。
- AC-4：运行支持取消、超时、预算终止、断线重放和进程重启后的显式恢复/失败状态。
- AC-5：审批 durable、first-answer-wins、带 revision/runtime epoch、过期时间和 reviewer scope。
- AC-6：Pi Spike 跑通一个只读 RAG + MCP/Skill 工具场景，并证明 Pi Session 不是企业鉴权事实源。
- AC-7：ACP Spike 跑通 session new/resume、事件映射、cancel 和 permission round-trip；load 失败不得静默创建新会话。
- AC-8：沙箱不可用时 fail closed；网络默认拒绝并按目标 allowlist 放行。
- AC-9：建立质量、任务成功率、工具失败率、人工介入率、P50/P95 延时、Token 和成本评测基线。
- AC-10：Pi/ACP Worker 与 Backend API 进程隔离；Runtime 只持有 Run-scoped Tool Grant，不能获得租户长期 MCP secret、数据库连接或业务 Token。
- AC-11：HTTP command 重试幂等；SSE 断开不推导 Run 成功，客户端可按 `after_seq` 重放并独立查询终态。
- AC-12：共享 Worker 与独立 Runtime Cell 的路由符合 REQ-059 AG-2；任何沙箱、挂载或网络策略失败均拒绝启动而非降级。
- AC-13：ToolGrant TTL、单次写调用、撤销和 `reserve -> execute -> reconcile -> settle/release` 预算语义具备并发与重放测试。
- AC-14：Worker spool 在 ACK 丢失、重复发送和重启后可重放，且不会产生重复 RunEvent 或重复终态。
- AC-15：写工具在 execute 前后故障均有测试；无法 reconcile 时稳定进入 `outcome_unknown`，不会再次调用 Provider。
- AC-16：`TurnInput` 默认排队为下一 Run，显式 steer 才注入当前 Run；`HumanInputRequest` 与 `ApprovalRequest` 状态和响应端点分离。
- AC-17：cancel/timeout 遇到 executing/reconciling 写 Tool 时不得先落 Run 终态；先 reconcile，无法确认时 ToolCall=`outcome_unknown` 且 Run=`resume_required`。未知结果经 Provider 对账或具名人工裁决为 succeeded/failed 前，Run 不得终结。
- AC-18：`resume_required -> starting` 只能由同一 Binding/epoch 恢复成功触发；新 Binding 必须创建新 Run。
- AC-19：旧 Direct RAG/Skill 通过无状态 `CompatibilityRunAdapter` 写统一 RunEvent/terminal contract，不伪造 Runtime Session，不接收新 Workspace 输入。

## Non-goals

- 不用 LangChain/LangGraph/Pi/OpenClaw/Nuwax 任一框架替代 MetaEduBase 企业控制面。
- 不把旧 AI Chat 或确定性业务 Workflow 强制迁入 Agent Loop；新 Workspace 统一 Turn Loop 不等于每次都检索或调用工具。
- 不整体 fork 外部项目或复用其页面作为产品入口。
- 不展示或持久化原始 Chain-of-Thought。
- 不在本需求实现长期记忆抽取和治理，归 REQ-061。

## Dependencies / Next Step

- 依赖 REQ-041 与 REQ-047 的持久化契约。
- 开工前先完成 TD-085 中会阻塞 Runtime 接线的依赖倒置切片，但不要求一次性重写现有 RAG/Skill。
- 先产出 AgentTurnLoopRuntime + RunEvent + ToolGrant contract-first spec，再按已冻结的 HTTP/JSON command + SSE/ACK 实施 Pi Worker；ACP/LangGraph Adapter 复用相同 Port、终态和事件语义。
