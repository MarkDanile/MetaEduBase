# BUG-008: REQ-013 Context Packer 引入 structlog 依赖但 pyproject 未声明 — backend 重启 import 失败

Status: 🔵 Ready
Priority: P1
Milestone: P1 RAG 治理
Related: REQ-013 / context_packer.py

## Problem

REQ-013 PR #305 在 `packages/server-python/app/contexts/knowledge/application/context_packer.py:40` 新增 `import structlog`，但 `packages/server-python/pyproject.toml` 未声明该依赖，dev `.venv` 也没装。

**现象**：

- `python -c "from app.contexts.knowledge.application.context_packer import ContextPacker"` → `ModuleNotFoundError: No module named 'structlog'`
- `python -m uvicorn app.main:app` → 启动时 import 链崩在 `context_packer.py:40`
- 重启后端（`./dev.sh backend` / `./dev.sh restart_backend`）后任何新 uvicorn 进程无法启动
- 当前 `localhost:8000` 的 200 响应是 PR #305 之前的老 uvicorn 进程（PID 6602）维持；该进程不依赖新代码

**用户影响**：

- `./dev.sh` 看起来"卡死"——实际是 backend skip（检测老进程在跑）+ 后续 `restart_backend` 失败未透出
- 任何 backend 重启 = 服务不可用
- 真 PG 验收（REQ-014 后续 PR）无法在重启后的 dev 环境跑

## Repro

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase/packages/server-python
./.venv/bin/python -c "import structlog"
# ModuleNotFoundError: No module named 'structlog'

./.venv/bin/python -c "from app.contexts.knowledge.application.context_packer import ContextPacker"
# ModuleNotFoundError: No module named 'structlog' (from context_packer.py:40)
```

## Root Cause

`context_packer.py:40`：

```python
import structlog
```

未在 `pyproject.toml` 的 dependencies 中声明。REQ-013 塑形时（PR #304 plan）没把 `structlog` 列为新依赖；PR #305 实现时也没补。

## Fix

`packages/server-python/pyproject.toml` 在 dependencies 段增加 `structlog>=24.1.0`（或项目实际使用的版本，需先在 dev 装一遍定版本）。

## Validation

- `cd packages/server-python && pip install -e ".[dev,ai]"` 后 `python -c "import structlog"` 退出 0
- `python -c "from app.contexts.knowledge.application.context_packer import ContextPacker"` 退出 0
- `./dev.sh backend` 后新 uvicorn 健康检查 200
- 439+ mock pytest 0 业务代码回归
- BUG-006 / BUG-007 / REQ-013 / REQ-014 现有验收命令不退步

## Scope

- 单文件 `pyproject.toml` + lock file（如 poetry.lock / uv.lock）
- 不动业务代码
- 不动 context_packer.py（用法保持）
- 不开新 PR 改 structlog 行为

## Delivery

- 计划 PR 标题：`fix(deps): BUG-008 add structlog to pyproject dependencies`
- 关联 commit：补 pyproject + 重装 + 锁文件
- 修完后回填 Backlog / work-log / current-work

## Follow-up

- 是否需要补 `structlog` 业务使用（context_packer 的 structlog 用途未在本 PR 体现）→ 另开 REQ / TD 评估
- 同样思路 review：REQ-013 是否引入其它未声明依赖？→ 跑 `pip check` + `pip list --not-required` 找孤儿
