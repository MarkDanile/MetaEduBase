# REQ-041: AI Workspace 会话持久化与多会话事实源

> Status: ⚫ Candidate
> Priority: P0
> Milestone: P3 / Enterprise Agent Platform
> Area: AI Workspace / Conversation / Message
> Target Context: `agent_workspace`（代码与迁移落地后再同步 `ARCHITECTURE.md`）
> Created: 2026-07-23（补齐既有 Backlog 候选事实源）
> Parent: REQ-059
> Related: REQ-042 / REQ-043 / REQ-047 / REQ-061

## Problem

当前 AI Chat 的消息只保存在页面内存中，刷新、切换页面或重新登录后即丢失；后端 `/ai/chat/evidence` 也是一次请求返回完整回答，没有产品级 Conversation 和 Message。外部 Runtime 自带 Session 不能替代企业产品会话，否则更换 Runtime、会话恢复、权限审计和数据删除都会被供应商实现绑定。

## Scope

- 建立 tenant-scoped `Conversation` 与 `Message` 事实源。
- 本需求归属目标上下文 `agent_workspace`，只拥有 Conversation/Message 及用户可见会话生命周期；不拥有 Runtime live handle、ToolGrant、Approval 状态机或业务报告字段。
- 支持新建、自动/手工命名、置顶、取消置顶、归档、恢复、软删除和搜索。
- Message 保存用户可见内容、角色、状态、创建者和必要引用；sources、diagnostics、artifact、run 采用稳定引用，不将所有对象复制进消息 JSON。
- 支持按 Conversation 分页加载历史，保证顺序稳定和重复请求幂等。
- 用户输入先持久化为 Message，再由 `agent_execution` 建立不可变 `TurnInput`；活动 Run 中的普通新输入默认排队到下一 Run，显式 steer 由 REQ-043 处理。
- 产品 Conversation 与 Runtime Session 解耦；`RuntimeSessionBinding` 归 `agent_execution`，由 REQ-047/043 承接持久化与 Runtime 接线。
- `agent_workspace` 与 `agent_execution` 只通过稳定 ID、application port 和显式 DTO 交互，不共享 ORM model 或 repository。
- 为后续 fork/branch 保留父会话和分叉消息引用，不要求 V1 交付完整树形 UI。

## Acceptance

- AC-1：tenant A 无法读取、搜索、修改或恢复 tenant B 的会话和消息。
- AC-2：新建、重命名、置顶、归档、恢复、删除和搜索均有 API 与持久化测试。
- AC-3：页面刷新和重新登录后可恢复会话列表及消息历史。
- AC-4：消息写入具备幂等键；客户端重试不会产生重复用户消息或回答。
- AC-5：与 REQ-047 contract-first 冻结 Message 引用的 Run、Artifact、Evidence 和 Runtime Binding 的删除/保留关系；Conversation 删除不得以 ORM cascade 绕过执行审计、业务保留或法定删除策略。
- AC-6：不保存原始 Chain-of-Thought；thinking 仅保存可公开的结构化摘要或运行事件引用。
- AC-7：现有 `/ai/chat/evidence` Direct RAG 回答可作为首个兼容路径写入 Conversation，不要求先接 Pi；新 Agent Workspace 的统一 Turn Loop 语义由 REQ-043 承接。

## Non-goals

- 不实现 Agent 规划和工具循环，归 REQ-043。
- 不实现长期语义记忆，归 REQ-061。
- 不把 Pi Session、ACP Session 或本地 JSONL 作为产品会话数据库。
- 不在本需求完成三栏工作台视觉重构，归 REQ-042。

## Dependencies / Next Step

- 先以 REQ-059 的数据所有权与事件边界为约束补交付 spec/plan。
- 与 REQ-047 contract-first 对齐 Conversation、Message、Run 和 Artifact 的 ID、删除/保留与终态关系，并保持两个上下文独立迁移。
