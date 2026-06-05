# TD-004 测试数据库可复现 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **交付历史（2026-06-04）：** TD-004 已通过 PR #23（merge commit `b8b34a6`）合并到 `main`。本文保留为实施步骤参考，收口时遗留的活动式交付占位（回填提示与 Task 8 输出占位）已在收口阶段回填到 `current-work.md` / `technical-debt.md` / `work-log.md`，详见最近完成记录。TD-004 的后续收口任务见 `TD-013`，由 Claude Code 接手。

**Goal:** 让后端测试数据库可由 `TEST_DATABASE_URL` 配置，并提供 `./dev.sh init-test-db` / `make init-test-db` 显式启动入口，让任意新环境跑通 `cd packages/server-python && .venv/bin/python -m pytest -q`。

**Architecture:** 新增 `app/shared/infrastructure/test_db_setup.py` 模块，复用 `dev_setup.py` 的 async 风格 + asyncpg 驱动；conftest 改读 env、移除 `Base.metadata.create_all`，schema 改由前置脚本（Alembic upgrade head）创建。`dev.sh` 与 `Makefile` 暴露入口；文档同步事实。严格不动测试隔离逻辑、不引入新依赖、不新建 docker-compose profile。

**Tech Stack:** Python 3.12、asyncpg、SQLAlchemy 2 async、Alembic、pytest-asyncio。

