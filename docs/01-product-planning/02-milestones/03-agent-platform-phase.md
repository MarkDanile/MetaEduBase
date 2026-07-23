# P3: 阶段三 — 企业 Agent 平台化

Status: 🟡 Doing
Current: Yes
External:

## Goal

把 MetaEduBase 从“具备 RAG、MCP、Skill 和若干 AI 应用的能力底座”升级为面向教育和园区的企业级可控 Agent 平台：用户在统一 Workspace 中发起任务，系统能够按复杂度选择 Direct RAG、确定性 Skill 或 Agent Runtime，自主制定计划、调用受治理工具、处理中断与审批、生成可追溯产物，并在刷新、断线和进程重启后保持明确状态。P3 采用园区纵向优先策略，按 APP-005 企业 360 背调、APP-009 AI 载体选址、APP-012 招商动态报表、APP-030 会展招商、APP-016 产业研究辅助平台形成近期应用主线，教育应用随后承担跨行业复用验证。

P3 的目标体验类似 Codex，但企业事实源和权限边界由 MetaEduBase 持有。Pi、ACP、Codex、OpenCode 等只作为 Runtime 或源码参考，不取代产品会话、租户权限、运行事件、审批、产物和记忆治理。

## Phase Entry

2026-07-23 正式进入 P3。进入条件已经满足：

- P2 已完成 Retrieval Optimization、RAG 真实效果评测和生产链路稳定化。
- REQ-044 MCP Registry、REQ-045 SkillRunner、REQ-052 智能问数已交付，可作为 Tool Provider。
- APP-005 企业 360 背调已完成真实业务闭环，是第一个产业园区 AI 应用，也是 P3 首个平台化样板，但不定义平台内核。
- BUG-017/018/019/020 已收口身份、租户、Token、MCP 凭证、SSRF 和文件边界的高风险问题。
- REQ-059 已完成 OpenClaw、Pi、Nuwax/NuwaClaw、Open Design 和 Codex 源码研究与首版 Control Plane 契约。

## Product Boundary

```text
Enterprise Agent Control Plane (MetaEduBase owns truth)
  - tenant / identity / policy / audit / budget
  - conversation / message / run / event / approval
  - artifact / evidence / memory / runtime binding

Capability Providers
  - Direct RAG / Knowledge / Graph Recall
  - MCP Registry / Invocation
  - Skill Registry / deterministic SkillRunner
  - QueryService / structured data

Pluggable Runtimes
  - DirectRagRuntime
  - SkillRuntime
  - PiRuntimeAdapter
  - AcpRuntimeAdapter

Agent Apps
  - industrial-park applications first, education applications follow
  - APP-005 due diligence is the first park app, not the kernel
```

## Tracks

### 轨道 A：Control Plane 与 Workspace

| 能力 | 任务 | 阶段目标 |
|------|------|----------|
| 产品会话事实源 | REQ-041 | tenant-scoped Conversation/Message，新建、命名、置顶、归档、删除、搜索、恢复和幂等消息 |
| 运行事实源 | REQ-047 | AgentRun/RunEvent/ToolCall/Approval/Artifact/Evidence，单调 seq、独立终态和 after-seq 重放 |
| Codex 式 Workspace | REQ-042 | 左会话、中 Run/Event 时间线、右计划/审批/产物/证据；Direct RAG、Skill 和 Agent 使用同一协议 |
| 控制台信息架构 | REQ-060 | MCP/Skill 归入能力中心，移除重复 Skill 入口，Sidebar/Router/Home 使用同一 permission/nav 事实源 |

### 轨道 B：Runtime 与 Agentic RAG

| 能力 | 任务 | 阶段目标 |
|------|------|----------|
| 现有边界收口 | TD-085 | 抽 LLM Port，收缩 AIChatService，移除 Skill 通用层中的企业背调语义，避免新增平行编排链 |
| Runtime Port | REQ-043 | `AgentRuntimePort`、RuntimeRegistry、Session actor、事件流 + 独立 terminal result、显式 resume 失败 |
| Tool Gateway | REQ-043 | Run-scoped ToolGrant、ToolRouter、策略校验、审计和结果裁剪，复用现有 RAG/MCP/Skill/QueryService |
| Pi Native Runtime | REQ-043 | 固定版本 Pi SDK + 独立 Node Worker，跑通只读多步骤 Pilot、预算、取消和恢复 |
| ACP External Runtime | REQ-043 | 能力协商、new/load/resume、prompt/steer、cancel、permission round-trip 和事件映射 |
| 复杂度路由 | REQ-043 | `direct_rag / deterministic_skill / agent_runtime` 可审计分流，简单问答保留低延时路径 |

### 轨道 C：企业安全、治理与记忆

