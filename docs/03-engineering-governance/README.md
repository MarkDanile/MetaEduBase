# Engineering Governance — 工程治理入口

本目录是跨 AI IDE、工程规则、质量门禁、技术债和复盘的事实源。开始开发任务时，优先从 `current-work.md` 进入，再按任务类型渐进式读取相关规则。

## 核心入口

| 文件 / 目录 | 说明 |
|-------------|------|
| [current-work.md](current-work.md) | 当前开发工作台、任务入口和交接状态 |
| [workflow.md](workflow.md) | 跨 AI IDE / 插件开发流程 |
| [task-modes.md](task-modes.md) | 默认模式路由、开工条件和完成标准 |
| [technical-debt.md](technical-debt.md) | 技术债总账和优先级 |
| [work-log.md](work-log.md) | 已完成任务的一行式历史索引 |
| [01-rules](01-rules/docs.md) | 长期工程规则；基础原则见 [engineering-principles.md](01-rules/engineering-principles.md) |
| [02-matrices](02-matrices/) | 行为等价矩阵和验证矩阵 |
| [03-retrospectives](03-retrospectives/README.md) | 复盘、根因分析和纠正动作 |

## 使用规则

- 当前任务状态只维护在 `current-work.md`。
- 长期规则放在 `01-rules/`，不要复制到 IDE 私有目录。
- 技术债、复盘和 follow-up 必须形成稳定编号，不能只停留在聊天记录。
- 提交、PR、合并或声明完成前，执行 `01-rules/quality-gates.md#完成门禁`。
