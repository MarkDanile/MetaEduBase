# Product Roadmap — 产品路线图

本文件只记录里程碑和阶段目标，帮助快速判断“项目往哪里走”。详细需求进入 `docs/01-product-planning/04-backlog.md` 或 `docs/01-product-planning/05-requirements/*`，实施计划进入 `docs/02-delivery-plans/02-plans/*`。

## 当前里程碑阶段

| 里程碑阶段 | 状态 | 阶段目标 | 详情 |
|------------|------|----------|------|
| P1 阶段一：验证期 | 🟡 Doing | 在 PostgreSQL 单引擎 + 最少基础设施依赖下，验证 RAG 问答链路和文档抽取链路。 | [P1 Validation Phase](02-milestones/01-validation-phase.md) |
| P2 阶段二：增长期 | ⚫ Candidate | 在不引入过早复杂度的前提下，提升召回质量、抽取质量与系统稳定性。 | [P2 Growth Phase](02-milestones/02-growth-phase.md) |
| P3 阶段三：规模化 | ⚪ Future | 按容量、性能、可用性和质量瓶颈触发升级，逐项演进到多引擎、多模态和可观测能力。 | [P3 Scale Phase](02-milestones/03-scale-phase.md) |

## 路线图规则

- 本文件只记录三阶段路线图，不承载功能清单、技术债清单或实施步骤。
- 阶段详情进入 `docs/01-product-planning/02-milestones/*`，并按“产品能力 / 检索与抽取质量 / 基础设施”三条轨道维护。
- 具体需求进入 backlog、requirement、spec 或 plan；状态变化应能追溯到 backlog、iteration、spec、plan、PR 或复盘。
- 外部项目管理系统上线后，在对应里程碑或 backlog 条目中增加 `External:`，不把外部系统截图或长文本复制进仓库。
