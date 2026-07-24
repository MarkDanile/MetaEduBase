# REQ-047: Agent Run、产物、证据与人工确认中心

> Status: 🟣 Shaping
> Core Contract: 🟡 Doing（Slice E0 已完成，下一步 E1；完整 REQ-047 继续 Shaping）
> Priority: P0
> Milestone: P3 / Enterprise Agent Platform
> Area: Agent Run / Event / Approval / Artifact / Evidence
> Target Context: `agent_execution`
> Created: 2026-07-23（重塑既有 Backlog 候选）
> Parent: REQ-059
> Related: REQ-041 / REQ-042 / REQ-043 / REQ-046
> Core Spec: [REQ-041/047 联合核心契约](../../02-delivery-plans/01-specs/2026-07-24-req-041-047-conversation-run-contract.md)
> Core Plan: [Durable Core 分 Slice 实施计划](../../02-delivery-plans/02-plans/2026-07-24-req-041-047-conversation-run-contract-plan.md)

## Problem

当前 RAG diagnostics、MCP/Skill 审计和企业背调报告/证据分别存在各自上下文，尚无跨应用的 Agent Run、可重放事件、审批和产物事实源。若未来只把工具卡片、审批卡和文件塞进 Message JSON，系统无法可靠恢复运行、处理并发审批、版本化产物或统一审计。

## Scope

- 本需求归属目标上下文 `agent_execution`，拥有 AgentDefinitionVersion、RuntimeProfile、AgentRun、RunEvent、RuntimeSessionBinding、TurnInput、HumanInputRequest、ToolCall、ToolGrant、ModelGrant、ApprovalRequest、Artifact、EvidenceItem、运行 Snapshot 和执行策略 Port；不拥有 Conversation 生命周期、长期 Memory 或业务领域状态。
- `AgentRun`：通过稳定 ID 关联 Conversation、输入消息、Agent/Runtime、状态、预算、开始/结束时间和终态原因；不共享 `agent_workspace` 的 ORM model/repository。
- `RunEvent`：每 Run 单调递增 seq，覆盖 phase、plan summary、tool lifecycle、evidence、input、approval、artifact、retry、usage、error 和 terminal；`(tenant_id, run_id, seq)` 唯一。Worker `(runtime_binding_id, runtime_epoch, runtime_seq)` 只用于幂等摄取与 ACK。
- `RunEvent` 内联仅允许已裁剪、classification 不高于 `internal` 且 `<= 32 KiB` 的 JSON；更大、二进制或敏感 payload 外置，仅保存 ref/digest/size/content type/classification/expiry，外置成功后才能提交引用事件。
- `TurnInput`：引用用户 Message/附件和 queued/steer 交付方式；活动 Run 中普通新输入默认排队为下一 Run。
- `HumanInputRequest`：Runtime 追问、允许回答者、状态、过期和响应引用；与 Approval 分离。
- `ToolCall`：工具标识、授权快照、参数/结果摘要、风险、幂等/对账能力、状态、审计引用和耗时；支持 `outcome_unknown`。
- `ApprovalRequest`：精确绑定 ToolCall/参数摘要/revision/runtime epoch、audience/reviewer、option 白名单、过期、first-answer-wins 和 terminal reason；V1 不支持 `allow-always`。
- `RuntimeCapabilitySnapshot / RunConfigSnapshot / ContextSnapshot`：固化本 Run 的 Runtime 能力、Agent/模型/工具/预算/Policy 和上下文引用；配置变化只影响下一 Run。
- `Artifact`：报告、表格、清单、工单草稿等类型、版本、内容地址、创建 Run 和确认状态。
- `EvidenceItem`：来源类型、稳定引用、摘要、血缘、可见范围和 Artifact/Run 关联。
- SSE 读取支持 `after_seq`、有界保留、完整性标记和历史重放；默认热重放 90 天，Run 终态、Approval 决策、ToolCall 审计和 payload digest 默认保留 365 天，Artifact/Evidence 服从业务与租户策略。
- 不持久化原始 Chain-of-Thought、密钥、数据库连接、长期 Token 或未裁剪敏感响应；thinking 只映射为可公开的 plan/phase/tool/evidence/usage/error 摘要。

