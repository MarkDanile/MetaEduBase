# Local Development — 本地开发入口

本文件记录 MetaEduBase 的本地开发主入口、常见场景命令、数据库初始化边界和环境阻塞记录方式。它服务的是“如何稳定进入开发状态”，而不是解释脚本内部实现细节。

Git 流程见 `docs/03-engineering-governance/01-rules/git-workflow.md`，验证矩阵见 `docs/03-engineering-governance/01-rules/quality-gates.md`。

## 这份文档回答什么

- 本地开发优先从哪个命令入口开始
- 常见开发场景对应哪些稳定命令
- 开发库和测试库分别如何初始化
- 后端 / 前端 / shared 常用命令是什么
- 环境出问题时该怎么记录

## 主入口原则

### 优先使用稳定入口，而不是临时手拼命令

仓库对本地开发提供两个长期稳定入口：

1. 根目录 `./dev.sh`
2. `packages/server-python/Makefile`

默认优先级：

- 启动和管理本地开发环境：优先 `./dev.sh`
- 后端局部开发、迁移、测试和 lint：优先 `Makefile`
- 前端和 shared 包命令：优先 `pnpm --filter ...`

## 常见开发场景

### 1. 启动完整本地开发环境

```bash
./dev.sh init-db
./dev.sh
```

适用场景：

- 新环境首次进入项目
- 开发库尚未初始化
- 需要启动基础设施 + 后端 + 前端

### 2. 只启动或恢复基础设施

```bash
./dev.sh infra
./dev.sh status
```

适用场景：

- PostgreSQL / Redis / 对象存储尚未启动
- 想先确认基础设施状态，再决定是否启动应用层

### 3. 重启单个开发服务

```bash
./dev.sh backend
./dev.sh frontend
./dev.sh celery
```

适用场景：

- 单独重启后端
- 单独重启前端
- 启动或恢复 Celery worker

### 4. 停止或查看日志

```bash
./dev.sh stop
./dev.sh logs
./dev.sh logs frontend
./dev.sh logs celery
```

适用场景：

- 结束开发会话
- 定位服务未启动、端口未监听或运行时错误

## 开发数据库与测试数据库

### 开发数据库

开发数据库是本地开发环境使用的业务库，初始化入口：

```bash
./dev.sh init-db
# 或
cd packages/server-python && make init-dev-db
```

这里会执行迁移，并在显式允许的前提下准备默认开发 seed。开发 seed 与测试 seed 是两条不同边界，不要混用。

### 测试数据库

测试数据库只服务后端测试，初始化入口：

```bash
./dev.sh init-test-db
# 或
cd packages/server-python && make init-test-db
```

适用场景：

- 新环境首次运行后端测试
- 测试库需要重新准备
- 切换到新的测试连接串

测试库连接串可通过 `TEST_DATABASE_URL` 覆盖。具体连接值属于运行时事实，不建议在规则文档里反复维护多份。

## 后端常用命令

```bash
cd packages/server-python
make install
make dev
make lint
make test
make migrate
make seed-dev
make migrate-create msg="description"
make migrate-downgrade
```

建议理解为三个层次：

- 依赖与运行：`make install`、`make dev`
- 质量验证：`make lint`、`make test`
- 数据库演进：`make migrate`、`make seed-dev`、`make migrate-create`、`make migrate-downgrade`

## 前端与 shared 常用命令

### 前端

```bash
pnpm --filter @metaedu/web dev
pnpm --filter @metaedu/web lint
pnpm --filter @metaedu/web typecheck
pnpm --filter @metaedu/web build
```

### shared

```bash
pnpm --filter @metaedu/shared typecheck
```

当任务涉及 shared schema / type 变更时，通常至少要跑 shared typecheck 和前端 typecheck。

## 如何选择命令

| 目标 | 优先入口 |
|------|----------|
| 启动完整开发环境 | `./dev.sh` |
| 初始化开发数据库 | `./dev.sh init-db` 或 `make init-dev-db` |
| 初始化测试数据库 | `./dev.sh init-test-db` 或 `make init-test-db` |
| 后端局部开发 | `make dev` / `make test` / `make lint` |
| 前端局部开发 | `pnpm --filter @metaedu/web ...` |
| shared 契约验证 | `pnpm --filter @metaedu/shared typecheck` |

如果一个需求能通过稳定入口完成，不优先依赖一次性手拼命令。

## 代码探索与搜索工具选择

本项目默认同时使用 `CodeGraph` 和 `rg`，但分工不同。目标不是“所有问题都上图工具”，而是先用最合适的入口拿到可信上下文。

### 默认分工

- 结构问题优先 `CodeGraph`：例如影响面分析、调用链梳理、跨模块重构、契约消费链排查。
- 文本问题优先 `rg`：例如字段名、状态值、接口路径、文案、CSS class、design token 和文档关键字搜索。
- 真正声明完成前，仍以 typecheck、测试或人工验收作为最终验证；`CodeGraph` 和 `rg` 都不替代验证。

### 优先使用 CodeGraph 的场景

- 改 API / DTO / shared schema，想先确认前端或后端的消费链。
- 改共用 helper、service、resolver、query 封装，想先看影响面。
- 接手陌生模块，想先看页面、service、query、组件之间如何串联。
- 复核其他 AI IDE 的改动，确认是否漏掉间接调用方或 adapter。

### 直接使用 `rg` 更划算的场景

- 查字段字面量、枚举值、状态值、错误文案或 query param。
- 查 `ui-*` / `liquid-*` / token / CSS 规则等样式文本。
- 查 spec、plan、任务卡、技术债或规则文档中的关键词。
- 查接口路径、环境变量名、命令名或脚本入口。

### 推荐顺序

对于跨文件、跨层、跨模块任务，默认顺序是：

1. 先用 `CodeGraph` 建结构地图，避免漏掉消费方。
2. 再用 `rg` 查字段命中和具体文本位置，避免只停留在抽象关系。
3. 最后跑与改动范围匹配的验证，确认不是“分析正确但实现仍有误”。

对于单文件、小型文本修改、样式调整和文档编辑，通常直接 `rg` 即可，不必先上 `CodeGraph`。

## 环境阻塞记录

如果命令因为本地依赖、数据库、端口占用或缺失配置无法运行，不要只写“失败”。必须记录：

- 命令
- 失败摘要
- 推断原因
- 是否影响当前交付
- 后续恢复步骤或对应任务编号

这类记录应同步到 `docs/03-engineering-governance/current-work.md`，必要时入账到技术债或 follow-up。

## 何时更新本文件

只有下面这些变化值得更新 `local-development.md`：

- 新增或替换稳定开发入口
- 常见开发场景的推荐命令发生变化
- 开发库 / 测试库初始化边界发生变化
- workspace 包结构变化导致常用命令入口改变

如果只是脚本内部实现细节、临时排障过程或偶发本机问题，通常不更新本文件。
