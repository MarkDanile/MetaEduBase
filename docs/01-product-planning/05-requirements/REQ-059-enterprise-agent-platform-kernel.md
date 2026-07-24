# REQ-059: 企业级可控 Agent 平台内核与 Runtime 中立控制面

> Status: 🟢 Done
> Priority: P0
> Milestone: P3 / Enterprise Agent Platform
> Area: Agent Platform / Control Plane / Runtime / Multi-tenant
> Created: 2026-07-23
> Completed: 2026-07-24（Architecture Gate via PR #475）
> Source: 用户关于 Codex 式超级智能体、Pi / ACP 集成和教育/园区企业控制台的连续规划讨论
> Related: REQ-041 / REQ-042 / REQ-043 / REQ-047 / REQ-049 / REQ-060 / REQ-061 / REQ-062 / REQ-063 / TD-085
> Spec: [源码研究与控制面契约](../../02-delivery-plans/01-specs/2026-07-23-req-059-enterprise-agent-platform-control-plane.md)

## Problem

MetaEduBase 已具备 RAG、证据链、MCP Registry、Skill Registry / SkillRunner、智能问数和企业背调应用，但这些能力目前分别由 AI Chat、SkillRunner 和业务 Orchestrator 编排。系统尚无产品无关的 Conversation、AgentRun、RunEvent、Runtime Session Binding、ToolCall、Approval、Artifact 和 Memory 控制面，继续直接接入 Pi、ACP 或其他 Agent 会形成新的平行会话和执行事实源。

目标不是把旧 `/ai/chat/evidence` 或确定性业务 Workflow 强制迁入自由 Agent，也不是把企业背调提升为平台内核，而是建立一个类似 Codex 使用体验、同时满足企业多租户、权限、审计、审批和可恢复要求的 Agent 平台。进入新 Agent Workspace 的每次输入统一进入 `AgentTurnLoopRuntime`；模型可以零工具直接回答，也可以自主选择受治理工具，不再由外部“简单/复杂问题分类器”绕过 Turn Loop。

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
  - Pi SDK / Worker Runtime（V1 默认 AgentTurnLoopRuntime）
  - ACP External Runtime Adapter
  - LangGraph / self-hosted Runtime Adapter（后续）
  - Direct RAG / Skill compatibility adapters（旧入口与确定性 Workflow）

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

`AgentTurnLoopRuntime` Adapter 至少提供以下能力。V1 传输已冻结为内部 HTTP/JSON command + SSE event stream，协议细节与 Adapter 实现由 REQ-043 承接：

```text
initialize -> capabilities
create_session / resume_session
start_turn(TurnInput) -> event stream + independent terminal result
stream_events(after_runtime_seq)
ack_events(through_runtime_seq)
get_status / set_mode / set_config_option
respond_input / respond_approval
steer_turn / cancel_run
close_session(discard_persistent_state)
```

每个 Runtime Session 的可变操作必须串行化；Runtime Binding 先持久化再缓存句柄。Worker 事件使用 `(runtime_binding_id, runtime_epoch, runtime_seq)` 去重，Control Plane 持久化为单调 `RunEvent.seq` 后再 ACK；浏览器只消费 MetaEduBase 的 `run_id + seq`，不直连 Worker。

## Turn Execution

| 入口 | V1 语义 |
|------|---------|
| 新 Agent Workspace | 始终进入配置绑定的 `AgentTurnLoopRuntime`；零工具回答是正常终止，不是旁路 |
| RAG / Query / MCP / Skill | 作为 Run-scoped Tool 经 `ToolGateway` 暴露，由模型按当前任务决定是否调用 |
| 确定性 Agent App Workflow | 可以固定调用 SkillRunner / 业务 Workflow，不强制改为自由循环 |
| 旧 `/ai/chat/evidence` | 保留兼容，逐步写入 Conversation/RunEvent，不定义新 Workspace 语义 |
| Claude Code、Codex、OpenCode 等外部 Agent | 后续通过 ACP Adapter 接入，同样不拥有企业事实源 |
| 高风险写操作 | L3 精确审批；无幂等键或可靠对账能力时只能生成 L2 草稿 |

GraphRAG 是关系索引与推理增强，只作为可选 Retrieval Tool，不作为平台版本号、Runtime 或全局默认方案。

## External Project Decisions

