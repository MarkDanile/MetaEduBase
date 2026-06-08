# AGENTS.md

本文件是跨 AI IDE 的仓库入口，只保留导航和开工顺序。规则正文以 `docs/` 下的事实源为准，不在入口文件复制第二份。

## 开工顺序

1. 先读 `docs/03-engineering-governance/current-work.md`，确认当前任务、候选任务、验证状态和下一步。
2. 只要会修改仓库文件，先确认不在 `main`；若在 `main`，按 `docs/03-engineering-governance/01-rules/git-workflow.md#开发前分支门禁` 创建任务分支后再改文件。
3. 按任务类型进入 `docs/03-engineering-governance/task-modes.md`，再渐进式读取对应 spec、plan、技术债、需求或架构约束。
4. 涉及 plan-do、superpower、compound-engineering-plugin 或其他 AI IDE/插件交接时，读取 `docs/03-engineering-governance/workflow.md`。
5. 使用插件生成 spec/plan 时，插件目录只作为兼容输出；交付依据必须迁移或镜像到 `docs/02-delivery-plans/01-specs/*` / `docs/02-delivery-plans/02-plans/*`。
6. 提交、PR、合并或声明完成前，执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`；完整 Git 闭环按 `docs/03-engineering-governance/01-rules/git-workflow.md#快速交付通道`。

## 核心事实源

| File | Content |
|------|---------|
| [current-work.md](docs/03-engineering-governance/current-work.md) | 当前开发工作台、任务入口、交接状态 |
| [docs/README.md](docs/README.md) | 文档体系总入口与分层目录说明 |
| [product planning](docs/01-product-planning/README.md) | 里程碑、迭代、需求池、AI 应用组合入口 |
| [delivery specs](docs/02-delivery-plans/01-specs/README.md) | 插件无关的需求、设计和验收标准目录约定 |
| [delivery plans](docs/02-delivery-plans/02-plans/README.md) | 插件无关的实施计划和任务拆分目录约定 |
| [workflow.md](docs/03-engineering-governance/workflow.md) | 跨 AI IDE / 插件开发流程、计划来源、收尾规范 |
| [task-modes.md](docs/03-engineering-governance/task-modes.md) | 任务模式入口、默认模式路由与各模式完成标准 |
| [technical-debt.md](docs/03-engineering-governance/technical-debt.md) | 技术债总账、定期复盘规范、任务状态流 |
| [work-log.md](docs/03-engineering-governance/work-log.md) | 已完成任务长期索引 |
| [review-scorecard.md](docs/03-engineering-governance/01-rules/review-scorecard.md) | 任务评审评分卡、follow-up 分流和规则改进判断 |

## 工程规则索引

| File | Content |
|------|---------|
| [architecture.md](docs/03-engineering-governance/01-rules/architecture.md) | 架构实现约束、上下文划分、核心流转与修改边界 |
| [coding-style.md](docs/03-engineering-governance/01-rules/coding-style.md) | 命名、格式、设计系统、共享组件 |
| [testing.md](docs/03-engineering-governance/01-rules/testing.md) | 测试策略、环境隔离、稳定入口与 mock 边界 |
| [local-development.md](docs/03-engineering-governance/01-rules/local-development.md) | 本地开发入口、场景化命令与数据库初始化边界 |
| [quality-gates.md](docs/03-engineering-governance/01-rules/quality-gates.md) | 验证矩阵、完成门禁、收尾记录模板 |
| [contracts.md](docs/03-engineering-governance/01-rules/contracts.md) | 契约所有权、变更边界、同步步骤与验证基线 |
| [git-workflow.md](docs/03-engineering-governance/01-rules/git-workflow.md) | 分支、提交、PR、合并流程 |
| [security.md](docs/03-engineering-governance/01-rules/security.md) | 鉴权、注入防护、密钥管理 |
| [data-integrity.md](docs/03-engineering-governance/01-rules/data-integrity.md) | 级联删除、孤儿数据清理 |
| [docs.md](docs/03-engineering-governance/01-rules/docs.md) | 文档同步、注释约定、链接维护 |
| [workbench.md](docs/03-engineering-governance/01-rules/workbench.md) | current-work 保留策略和状态维护 |

## 兼容入口

`.claude/rules/*` 与 `.trae/rules/*` 只保留 IDE 兼容跳转，不维护规则正文。历史插件输出保留在 `docs/90-compat-legacy/*`，不得作为新的唯一交付事实源。
