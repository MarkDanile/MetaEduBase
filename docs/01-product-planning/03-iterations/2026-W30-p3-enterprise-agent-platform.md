# Iteration 2026-W30: P3 企业 Agent 平台控制面塑形

Status: 🟡 Doing
Dates: 2026-07-20 ~ 2026-07-26
Goal: 完成 P2 -> P3 路线切换，冻结企业 Agent Control Plane、源码依据、任务依赖顺序和园区优先的首批 Pilot 边界，为 REQ-041/047 contract-first 设计建立开工门禁。

## Committed Scope

| ID | 类型 | 状态 | 摘要 | 本迭代退出条件 |
|----|------|------|------|----------------|
| REQ-059 | REQ | 🟢 Done | 企业级可控 Agent 平台内核与 Runtime 中立控制面 | PR #475 已合并；源码研究、Context Map、命名、Runtime/RunEvent/ToolGrant 契约、八项 Architecture Gate 决策、AI Delivery Matrix 和 APP-005/009 Pilot Rubric 已冻结 |

## Ready Queue

本表只表示 REQ-059 完成 Architecture Gate 后的建议顺序，不把 Candidate 状态提前写成 Planned/Doing。

| 顺序 | 任务 | 当前状态 | 下一步 |
|------|------|----------|--------|
| 1 | REQ-041 Conversation/Message | 🟡 Doing | W1 与 E0/E1/B1 已合并；guarded DELETE/restore 已开放，新 Workspace submit-turn 保持关闭；下一步 A1 |
| 2 | REQ-047 Run/Event/Approval/Artifact | 🟣 Shaping（Core A1 Ready） | B1 已由 PR #485 合并；后续 A1/R1，HumanInput/Approval、Tool/Grant/Snapshot、Artifact/Evidence 继续独立塑形 |
| 2P | REQ-060 控制台导航 | ⚫ Candidate | 可独立并行补 spec/plan，收口重复 Skill、MCP/Skill 归位和 permission/nav 单一事实源 |
| 3 | REQ-042 Agent Workspace | ⚫ Candidate | 用 Direct RAG/Skill compatibility path 验收，不等待 Pi 才开始产品体验 |
| 4 | TD-085 边界收口 | ⚫ 待办 | 分 Slice 抽 LLM Port、Direct RAG 和业务专属逻辑，保持现有行为 |
| 5 | REQ-043 Runtime/Tool Gateway | ⚫ Candidate | 先 AgentTurnLoopRuntime/RuntimeProfile + Tool Gateway contract，再做 Pi read-only Pilot、L3 写恢复和 ACP/LangGraph Adapter |
| 6 | REQ-062 / APP-012 / APP-030 | ⚫ Candidate | Durable HITL/Sandbox 后完成动态采集发布闭环，再复用到会展招商 |
| 7 | REQ-061 / REQ-049 / APP-016 | ⚫ Candidate | 稳定控制面后建设长期记忆、主动任务和产业研究工作流 |

## Architecture Gate Decisions

| ID | 冻结值 | 影响 |
|----|--------|------|
| AG-1 | 内部 HTTP/JSON command + SSE event stream，终态独立查询 | 固定 V1 Worker contract 和断线/终态语义；Port 保留未来 gRPC 替换能力 |
| AG-2 | L0/L1 只读任务可共享 Worker；写操作、敏感租户、不可信 ACP、自定义文件/网络能力进入独立 Runtime Cell | 固定隔离与 fail-closed 默认值 |
| AG-3 | RunEvent 内联 JSON `<= 32 KiB` 且不高于 internal；大载荷/二进制/敏感内容外置；热重放 90 天，终态/审批/审计摘要 365 天 | 固定存储、归档和重放边界 |
| AG-4 | 256-bit opaque ToolGrant，默认 TTL 5 分钟、最大 15 分钟；写操作单次使用；预算 `reserve -> execute -> reconcile -> settle/release` | 固定短期授权、撤销和预算结算语义 |
| AG-5 | APP-005 保持 SkillRunner 生产基线并做只读 Agent 对照；APP-009 是首个新 Agent Pilot | 固定 Pilot 安全门槛，真实授权缺失只阻塞对应 Pilot |
| AG-6 | 首个 Slice 同时建立 `agent_workspace` 与 `agent_execution` 契约边界，`agent_memory` 后置 | 固定所有权和实施命名，不建立通用 `agent` context |
| AG-7 | 新 Agent Workspace 输入统一进入 AgentTurnLoopRuntime；Pi 默认绑定；切换 Runtime 新建 Binding | 固定零工具回答、queued/steer、Runtime 切换和旧入口兼容语义 |
| AG-8 | Worker SQLite spool + runtime_seq + ACK；写操作 prepare/approval/reserve/execute/reconcile/settle，未知结果禁止盲重试 | 固定至少一次事件投递和外部副作用恢复语义 |

