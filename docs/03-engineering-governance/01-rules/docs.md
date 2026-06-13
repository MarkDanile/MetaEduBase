# Docs — 文档规范

本文件记录文档归属、同步边界和注释规则。入口文件只导航，不复制规则正文。

## 文档结构

| 类型 | 位置 |
|------|------|
| AI IDE 入口 | `AGENTS.md` / `CLAUDE.md` / `.claude/rules/*` / `.trae/rules/*` |
| 文档总入口 | `docs/README.md` |
| 产品规划 | `docs/01-product-planning/*` |
| 交付 spec / plan | `docs/02-delivery-plans/01-specs/*` / `02-plans/*` |
| 当前工作台 | `docs/03-engineering-governance/current-work.md` |
| 技术债总账 | `docs/03-engineering-governance/technical-debt.md` |
| 工作日志 | `docs/03-engineering-governance/work-log.md` |
| 跨 AI 流程 | `docs/03-engineering-governance/workflow.md` |
| 任务模式 | `docs/03-engineering-governance/task-modes.md` |
| 工程规则 | `docs/03-engineering-governance/01-rules/*` |
| 基线 / 矩阵 / 复盘 | `02-baselines/*` / `03-matrices/*` / `04-retrospectives/*` |
| 历史插件输出 | `docs/90-compat-legacy/superpowers/*` |

## 文档更新规则

| 变化 | 同步位置 |
|------|----------|
| API / DTO / shared schema | `contracts.md`；系统级边界变化才改 `ARCHITECTURE.md` |
| models / migration / 数据所有权 | `contracts.md`、`data-integrity.md`；上下文边界变化才改 `ARCHITECTURE.md` |
| 本地命令 / 配置入口 | `local-development.md`；最短启动路径变化才改 `README.md` |
| 质量门禁 / 验证策略 | `quality-gates.md` + `scripts/engineering/*` |
| 任务模式 / 开工条件 | `task-modes.md` + `workflow.md` |
| Git / PR / 合并流程 | `git-workflow.md` + `workflow.md` |
| 产品路线图 / 需求池 | `docs/01-product-planning/*` |
| 复盘 / 纠正动作 | `04-retrospectives/*` + 对应 `REQ` / `BUG` / `TD` / `DOC` |
| 纯前端 UI 变更且无契约影响 | 通常无需更新顶层文档 |

## 任务池文档边界

- Backlog、technical-debt、work-log、review-score-log 只做索引和摘要，不承载长设计。
- `work-log.md` 和 `review-score-log.md` 最新在上。
- Backlog 和 technical-debt 新增条目按稳定编号追加，不为插入一行频繁重排大表。
- 详细内容进入 requirement、spec、plan、PR 或 retrospective。

## 注释规范

- 只写 WHY，不写显而易见的 WHAT。
- 不添加空泛 docstring。
- 复杂业务逻辑用短注释说明决策原因。
- TODO 必须说明原因和后续归属；能入账的进入 `REQ` / `BUG` / `TD` / `DOC`。

## 顶层文档原则

- `README.md` 记录项目定位、能力概览、仓库导航、最小启动路径。
- `ARCHITECTURE.md` 记录系统边界、关键流转、质量属性、演进方向。
- API 清单、数据库字段、固定测试数量、一次性迁移命令不要堆进顶层文档。
- 更新频率高于“系统边界变化”的内容，通常不属于 `ARCHITECTURE.md`。

## 工作模式

| 任务类型 | 模式 |
|----------|------|
| Bug fix、小功能、UI 调整 | Plan-Do |
| 未塑形新需求、里程碑拆解 | Product Planning |
| >3 文件、Schema 变更、新端点 | Spec / Plan |

任何模式都必须按 `current-work.md` 维护当前状态。插件生成的 spec/plan 只能作为草稿来源；任务卡片的 `Spec` / `Plan` 字段必须指向交付层规范副本。

## 禁止项

- 入口文件复制规则正文。
- 把一次性任务流水塞进 `workflow.md`。
- 把完整 PRD 塞进 Backlog。
- 把完整交付日志塞进 `current-work.md`。
- 留下断链、旧路径或交付状态占位。