**Spec:** [docs/specs/2026-06-04-td-004-test-database-reproducibility.md](../specs/2026-06-04-td-004-test-database-reproducibility.md)
**技术债条目:** [docs/engineering/technical-debt.md#td-004-让后端测试数据库环境可复现](../engineering/technical-debt.md)

---

## 文件结构

- **Create:** `packages/server-python/app/shared/infrastructure/test_db_setup.py` — 独立模块，幂等创建测试库、扩展、schema 并跑 Alembic upgrade head。
- **Modify:** `packages/server-python/tests/conftest.py:14-62` — `TEST_DB_URL` 读 env；删除 `Base.metadata.create_all`；保留其它行为。
- **Modify:** `packages/server-python/Makefile` — 新增 `init-test-db` target。
- **Modify:** `dev.sh` — 新增 `init-test-db` 子命令 + usage 文本。
- **Modify:** `docs/engineering/rules/local-development.md` — 新增测试库小节 + Makefile 行。
- **Modify:** `docs/engineering/rules/quality-gates.md` — 更新已知门禁状态。
- **Modify:** `README.md:154-156` — 后端测试段补一行。
- **Modify:** `docs/engineering/current-work.md` — 任务卡片登记 + 收尾。
- **Modify:** `docs/engineering/technical-debt.md` — TD-004 状态收口。
- **Modify:** `docs/engineering/work-log.md` — 一行索引。

---

## Task 1：新增 `test_db_setup.py` 模块

**Files:**
- Create: `packages/server-python/app/shared/infrastructure/test_db_setup.py`

- [x] **Step 1：创建模块文件**

> 实施过程发现：旧环境中 conftest 用 `Base.metadata.create_all` 建过表但未写入 `metaedu.alembic_version`，直接 `alembic upgrade head` 会报 `DuplicateTableError`。脚本加入兼容分支：检测到「业务表已存在且 alembic_version 缺失」时先 `alembic stamp head` 再走正常 upgrade。新环境零开销。
>
> 另一处坑：`make_url(...)` 返回的 SQLAlchemy URL 对象 `str()` 时会把密码 mask 成 `***`，不能把 `str(url)` 当连接串传给 alembic，必须用原始字符串。

写入以下内容（完整文件）：

> 完整实现见已 commit 的 [packages/server-python/app/shared/infrastructure/test_db_setup.py](../../packages/server-python/app/shared/infrastructure/test_db_setup.py)（含 `_stamp_if_legacy_schema` 兼容分支）。下面是简化骨架，仅作为对照阅读用：

```python
"""测试数据库初始化入口。

幂等创建测试库、安装 pgvector / ltree 扩展、创建 metaedu schema，
并通过 Alembic upgrade head 同步表结构。不写任何 seed；测试 seed
由 conftest._ensure_seed fixture 负责。

用法：
    python -m app.shared.infrastructure.test_db_setup

可通过 TEST_DATABASE_URL 环境变量覆盖默认连接串，默认值与
tests/conftest.py 一致。
"""

import asyncio
import logging
import os

import asyncpg
from sqlalchemy.engine import make_url

from app.config import settings
from app.shared.infrastructure.database import run_migrations

logger = logging.getLogger(__name__)

DEFAULT_TEST_DB_URL = (
    "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"
)


def _resolve_test_db_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)


async def _ensure_database(url) -> None:
    """连到 postgres 库，若目标库不存在则创建。"""
    admin_conn = await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database="postgres",
    )
    try:
        exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            url.database,
        )
        if exists:
            logger.info("测试数据库已存在：%s", url.database)
            return
        # CREATE DATABASE 不能在事务内执行；asyncpg 的 execute 默认 autocommit。
        await admin_conn.execute(f'CREATE DATABASE "{url.database}"')
        logger.info("已创建测试数据库：%s", url.database)
    finally:
        await admin_conn.close()


async def _ensure_extensions_and_schema(url) -> None:
    """连到测试库，幂等创建扩展与 metaedu schema。"""
    conn = await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database=url.database,
    )
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS ltree;")
        await conn.execute("CREATE SCHEMA IF NOT EXISTS metaedu;")
        logger.info("已确认扩展与 schema：vector, ltree, metaedu")
    finally:
        await conn.close()


async def _run_alembic_against(test_url: str) -> None:
    """临时把 settings.database_url 指向测试库后调用既有 run_migrations。"""
    original = settings.database_url
    settings.database_url = test_url
    try:
        await run_migrations()
    finally:
        settings.database_url = original


async def init_test_database() -> None:
    test_url_str = _resolve_test_db_url()
    url = make_url(test_url_str)
    await _ensure_database(url)
    await _ensure_extensions_and_schema(url)
    await _run_alembic_against(test_url_str)
    logger.info("测试数据库初始化完成：%s", url.database)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(init_test_database())


if __name__ == "__main__":
    main()
```

- [x] **Step 2：验证模块可被导入**

Run：
```bash
cd packages/server-python && .venv/bin/python -c "from app.shared.infrastructure.test_db_setup import init_test_database; print('ok')"
```
Expected：`ok`

- [x] **Step 3：首次跑脚本（前提：dev.sh infra 已起 PostgreSQL）**

Run：
```bash
cd packages/server-python && .venv/bin/python -m app.shared.infrastructure.test_db_setup
```
Expected：日志含「已创建测试数据库」或「测试数据库已存在」+「已确认扩展与 schema」+「数据库迁移完成」+「测试数据库初始化完成」；退出码 0。

- [x] **Step 4：再跑一次验证幂等**

Run：
```bash
cd packages/server-python && .venv/bin/python -m app.shared.infrastructure.test_db_setup
```
Expected：日志含「测试数据库已存在」；退出码 0。

- [x] **Step 5：commit**

```bash
git add packages/server-python/app/shared/infrastructure/test_db_setup.py
git commit -m "feat(server): add test_db_setup module for TD-004"
```

---

## Task 2：conftest 改用 env + 删除隐式建表

**Files:**
- Modify: `packages/server-python/tests/conftest.py:1-62`

- [x] **Step 1：在文件顶部新增 import 与默认值，把 TEST_DB_URL 改为读 env**

把这一段：
```python

from unittest.mock import patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.main import app
from app.shared.infrastructure.database import Base, get_session
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

TEST_DB_URL = "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"
```

替换为：
```python

import os
from unittest.mock import patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.main import app
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

DEFAULT_TEST_DB_URL = (
    "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"
)
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)
```

说明：同时删除 `from app.shared.infrastructure.database import Base` 中的 `Base`（不再使用 `Base.metadata.create_all`）。

- [x] **Step 2：删除 client fixture 中的 `Base.metadata.create_all`**

把 client fixture 的这一段：
```python
    # Clean template table before test run to ensure fresh state
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS metaedu"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("TRUNCATE TABLE metaedu.templates RESTART IDENTITY CASCADE"))
```

替换为：
```python
    # Clean template table before test run to ensure fresh state.
    # Schema/tables are expected to exist (run `./dev.sh init-test-db` or
    # `make init-test-db` once per environment); we only ensure the schema
    # namespace exists for older databases and reset per-test state.
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS metaedu"))
        await conn.execute(text("TRUNCATE TABLE metaedu.templates RESTART IDENTITY CASCADE"))
```

- [x] **Step 3：确认无其它 Base 引用**

Run：
```bash
grep -n "Base" packages/server-python/tests/conftest.py
```
Expected：无输出（已全部移除）。

- [x] **Step 4：跑最小冒烟测试，确认 conftest 可用**

前置：已执行过 Task 1 Step 3 / `./dev.sh init-test-db`。

Run：
```bash
cd packages/server-python && .venv/bin/python -m pytest tests/shared/test_health.py -q
```
Expected：2 passed。

- [x] **Step 5：commit**

```bash
git add packages/server-python/tests/conftest.py
git commit -m "refactor(server): read TEST_DATABASE_URL from env in conftest (TD-004)"
```

---

## Task 3：新增 `make init-test-db`

**Files:**
- Modify: `packages/server-python/Makefile`

- [x] **Step 1：在 `init-dev-db` target 之后插入 `init-test-db`**

把这一段：
```Makefile
.PHONY: dev install migrate init-dev-db seed-dev lint test

install:
	pip install -e ".[dev,ai]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

celery-worker:
	celery -A app.celery_app worker --loglevel=info

migrate:
	alembic upgrade head

init-dev-db:
	ALLOW_DEFAULT_SEED=true python -m app.shared.infrastructure.dev_setup
```

替换为：
```Makefile
.PHONY: dev install migrate init-dev-db init-test-db seed-dev lint test

install:
	pip install -e ".[dev,ai]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

celery-worker:
	celery -A app.celery_app worker --loglevel=info

migrate:
	alembic upgrade head

init-dev-db:
	ALLOW_DEFAULT_SEED=true python -m app.shared.infrastructure.dev_setup

init-test-db:
	python -m app.shared.infrastructure.test_db_setup
```

- [x] **Step 2：验证 target 可被 make 识别**

Run：
```bash
cd packages/server-python && make -n init-test-db
```
Expected：输出 `python -m app.shared.infrastructure.test_db_setup`。

- [x] **Step 3：commit**

```bash
git add packages/server-python/Makefile
git commit -m "build(server): add init-test-db target (TD-004)"
```

---

## Task 4：`dev.sh init-test-db` 子命令

**Files:**
- Modify: `dev.sh`

- [x] **Step 1：新增 `init_test_db` 函数**

在 `init_dev_db()` 函数定义之后新增：
```bash
init_test_db() {
  log "初始化测试数据库 (创建库 + 扩展 + Alembic upgrade head)..."
  start_infra
  cd "$SERVER_DIR"
  if [[ ! -d ".venv" ]]; then
    log "创建 Python 虚拟环境..."
    python3 -m venv .venv
    log "安装后端依赖..."
    .venv/bin/pip install -e ".[dev,ai]" -q
  fi
  if ! .venv/bin/python -c "import alembic" 2>/dev/null; then
    log "安装后端依赖..."
    .venv/bin/pip install -e ".[dev,ai]" -q
  fi
  .venv/bin/python -m app.shared.infrastructure.test_db_setup
  ok "测试数据库初始化完成"
}
```

- [x] **Step 2：在 `main()` 的 case 分支中加入 `init-test-db`**

在 `init-db)` 分支后插入：
```bash
    init-test-db)
      init_test_db
      ;;
```

- [x] **Step 3：更新两处 usage 文本（顶部注释 + 末尾 `*)` 分支）**

a) 顶部注释新增一行（在 `#   ./dev.sh init-db  ...` 之后）：
```bash
#   ./dev.sh init-test-db # 显式初始化测试数据库 (建库 + 扩展 + 迁移)
```

