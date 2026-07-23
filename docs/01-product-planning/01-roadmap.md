# Product Roadmap — 产品路线图

本文件只记录里程碑和阶段目标，帮助快速判断“项目往哪里走”。详细需求进入 `docs/01-product-planning/04-backlog.md` 或 `docs/01-product-planning/05-requirements/*`，实施计划进入 `docs/02-delivery-plans/02-plans/*`。

## 当前里程碑阶段

| 里程碑阶段 | 状态 | 阶段目标 | 详情 |
|------------|------|----------|------|
| P1 阶段一：验证期 | 🟢 Done | 在 PostgreSQL 单引擎 + 最少基础设施依赖下，验证 RAG 问答链路和文档抽取链路。 | [P1 Validation Phase](02-milestones/01-validation-phase.md) |
| P2 阶段二：增长期 | 🟢 Done | 完成 Retrieval Optimization、真实效果评测、MCP/Skill、智能问数和首个园区业务闭环，为 Agent 平台提供可治理能力资产。 | [P2 Growth Phase](02-milestones/02-growth-phase.md) |
| P3 阶段三：企业 Agent 平台化 | 🟡 Doing | 以园区应用为优先落地纵向，将现有 AI Chat、RAG、MCP、Skill 和业务应用升级为可会话、可规划、可调用工具、可审批、可恢复、可审计的企业级 Agent Harness。 | [P3 Enterprise Agent Platform](02-milestones/03-agent-platform-phase.md) |
| P4 阶段四：规模化与多模态 | ⚪ Future | 在 Agent 平台和真实应用证明价值后，按容量、性能、可用性和多模态需求逐项升级基础设施。 | [P4 Scale Phase](02-milestones/04-scale-phase.md) |

## 路线图规则

- 本文件只记录阶段路线图，不承载功能清单、技术债清单或实施步骤。
- P3 以企业 Agent 控制面、Workspace、Runtime、安全治理和真实应用为主线；多引擎、多模态和容量扩展进入 P4，避免基础设施目标压过产品目标。
- P3 的 AI 应用开发采用园区优先顺序：APP-005 企业 360 背调 -> APP-009 AI 载体选址 -> APP-012 招商动态报表 AI 生成 -> APP-030 会展招商 AI 工具 -> APP-016 产业研究辅助平台。APP-011/022 已并入主线应用，不重复立项；教育应用在园区近期主线后进入跨行业复用验证。
- 阶段详情进入 `docs/01-product-planning/02-milestones/*`，各阶段按自身目标维护轨道，不强制套用同一技术分类。
- 具体需求进入 backlog、requirement、spec 或 plan；状态变化应能追溯到 backlog、iteration、spec、plan、PR 或复盘。
- 外部项目管理系统上线后，在对应里程碑或 backlog 条目中增加 `External:`，不把外部系统截图或长文本复制进仓库。
