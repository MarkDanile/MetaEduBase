# BUG-021: `dev.sh` 跳过 Redis / MinIO 且 Celery Worker 无法启动

> Status: 🟡 In Progress
> Priority: P1
> Area: 本地开发 / Infrastructure / Celery
> Created: 2026-07-31
> Branch: `codex/bug-dev-sh-services`

## 现象

执行 `./dev.sh` 后 Backend 与 Frontend 可运行，但日志出现：

```text
[WARN] Redis 未运行，Celery Worker 跳过（文档解析/向量化任务将不可用）
[WARN] 请先执行 ./dev.sh infra 启动 Redis
```

现场同时存在以下异常：

- PostgreSQL 容器已运行时，`./dev.sh infra` 直接报告基础设施已运行，没有补启缺失的 Redis / MinIO。
- 本地 PostgreSQL 模式只启动 PostgreSQL，不尝试启动已安装的本地 Redis。
- Redis 恢复后，Celery 开发 wrapper 报 `FileNotFoundError: celery`，Worker 仍未上线。

登录 `401` 是开发库缺少默认 tenant / admin 的独立现场状态；执行 `./dev.sh init-db` 的 seed 后登录恢复 `200`，不把 seed 语义并入本 BUG。

## 根因

1. `ensure_docker_infra` 只要发现任意 PostgreSQL 容器便提前返回，把三项基础设施错误地当作一个整体状态。
2. `start_infra` 的 local 分支明确跳过 Redis，即使本机已有 `redis-server`。
3. `scripts/celery_worker_dev.py` 用 PATH 中的裸 `celery` 启动子进程；`uv sync` 不会激活 `.venv/bin`，因此 wrapper 找不到 executable。
4. 自动模式只按 Docker daemon / Colima 是否存在选路，可能在本地 PostgreSQL 已占用 `5432` 时误起 Docker PostgreSQL。

## 完成标准

- AC-1：Docker 模式逐项检查 PostgreSQL、Redis、MinIO，仅补启缺失服务。
- AC-2：local 模式在 Redis 未运行且 `redis-server` 可用时自动启动 Redis，并记录 workspace-local PID / log。
- AC-3：Celery wrapper 使用当前 Python 解释器执行 `-m celery`，不依赖 shell PATH。
- AC-4：自动模式识别已运行的本地 PostgreSQL，避免在 Docker 中再起一套占用同一端口的 PostgreSQL。
- AC-5：`./dev.sh status` 能识别本地 Redis；`./dev.sh stop` 只停止由脚本 PID 文件跟踪的本地 Redis。
- AC-6：脚本 contract tests、ruff、工程文档门禁和真实 Redis / Celery health check 通过。

## 验证方式

- `bash -n dev.sh`
- `pytest -q tests/scripts/test_celery_worker_dev.py tests/scripts/test_dev_sh_services.py`
- `ruff check scripts/celery_worker_dev.py tests/scripts/test_celery_worker_dev.py tests/scripts/test_dev_sh_services.py`
- `./dev.sh infra && ./dev.sh status`
- `redis-cli -h 127.0.0.1 -p 6379 ping`
- `.venv/bin/python -m celery -A app.celery_app inspect ping`
- `scripts/check-engineering-docs` 与 `git diff --check`

## 非目标

- 不改变 `./dev.sh` 与 `./dev.sh init-db` 的职责边界，不让普通启动隐式迁移或 seed 数据库。
- 不实现本地 MinIO 安装；local 模式仍明确提示 MinIO 未启动。
- 不处理 `dev_setup` 的 AI application JSONB seed 异常；该问题独立分流。
- 不修改 R1-S3-C writer fence 代码或契约。
