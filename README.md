# MetaEduBase

AI Native 职业教育知识基座。

MetaEduBase 面向职业教育场景，围绕知识资产的采集、处理、组织和消费构建统一平台。这个仓库的顶层文档遵循长期性原则：`README.md` 负责提供稳定入口和导航，不承担高频变化的实现细节。

## 项目定位

这个项目关注的不是单点 AI 能力，而是一整条知识资产生命周期：

1. 采集知识资产：文件、数据集、模板
2. 处理知识资产：解析、分块、抽取、索引、图谱构建
3. 组织知识资产：知识树、知识图谱、模板语义
4. 消费知识资产：搜索、问答、管理和复用

如果你是第一次进入仓库，这份文档应该帮助你快速回答两件事：

- 这个系统大致是什么
- 接下来应该读哪一份文档

## 核心能力

- 知识库与层级知识图谱管理
- 文档上传、解析、分块、索引与知识抽取
- Excel / CSV 数据集导入与结构化知识处理
- 基于检索增强生成的 AI 问答
- 数据要素模板管理与 AI 初始化
- 多租户隔离下的教学知识资产协作
- 面向 AI IDE 协作的任务、计划与交付规范

## 系统快照

| 组件 | 位置 | 职责 |
|------|------|------|
| Web App | `packages/web` | Vue 前端应用，承载知识库、资源库、数据集、模板和管理界面 |
| Backend API | `packages/server-python` | FastAPI 后端，负责认证、领域服务、异步任务编排和数据访问 |
| Shared Contracts | `packages/shared` | 前端共享 schema / type / helper，减少契约漂移 |
| MCP Server | `packages/mcp-server` | 面向外部 AI 工具的知识操作接口 |

基础设施默认围绕 PostgreSQL、Redis 和对象存储展开。更长期的系统边界、上下文划分和关键流转，请继续读 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 仓库导航

### 项目与架构

| 你想了解 | 先读这里 |
|----------|----------|
| 系统目标、边界、上下文、关键流程 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 架构实现约束、上下文目录、跨模块边界 | [docs/engineering/rules/architecture.md](docs/engineering/rules/architecture.md) |
| 本地启动、测试库初始化、常用命令 | [docs/engineering/rules/local-development.md](docs/engineering/rules/local-development.md) |
| 测试策略与环境约束 | [docs/engineering/rules/testing.md](docs/engineering/rules/testing.md) |
| API / DTO / shared schema 契约规则 | [docs/engineering/rules/contracts.md](docs/engineering/rules/contracts.md) |

### 工程协作

| 你要做什么 | 先读这里 |
|------------|----------|
| 接手当前任务、看交接状态 | [docs/engineering/current-work.md](docs/engineering/current-work.md) |
| 理解跨 IDE / 插件协作方式 | [docs/engineering/workflow.md](docs/engineering/workflow.md) |
| 按任务类型选择开工与验收方式 | [docs/engineering/task-modes.md](docs/engineering/task-modes.md) |
| 查看技术债总账与优先级 | [docs/engineering/technical-debt.md](docs/engineering/technical-debt.md) |
| 查看完成门禁与验证矩阵 | [docs/engineering/rules/quality-gates.md](docs/engineering/rules/quality-gates.md) |
| 了解 Git 提交、PR 与合并流程 | [docs/engineering/rules/git-workflow.md](docs/engineering/rules/git-workflow.md) |

### 需求与计划事实源

| 文档类型 | 位置 |
|----------|------|
| 长期需求 / 验收标准 | [docs/specs/](docs/specs/README.md) |
| 长期实施计划 / 任务拆分 | [docs/plans/](docs/plans/README.md) |
| 历史 superpower 兼容输出 | `docs/superpowers/*` |

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 20+
- pnpm 9+
- PostgreSQL、Redis 和对象存储的本地开发环境

如果你不确定如何准备本地依赖，直接阅读 [docs/engineering/rules/local-development.md](docs/engineering/rules/local-development.md)。那里是运行命令和环境说明的事实源。

### 最短启动路径

```bash
git clone https://github.com/MarkDanile/MetaEduBase.git
cd MetaEduBase
pnpm install
cd packages/server-python && make install && cd ../..

./dev.sh init-db
./dev.sh
```

启动后默认访问：

- Web: `http://localhost:3000`
- API Docs: `http://localhost:8000/docs`

默认开发账号、测试库初始化、日志查看、分服务启动和其他命令统一见 [docs/engineering/rules/local-development.md](docs/engineering/rules/local-development.md)。

## 开发与 AI 协作入口

这个仓库默认按“仓库文档是事实源，插件只是执行工具”来协作。

开始任何开发任务前：

1. 先读 [docs/engineering/current-work.md](docs/engineering/current-work.md)
2. 若涉及交接、plan-do、superpower 或其他 AI IDE，再读 [docs/engineering/workflow.md](docs/engineering/workflow.md)
3. 若任务属于技术债，继续读 [docs/engineering/technical-debt.md](docs/engineering/technical-debt.md)

`AGENTS.md`、`CLAUDE.md` 和其他 IDE 兼容目录都应把共享规则指回 `docs/engineering/*`，而不是各自维护第二份事实源。

## 部署与运行细节

- 容器与部署配置位于 `deploy/`
- 本地启动与测试命令见 `docs/engineering/rules/local-development.md`
- 质量门禁与收尾要求见 `docs/engineering/rules/quality-gates.md`

顶层文档只保留稳定入口。高频变化的命令、门禁和实现细节，统一收敛到 `docs/engineering/*` 和代码本身。

## License

MIT
