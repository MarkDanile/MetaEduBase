# REQ-059: 企业级可控 Agent 平台内核与 Runtime 中立控制面

> Status: 🟣 Shaping
> Priority: P0
> Milestone: P3 / Enterprise Agent Platform
> Area: Agent Platform / Control Plane / Runtime / Multi-tenant
> Created: 2026-07-23
> Source: 用户关于 Codex 式超级智能体、Pi / ACP 集成和教育/园区企业控制台的连续规划讨论
> Related: REQ-041 / REQ-042 / REQ-043 / REQ-047 / REQ-049 / REQ-060 / REQ-061 / REQ-062 / REQ-063 / TD-085
> Spec: [源码研究与控制面契约](../../02-delivery-plans/01-specs/2026-07-23-req-059-enterprise-agent-platform-control-plane.md)

## Problem

MetaEduBase 已具备 RAG、证据链、MCP Registry、Skill Registry / SkillRunner、智能问数和企业背调应用，但这些能力目前分别由 AI Chat、SkillRunner 和业务 Orchestrator 编排。系统尚无产品无关的 Conversation、AgentRun、RunEvent、Runtime Session Binding、ToolCall、Approval、Artifact 和 Memory 控制面，继续直接接入 Pi、ACP 或其他 Agent 会形成新的平行会话和执行事实源。

目标不是把所有 RAG 请求改成多轮 Agent，也不是把企业背调提升为平台内核，而是建立一个类似 Codex 使用体验、同时满足企业多租户、权限、审计、审批和可恢复要求的 Agent 平台。

## Product Boundary

```text
企业 Agent 控制面（MetaEduBase 拥有事实源）
  - identity / tenant / policy / audit / budget
  - conversation / message / run / event / task
  - approval / artifact / evidence / memory
  - runtime binding / cancellation / recovery

能力提供层
  - knowledge / Direct RAG
  - MCP registry / invocation
  - Skill registry / deterministic SkillRunner
  - structured data / internal query

可插拔 Runtime
  - Native / Direct RAG Runtime
  - MetaEdu Skill Runtime
  - Pi SDK / Worker Runtime
  - ACP External Runtime Adapter

Agent App
  - 企业背调、政策申报、园区运营、教学设计、学习规划等
```

企业 360 背调是第一个产业园区 AI 应用、首个已落地的 Agent App，也是 P3 首个平台化样板；它不是平台基础能力，也不得决定通用实体、事件和权限模型。当前园区应用主线固定为 APP-005 -> APP-009 -> APP-012 -> APP-030 -> APP-016；APP-011 并入 APP-016，APP-022 并入 APP-012。教育应用在园区近期主线后进入复用验证。

## Ownership Decisions

| 对象 | 事实源所有者 | 边界 |
|------|--------------|------|
| Conversation / Message | MetaEduBase | 产品会话；可重命名、置顶、归档、删除、搜索和 fork |
| AgentRun / RunEvent | MetaEduBase | 每次运行、顺序事件、终态、取消和恢复 |
| Runtime Session | 外部 Runtime | 仅通过 `RuntimeSessionBinding` 与产品会话关联，可丢失和重建 |
| Tool / Skill / RAG | MetaEduBase | 通过 Tool Gateway 统一授权、调用和审计 |
| Approval / Artifact / Evidence | MetaEduBase | 独立持久化，不塞入 Message JSON 充当唯一事实源 |
| Long-term Memory | MetaEduBase | tenant/user/agent 作用域、来源、TTL、删除和敏感信息策略 |
| 业务任务与报告 | 对应 Agent App | 引用通用 Run / Artifact；保留业务状态与领域模型 |

## Runtime Port Baseline

Runtime Adapter 至少提供以下能力，具体语言和传输方式在 REQ-043 Spike 冻结：

```text
initialize -> capabilities
create_session / resume_session
start_run -> event stream + independent terminal result
stream_events(after_seq)
get_status / set_mode / set_config_option
respond_approval
cancel_run
close_session(discard_persistent_state)
```

每个 Runtime Session 的可变操作必须串行化；Runtime Binding 先持久化再缓存句柄；事件包含 `tenant_id / conversation_id / run_id / seq`，客户端能够检测缺口并重放。

