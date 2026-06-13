# Local Development — 本地开发入口

本文件记录稳定本地入口。Git 流程见 `git-workflow.md`；验证矩阵见 `quality-gates.md`。

## 主入口原则

- 启动和管理本地开发环境：优先 `./dev.sh`。
- 后端局部开发、迁移、测试、lint：优先 `packages/server-python/Makefile`。
- 前端和 shared 包：优先 `pnpm --filter ...`。
- 如果稳定入口能完成任务，不优先依赖一次性手拼命令。

## 常见命令

| 目标 | 命令 |
|------|------|
| 初始化开发库 | `./dev.sh init-db` |
| 启动完整环境 | `./dev.sh` |
| 基础设施 | `./dev.sh infra` / `./dev.sh status` |
| 单服务 | `./dev.sh backend` / `frontend` / `celery` |
| 日志 / 停止 | `./dev.sh logs` / `./dev.sh stop` |
| 后端安装 | `cd packages/server-python && make install` |
| 后端开发 | `cd packages/server-python && make dev` |
| 后端 lint / test | `cd packages/server-python && make lint` / `make test` |
| 迁移 | `make migrate` / `make migrate-create msg=\"...\"` / `make migrate-downgrade` |
| 前端 | `pnpm --filter @metaedu/web dev` / `lint` / `typecheck` / `build` |
| shared | `pnpm --filter @metaedu/shared typecheck` |

## 数据库边界

- 开发库初始化：`./dev.sh init-db` 或 `make init-dev-db`。
- 测试库初始化：`./dev.sh init-test-db` 或 `make init-test-db`。
- 测试库只服务测试，不复用开发库；连接串可用 `TEST_DATABASE_URL` 覆盖。
- 开发 seed 与测试 seed 边界必须清楚，不把开发默认数据带入测试或生产判断。

## 环境阻塞记录

命令因本地依赖、数据库、端口、权限或配置失败时，不写“未测试”一笔带过。必须记录：

- 命令。
- 退出结果或失败摘要。
- 推断原因。
- 是否影响当前交付。
- 后续恢复步骤或对应任务编号。

这类记录同步到 `current-work.md`，必要时入账为技术债或 follow-up。

## 代码探索与搜索工具选择

可使用当前 AI IDE 可用的 CodeGraph、`rg`、Read、IDE 索引等工具。工具选择由任务和可用性决定；工具输出不替代测试、typecheck、代码审查或人工验收。

## 何时更新本文件

仅当稳定开发入口、开发库 / 测试库初始化边界、workspace 包结构或常见命令入口变化时更新。脚本内部实现、临时排障和单机偶发问题不更新本文件。
