# Product Roadmap — 产品路线图

本文件只记录里程碑和阶段目标，帮助快速判断“项目往哪里走”。详细需求进入 `docs/01-product-planning/04-backlog.md` 或 `docs/01-product-planning/05-requirements/*`，实施计划进入 `docs/02-delivery-plans/02-plans/*`。

## 当前里程碑

| 里程碑 | 状态 | 目标 | 主要事实源 |
|--------|------|------|------------|
| M1 知识资产处理平台 | Doing | 打通文件、数据集、分块、抽取、索引和知识图谱的核心链路。 | `ARCHITECTURE.md` / `docs/90-compat-legacy/superpowers/specs/2026-05-15-document-pipeline-design.md` |
| M2 模板化结构抽取平台 | Candidate | 用数据要素模板沉淀可复用抽取能力，降低手工结构化成本。 | `docs/90-compat-legacy/superpowers/plans/2026-05-27-structured-template-plan.md` |
| M3 前端设计系统与多主题语义层 | Doing | 用 `ui-*` 语义层收敛历史 `liquid-*` 样式，稳定跨页面体验。 | `docs/03-engineering-governance/work-log.md#2026-06-05-设计系统迁移liquid--ui-` |
| M4 工程治理与跨 AI 工作流 | Doing | 让 Codex、Claude Code、superpower、Trae 等工具共享同一套事实源、规则和交付闭环。 | `docs/03-engineering-governance/workflow.md` / `docs/03-engineering-governance/01-rules/*` |
| M5 架构演进与技术债收敛 | Candidate | 持续降低契约漂移、测试环境、数据完整性和大文件复杂度风险。 | `docs/03-engineering-governance/technical-debt.md` |
| M6 工程协作规则模板化 | Future | 当本项目规则经过长期实践验证后，抽象为可迁移的工程协作规则模板包，支持快速应用到新项目。 | `docs/01-product-planning/04-backlog.md#backlog` |

## 路线图规则

- 本文件不记录每个需求的完整描述。
- 状态变化应能追溯到 backlog、iteration、spec、plan、PR 或复盘。
- 当一个里程碑需要展开细节时，在 `docs/01-product-planning/02-milestones/` 新建独立文件，并在本表链接。
- 外部项目管理系统上线后，在对应里程碑或 backlog 条目中增加 `External:`，不把外部系统截图或长文本复制进仓库。
