# AGENTS.md

## 核心原则

**Tradeoff:** 谨慎优先于速度。对于简单任务，请自行判断。

开始任何开发任务前，先阅读 `docs/03-engineering-governance/current-work.md`，确认当前任务、相关计划、架构约束、验证状态和下一步。若任务涉及 plan-do、superpower、compound-engineering-plugin 或其他 AI IDE/插件交接，继续阅读 `docs/03-engineering-governance/workflow.md`。

只要任务会修改仓库文件，先确认当前不在 `main`；若在 `main`，按 `docs/03-engineering-governance/01-rules/git-workflow.md#开发前分支门禁` 创建任务分支后，再更新工作台、spec、plan 或代码。

使用 superpower、compound-engineering-plugin 或其他插件生成 spec/plan 时，不要假设插件能自动识别仓库新路径；本次开发依据必须迁移或镜像到 `docs/02-delivery-plans/01-specs/*` / `docs/02-delivery-plans/02-plans/*`，并在任务卡片中记录原始插件输出。

提交、PR、合并或声明任务完成前，执行 `docs/03-engineering-governance/01-rules/quality-gates.md#完成门禁`；完整 Git 闭环按 `docs/03-engineering-governance/01-rules/git-workflow.md#快速交付通道` 执行。PR 链接是默认交付事实源，禁止把最终回复当作事实源。

当任务涉及技术债记录、技术债复盘、工程治理、重构优先级或质量门禁时，先阅读 `docs/03-engineering-governance/technical-debt.md`，并以其中的状态流、任务模板和复盘规范为准。

当任务涉及里程碑、迭代、需求池或需求塑形时，先阅读 `docs/01-product-planning/README.md`，再按需进入 roadmap、backlog、requirement、spec 或 plan。

`docs/01-product-planning/*` 用于管理项目规划；进入开发后，交付层 spec / plan 与工程治理层验证闭环仍是重中之重。

### 1. 先想后写
**不要假设。不要隐藏困惑。呈现权衡。**

- 明确陈述假设。不确定时提问。
- 存在多种解读时全部呈现，不静默选择。
- 有更简单方案就说出来。有理由时反驳。
- 有不清楚的地方，停下来。说出困惑所在。

### 2. 极简主义
**解决问题的最少代码。不投机性扩展。**

- 不做超出请求的功能。
- 单次使用不抽象。
- 不做没被要求的"灵活性"或"可配置性"。
- 不处理不可能发生的错误场景。
- 如果写了 200 行而可以用 50 行完成，重写。

自问："高级工程师会说这过于复杂吗？"如果是，简化。

### 3. 手术式改动
**只改必须改的。只清理自己的烂摊子。**

- 不"改善"相邻代码、注释或格式。
- 不重构没坏的东西。
- 匹配现有风格，即使你会用不同方式写。
- 注意到无关的死代码时，说明它——不要删除。

当变更造成孤儿代码时：
- 移除你的变更导致不再使用的 imports/变量/函数。
- 不要移除已有的死代码，除非被要求。

检验标准：每行变更都能追溯到用户需求。

### 4. 目标驱动
**定义成功标准。循环直到验证。**

将任务转化为可验证目标：
- "添加验证" → "为无效输入写测试，然后让测试通过"
- "修复 bug" → "写一个能复现它的测试，然后让测试通过"
- "重构 X" → "确保测试前后都通过"

多步任务先简述计划：
```
1. [步骤] → 验证: [检查方式]
2. [步骤] → 验证: [检查方式]
3. [步骤] → 验证: [检查方式]
```

强成功标准让你独立循环。弱标准（"让它工作"）需要不断确认。

---

**检验原则是否有效：** diff 中不必要的变更更少，重写由于过度复杂化更少，澄清问题在错误之前而非之后出现。

## Rules Index

| File | Content |
|------|---------|
| [current-work.md](docs/03-engineering-governance/current-work.md) | 当前开发工作台、任务入口、交接状态 |
| [docs/README.md](docs/README.md) | 文档体系总入口与分层目录说明 |
| [workflow.md](docs/03-engineering-governance/workflow.md) | 跨 AI IDE / 插件开发流程、计划来源、收尾规范 |
| [task-modes.md](docs/03-engineering-governance/task-modes.md) | 任务模式入口、默认模式路由与各模式完成标准 |
| [technical-debt.md](docs/03-engineering-governance/technical-debt.md) | 技术债总账、定期复盘规范、任务状态流 |
| [product/README.md](docs/01-product-planning/README.md) | 产品规划、路线图、迭代和需求池目录约定 |
| [specs/README.md](docs/02-delivery-plans/01-specs/README.md) | 插件无关的需求、设计和验收标准目录约定 |
| [plans/README.md](docs/02-delivery-plans/02-plans/README.md) | 插件无关的实施计划和任务拆分目录约定 |
| [retrospectives/README.md](docs/03-engineering-governance/03-retrospectives/README.md) | 复盘、根因分析和纠正动作追踪 |
| [architecture.md](docs/03-engineering-governance/01-rules/architecture.md) | 架构实现约束、上下文划分、核心流转与修改边界 |
| [coding-style.md](docs/03-engineering-governance/01-rules/coding-style.md) | Naming, formatting, design tokens, shared components |
| [testing.md](docs/03-engineering-governance/01-rules/testing.md) | 测试策略、环境隔离、稳定入口与 mock 边界 |
| [local-development.md](docs/03-engineering-governance/01-rules/local-development.md) | 本地开发入口、场景化命令与数据库初始化边界 |
| [quality-gates.md](docs/03-engineering-governance/01-rules/quality-gates.md) | 验证矩阵、完成门禁、收尾记录模板 |
| [contracts.md](docs/03-engineering-governance/01-rules/contracts.md) | 契约所有权、变更边界、同步步骤与验证基线 |
| [git-workflow.md](docs/03-engineering-governance/01-rules/git-workflow.md) | Branches, commits, PR flow |
| [security.md](docs/03-engineering-governance/01-rules/security.md) | Auth, injection prevention, secrets |
| [data-integrity.md](docs/03-engineering-governance/01-rules/data-integrity.md) | Cascade delete, orphan cleanup |
| [docs.md](docs/03-engineering-governance/01-rules/docs.md) | Doc sync rules, comment conventions |
| [Legacy PRD](docs/90-compat-legacy/superpowers/specs/2026-05-15-document-pipeline-design.md) | Historical superpower document pipeline spec |