b) 末尾 `*)` 分支：
- 把 `echo "用法: $0 {all|infra|backend|frontend|celery|init-db|stop|status|logs}"` 替换为 `echo "用法: $0 {all|infra|backend|frontend|celery|init-db|init-test-db|stop|status|logs}"`。
- 在 `echo "  init-db   显式初始化开发数据库 (迁移 + 默认开发账号)"` 之后新增：
  ```bash
      echo "  init-test-db 显式初始化测试数据库 (建库 + 扩展 + 迁移)"
  ```

- [x] **Step 4：验证子命令可被识别**

Run：
```bash
./dev.sh init-test-db
```
Expected：复用 `start_infra` 后调用脚本，最终输出 `[OK] 测试数据库初始化完成`，退出码 0。

- [x] **Step 5：再跑一次验证幂等**

Run：
```bash
./dev.sh init-test-db
```
Expected：日志含「测试数据库已存在」，退出码 0。

- [x] **Step 6：commit**

```bash
git add dev.sh
git commit -m "feat(dev): add init-test-db subcommand (TD-004)"
```

---

## Task 5：文档同步 — `local-development.md`

**Files:**
- Modify: `docs/engineering/rules/local-development.md`

- [x] **Step 1：在「数据库迁移」表新增 `make init-test-db` 一行**