## Product Decisions

| 决策 | 冻结值 | 影响 |
|------|--------|------|
| 园区第一个平台化样板 | APP-005 企业 360 背调；V0 状态保持 Done，优先接入统一 Control Plane/Workspace，并保留 SkillRunner 生产基线 | 决定背调 compatibility、Agent 只读对照 Rubric 和迁移边界 |
| 园区近期应用主线 | APP-005 -> APP-009 -> APP-012 -> APP-030 -> APP-016 | 固定业务顺序、首个闭环与数据授权门槛；APP-011 并入 016，APP-022 并入 012 |
| 首个新 Agent Pilot | APP-009 AI 载体选址 | 真实资产 Catalog + 授权地图/交通来源；输出多方案、硬约束、权衡和证据，不自动锁房 |
| 共享采集平台 | REQ-062 支撑 APP-012/030 | 先建 Campaign/FormSchemaVersion/Submission/ReportSnapshot 契约，ReportSnapshot 引用 AgentRun/Artifact，禁止两应用重复建设动态表单和运行状态机 |
| 外部数据治理 | REQ-063 支撑 APP-009/016 | 先确认来源授权、网络策略、SourceSnapshot 和新鲜度，再允许 Runtime 调用 |
| 教育复用样例 | 园区近期五应用主线形成闭环后再选择 | 不阻塞当前园区优先交付；用于后续跨行业复用验证 |

## Out of Scope

- 本迭代不创建 Agent Runtime Worker、不引入 Pi npm 依赖、不实现新 UI；后续 Core Slice 可按已签字联合 plan 独立落库。
- REQ-041 只有联合 spec/plan 完成后才可翻 Ready；REQ-047 只允许标 Core Ready，extended contracts 未完成前保持 Shaping；REQ-060 仍须先完成独立 spec/plan。
- 不更新 `ARCHITECTURE.md` 声称新 bounded context 已落地。
- 不引入 P4 的 Milvus、Neo4j、Elasticsearch、多模态或 HA 基础设施。

## Review

| 信号 | 结论 | 后续任务 |
|------|------|----------|
| 外部项目普遍把 live handle/approval/token 保存在内存 | 企业事实源必须落 MetaEduBase；内存 Registry 只能做缓存 | REQ-041 / REQ-047 |
| Pi 提供强 Agent Loop 但无企业权限/MCP/沙箱 | Pi 只能进入隔离 Worker，并通过 Tool Gateway 使用能力 | REQ-043 |
| Pi 队列和工具结果无法证明外部写入是否已发生 | Worker 增加 spool/ACK，写 Tool 必须 reconcile；未知结果进入 `outcome_unknown` | REQ-043 / REQ-047 |
| 现有 AIChatService/SkillRunner 已有边界倒置 | 不能先加第四条编排链；先 contract，再分 Slice 收口 | TD-085 |
| 菜单存在 Skill 重复和管理层级漂移 | REQ-060 可与持久化控制面并行，但不能展示未交付模块 | REQ-060 |
| 招商团队确认园区近期五应用，且与旧候选重叠 | 固定 APP-005/009/012/030/016；APP-011 并入 016，APP-022 并入 012；教育样例顺延 | APP-005/009/012/030/016 / REQ-062/063 |

## Evidence

- [P3 Milestone](../02-milestones/03-agent-platform-phase.md)
- [REQ-059 Requirement](../05-requirements/REQ-059-enterprise-agent-platform-kernel.md)
- [REQ-059 Source Study & Contract](../../02-delivery-plans/01-specs/2026-07-23-req-059-enterprise-agent-platform-control-plane.md)
- [REQ-041/047 Core Contract](../../02-delivery-plans/01-specs/2026-07-24-req-041-047-conversation-run-contract.md)
- [REQ-041/047 Core Plan](../../02-delivery-plans/02-plans/2026-07-24-req-041-047-conversation-run-contract-plan.md)
- [PR #475](https://github.com/MarkDanile/MetaEduBase/pull/475) / squash merge `132730a0`
- [Current Work](../../03-engineering-governance/current-work.md)
- [AI Delivery Routing Matrix](../../03-engineering-governance/03-matrices/agent-platform-ai-delivery-routing.md)
