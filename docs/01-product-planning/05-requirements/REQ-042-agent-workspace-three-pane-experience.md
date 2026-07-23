# REQ-042: Codex 式 Agent Workspace 三栏体验

> Status: ⚫ Candidate
> Priority: P0
> Milestone: P3 / Enterprise Agent Platform
> Area: AI Workspace / UI / Streaming Events
> Created: 2026-07-23（补齐既有 Backlog 候选事实源）
> Parent: REQ-059
> Related: REQ-041 / REQ-043 / REQ-047 / REQ-060

## Problem

当前 AI Chat 是单页内存消息列表和一次性 HTTP 请求，只能展示用户/助手文本及 RAG 来源，无法承载会话切换、运行阶段、工具调用、审批、任务、产物、证据、断线重连和恢复。目标是建设 Codex 式工作界面，但保持教育和园区企业软件所需的克制、可扫描和高频操作效率。

## Scope

- 左栏：会话列表、搜索、新建、重命名、置顶、归档和删除。
- 中栏：用户/助手消息与统一 RunEvent 时间线，Composer 固定且支持停止、继续和附件。
- 右栏：任务/计划、审批、产物、证据与运行详情，可按场景配置默认 Tab。
- 通过 `run_id + seq` 消费统一 SSE 事件，支持 after-seq 重连、缺口检测和终态恢复。
- 显示 plan summary、current phase、tool lifecycle、evidence、approval、artifact、retry/error summary。
- 响应式布局：窄屏使用抽屉/Tab，不允许三栏压缩后文本重叠。
- 浅色/深色主题沿用现有中性工作台设计系统。

## Acceptance

- AC-1：用户可完成会话创建、切换、搜索、置顶、归档和删除，不丢失当前草稿。
- AC-2：运行中可以停止；刷新或断线后可从最后 seq 恢复，不重复渲染事件。
- AC-3：工具、审批、产物和证据使用结构化组件，不伪装成普通助手文本。
- AC-4：审批操作展示范围、风险、参数摘要和有效选项；过期或已处理状态不可重复提交。
- AC-5：不展示原始 Chain-of-Thought；thinking UI 只消费平台批准的摘要事件。
- AC-6：桌面与移动视口无文本遮挡、横向溢出和控件跳动，并有 Playwright 截图验收。
- AC-7：Direct RAG、SkillRunner 和 Agent Runtime 在同一时间线协议下呈现，UI 不依赖某个 Runtime 私有事件。

## Non-goals

- 不在前端直接连接 Pi、ACP 或 MCP Server。
- 不通过 iframe 集成外部 Agent 页面。
- 不在本需求定义 Runtime 内部规划算法。
- 不在页面展示“功能介绍”式营销文案或原始模型推理。

## Dependencies / Next Step

- 依赖 REQ-041 会话事实源、REQ-047 RunEvent/Approval/Artifact 契约。
- 导航归属和权限显示遵循 REQ-060，不在页面内硬编码角色菜单。