把这一段：
```md
| `make migrate` | 执行 Alembic upgrade head |
| `make seed-dev` | 仅写入默认开发租户 / admin，要求 schema 已迁移完成，并通过 `ALLOW_DEFAULT_SEED=true` 显式放行 |
| `make migrate-create msg="description"` | 生成新迁移 |
| `make migrate-downgrade` | 回滚一个迁移 |
```

替换为：
```md
| `make migrate` | 执行 Alembic upgrade head |
| `make seed-dev` | 仅写入默认开发租户 / admin，要求 schema 已迁移完成，并通过 `ALLOW_DEFAULT_SEED=true` 显式放行 |
| `make init-test-db` | 显式初始化测试数据库：建库、安装 vector / ltree 扩展、执行 Alembic upgrade head；可通过 `TEST_DATABASE_URL` 覆盖默认连接串 |
| `make migrate-create msg="description"` | 生成新迁移 |
| `make migrate-downgrade` | 回滚一个迁移 |
```

- [x] **Step 2：在「启动服务」表新增 `init-test-db` 行**

把这一段：
```md
| `./dev.sh init-db` | 显式初始化开发数据库：执行迁移并创建默认开发账号 |
| `./dev.sh stop` | 停止全部服务 |
```

替换为：
```md
| `./dev.sh init-db` | 显式初始化开发数据库：执行迁移并创建默认开发账号 |
| `./dev.sh init-test-db` | 显式初始化测试数据库：建库、安装扩展、执行 Alembic upgrade head |
| `./dev.sh stop` | 停止全部服务 |
```

同步把对应的 bash 代码块加一行：
```bash
./dev.sh init-db
./dev.sh stop
```
改为：
```bash
./dev.sh init-db
./dev.sh init-test-db
./dev.sh stop
```

- [x] **Step 3：新增「测试数据库」小节，放在「数据库迁移」与「前端」之间**

新增：
```md
## 测试数据库

后端 pytest 依赖 `metaedu_test` 库。新环境首次运行测试前需要执行一次初始化：

```bash
./dev.sh init-test-db
# 或
cd packages/server-python && make init-test-db
```

可通过 `TEST_DATABASE_URL` 环境变量覆盖默认连接串（默认 `postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test`，与 `tests/conftest.py` 一致）：

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:pwd@host:5432/dbname ./dev.sh init-test-db
TEST_DATABASE_URL=postgresql+asyncpg://user:pwd@host:5432/dbname \
  cd packages/server-python && .venv/bin/python -m pytest -q
```

