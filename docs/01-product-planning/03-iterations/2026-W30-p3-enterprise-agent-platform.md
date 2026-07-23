# Iteration 2026-W30: P3 企业 Agent 平台控制面塑形

Status: 🟡 Doing
Dates: 2026-07-20 ~ 2026-07-26
Goal: 完成 P2 -> P3 路线切换，冻结企业 Agent Control Plane、源码依据、任务依赖顺序和园区优先的首批 Pilot 边界，为 REQ-041/047 contract-first 设计建立开工门禁。

## Committed Scope

| ID | 类型 | 状态 | 摘要 | 本迭代退出条件 |
|----|------|------|------|----------------|
| REQ-059 | REQ | 🟣 Shaping | 企业级可控 Agent 平台内核与 Runtime 中立控制面 | 源码研究、Context Map、命名、Runtime/RunEvent/ToolGrant 契约和 P3 里程碑已沉淀；六项待决策有明确选择或进入独立 Spike |

## Ready Queue

本表只表示 REQ-059 通过 Architecture Gate 后的建议顺序，不把 Candidate 状态提前写成 Planned/Doing。

| 顺序 | 任务 | 当前状态 | 下一步 |
|------|------|----------|--------|
| 1 | REQ-041 Conversation/Message | ⚫ Candidate | 与 REQ-047 联合补数据关系、删除/保留、幂等和 API spec，先实施产品会话事实源 |
| 2 | REQ-047 Run/Event/Approval/Artifact | ⚫ Candidate | 冻结状态机、seq、terminal result、SSE replay 和持久化审批，紧随 REQ-041 实施 |
| 2P | REQ-060 控制台导航 | ⚫ Candidate | 可独立并行补 spec/plan，收口重复 Skill、MCP/Skill 归位和 permission/nav 单一事实源 |
| 3 | REQ-042 Agent Workspace | ⚫ Candidate | 用 Direct RAG/Skill compatibility path 验收，不等待 Pi 才开始产品体验 |
| 4 | TD-085 边界收口 | ⚫ 待办 | 分 Slice 抽 LLM Port、Direct RAG 和业务专属逻辑，保持现有行为 |
| 5 | REQ-043 Runtime/Tool Gateway | ⚫ Candidate | 先 contract + Tool Gateway，再 Pi read-only Pilot，最后 ACP/沙箱硬化 |
| 6 | REQ-061 / REQ-049 | ⚫ Candidate | 稳定控制面后建设长期记忆，再增加主动任务和事件触发 |

## Decisions Required

| 决策 | 推荐默认值 | 影响 |
|------|------------|------|
| Control Plane -> Node Worker 传输 | 首期 HTTP command + SSE/NDJSON event Spike，保留替换为 gRPC 的 Port | 决定 Worker contract 和故障语义，不影响产品实体 |
| Runtime 隔离 | 低风险只读共享 Worker 池；高风险/写任务独立 Runtime Cell | 决定部署成本和故障域 |
| RunEvent Payload | 小事件入 PG，大 Tool Result/Artifact 外置对象存储并存 ref/digest | 决定表膨胀、审计和重放 |
| Tool Grant | 服务端 opaque token，Run/runtime epoch/operation/TTL 绑定并可撤销 | 决定 Runtime 不持有长期凭证的实现 |
| 园区第一个平台化样板 | APP-005 企业 360 背调；V0 状态保持 Done，优先接入统一 Control Plane/Workspace，并保留 SkillRunner 生产基线 | 决定背调 compatibility、Agent 只读对照 Rubric 和迁移边界 |
| 园区近期应用主线 | APP-005 -> APP-009 -> APP-012 -> APP-030 -> APP-016 | 固定业务顺序、首个闭环与数据授权门槛；APP-011 并入 016，APP-022 并入 012 |
| 首个新 Agent Pilot | APP-009 AI 载体选址 | 真实资产 Catalog + 授权地图/交通来源；输出多方案、硬约束、权衡和证据，不自动锁房 |
| 共享采集平台 | REQ-062 支撑 APP-012/030 | 先建 Campaign/FormSchemaVersion/Submission/ReportSnapshot 契约，ReportSnapshot 引用 AgentRun/Artifact，禁止两应用重复建设动态表单和运行状态机 |
| 外部数据治理 | REQ-063 支撑 APP-009/016 | 先确认来源授权、网络策略、SourceSnapshot 和新鲜度，再允许 Runtime 调用 |
| 教育复用样例 | 园区近期五应用主线形成闭环后再选择 | 不阻塞当前园区优先交付；用于后续跨行业复用验证 |

## Out of Scope

- 本迭代不创建 Agent Runtime Worker、不引入 Pi npm 依赖、不实现数据库表或新 UI。
- 不把 REQ-041/047/060 从 Candidate 提前翻 Ready；必须先完成各自交付 spec/plan。
- 不更新 `ARCHITECTURE.md` 声称新 bounded context 已落地。
- 不引入 P4 的 Milvus、Neo4j、Elasticsearch、多模态或 HA 基础设施。

## Review

| 信号 | 结论 | 后续任务 |
|------|------|----------|
| 外部项目普遍把 live handle/approval/token 保存在内存 | 企业事实源必须落 MetaEduBase；内存 Registry 只能做缓存 | REQ-041 / REQ-047 |
| Pi 提供强 Agent Loop 但无企业权限/MCP/沙箱 | Pi 只能进入隔离 Worker，并通过 Tool Gateway 使用能力 | REQ-043 |
| 现有 AIChatService/SkillRunner 已有边界倒置 | 不能先加第四条编排链；先 contract，再分 Slice 收口 | TD-085 |
| 菜单存在 Skill 重复和管理层级漂移 | REQ-060 可与持久化控制面并行，但不能展示未交付模块 | REQ-060 |
| 招商团队确认园区近期五应用，且与旧候选重叠 | 固定 APP-005/009/012/030/016；APP-011 并入 016，APP-022 并入 012；教育样例顺延 | APP-005/009/012/030/016 / REQ-062/063 |

## Evidence

- [P3 Milestone](../02-milestones/03-agent-platform-phase.md)
- [REQ-059 Requirement](../05-requirements/REQ-059-enterprise-agent-platform-kernel.md)
- [REQ-059 Source Study & Contract](../../02-delivery-plans/01-specs/2026-07-23-req-059-enterprise-agent-platform-control-plane.md)
- [Current Work](../../03-engineering-governance/current-work.md)