| 能力 | 任务 | 阶段目标 |
|------|------|----------|
| 持久化审批 | REQ-047 / REQ-043 | first-answer-wins、revision/runtime epoch、过期、reviewer scope，进程重启后可处理 |
| 沙箱与 Workspace Lease | REQ-043 | Worker 与 API 隔离；文件默认只读、网络默认拒绝；沙箱不可用时 fail closed |
| 记忆治理 | REQ-061 | Working Context、Conversation Summary、长期 Memory 和 Enterprise Knowledge 分层；tenant/user/agent/purpose/TTL/来源/删除 |
| 主动任务 | REQ-049 | 只在稳定 Run/Approval/Artifact 上增加 schedule/event trigger，不另建任务事实源 |
| 可观测与预算 | REQ-047 / REQ-043 | P50/P95、step/tool/retry/token/cost、resume/event gap、approval/sandbox/policy 指标 |

### 轨道 D：真实 Agent Apps

| 场景 | 角色 | P3 使用方式 |
|------|------|-------------|
| APP-005 企业 360 背调 | 第一个园区应用、首个平台化样板 | V0 与生产治理保持已完成；优先接入统一 Conversation、Run/Event、Approval、Artifact、Evidence 和 Workspace，以现有 SkillRunner 为生产基线，再用只读 Agent 路径做受控对照 |
| APP-009 AI 载体选址 | 第二个园区应用、首个新 Agent Pilot | 连接资产管理系统和 REQ-063 受治理外部交通/配套数据，按企业硬约束与偏好生成多套可解释方案，不自动锁定房源 |
| APP-012 招商动态报表 | 第三个园区应用 | 经 REQ-062 完成统计要求解析、系统覆盖判断、动态表单发布、多人填报、汇总报表和常态化模板 |
| APP-030 会展招商 | 第四个园区应用 | 复用 REQ-062，支持展会模板、百人级受众、表单/对话登记、线索去重、进度和领导汇总，不重建表单引擎 |
| APP-016 产业研究辅助平台 | 第五个园区应用 | 经 REQ-063 和研究 Skill 组织产业研究项目、内外部来源、产业链/企业分析、证据化报告和招商指导；吸收 APP-011 |
| 教育 Agent Pilot | 跨行业复用验证 | 在园区近期五应用主线形成闭环后，再从 APP-001 单课程授权样例或独立备课样例中选择，不抢占当前资源 |

## Delivery Order

下面是依赖顺序，不代表把全部工作压进一个 PR。每个 Requirement 进入实现前仍需独立 spec/plan 和完成门禁。

| 顺序 | 波次 | 任务 | 依赖与完成信号 |
|------|------|------|----------------|
| 0 | Architecture Gate | REQ-059 | 冻结 Context Map、Runtime/RunEvent/ToolGrant contract、传输协议选择和两个 Pilot Rubric |
| 1 | Durable State | REQ-041 | Conversation/Message schema、API、删除/保留策略和 Direct RAG 写入路径 |
| 2 | Durable Execution | REQ-047 | AgentRun/Event/Approval/Artifact/Evidence 状态机、seq、终态、SSE 重放；与 REQ-041 contract-first 联合设计 |
| 2P | Navigation Parallel | REQ-060 | 架构命名冻结后可并行实施；只收口已有入口和权限，不提前展示未交付 Agent Builder |
| 2A | App Foundation Shaping | REQ-062 contract + REQ-063 source Spike | REQ-062 在 Run/Artifact 上塑形 Campaign/Form/Submission；REQ-063 先确认授权来源、许可、网络和快照策略，Connector 等待 Tool Gateway |
| 3 | Workspace | REQ-042 | 用 Direct RAG/Skill compatibility path 验证刷新、重连、停止、审批卡和产物 UI，不依赖 Pi 才能验收 |
| 4 | Boundary Closure | TD-085 | 分 Slice 抽 LLM Port、Direct RAG 边界和业务专属逻辑，为 Tool Gateway 接线；行为特征测试全绿 |
| 5 | Runtime Foundation | REQ-043 contract + Tool Gateway | Runtime Port、RuntimeRegistry、ToolGrant、ToolRouter、ContextAssembler 和三档路由 |
| 6 | Pi Pilot | REQ-043 Pi Worker | 先以 APP-005 只读对照验证兼容路径，再用 APP-009 的真实资产 + 授权外部数据验证多方案选址；补齐预算、取消和故障恢复，且不在 FastAPI 进程内运行 Pi |
| 7 | Runtime Hardening | REQ-043 ACP + Sandbox | durable approval、workspace lease、network allowlist、ACP round-trip、kill/restart/tenant attack tests |
| 8 | Memory & Active Work | REQ-061 -> REQ-049 | 先长期记忆治理，再增加定时/事件触发；敏感信息默认不自动抽取 |

## Current Iteration

- [2026-W30 P3 企业 Agent 平台控制面塑形](../03-iterations/2026-W30-p3-enterprise-agent-platform.md)
- 当前只推进 Architecture Gate 和下一波 contract-first 准备，不直接实施 Pi Worker。

## Completion Criteria