脚本幂等，可反复运行。
```

- [x] **Step 4：commit**

```bash
git add docs/engineering/rules/local-development.md
git commit -m "docs(local-development): document init-test-db and TEST_DATABASE_URL (TD-004)"
```

---

## Task 6：文档同步 — `quality-gates.md`

**Files:**
- Modify: `docs/engineering/rules/quality-gates.md`

- [x] **Step 1：更新「已知门禁状态」中关于后端 pytest 的描述**

把这一行：
```md
- 后端完整 pytest 依赖 `localhost:5432/metaedu_test`；测试环境可复现问题见 `TD-004`。
```

替换为：
```md
- 后端完整 pytest 依赖 `metaedu_test` 测试库；新环境运行 `./dev.sh init-test-db` 或 `cd packages/server-python && make init-test-db` 显式初始化，可通过 `TEST_DATABASE_URL` 覆盖默认连接串。
```

- [x] **Step 2：commit**

```bash
git add docs/engineering/rules/quality-gates.md
git commit -m "docs(quality-gates): refresh backend pytest gate status (TD-004)"
```

---

## Task 7：文档同步 — `README.md`

**Files:**
- Modify: `README.md`（约 line 152-155，「开发」段）

- [x] **Step 1：补一行 `make init-test-db` 提示**

把这一段：
```md
## 开发

```bash
# 后端 lint + 测试
cd packages/server-python && make lint && make test
```

替换为：
```md
## 开发

```bash
# 后端 lint + 测试 (首次需先 `make init-test-db` 初始化测试库)
cd packages/server-python && make lint && make test
```

- [x] **Step 2：commit**

```bash
git add README.md
git commit -m "docs(readme): mention init-test-db prerequisite (TD-004)"
```

---

## Task 8：端到端验证

> 本任务不产生 commit；产生的是供任务卡片记录的真实验证证据。

- [x] **Step 1：确认 PostgreSQL 已运行**

Run：
```bash
./dev.sh status
```
Expected：PostgreSQL 显示 ✅。如未运行，先 `./dev.sh infra`。

- [x] **Step 2：脚本端到端**

Run：
```bash
./dev.sh init-test-db
./dev.sh init-test-db
```
Expected：两次退出码 0；第二次日志含「测试数据库已存在」。

- [x] **Step 3：Env 覆盖能跑**

Run：
```bash
TEST_DATABASE_URL=postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test \
  bash -c 'cd packages/server-python && .venv/bin/python -m pytest tests/shared/test_health.py -q'
```
Expected：2 passed。

- [x] **Step 4：完整 pytest**

Run：
```bash
cd packages/server-python && .venv/bin/python -m pytest -q
```
Expected：与 TD-012 baseline 一致的 87 passed。

如未达 87 passed，**不得**写「通过」；按 quality-gates.md 记录失败摘要并判断是否本任务引入。

- [x] **Step 5：ruff 无回归**

Run：
```bash
cd packages/server-python && .venv/bin/python -m ruff check app/ tests/
```
Expected：退出码 0。

- [x] **Step 6：文档落点齐全**

Run：
```bash
rg -n "init-test-db|TEST_DATABASE_URL" \
  docs/engineering/rules/local-development.md \
  docs/engineering/rules/quality-gates.md \
  README.md \
  packages/server-python/Makefile \
  packages/server-python/tests/conftest.py \
  packages/server-python/app/shared/infrastructure/test_db_setup.py \
  dev.sh
```
Expected：每个文件至少 1 处命中。

---

## Task 9：登记任务卡片到 `current-work.md`

**Files:**
- Modify: `docs/engineering/current-work.md`

> 这一步建议在 Task 1 前先做（写最初的「🟡 进行中」卡片），实施过程中持续回写状态、当前进展和验证结果。本步骤合并在 Plan 末尾是因为最终状态必须基于真实验证产物。

- [x] **Step 1（开工时）：把 `TD-004` 候选项替换为完整任务卡片**

把这一段：
```md
## 下一批候选任务

- `TD-004`：让后端测试数据库环境可复现。详见 `docs/engineering/technical-debt.md`。
```

替换为：
```md
## 下一批候选任务

当前无候选任务。
```

并在「## 当前进行中」之后插入：
```md
### TD-004: 让后端测试数据库环境可复现

