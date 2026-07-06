# BUG-013 — 资源库 / 数据库页面 GET 接口 500

> Status: 🟢 Done
> Priority: P1
> Area: 后端 / document 接口 + structured_data 接口
> Created: 2026-07-07
> Closed: 2026-07-07 (commit TBD)

## 现象

两个 GET 接口同时 500：

1. **资源库页面**（前端 `ResourceLibraryView`）加载文件夹树失败
   ```
   GET http://localhost:3000/api/v1/document/folders
   → Request failed with status code 500
   ```
2. **资源库页面**（同上）文件列表加载失败
   ```
   GET http://localhost:3000/api/v1/document/files?limit=100
   → Request failed with status code 500
   ```
3. **数据库页面**（前端 `DatabaseView`）数据集列表加载失败
   ```
   GET http://localhost:3000/api/v1/structured-data/datasets?sort_by=created_at&sort_dir=desc
   → Request failed with status code 500
   ```

## 根因（2026-07-07 traceback 定位）

**PostgreSQL 服务未运行。** Backend 进程已启动但所有 SQL 请求通过 asyncpg 连接池连 `localhost:5432` 时失败：

```
asyncpg/connect_utils.py:1249 raise last_error or exceptions.TargetServerAttributeNotMatched
File "uvloop/loop.pyx", line 2020, in uvloop.loop.Loop.create_connection
ConnectionRefusedError: [Errno 61] Connection refused
```

**链路还原**：
1. 用户停掉 dev 环境（PG / Redis / MinIO）或 `./dev.sh stop` 后未重启
2. Backend (`uvicorn`) 仍跑（自动 reload 模式） → 启动成功（lifespan 只 build QueryService + 无 DB preflight）
3. 前端任意 GET 请求 → backend 路由处理 → `Depends(get_session)` → asyncpg pool 取连接 → 5432 refused → SQLAlchemy 抛 `OperationalError` → FastAPI 默认 exception handler 返回 500

3 个 endpoint 全部 500 因为它们都依赖 `get_session()`；这是 **runtime 环境问题**，不是代码 bug。

**RELEVANT**：
- PR #417 (REQ-052) 不引入此问题。代码本体（`folders.py` / `files.py` / `structured_data/router.py`）30+ commits 内未改。
- 但 PR #417 的 `app/main.py:30-47` lifespan 没有 **DB preflight check**，因此 backend 启动时不知道 PG 是否可用。

## 影响面

- 仅当 PG 不可用时触发。正常 dev 环境（`./dev.sh` 一键启动）下不会复现。

## 修复

### 立即恢复（用户操作）

```bash
./dev.sh          # 启动 PG + Redis + MinIO + backend + frontend
./dev.sh init-db  # 应用所有迁移（含 REQ-052 012-015）
```

或者仅启动 PG：

```bash
./dev.sh infra    # 仅启动基础设施
./dev.sh backend  # 重启后端（如果 lifespan 已失败）
```

### 代码防御（fix/bug-013-resource-database-500 commit）

在 `app/main.py` 加 **全局 exception handler**：捕获 `asyncpg.exceptions.PostgresConnectionError` 和 `sqlalchemy.exc.OperationalError`，返回 **503 Service Unavailable**（不是 500） + 明确 message。这样：

- 前端能区分"server bug"（500）vs"infra down"（503）
- 运维人员从 traceback 立刻知道是 PG 问题
- 符合 RFC 7231：503 用于"暂时不可用，重试可能成功"

## 完成标准

- AC-1：3 个 GET endpoint 在 PG 正常时返回 200 + 合法 JSON（用户操作后实测）
- AC-2：3 个 GET endpoint 在 PG 宕机时返回 **503**（不是 500）+ `{"detail": "数据库暂时不可用，请稍后重试"}`
- AC-3：handler 单测覆盖：注入 fake DB pool 抛 `OperationalError` → 断言 503 响应
- AC-4：handler 不影响其他 500（真正的代码 bug 仍返回 500，handler 只匹配 DB 错误）

## 验证

- 用户操作：`./dev.sh && ./dev.sh init-db` → 3 endpoint 恢复 200
- 单测：注入 mock 触发 `OperationalError` → 503 响应
- 端到端：`pkill postgres` → 重启 backend → 重启 frontend → 资源库/数据库页面显示 503 而非 500
