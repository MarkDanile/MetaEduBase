# TD-004 设计：让后端测试数据库环境可复现

- 任务编号：`TD-004`
- 类型：技术债 / 基础设施
- 领域：Testing / Delivery
- 日期：2026-06-04
- 关联：`docs/engineering/technical-debt.md#td-004-让后端测试数据库环境可复现`

## 背景与证据

- `packages/server-python/tests/conftest.py:14` 硬编码 `TEST_DB_URL = "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"`，无 env 覆盖。
- 同文件 `client` fixture 通过 `Base.metadata.create_all` 隐式建表，绕过 Alembic；测试库实际依赖 schema 与生产迁移路径之间出现漂移时无法被发现。
- 仓库不存在创建 `metaedu_test` 库、安装 `vector` / `ltree` 扩展或运行迁移的统一入口；`./dev.sh init-db` 只面向 dev 库，`Makefile` 只有 `init-dev-db` / `seed-dev`。
- 当前环境中 `pytest` 收集 81+ 测试，其中 ~66 个集成测试一旦本地缺 `metaedu_test`，全部连接失败；新环境或 CI 无可复现路径。

## 目标

- 测试数据库 URL 可通过 `TEST_DATABASE_URL` 环境变量配置；默认值保持与现状一致，避免破坏已有本地开发。
- 提供一条显式启动入口（脚本 + Makefile target），让新环境能在不猜测建库步骤的情况下跑通 `cd packages/server-python && .venv/bin/python -m pytest -q`。
- 测试库 schema 改由 Alembic upgrade head 创建，与生产迁移路径一致；conftest 不再承担建表职责。
- 文档（local-development、quality-gates、README）同步事实。

## 非目标

- 不调整 pytest 用例间的隔离粒度（仍保持现有 `TRUNCATE templates` 行为；其它表跨用例残留如有问题另开 TD-xxx）。
- 不改 Alembic 配置、不动业务测试代码、不调整 `docker-compose.dev.yml`。
- 不引入新的容器（如 `testcontainers-python`），不新建独立 docker-compose profile。
- 不写默认 admin / tenant 之外的 seed 数据（仍由 `conftest._ensure_seed` 负责）。

## 设计

### 1. `conftest.py` 改造

- 引入 `os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)`；`DEFAULT_TEST_DB_URL` 与当前硬编码值一致。
- 删除 `client` fixture 中 `await conn.run_sync(Base.metadata.create_all)`；保留 `CREATE SCHEMA IF NOT EXISTS metaedu` 作为最后兜底（脚本已建过 schema 时是 no-op）。
- 保留现有 `TRUNCATE metaedu.templates RESTART IDENTITY CASCADE` 行为（属于 fixture 内的测试隔离逻辑，本次不动）。
- `_get_test_session` 复用同一个 URL。

### 2. 新增 `app/shared/infrastructure/test_db_setup.py`

模块独立入口，可通过 `python -m app.shared.infrastructure.test_db_setup` 调用。仓库依赖只有 `asyncpg`（不引入 `psycopg2`），实现完全模仿既有 `dev_setup.py` 的 async 风格。顺序：

1. 解析 `TEST_DATABASE_URL`（默认 `postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test`，与 conftest 一致），用 `sqlalchemy.engine.make_url` 拆出 host / port / user / password / dbname。
2. 用 `asyncpg.connect(database="postgres", ...)` 幂等创建测试库：先查 `pg_database` 是否存在 dbname，缺则 `CREATE DATABASE <dbname>`（`CREATE DATABASE` 不能放在事务里，直接调用 `await conn.execute(...)`，asyncpg 默认是 autocommit）。
3. 用 `asyncpg.connect(database=<dbname>, ...)` 幂等执行：
   - `CREATE EXTENSION IF NOT EXISTS vector;`
   - `CREATE EXTENSION IF NOT EXISTS ltree;`
   - `CREATE SCHEMA IF NOT EXISTS metaedu;`
4. 临时将 `settings.database_url`（`pydantic-settings` 字段，运行时可写）指向 test DB URL，调用既有 `app.shared.infrastructure.database.run_migrations()`；完成后恢复原值。
5. 不写 seed；seed 由 conftest `_ensure_seed` 在 fixture 中负责。

幂等约束：脚本可反复执行；alembic upgrade head 在 schema 已 up-to-date 时是 no-op；扩展和库的创建均带 IF NOT EXISTS 或先查后建。

**遗留环境兼容**：旧 `conftest.py` 通过 `Base.metadata.create_all` 直接建表，未写入 `metaedu.alembic_version`，直接 `alembic upgrade head` 会报 `DuplicateTableError`。实现上在 `_run_alembic_against` 前先检查：若业务表（以 `metaedu.tenants` 为探针）已存在但 `alembic_version` 表缺失，先 `alembic stamp head` 让 alembic 认领，再走正常 upgrade。新环境（业务表全不存在）不触发该分支，零开销。