状态：🟡 进行中
类型：技术债 / 基础设施
领域：Testing / Delivery
当前执行模式：plan-do
最近接手工具：Claude Code
分支：`refactor/td-004-test-db-reproducibility`

需求来源：
- Spec: `docs/specs/2026-06-04-td-004-test-database-reproducibility.md`
- Plan: `docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md`
- 技术债：`docs/engineering/technical-debt.md#td-004-让后端测试数据库环境可复现`
- 架构约束：`docs/engineering/rules/local-development.md`，`docs/engineering/rules/quality-gates.md`
- 插件输出：
- 任务模式：`docs/engineering/task-modes.md#技术债修复`

当前进展：
- 已完成：spec 落盘并通过 self-review；plan 落盘
- 正在处理：实施 Task 1-7
- 未完成：端到端验证 + 收尾

下一步：
1. 按 plan 推进 Task 1-7
2. 跑完 Task 8 验证
3. 按用户要求推进 Git 闭环

验证状态：
- 已运行：
- 未运行：完整 pytest，将在 Task 8 执行
- 当前失败：

交接备注：
- 行为变化：测试 schema 由 conftest 内的 `Base.metadata.create_all` 改为前置 `init-test-db`（Alembic upgrade head）；未跑 init-test-db 的环境会显式失败。
```

- [x] **Step 2（开工时）：开分支**

Run：
```bash
git checkout -b refactor/td-004-test-db-reproducibility
git add docs/specs/2026-06-04-td-004-test-database-reproducibility.md \
        docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md \
        docs/engineering/current-work.md
git commit -m "docs(td-004): land spec, plan, and task card"
```

- [x] **Step 3（Task 8 后）：把任务卡迁移到「最近完成」并改为 🟢 完成**

把「## 当前进行中」下的 TD-004 卡片整段剪切到「## 最近完成」首位，并把：
- `状态：🟡 进行中` → `状态：🟢 完成`
- `当前执行模式` 保持 `plan-do`
- `当前进展` → 简短总结：`已完成：模块新增 + conftest 改 env + Makefile/dev.sh 入口 + 文档同步 + 端到端验证`，`正在处理` / `未完成` 留空
- `下一步：1.` 留空，第 2、3 项删掉
- `验证状态` → 填入 Task 8 真实命令与结果（含退出码 / passed 数）
- `交接备注` → 末尾补 PR 编号、merge commit 与完成日期；2026-06-04 实际回填：`PR #23`（https://github.com/MarkDanile/MetaEduBase/pull/23）；merge commit `b8b34a6`；完成日期 `2026-06-04`。

> 收尾合并后再次回填 PR 编号、merge commit 和完成日期，不得保留交付占位。

把「## 当前进行中」段落恢复为：
```md
## 当前进行中

当前无正在执行的任务。
```

- [x] **Step 4：commit**

```bash
git add docs/engineering/current-work.md
git commit -m "docs(current-work): mark TD-004 complete after verification"
```

---

## Task 10：更新 `technical-debt.md`

**Files:**
- Modify: `docs/engineering/technical-debt.md`（TD-004 段落）

- [x] **Step 1：状态改为 🟢 完成 + 备注追加完成摘要**

把这一段：
```md
### TD-004: 让后端测试数据库环境可复现

状态：⚫ 待办
优先级：P1
领域：测试 / 交付
证据：`packages/server-python/tests/conftest.py:13` 硬编码 `postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test`。当前环境中，`pytest` 收集到 81 个测试，其中 15 个不依赖数据库的测试通过，66 个集成测试在连接本地 PostgreSQL 时失败。
问题：测试执行依赖隐式本地数据库，新环境或 CI 中很难稳定复现。
完成标准：测试数据库 URL 可配置，并通过文档或 dev/test compose profile 提供明确的测试数据库启动方式。
验证方式：全新环境能启动所需测试数据库，并执行 `cd packages/server-python && .venv/bin/python -m pytest -q`，无需猜测手动建库步骤。
备注：
```