## Acceptance

- AC-1：Run 状态机覆盖 queued/starting/running/waiting_input/waiting_approval/resume_required/cancelling/completed/failed/cancelled/expired，非法迁移失败。
- AC-2：`(tenant_id, run_id, seq)` 唯一且 seq 单调递增；客户端可检测 gap 并按 after_seq 重放。
- AC-3：终态独立持久化，不仅依赖事件流中的 done/error。
- AC-4：审批进程重启后仍可查询和处理；重复或冲突回答有稳定幂等语义。
- AC-5：Artifact 支持版本、来源 Run、创建者、tenant、确认/退回和归档；大文件不直接塞数据库 JSON。
- AC-6：Evidence 可回溯到 RAG source、MCP invocation、Query audit 或其他受治理来源，不接受模型自造引用。
- AC-7：企业背调可逐步引用通用 Run/Artifact/Evidence，但保留 DdTask/DdReport 业务状态，不强制一次迁表。
- AC-8：所有查询和 SSE 重放强制 tenant、conversation 和 actor 可见性边界。
- AC-9：32 KiB 内联边界、敏感 classification 外置、对象写入失败和 payload digest 完整性均有测试。
- AC-10：90/365 天默认保留策略可按租户策略执行归档/删除，且不会绕过业务、法定或安全删除要求。
- AC-11：事件和日志中不存在原始 Chain-of-Thought、长期凭证及未裁剪敏感 Tool Result。
- AC-12：Worker 事件按 runtime binding/epoch/seq 幂等摄取；ACK 丢失与重放不会生成重复 RunEvent 或终态。
- AC-13：ToolCall 覆盖 prepared/waiting_approval/reserved/executing/reconciling/succeeded/failed/outcome_unknown/cancelled；`outcome_unknown` 是未解决的非终态，不自动重试，仅可经 Provider 对账或具名人工裁决转为 succeeded/failed。
- AC-14：HumanInputRequest 与 ApprovalRequest 在状态、权限、响应和过期语义上完全分离。
- AC-15：Run 终态前不存在活动 ToolCall/Input/Approval；审批过期原子取消未执行 ToolCall 并释放 Grant/预算。
- AC-16：cancel/timeout 不越过 executing/reconciling 写 Tool；存在 `outcome_unknown` 时 Run 保持非终态 `resume_required`，不得完成、失败、取消或过期。
- AC-17：Worker 终态事件只作 observation；RunCoordinator 以独立 terminal result 原子提交唯一 canonical 终态事件，冲突结果 fail closed 并记录 digest。

## Non-goals

- 不定义具体 Agent 规划算法。
- 不把业务报告 schema 统一成一个万能 JSON。
- 不用内存 Map 作为审批唯一存储。
- 不在本需求实现完整任务调度，主动触发归 REQ-049。

## Dependencies / Next Step

- Conversation/Message/Run/Event Durable Core 已与 REQ-041 冻结；W1 与 E0 已合并，后续按 E1/B1/A1/R1 推进。两个 context 分别迁移，不共享 ORM/repository；E1 的 RunEvent/receipt 与 Runtime ACK cursor 必须在同一事务提交。
- 完整 REQ-047 仍处于 Shaping：HumanInput/Approval、ToolCall/Grant/Snapshot、Artifact/Evidence 必须分别补充字段、状态、权限、retention 与故障 spec/plan，完成前不得把 REQ-047 整体翻 Ready/Done。
- Durable Core 为 REQ-042 提供稳定 UI 事件协议，为 REQ-043 提供 Runtime 输出事实源；首个兼容路径支持 Direct RAG/SkillRunner，不等待 Pi Worker。
