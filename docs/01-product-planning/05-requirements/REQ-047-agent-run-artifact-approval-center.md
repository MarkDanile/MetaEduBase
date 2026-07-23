# REQ-047: Agent Run、产物、证据与人工确认中心

> Status: ⚫ Candidate
> Priority: P0
> Milestone: P3 / Enterprise Agent Platform
> Area: Agent Run / Event / Approval / Artifact / Evidence
> Created: 2026-07-23（重塑既有 Backlog 候选）
> Parent: REQ-059
> Related: REQ-041 / REQ-042 / REQ-043 / REQ-046

## Problem

当前 RAG diagnostics、MCP/Skill 审计和企业背调报告/证据分别存在各自上下文，尚无跨应用的 Agent Run、可重放事件、审批和产物事实源。若未来只把工具卡片、审批卡和文件塞进 Message JSON，系统无法可靠恢复运行、处理并发审批、版本化产物或统一审计。

## Scope

- `AgentRun`：关联 Conversation、输入消息、Agent/Runtime、状态、预算、开始/结束时间和终态原因。
- `RunEvent`：每 Run 单调递增 seq，覆盖 phase、plan summary、tool lifecycle、evidence、approval、artifact、retry、usage、error 和 terminal。
- `ToolCall`：工具标识、授权快照、参数/结果摘要、风险、状态、审计引用和耗时。
- `ApprovalRequest`：revision/runtime epoch、audience/reviewer、option 白名单、过期、first-answer-wins 和 terminal reason。
- `Artifact`：报告、表格、清单、工单草稿等类型、版本、内容地址、创建 Run 和确认状态。
- `EvidenceItem`：来源类型、稳定引用、摘要、血缘、可见范围和 Artifact/Run 关联。
- SSE 读取支持 `after_seq`、有界保留、完整性标记和历史重放。

## Acceptance

- AC-1：Run 状态机覆盖 queued/running/waiting_approval/completed/failed/cancelled/expired，非法迁移失败。
- AC-2：同一 Run 的 seq 唯一递增；客户端可检测 gap 并按 after_seq 重放。
- AC-3：终态独立持久化，不仅依赖事件流中的 done/error。
- AC-4：审批进程重启后仍可查询和处理；重复或冲突回答有稳定幂等语义。
- AC-5：Artifact 支持版本、来源 Run、创建者、tenant、确认/退回和归档；大文件不直接塞数据库 JSON。
- AC-6：Evidence 可回溯到 RAG source、MCP invocation、Query audit 或其他受治理来源，不接受模型自造引用。
- AC-7：企业背调可逐步引用通用 Run/Artifact/Evidence，但保留 DdTask/DdReport 业务状态，不强制一次迁表。
- AC-8：所有查询和 SSE 重放强制 tenant、conversation 和 actor 可见性边界。

## Non-goals

- 不定义具体 Agent 规划算法。
- 不把业务报告 schema 统一成一个万能 JSON。
- 不用内存 Map 作为审批唯一存储。
- 不在本需求实现完整任务调度，主动触发归 REQ-049。

## Dependencies / Next Step

- 与 REQ-041 contract-first 设计 Conversation/Message/Run 引用。
- 为 REQ-042 提供稳定 UI 事件协议，为 REQ-043 提供 Runtime 输出事实源。