源码研究基线固定于 2026-07-24；进入 Spike 前必须重新核对上游版本、许可证和破坏性变更。精确源码路径、可借鉴点、禁用项和任务映射见 [控制面 spec §2.4](../../02-delivery-plans/01-specs/2026-07-23-req-059-enterprise-agent-platform-control-plane.md#24-后续-req-实施源码导航)：

- [OpenClaw `5e651d5`](https://github.com/openclaw/openclaw/tree/5e651d5ac76ce2ad41e1a0205bed210f818ad8b9)
- [Pi `a5afc3f`](https://github.com/earendil-works/pi/tree/a5afc3f171e422e08a2ccc342827719f9952f38a)
- [Nuwax Web `1278e30`](https://github.com/nuwax-ai/nuwax/tree/1278e30dc42fff2c741185775f7cade5bf01389e)
- [NuwaClaw `77bccef`](https://github.com/nuwax-ai/nuwaclaw/tree/77bccefe701a5a73895dced587fea0636c7216f6)
- [RCoder `2189eaf`](https://github.com/nuwax-ai/rcoder/tree/2189eaffc4d2a6b0bc92b988c859698b0377124b)
- [Claude ACP Adapter `3b72577`](https://github.com/agentclientprotocol/claude-agent-acp/tree/3b725779996a7c8b99b26ef3553abb915423037a)
- [Open Design `506c290`](https://github.com/nexu-io/open-design/tree/506c2900b972e6f3a25cfe5fabd7041ec6d869ca)（`0.16.1`）
- [Codex `39a2438`](https://github.com/openai/codex/tree/39a2438d16514d0d6f88105d17b0f747994af487)
- [LangGraph `31f90df`](https://github.com/langchain-ai/langgraph/tree/31f90df3e6b0268fa77fd2d118a917d420b84a68)
- [Kimi CLI `4a550ef`](https://github.com/MoonshotAI/kimi-cli/tree/4a550effdfcb29a25a5d325bf935296cc50cd417)
- [LangChain `64f5ebf`](https://github.com/langchain-ai/langchain/tree/64f5ebf97101f4ce1bd9a150ba27281f957516a7)
- [OpenCode `743f641`](https://github.com/anomalyco/opencode/tree/743f6410f2e5002723fc5e893039ac49fbfe0de8)

| 项目 | 采用内容 | 不采用内容 |
|------|----------|------------|
| OpenClaw | Runtime Registry、ACP 控制面、Session Actor Queue、事件账本、持久化审批和任务恢复设计 | 不整体嵌入；其单一可信 Operator 域不作为共享多租户后端 |
| Pi | Agent Loop、SDK、树形 Session、steer/follow-up、compaction 和 Hook | 不把 Pi JSONL、页面或进程权限当企业事实源和权限系统 |
| Nuwax / NuwaClaw | ACP Adapter、能力协商、Intervention 映射和产品交互 | 不复制 yolo、沙箱降级关闭、内存审批和单机 Engine 管理默认值 |
| Open Design | Runtime Agent Definition、Generic Engine、Conversation/Runtime Session 分离、Run Event、Tool Token 和 Workspace 产品模式 | 不复制自动审批、自动 confirm、allow-all-tools、内存 Run/Token Registry 和单用户 Memory |
| Codex | Thread/Turn/Item、App Server、ThreadManager、Session/TurnContext、ToolRouter/Registry、Rollout/State DB 和 Permission/Sandbox 分层 | 不猜测未公开桌面服务端；不直接套用本地 Coding Agent 权限模型替代企业租户策略 |
| LangGraph / LangChain | checkpoint、interrupt/resume、pending writes、middleware 和 conformance 测试思路 | 不把 checkpoint/middleware 当企业 RunEvent、Approval 或 ToolGateway；不可逆写入不使用通用自动重试 |
| Kimi CLI / OpenCode | ACP Server、Session/steer/cancel、MCP/Hook、Session runner、事件投影和 Workspace 交互 | 不复制本地 session/wire、进程内 registry、yolo/会话级自动批准或 local-first 权限边界 |

生产优先采用固定版本包和隔离 Runtime Worker；不整体 fork 任一项目。Pi 第一阶段走 Node Worker/Sidecar Spike，ACP 作为外部 Agent 南向协议，前端始终只连接 MetaEduBase API/SSE。源码与专家解读冲突时，以固定 commit 的源码和测试为准；无法回溯数据集与方法的准确率数字不进入验收基线。

## Source-aligned Naming

- 产品 `Conversation / Message / AgentRun / RunEvent` 分别映射 Codex `Thread / Message Item / Turn / Item/Event`，保留面向教育和园区业务的清晰命名。
- 核心应用服务采用 `RunCoordinator / RuntimeProfileResolver / AgentTurnLoopRuntime / RuntimeRegistry / ToolRouter / ToolGateway / ContextAssembler / RunEventLedger / ApprovalService`。
- Runtime 配置采用 `AgentDefinitionVersion / RuntimeProfile / RuntimeSessionBinding`；切换 Runtime 创建新 Binding，不迁移私有 checkpoint。`TurnInput / HumanInputRequest / RuntimeCapabilitySnapshot / RunConfigSnapshot / ContextSnapshot / ModelGrant` 固化输入、能力与运行配置。
- `Planner / Executor / Evaluator` 只描述能力，不建立三个平行状态机：计划是 RunEvent/Artifact，工具执行进入 Tool Gateway，评估拆为 Evidence/Budget/Stop Policy，模型循环由 Runtime 负责。
- 新 bounded context 候选名为 `agent_workspace / agent_execution / agent_memory`，不建立含义无边界的通用 `agent` context。

## Delivery Map

| 阶段 | 任务 | 目标 |
|------|------|------|
| 0 | REQ-059 | 冻结 Context Map、Runtime/RunEvent/ToolGrant contract 和评测场景 |
| 1 | REQ-041 / REQ-047 | Conversation/Message 与 AgentRun/Event/Approval/Artifact 持久化；旧 Direct RAG/Skill 先接兼容事件路径 |
| 2 | REQ-042 / REQ-060 | Agent Workspace 与权限化导航信息架构 |
| 2A | REQ-062 contract / REQ-063 source Spike | 在 Run/Artifact 契约上塑形动态采集模型；并行确认外部来源授权、许可、网络和快照策略，不提前实现自由爬虫 |
| 3 | TD-085 | 现有 AI Chat / Skill / DD 边界渐进收口，抽 LLM Port 和 Tool Gateway 接线边界 |
| 4 | REQ-043 / REQ-063 | `AgentTurnLoopRuntime`、Runtime Profile、Tool Gateway；Pi 先做 APP-005 只读对照，再以 APP-009 验证受治理外部数据与多方案选址；最后做 ACP/沙箱硬化 |
| 5 | REQ-062 implementation | 建立 APP-012/030 共用的 Campaign、FormSchemaVersion、Submission 和 ReportSnapshot；ReportSnapshot 引用 AgentRun/Artifact，不在应用内重复实现动态表单或运行状态机 |
| 6 | REQ-061 / REQ-049 | 记忆治理、长期任务、周期采集、催办和主动触发 |

## Acceptance For Architecture Gate

- AC-1：固定控制面、能力层、Runtime 和 Agent App 的依赖方向与数据所有权。
- AC-2：REQ-041/042/043/047/060/061 均有独立范围、依赖和非目标，不以单个大需求直接实现整个平台。
- AC-3：Runtime Port、统一事件最小字段和终态语义进入后续交付 spec。
- AC-4：明确新 Workspace 统一进入 Agent Turn Loop；零工具回答、工具调用、预算终止、确定性 Workflow 与旧 Direct RAG 兼容路径各自有稳定边界。
- AC-5：明确 Tool Gateway 是 Runtime 调用 MCP、Skill、RAG 和内部查询的唯一企业治理入口。
- AC-6：明确不保存或展示原始 Chain-of-Thought，只展示计划摘要、阶段、工具生命周期、证据、审批和错误摘要。
- AC-7：正式实施新增 bounded context 时再同步 `ARCHITECTURE.md`；本 Architecture Gate 不虚构已存在架构。
- AC-8：外部项目判断可追溯到固定 commit 源码；命名、集成和生产禁用项进入交付 spec，不以飞书文章或 README 架构图替代实现证据。
- AC-9：应用验收顺序固定为 APP-005/009/012/030/016；APP-011/022 完成合并去重，APP-009/016 共用 REQ-063，APP-012/030 共用 REQ-062，同时保持业务状态与平台通用实体解耦。
- AC-10：Architecture Gate 八项决策冻结到控制面 spec；后续实现改变所有权、失败语义、安全默认值或 Pilot 安全门槛时必须回到 REQ-059 评审。

## Non-goals

- 不在本需求直接实现 UI、数据库表或外部 Runtime。
- 不整体 fork OpenClaw、Pi 或 Nuwax。
- 不用 Pi/ACP 页面嵌入代替 MetaEduBase Workspace。
- 不让 Agent Runtime 直接持有租户 MCP 密钥或数据库连接。
- 不把企业背调、教育或园区任一场景字段写入平台通用实体。

## Architecture Gate Decisions

完整硬语义见 [控制面 spec §15.2](../../02-delivery-plans/01-specs/2026-07-23-req-059-enterprise-agent-platform-control-plane.md#152-architecture-gate-冻结决策)：

| ID | 已冻结决策 |
|----|------------|
| AG-1 | Control Plane -> Worker 首期使用内部 HTTP/JSON command + SSE event stream，终态独立查询；Port 保留未来 gRPC 替换能力 |
| AG-2 | L0/L1 只读任务可共享 Worker 池；写操作、敏感租户、不可信 ACP 和额外文件/网络能力进入独立 Runtime Cell |
| AG-3 | RunEvent 内联 JSON 上限 32 KiB；大载荷、二进制和敏感内容外置；热重放默认 90 天，终态/审批/审计摘要默认 365 天 |
| AG-4 | ToolGrant 使用 256-bit opaque token，默认 TTL 5 分钟、最大 15 分钟；写操作单次使用；预算由控制面 reserve、按 execute/reconcile 结果 settle/release |
| AG-5 | APP-005 是 deterministic baseline + 只读 Agent 对照；APP-009 是首个新 Agent Pilot；真实授权缺失只阻塞对应 Pilot |
| AG-6 | 首个 Slice 同时建立 `agent_workspace` 与 `agent_execution` 契约边界，`agent_memory` 后置，不建立通用 `agent` context |
| AG-7 | 新 Agent Workspace 输入统一进入 `AgentTurnLoopRuntime`；Pi 是 V1 默认绑定；零工具回答不是旁路，旧 AI Chat 和确定性 Workflow 保留兼容边界 |
| AG-8 | Worker 使用 SQLite spool + `runtime_seq` + Control Plane ACK；写工具执行遵循 prepare/approval/reserve/execute/reconcile/settle，未知结果进入 `outcome_unknown` 且禁止盲重试 |

## Completion Evidence

- Context Map、源码对比、目标命名、Runtime/RunEvent/ToolGrant/Approval/Sandbox 和 Worker ACK/写操作恢复基线已进入控制面 spec。
- 12 个参考仓库均已登记 GitHub 地址、固定 commit、精确源码路径、可借鉴/禁用边界和后续 REQ 映射。
- APP-005/009 首批 Pilot 的安全门槛、证据口径和真实数据阻塞语义已冻结；不使用无数据集依据的聚合准确率。
- REQ-041/043/047/060/061/062/063 均有独立所有权、依赖和非目标；REQ-059 不直接实现整个 Agent 平台。
- 后续任务复杂度、编码模型、推理强度、可下放范围和双模型评审门禁见 [AI Delivery Routing Matrix](../../03-engineering-governance/03-matrices/agent-platform-ai-delivery-routing.md)。
- 真实地图/交通、动态统计、展会和产业研究输入由对应 Requirement 跟踪，不再作为 Architecture Gate 的未决问题。

## Closeout Review

| 维度 | 得分 | 证据 |
|------|------|------|
| 范围与需求匹配 / 15 | 15 | Control Plane、Runtime、园区应用和非目标边界均进入 Requirement/Spec/Milestone |
| 实现质量 / 20 | 20 | 八项 Architecture Gate 决策、目标命名、实施顺序和 12 仓库源码导航形成单一事实源 |
| 测试与验证证据 / 20 | 18 | 文档全量门禁、diff、固定 commit 路径和 URL 一致性通过；本任务为 M0 文档，不运行代码测试 |
| 事实源与流程遵守 / 15 | 15 | PR #475 合并后同步 Requirement、Backlog、Iteration、Milestone、work-log 和工作台 |
| 风险与行为变化控制 / 15 | 15 | 明确不保存 CoT、Pi 不进 API 进程、沙箱 fail closed、写操作 reconcile/unknown 和 Pilot 边界 |
| 可评审性与交接质量 / 10 | 10 | 独立模型复审、用户签字、源码路径与后续 REQ/模型分工均可追踪 |
| 持续改进信号 / 5 | 4 | 7 项架构反例已当前收口；未新增规则，后续通过各 Adapter conformance suite 验证 |

总分：97/100。结论：优秀，可关闭 Architecture Gate；无必修 follow-up，后续实施按既定独立 Requirement 推进。

## Delivery Record

| 日期 | 阶段 | 结果 |
|------|------|------|
| 2026-07-23 | 路线与应用塑形 | PR #474 合并，建立 REQ-059、P3 路线、园区五应用和 Runtime 中立方向 |
| 2026-07-24 | Architecture Gate | [PR #475](https://github.com/MarkDanile/MetaEduBase/pull/475) squash merge `132730a0`；冻结八项架构决策、AI Delivery Matrix 和 12 仓库源码导航 |
| 2026-07-24 | 验证与签字 | `scripts/check-engineering-docs --full`、`git diff --check`、上游固定路径/URL 一致性通过；独立模型复审无阻塞；用户完成架构确认 |

## Remaining Inputs

- REQ-063：APP-009/016 的首批授权外部来源、许可、网络范围和 SourceSnapshot 策略。
- REQ-062：APP-012 首个真实统计要求、填报角色和输出格式。
- APP-030/016 后续 Requirement：真实展会与产业研究课题。

这些输入缺失会阻塞对应业务 Pilot 的真实验收，不改变 REQ-059 Architecture Gate 已完成的事实，也不得用 mock/dry-run 冒充业务完成。