## Runtime Routing

| 请求类型 | 默认路径 |
|----------|----------|
| FAQ、单轮知识问答 | Direct RAG，保留低延时路径 |
| 固定 SOP、确定性报告 | SkillRunner |
| 跨系统、多步骤、需要动态决策 | Agent Runtime |
| Claude Code、Codex、OpenCode 等外部 Agent | ACP Adapter |
| 高风险写操作 | 确定性 Workflow 或人工审批 |

Agentic RAG 是复杂请求能力档，不替换所有请求的默认路径。GraphRAG 是关系索引与推理增强，不作为平台版本号或全局默认方案。

## External Project Decisions

源码研究基线固定于 2026-07-23；进入 Spike 前必须重新核对上游版本、许可证和破坏性变更：

- [OpenClaw `5e651d5`](https://github.com/openclaw/openclaw/tree/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9)
- [Pi `a5afc3f`](https://github.com/earendil-works/pi/tree/a5afc3f171e422e08a2ccc342827719f9952f38a)
- [Nuwax Web `1278e30`](https://github.com/nuwax-ai/nuwax/tree/1278e30dc42fff2c741185775f7cade5bf01389e)
- [NuwaClaw `77bccef`](https://github.com/nuwax-ai/nuwaclaw/tree/77bccefe701a5a73895dced587fea0636c7216f6)
- [RCoder `2189eaf`](https://github.com/nuwax-ai/rcoder/tree/2189eaffc4d2a6b0bc92b988c859698b0377124b)
- [Claude ACP Adapter `3b72577`](https://github.com/agentclientprotocol/claude-agent-acp/tree/3b725779996a7c8b99b26ef3553abb915423037a)
- [Open Design `506c290`](https://github.com/nexu-io/open-design/tree/506c2900b972e6f3a25cfe5fabd7041ec6d869ca)（`0.16.1`）
- [Codex `39a2438`](https://github.com/openai/codex/tree/39a2438d16514d0d6f88105d17b0f747994af487)

| 项目 | 采用内容 | 不采用内容 |
|------|----------|------------|
| OpenClaw | Runtime Registry、ACP 控制面、Session Actor Queue、事件账本、持久化审批和任务恢复设计 | 不整体嵌入；其单一可信 Operator 域不作为共享多租户后端 |
| Pi | Agent Loop、SDK、树形 Session、steer/follow-up、compaction 和 Hook | 不把 Pi JSONL、页面或进程权限当企业事实源和权限系统 |
| Nuwax / NuwaClaw | ACP Adapter、能力协商、Intervention 映射和产品交互 | 不复制 yolo、沙箱降级关闭、内存审批和单机 Engine 管理默认值 |
| Open Design | Runtime Agent Definition、Generic Engine、Conversation/Runtime Session 分离、Run Event、Tool Token 和 Workspace 产品模式 | 不复制自动审批、自动 confirm、allow-all-tools、内存 Run/Token Registry 和单用户 Memory |
| Codex | Thread/Turn/Item、App Server、ThreadManager、Session/TurnContext、ToolRouter/Registry、Rollout/State DB 和 Permission/Sandbox 分层 | 不猜测未公开桌面服务端；不直接套用本地 Coding Agent 权限模型替代企业租户策略 |

生产优先采用固定版本包和隔离 Runtime Worker；不整体 fork 任一项目。Pi 第一阶段走 Node Worker/Sidecar Spike，ACP 作为外部 Agent 南向协议，前端始终只连接 MetaEduBase API/SSE。源码与专家解读冲突时，以固定 commit 的源码和测试为准；无法回溯数据集与方法的准确率数字不进入验收基线。

## Source-aligned Naming

- 产品 `Conversation / Message / AgentRun / RunEvent` 分别映射 Codex `Thread / Message Item / Turn / Item/Event`，保留面向教育和园区业务的清晰命名。
- 核心应用服务采用 `RunCoordinator / RunRoutingService / AgentRuntimePort / RuntimeRegistry / ToolRouter / ToolGateway / ContextAssembler / RunEventLedger / ApprovalService`。
- `Planner / Executor / Evaluator` 只描述能力，不建立三个平行状态机：计划是 RunEvent/Artifact，工具执行进入 Tool Gateway，评估拆为 Evidence/Budget/Stop Policy，模型循环由 Runtime 负责。
- 新 bounded context 候选名为 `agent_workspace / agent_execution / agent_memory`，不建立含义无边界的通用 `agent` context。

## Delivery Map

| 阶段 | 任务 | 目标 |
|------|------|------|
| 0 | REQ-059 | 冻结 Context Map、Runtime/RunEvent/ToolGrant contract 和评测场景 |
| 1 | REQ-041 / REQ-047 | Conversation/Message 与 AgentRun/Event/Approval/Artifact 持久化；Direct RAG 先接兼容路径 |
| 2 | REQ-042 / REQ-060 | Agent Workspace 与权限化导航信息架构 |
| 2A | REQ-062 contract / REQ-063 source Spike | 在 Run/Artifact 契约上塑形动态采集模型；并行确认外部来源授权、许可、网络和快照策略，不提前实现自由爬虫 |
| 3 | TD-085 | 现有 AI Chat / Skill / DD 边界渐进收口，抽 LLM Port 和 Tool Gateway 接线边界 |
| 4 | REQ-043 / REQ-063 | Runtime Port、Tool Gateway、复杂度路由；Pi 先做 APP-005 只读对照，再以 APP-009 验证受治理外部数据与多方案选址；最后做 ACP/沙箱硬化 |
| 5 | REQ-062 implementation | 建立 APP-012/030 共用的 Campaign、FormSchemaVersion、Submission 和 ReportSnapshot；ReportSnapshot 引用 AgentRun/Artifact，不在应用内重复实现动态表单或运行状态机 |
| 6 | REQ-061 / REQ-049 | 记忆治理、长期任务、周期采集、催办和主动触发 |

## Acceptance For Shaping

- AC-1：固定控制面、能力层、Runtime 和 Agent App 的依赖方向与数据所有权。
- AC-2：REQ-041/042/043/047/060/061 均有独立范围、依赖和非目标，不以单个大需求直接实现整个平台。
- AC-3：Runtime Port、统一事件最小字段和终态语义进入后续交付 spec。
- AC-4：明确 Direct RAG / SkillRunner / Agent Runtime 分流策略及延时、步骤数、Token、成本上限。
- AC-5：明确 Tool Gateway 是 Runtime 调用 MCP、Skill、RAG 和内部查询的唯一企业治理入口。
- AC-6：明确不保存或展示原始 Chain-of-Thought，只展示计划摘要、阶段、工具生命周期、证据、审批和错误摘要。
- AC-7：正式实施新增 bounded context 时再同步 `ARCHITECTURE.md`；本 Shaping 不虚构已存在架构。
- AC-8：外部项目判断可追溯到固定 commit 源码；命名、集成和生产禁用项进入交付 spec，不以飞书文章或 README 架构图替代实现证据。
- AC-9：应用验收顺序固定为 APP-005/009/012/030/016；APP-011/022 完成合并去重，APP-009/016 共用 REQ-063，APP-012/030 共用 REQ-062，同时保持业务状态与平台通用实体解耦。

## Non-goals

- 不在本需求直接实现 UI、数据库表或外部 Runtime。
- 不整体 fork OpenClaw、Pi 或 Nuwax。
- 不用 Pi/ACP 页面嵌入代替 MetaEduBase Workspace。
- 不让 Agent Runtime 直接持有租户 MCP 密钥或数据库连接。
- 不把企业背调、教育或园区任一场景字段写入平台通用实体。

## Open Decisions

- Pi Worker 首期采用 HTTP/SSE、NDJSON RPC 还是 gRPC。
- Runtime Worker 的租户隔离采用共享池 + 强策略，还是高风险租户独立 Cell。
- RunEvent 保留周期、归档和大 Payload 外置策略。
- Tool Grant 的短期凭证格式、撤销和预算扣减模型。
- APP-005/009/012/030/016 分别采用哪些真实授权样例、Rubric 和上线门槛；首个 REQ-062 Campaign 与首个 REQ-063 外部来源由哪个园区提供。
