# Product Planning — 产品规划入口

本目录是插件无关的产品规划事实源，用于承接里程碑、迭代、需求池和可交付需求。它位于 `docs/02-delivery-plans/01-specs/*` / `docs/02-delivery-plans/02-plans/*` 之前，不替代开发计划，也不替代外部项目管理系统。

## 四层关系

| 层级 | 事实源 | 内容边界 |
|------|--------|----------|
| Roadmap | `docs/01-product-planning/01-roadmap.md` | 里程碑、阶段目标、当前判断；不放详细需求 |
| Milestones | `docs/01-product-planning/02-milestones/*` | 单个里程碑详情；只在需要展开时创建 |
| Iteration | `docs/01-product-planning/03-iterations/*` | 当前和近期 1 到 2 个迭代；不做长期历史档案 |
| Backlog | `docs/01-product-planning/04-backlog.md` | 需求、Bug、技术债、文档和运营任务索引；不写完整 PRD |
| AI Applications | `docs/01-product-planning/06-ai-applications/*` | 真实 AI 应用组合、应用广场、教育类应用与后续行业场景验证包；不写交付计划 |
| Delivery | `docs/02-delivery-plans/01-specs/*` / `docs/02-delivery-plans/02-plans/*` / `docs/03-engineering-governance/current-work.md` | 进入交付后的需求、计划和当前执行状态 |

## 使用规则

- 需求池只记录清单和少量判断；详细需求进入 `docs/01-product-planning/05-requirements/REQ-xxx.md`。
- `docs/01-product-planning/06-ai-applications/*` 只管理应用组合视角。应用验证业务价值，P1 / P2 / P3 里程碑验证底座成熟度，两者是双轴关系。
- 已准备开发的复杂需求，再迁入或镜像到 `docs/02-delivery-plans/01-specs/*` 和 `docs/02-delivery-plans/02-plans/*`；进入交付后，以交付层 spec / plan 为开发依据。
- `docs/03-engineering-governance/current-work.md` 只记录当前执行窗口，不承载长期需求池。
- 外部系统如云效、Jira、TAPD 可写入 `External:` 字段；当前仓库 Markdown 仍是 AI IDE 交接事实源。
- 复盘、失败、Review 或交接发现的问题，进入 `docs/03-engineering-governance/04-retrospectives/*`，并转成可跟踪的 `REQ` / `BUG` / `TD` / `DOC` / `OPS` 条目。

## 状态流

| 状态 | 含义 |
|------|------|
| ⚪ Idea | 只有想法，未确认价值和边界 |
| ⚫ Candidate | 值得保留，尚未排期 |
| 🟣 Shaping | 正在澄清目标、范围、验收标准 |
| 🔵 Ready | 可进入 spec / plan 或近期迭代 |
| 🟡 Planned | 已放入迭代 |
| 🟡 Doing | 已进入当前执行窗口 |
| 🔴 Blocked | 有明确外部依赖、环境阻塞或决策阻塞 |
| 🟢 Done | 已交付或关闭 |
| ⚪ Dropped | 明确不做，保留原因 |
| ⚪ Future | 远期候选，只保留方向，不进入近期排期 |

状态名是事实源，颜色只用于快速扫视。产品规划层表格和 `Status:` 字段应使用 `颜色 状态名` 格式，例如 `⚫ Candidate`。

## 编号

| 类型 | 示例 | 说明 |
|------|------|------|
| REQ | `REQ-001` | 产品需求或能力建设 |
| APP | `APP-001` | 真实 AI 应用组合或应用广场条目 |
| BUG | `BUG-001` | 缺陷、回归、异常 |
| TD | `TD-001` | 技术债，详情仍以 `docs/03-engineering-governance/technical-debt.md` 为准 |
| DOC | `DOC-001` | 文档、流程、规则治理 |
| OPS | `OPS-001` | 运营、发布、环境或非代码交付任务 |

编号稳定后不重排。外部系统编号不替代仓库编号，只记录到 `External`。