- MetaEduBase 持有 Conversation、Message、AgentRun、RunEvent、RuntimeSessionBinding、ToolCall、ApprovalRequest、Artifact、EvidenceItem 和 MemoryItem 的企业事实源或已批准的阶段边界。
- 同一 Conversation 可通过统一 Workspace 使用 Direct RAG、SkillRunner 和至少一个 Agent Runtime，产品会话与 Runtime 私有 Session 解耦。
- Direct RAG 保持低延时路径；Agent 路径具备 step/token/time/cost/tool retry 上限和明确终止原因。
- Tool 调用全部经过 Tool Gateway；Runtime 无法获得租户长期 MCP secret、数据库连接或业务 Token。
- Approval 在服务重启后仍可查询和处理；冲突回答、过期和 Runtime epoch 变化具有稳定语义。
- Runtime Worker 与 Backend API 隔离；sandbox/network policy 失败时 fail closed；ACP load 失败不得静默创建新 Session。
- SSE 断线可按 `after_seq` 重放，客户端能发现事件缺口；Run terminal state 不依赖最后一帧流事件。
- 按 APP-005 -> APP-009 -> APP-012 -> APP-030 -> APP-016 的园区主线完成分阶段真实授权验收；APP-011/022 不再形成重复实现；APP-005 保留 SkillRunner 生产基线和制审分离，不用 Agent 路径冒充替换完成。
- UI 不展示或持久化原始 Chain-of-Thought，只显示计划摘要、阶段、工具生命周期、证据、审批、usage 和错误摘要。
- 建立 Route accuracy、Task success、Groundedness/Evidence coverage、Tool failure、Human intervention、P50/P95、Token/Cost 的基线。

## Non-goals

- 不把所有 AI Chat 请求强制升级为 Agent Loop。
- 不把 GraphRAG、Neo4j、Milvus、Elasticsearch 或多模态作为 P3 成功前提；这些进入 P4 指标触发式升级。
- 不整体 fork OpenClaw、Pi、Nuwax、Open Design 或 Codex，不嵌入其页面。
- 不把 Pi/ACP Session、JSONL 或内存 Map 作为企业产品事实源。
- 不在 P3 首期开放自由 Agent 的高风险自动写操作；先生成草稿/Action Proposal，再经确定性策略和审批执行。
- 不建立一个同时承载平台、教育和园区业务语义的通用 `agent` 上下文。

## Open Items

| ID | 状态 | 说明 | 事实源 |
|----|------|------|--------|
| REQ-059 | 🟣 Shaping | Control Plane、源码研究、命名和 Runtime 中立边界；Ready 前确认六项待决策 | [Requirement](../05-requirements/REQ-059-enterprise-agent-platform-kernel.md) / [Spec](../../02-delivery-plans/01-specs/2026-07-23-req-059-enterprise-agent-platform-control-plane.md) |
| REQ-041 | ⚫ Candidate | Conversation/Message 与多会话事实源 | [Requirement](../05-requirements/REQ-041-ai-workspace-conversation-persistence.md) |
| REQ-047 | ⚫ Candidate | Run/Event/Approval/Artifact/Evidence | [Requirement](../05-requirements/REQ-047-agent-run-artifact-approval-center.md) |
| REQ-060 | ⚫ Candidate | 控制台信息架构和权限化导航，可与 Durable State 并行 | [Requirement](../05-requirements/REQ-060-enterprise-console-information-architecture.md) |
| REQ-042 | ⚫ Candidate | Codex 式 Agent Workspace | [Requirement](../05-requirements/REQ-042-agent-workspace-three-pane-experience.md) |
| TD-085 | ⚫ 待办 | 收口 AI Chat、Skill 与 Agent App 上下文边界倒置 | [Technical Debt](../../03-engineering-governance/technical-debt.md#td-085-收口-ai-chatskill-与-agent-app-的上下文边界倒置) |
| REQ-043 | ⚫ Candidate | Runtime Port、Tool Gateway、Pi Worker、ACP 和 Agentic RAG | [Requirement](../05-requirements/REQ-043-runtime-neutral-agentic-rag-orchestration.md) |
| REQ-061 | ⚫ Candidate | Agent Memory 与 Context Governance | [Requirement](../05-requirements/REQ-061-agent-memory-and-context-governance.md) |
| REQ-062 | ⚫ Candidate | APP-012/030 共用的动态采集、填报与报表发布平台 | [Requirement](../05-requirements/REQ-062-dynamic-data-collection-and-reporting.md) |
| REQ-063 | ⚫ Candidate | APP-009/016 共用的受治理外部数据采集与证据链 | [Requirement](../05-requirements/REQ-063-governed-external-data-acquisition.md) |

## Evidence

- [REQ-059 源码研究与控制面契约](../../02-delivery-plans/01-specs/2026-07-23-req-059-enterprise-agent-platform-control-plane.md)
- [AI Applications](../06-ai-applications/README.md)
- [Product Backlog](../04-backlog.md)
- [Current Work](../../03-engineering-governance/current-work.md)
- [Technical Debt](../../03-engineering-governance/technical-debt.md)