替换为（验证结果以 Task 8 真实输出为准；下面是模板，实施时把验证摘要替换为真实数字。2026-06-04 实际验证摘要：`./dev.sh init-test-db` 跑两次均退出码 0；`TEST_DATABASE_URL=... .venv/bin/python -m pytest tests/shared/test_health.py -q` → 2 passed；`cd packages/server-python && .venv/bin/python -m pytest -q` → 87 passed in 23.36s；`cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` → 退出码 0）：
```md
### TD-004: 让后端测试数据库环境可复现

状态：🟢 完成
优先级：P1
领域：测试 / 交付
证据：`packages/server-python/tests/conftest.py:14` 硬编码 `postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test`。当前环境中，`pytest` 收集到 81 个测试，其中 15 个不依赖数据库的测试通过，66 个集成测试在连接本地 PostgreSQL 时失败。
问题：测试执行依赖隐式本地数据库，新环境或 CI 中很难稳定复现。
完成标准：测试数据库 URL 可配置，并通过文档或 dev/test compose profile 提供明确的测试数据库启动方式。
验证方式：全新环境能启动所需测试数据库，并执行 `cd packages/server-python && .venv/bin/python -m pytest -q`，无需猜测手动建库步骤。
备注：2026-06-04 按流程开始处理。2026-06-04 完成。Spec：`docs/specs/2026-06-04-td-004-test-database-reproducibility.md`；Plan：`docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md`。改动：新增 `app/shared/infrastructure/test_db_setup.py`（asyncpg 幂等建库 + 扩展 + Alembic upgrade head）；conftest 改读 `TEST_DATABASE_URL` env 并移除 `Base.metadata.create_all`；新增 `./dev.sh init-test-db` 与 `make init-test-db`；同步 local-development、quality-gates、README。验证：`./dev.sh init-test-db` 跑两次均退出码 0；`TEST_DATABASE_URL=... .venv/bin/python -m pytest tests/shared/test_health.py -q` → 2 passed；`cd packages/server-python && .venv/bin/python -m pytest -q` → 87 passed in 23.36s；`cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` → 退出码 0。PR #23（https://github.com/MarkDanile/MetaEduBase/pull/23）；merge commit `b8b34a6`；完成日期 `2026-06-04`。后续 follow-up 见 `TD-013`。
```

- [x] **Step 2：commit**

```bash
git add docs/engineering/technical-debt.md
git commit -m "docs(td): close TD-004 with completion notes"
```

---

## Task 11：更新 `work-log.md`

**Files:**
- Modify: `docs/engineering/work-log.md`

- [x] **Step 1：在日期段顶部插入一行索引**

如 work-log.md 已有 2026-06-04 段落，把它最末尾追加：
```md
- 2026-06-04 — TD-004 后端测试数据库可复现 — Spec `docs/specs/2026-06-04-td-004-test-database-reproducibility.md`，Plan `docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md`
```

若无 2026-06-04 段落，按现有格式新增一段（保持与已有索引行的样式一致——一行一条，含日期 + 任务编号 + 简述 + 链接）。

- [x] **Step 2：commit**

```bash
git add docs/engineering/work-log.md
git commit -m "docs(work-log): index TD-004"
```

---

## Task 12：Git 完整交付闭环

> 按 `docs/engineering/rules/git-workflow.md#完整交付闭环` 推进。

- [x] **Step 1：再次回读 current-work.md，确认状态与事实一致**

Run：
```bash
sed -n '/TD-004/,/^###/p' docs/engineering/current-work.md | head -60
```
Expected：状态 `🟢 完成`、验证结果含真实命令与退出码、整篇无未回填的交付占位。

- [x] **Step 2：push 当前分支**

```bash
git push -u origin refactor/td-004-test-db-reproducibility
```

- [x] **Step 3：创建 PR**

