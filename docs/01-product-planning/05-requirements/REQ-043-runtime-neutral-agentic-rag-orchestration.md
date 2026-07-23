# REQ-043: Runtime 中立的 Agentic RAG 与工具编排

> Status: ⚫ Candidate
> Priority: P0
> Milestone: P3 / Enterprise Agent Platform
> Area: Agent Runtime / Agentic RAG / Tool Gateway / ACP
> Created: 2026-07-23（重塑既有 Backlog 候选）
> Parent: REQ-059
> Related: REQ-041 / REQ-042 / REQ-044 / REQ-045 / REQ-047 / REQ-061 / TD-085
> Architecture Spec: [REQ-059 源码研究与控制面契约](../../02-delivery-plans/01-specs/2026-07-23-req-059-enterprise-agent-platform-control-plane.md)

## Problem

现有 AI Chat 内置一次 `query_internal_data` Tool Calling，SkillRunner 负责固定 SOP，尚无可替换 Runtime、统一工具授权、自主规划、证据评估、多轮重试、取消和恢复。直接把 Pi SDK 或 ACP 接入页面会制造第二套会话、权限和事件事实源；把所有请求升级成 Agent 又会放大延时和成本。

## Scope

### Runtime-neutral Control

- 定义 `AgentRuntimePort`：initialize、create/resume session、start run（事件流 + 独立 terminal result）、status/config、approval response、cancel、close/discard。
- Runtime 事件映射为 REQ-047 `RunEvent`；事件流与独立终态结果分离。
- 每 Session 串行 actor queue；Runtime Binding 持久化后才能缓存 handle。
- 支持 Native Direct RAG、SkillRunner、Pi Worker 和 ACP Adapter 四类实现。
- `resume_session` 失败必须返回稳定错误；禁止模仿 NuwaClaw 当前产品适配层静默 fallback 到 new session。

### Tool Gateway

- Agent 只获得一次 Run 的短期 Tool Grant，不持有真实 MCP 凭证、数据库连接或服务 Token。
- Tool Gateway 按 tenant、actor、agent、run、tool、参数和风险级别校验后，路由到 RAG、MCPInvocationService、SkillRunner、QueryService 或业务 API。
- 工具调用、结果摘要、耗时、预算和错误统一审计；敏感 Payload 按策略裁剪或外置。
- 高风险写操作必须经过确定性策略和持久化 Approval，不由 Prompt 自行放行。

### Agentic RAG Loop

- 复杂度路由：Direct RAG、固定 Skill、动态 Agent 三档。
- Agent 可制定计划、调用工具、检查证据覆盖与矛盾、有限重试并生成结构化产物。
- 每次 Run 配置最大步骤、墙钟时间、Token、成本、工具调用数和重试数。
- 证据不足时显式降级、追问或交给人工，不循环到预算耗尽。
- 采用 Pi 式统一 Agent Loop；计划保存为 `plan.summary`/Artifact，工具执行经 Tool Gateway，评估拆为 `EvidencePolicy / BudgetPolicy / StopPolicy`，不建立 Planner/Executor/Evaluator 三个平行会话状态机。

### Integration Spikes

- Pi：优先固定 npm 版本的 Node Worker/Sidecar，通过 Adapter 接入；评估通用 AgentHarness + 自定义 SessionStorage，不 fork 全仓。
- ACP：实现外部 Runtime Adapter，验证 initialize、new/load/resume、prompt/steer、cancel、permission 和 session update。
- OpenClaw：只作为控制面和持久化设计参考，不作为共享多租户后端整体嵌入。
- Open Design：借鉴 `RuntimeAgentDef`、Generic Engine、Run-scoped Tool Token 和 Conversation/Runtime Session 分离；禁用自动审批、自动 confirm 和 allow-all-tools 默认值。
- Codex：借鉴 Thread/Turn/Item、ToolRouter/Registry、Session/TurnContext、Rollout 和 Permission/Sandbox 分层，不假定桌面产品未公开实现。

## Acceptance

- AC-1：同一 Conversation 可切换兼容 Runtime，产品消息、Run、Artifact 和审批事实源不变。
- AC-2：Direct RAG 保持低延时快路径；只有复杂请求进入多步 Agent。
- AC-3：Runtime 不能绕过 Tool Gateway 直接使用租户凭证；跨租户 Tool Grant 必须失败。
- AC-4：运行支持取消、超时、预算终止、断线重放和进程重启后的显式恢复/失败状态。
- AC-5：审批 durable、first-answer-wins、带 revision/runtime epoch、过期时间和 reviewer scope。
- AC-6：Pi Spike 跑通一个只读 RAG + MCP/Skill 工具场景，并证明 Pi Session 不是企业鉴权事实源。
- AC-7：ACP Spike 跑通 session new/resume、事件映射、cancel 和 permission round-trip；load 失败不得静默创建新会话。
- AC-8：沙箱不可用时 fail closed；网络默认拒绝并按目标 allowlist 放行。
- AC-9：建立质量、任务成功率、工具失败率、人工介入率、P50/P95 延时、Token 和成本评测基线。
- AC-10：Pi/ACP Worker 与 Backend API 进程隔离；Runtime 只持有 Run-scoped Tool Grant，不能获得租户长期 MCP secret、数据库连接或业务 Token。

## Non-goals

- 不用 LangChain/LangGraph/Pi/OpenClaw/Nuwax 任一框架替代 MetaEduBase 企业控制面。
- 不把全部聊天强制改为 Agentic 多轮检索。
- 不整体 fork 外部项目或复用其页面作为产品入口。
- 不展示或持久化原始 Chain-of-Thought。
- 不在本需求实现长期记忆抽取和治理，归 REQ-061。

## Dependencies / Next Step

- 依赖 REQ-041 与 REQ-047 的持久化契约。
- 开工前先完成 TD-085 中会阻塞 Runtime 接线的依赖倒置切片，但不要求一次性重写现有 RAG/Skill。
- 先产出 Runtime Port + RunEvent + Tool Grant contract-first spec，再选择 Pi/ACP Spike 传输协议。
