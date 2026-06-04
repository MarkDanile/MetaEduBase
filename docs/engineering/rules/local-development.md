# Local Development — 本地开发命令

本文件记录本地启动、调试、依赖安装和常用运行命令。Git 分支、提交和 PR 流程见 `docs/engineering/rules/git-workflow.md`；验证门禁见 `docs/engineering/rules/quality-gates.md`。

## 启动服务

```bash
./dev.sh
./dev.sh infra
./dev.sh backend
./dev.sh frontend
./dev.sh celery
./dev.sh init-db
./dev.sh stop
./dev.sh status
./dev.sh logs [backend|frontend|celery]
```

| 命令 | 用途 |
|------|------|
| `./dev.sh` | 启动全部服务，设计为幂等 |
| `./dev.sh infra` | 仅启动基础设施：PostgreSQL / Redis / MinIO |
| `./dev.sh backend` | 仅重启后端 |
| `./dev.sh frontend` | 仅重启前端 |
| `./dev.sh celery` | 仅启动 Celery Worker |
| `./dev.sh init-db` | 显式初始化开发数据库：执行迁移并创建默认开发账号 |
| `./dev.sh stop` | 停止全部服务 |
| `./dev.sh status` | 查看服务状态 |
| `./dev.sh logs [backend|frontend|celery]` | 查看指定服务日志 |

## 后端

```bash
cd packages/server-python
make install
make init-dev-db
make dev
make lint
make test
.venv/bin/pytest tests/contexts/identity/test_auth.py -v
.venv/bin/pytest -v -k "test_create"
```

| 命令 | 用途 |
|------|------|
| `make install` | 安装后端依赖 |
| `make init-dev-db` | 显式初始化开发数据库：执行 Alembic 迁移并通过 `ALLOW_DEFAULT_SEED=true` 创建默认开发租户 / admin |
| `make dev` | 启动 FastAPI 开发服务 |
| `make lint` | 运行 ruff check + mypy |
| `make test` | 运行后端 pytest |
| `.venv/bin/pytest tests/contexts/identity/test_auth.py -v` | 运行单个测试文件 |
| `.venv/bin/pytest -v -k "test_create"` | 按关键词运行测试 |

## 数据库迁移

```bash
cd packages/server-python
make migrate
make seed-dev
make migrate-create msg="description"
make migrate-downgrade
```

| 命令 | 用途 |
|------|------|
| `make migrate` | 执行 Alembic upgrade head |
| `make seed-dev` | 仅写入默认开发租户 / admin，要求 schema 已迁移完成，并通过 `ALLOW_DEFAULT_SEED=true` 显式放行 |
| `make migrate-create msg="description"` | 生成新迁移 |
| `make migrate-downgrade` | 回滚一个迁移 |

## 前端

```bash
cd packages/web
pnpm dev
pnpm typecheck
pnpm build
pnpm lint
```

| 命令 | 用途 |
|------|------|
| `pnpm dev` | 启动 Vite 开发服务 |
| `pnpm typecheck` | 运行 vue-tsc 类型检查 |
| `pnpm build` | 生产构建 |
| `pnpm lint` | 运行前端 ESLint |

## Shared Package

```bash
pnpm --filter @metaedu/shared typecheck
```

涉及 `packages/shared` schema 或 type 变更时运行该命令，并同时运行前端 typecheck。

## 环境阻塞记录

如果命令因为本地依赖、数据库、端口占用或缺失配置无法运行，不要只写“失败”。必须记录：

- 命令。
- 失败摘要。
- 推断原因。
- 是否影响当前交付。
- 后续恢复步骤或对应技术债。