### 3. `dev.sh init-test-db`

- 新增子命令 `init-test-db`：
  1. 调用 `start_infra` 确保 PostgreSQL（Docker 或本地 Homebrew）已运行。
  2. 检查 `.venv` 与依赖（与 `init_dev_db` 同款），不重复造轮子。
  3. 调用 `.venv/bin/python -m app.shared.infrastructure.test_db_setup`。
- `usage` 文本同步追加 `init-test-db` 说明。

### 4. `Makefile`

- 新增 target：
  ```Makefile
  init-test-db:
  	python -m app.shared.infrastructure.test_db_setup
  ```
- 不在 Makefile 中硬编码 `TEST_DATABASE_URL`（由模块默认值或用户 env 提供，避免和 conftest 默认值出现第二份事实源）。
- 在 `test:` target 不强制依赖 `init-test-db`，保留用户按需运行的自由（避免反复跑迁移）。

### 5. 文档同步

- `docs/engineering/rules/local-development.md`：
  - 「数据库迁移」表新增 `make init-test-db` 一行。
  - 新增「测试数据库」小节，列出 `./dev.sh init-test-db`、`TEST_DATABASE_URL` env、默认值。
- `docs/engineering/rules/quality-gates.md`：
  - 「已知门禁状态」中关于「后端完整 pytest 依赖 `localhost:5432/metaedu_test`」的描述改为完成后事实：通过 `./dev.sh init-test-db` / `make init-test-db` 准备，`TEST_DATABASE_URL` 可覆盖。
- `README.md` 后端测试段（如有）：补一行 `./dev.sh init-test-db`。
- `docs/engineering/technical-debt.md#td-004`：状态 → `🟢 完成`，备注追加完成日期、提交、验证摘要。
- `docs/engineering/current-work.md`：登记任务卡片；完成后迁移到「最近完成」。
- `docs/engineering/work-log.md`：新增一行索引。

## 行为变化声明检查

按 `docs/engineering/rules/quality-gates.md#行为变化声明检查`：本任务**不是**「零业务逻辑变更」，存在以下可观察行为变化，需在 PR 描述与最终回复中显式说明：

- 测试 schema 由 conftest 内的 `Base.metadata.create_all` 改为前置脚本中的 `alembic upgrade head`。未运行 `init-test-db` 的环境会显式失败（连接成功但缺表/缺扩展），而非隐式建表。
- 新增模块 `app.shared.infrastructure.test_db_setup`、新增 `dev.sh init-test-db` 子命令、新增 `make init-test-db` target。
- 默认行为（已有本地开发 + `metaedu_test` 已存在）兼容：URL env 缺省时回落到当前硬编码值；conftest 仍执行 `CREATE SCHEMA IF NOT EXISTS metaedu` 与 `TRUNCATE templates`。

## 验证方式

| 验证 | 命令 | 期望 |
|------|------|------|
| 脚本幂等 | `./dev.sh init-test-db` 跑两次 | 两次都退出码 0 |
| Env 覆盖能跑 | `TEST_DATABASE_URL=postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test .venv/bin/python -m pytest tests/shared/test_health.py -q` | passed |
| 端到端 | `cd packages/server-python && .venv/bin/python -m pytest -q` | 87 passed（与 TD-012 baseline 对齐） |
| ruff 无回归 | `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` | 退出码 0 |
| 文档检查 | `rg -n "init-test-db|TEST_DATABASE_URL" docs/engineering/rules README.md` | 落点齐全 |

如端到端 pytest 因本地缺扩展（vector/ltree）失败，必须记录失败摘要，不得写「通过」。

## PR 范围边界

只触碰：

- `packages/server-python/tests/conftest.py`
- `packages/server-python/app/shared/infrastructure/test_db_setup.py`（新增）
- `packages/server-python/Makefile`
- `dev.sh`
- `docs/engineering/rules/local-development.md`
- `docs/engineering/rules/quality-gates.md`
- `README.md`（仅若存在后端测试段）
- `docs/engineering/current-work.md`
- `docs/engineering/technical-debt.md`
- `docs/engineering/work-log.md`
- `docs/specs/2026-06-04-td-004-test-database-reproducibility.md`（本文件）
- `docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md`（下一步生成）

不引入任何与 TD-004 范围无关的资产清理或代码改动。

## 风险与回滚

- **风险**：`psycopg2` 同步连接在某些云环境下被禁；本地仓库已有该依赖，影响面仅限本地开发，可接受。
- **风险**：用户未跑 `init-test-db` 直接 `pytest`，会比之前更早失败；通过文档与错误信息引导。
- **回滚**：还原 conftest 单行 + 删除新模块 / target / 子命令即可；无 schema 变化、无数据迁移。