```bash
gh pr create --base main --head refactor/td-004-test-db-reproducibility \
  --title "refactor(server): make backend test DB reproducible (TD-004)" \
  --body-file - <<'EOF'
## 摘要

- 测试库连接串改读 `TEST_DATABASE_URL` env（默认值与现状一致）。
- 新增 `app/shared/infrastructure/test_db_setup.py`，幂等建库 + 装 vector/ltree 扩展 + 跑 Alembic upgrade head。
- 新增 `./dev.sh init-test-db` 与 `make init-test-db` 入口。
- conftest 不再隐式 `Base.metadata.create_all`，schema 由前置脚本提供。
- 同步 local-development、quality-gates、README、current-work、technical-debt、work-log。

## 行为变化声明

不是「零业务逻辑变更」。未跑 `init-test-db` 的环境会显式失败（连接成功但缺表/缺扩展），而非隐式建表。其它行为保持兼容：
- `TEST_DATABASE_URL` 缺省时回落到当前硬编码值；
- conftest 仍执行 `CREATE SCHEMA IF NOT EXISTS metaedu` 与 `TRUNCATE templates`。

## 验证

<贴 Task 8 真实输出>

## 关联

- Spec：[docs/specs/2026-06-04-td-004-test-database-reproducibility.md](../specs/2026-06-04-td-004-test-database-reproducibility.md)
- Plan：[docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md](2026-06-04-td-004-test-database-reproducibility-plan.md)
- 技术债：TD-004

## PR 范围

仅触碰 Spec PR 边界列出的文件，未顺手做无关清理。
EOF
```

- [x] **Step 4：合并到 main（按 git-workflow.md 默认策略，squash）**

```bash
gh pr merge --squash --delete-branch
```

- [x] **Step 5：回填 PR 编号 / merge commit / 完成日期**

把 `docs/engineering/current-work.md`「最近完成」中的 TD-004 卡片 `交接备注` 末行、`docs/engineering/technical-debt.md` TD-004 `备注` 末段、`docs/engineering/work-log.md` 对应行的回填占位替换为真实编号；2026-06-04 实际替换为：`PR #23`（https://github.com/MarkDanile/MetaEduBase/pull/23）；merge commit `b8b34a6`；完成日期 `2026-06-04`。

Run：
```bash
git log --oneline -1 main
gh pr view --json number,mergeCommit
```

把真实编号写回三处，commit：
```bash
git add docs/engineering/current-work.md docs/engineering/technical-debt.md docs/engineering/work-log.md
git commit -m "docs(engineering): backfill TD-004 PR + merge commit"
git push
```

> 该 commit 直接落到 `main`（属于交付占位回填，符合 git-workflow.md 例外）。如仓库禁止直推 main，改走 follow-up PR。

---

## Self-Review 检查

**Spec 覆盖：**

| Spec 章节 | 对应任务 |
|----------|---------|
| 1. conftest.py 改造 | Task 2 |
| 2. 新增 test_db_setup.py | Task 1 |
| 3. dev.sh init-test-db | Task 4 |
| 4. Makefile | Task 3 |
| 5. 文档同步：local-development | Task 5 |
| 5. 文档同步：quality-gates | Task 6 |
| 5. 文档同步：README | Task 7 |
| 5. 文档同步：technical-debt | Task 10 |
| 5. 文档同步：current-work | Task 9 |
| 5. 文档同步：work-log | Task 11 |
| 行为变化声明 | Task 12 PR body |
| 验证方式 | Task 8 |
| PR 范围边界 | 各任务 Files 段 + Task 12 PR body |

无 placeholder（每步含可执行命令与代码块）。函数名一致：`init_test_database()` / `_ensure_database()` / `_ensure_extensions_and_schema()` / `_run_alembic_against()` 在 Task 1 与 Task 4 调用一致。`DEFAULT_TEST_DB_URL` 在 Task 1（模块）与 Task 2（conftest）使用同一名字，默认值字符串完全一致。

---

## 任务顺序与回滚

推荐执行顺序：**Task 9 Step 1-2（开分支 + 任务卡）→ Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 → Task 7 → Task 8 → Task 9 Step 3-4 → Task 10 → Task 11 → Task 12**。

回滚：还原 `conftest.py`、删除 `test_db_setup.py` / Makefile target / dev.sh 子命令、回滚文档段落。无 schema 变化、无数据迁移、无 dependency 改动。
