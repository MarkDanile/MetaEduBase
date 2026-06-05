# TD-005 抽取后端任务生命周期 helper — Plan

> **交付历史（2026-06-05）：** TD-005 已通过 PR #34（merge commit `e5197a5`）合并到 `main`。本文保留为历史实施计划；下方清单已按最终交付状态收口，真实交付事实以 `docs/engineering/technical-debt.md#td-005-拆分大型后端任务流水线文件` 和 PR #34 为准。

## 任务入口

- Spec: `docs/specs/2026-06-05-td-005-task-lifecycle-helpers.md`
- 技术债: `docs/engineering/technical-debt.md#td-005-拆分大型后端任务流水线文件`
- 任务卡片: `docs/engineering/current-work.md` 的 TD-005 卡片
- 当前执行模式: `manual`（Claude Code 直接编辑文件，不使用插件）
- 完成后 Git 阶段: 提交 → push → PR → 合并 `main`（按 `docs/engineering/rules/git-workflow.md#快速交付通道`）

## 实施顺序

### 1. 新增共享 helper 模块

- [x] spec/plan 起草（已在 `docs/specs/` 和本文件）
- [x] 创建 `packages/server-python/app/shared/tasks/__init__.py`（空包）
- [x] 创建 `packages/server-python/app/shared/tasks/lifecycle.py`：
  - 公共函数：`get_sync_session`、`run_in_session`、`update_task_status`、`create_task`
  - 兼容别名：`_get_sync_session` / `_run_in_session` / `_update_task_status` / `_create_task`
  - `create_task` 接受 keyword-only `file_id` / `dataset_id`，至少一个非空

**验证点**：模块可被独立 import，无运行时副作用。

### 2. 重构 `document/tasks.py`

- [x] 在文件顶部加入 `from app.shared.tasks.lifecycle import (get_sync_session, run_in_session, update_task_status as _update_task_status, create_task as _create_task)`
- [x] 删除本地 `_get_sync_session`（21 行）
- [x] 删除本地 `_run_in_session`（10 行）
- [x] 删除本地 `_update_task_status`（22 行）
- [x] 删除本地 `_create_task`（14 行）
- [x] 确认所有调用点（`_update_task_status(...)`、`_create_task(...)`、`_run_in_session(...)`、`_get_sync_session()`）不需要改

**验证点**：本地 `_get_*` / `_update_*` / `_create_*` 定义全部消失；`rg` 校验。

### 3. 重构 `structured_data/tasks.py`

- [x] 同上：引入共享 import、删除 4 个本地 helper（38 行）
- [x] 确认所有调用点不需要改

**验证点**：与上面一致。

### 4. 编写 `tests/shared/test_task_lifecycle.py`

- [x] 用 `conftest.py` 的 `TEST_DATABASE_URL` 和 `async_session_factory` 风格
- [x] 覆盖矩阵：
  - `update_task_status` status=running, progress=0 → 写 `started_at`，不写 `completed_at`
  - `update_task_status` status=running, progress>0 → 不写 `started_at`，不写 `completed_at`
  - `update_task_status` status=success → 写 `completed_at`
  - `update_task_status` status=failed + error_message → 写 `completed_at` + `error_message`
  - `update_task_status` 总是写 `updated_at`（与 structured_data 旧实现差异点）
  - `create_task` 传 `file_id` → 写入 `file_id` 列
  - `create_task` 传 `dataset_id` → 写入 `dataset_id` 列
  - `create_task` 同时为空 → 抛 `ValueError`
  - `run_in_session` commit 路径正常返回
  - `run_in_session` 异常路径触发 rollback 并 re-raise

**验证点**：`pytest tests/shared/test_task_lifecycle.py -v` 全部通过。

### 5. 验证

- [x] `cd packages/server-python && .venv/bin/python -m pytest tests/shared/test_task_lifecycle.py -v` 退出码 0
- [x] `cd packages/server-python && .venv/bin/python -m pytest -q` 退出码 0（baseline 114+ passed）
- [x] `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0
- [x] `rg -n "def _get_sync_session|def _run_in_session|def _update_task_status|def _create_task" packages/server-python/app/contexts/` 仍可命中 0 行（仅共享模块保留）

### 6. Git 闭环

- [x] 同步 `docs/engineering/current-work.md` 任务卡片状态：进行中 → 待验证 → 完成
- [x] 创建分支：`git checkout -b refactor/td-005-task-lifecycle-helpers`
- [x] 暂存并提交：`refactor(server): extract task lifecycle helpers from pipeline tasks`
- [x] push：`git push -u origin refactor/td-005-task-lifecycle-helpers`
- [x] 创建 PR：`gh pr create --title "refactor(server): TD-005 extract task lifecycle helpers" --body "..."`
- [x] 检查 `gh pr checks` 通过
- [x] squash merge：`gh pr merge --squash --delete-branch`
- [x] 回填 `docs/engineering/current-work.md` 最近完成区 + `docs/engineering/technical-debt.md` 备注 + `docs/engineering/work-log.md` 索引

## 任务拆分（按 plan-do 步骤）

1. 写 spec/plan（已完成）
2. 抽共享 helper + 收尾两文件
3. 补聚焦测试
4. 跑后端验证
5. 走完整 Git 流程
6. 回填三处任务事实源

每一步都有明确的「命令 + 退出码 + 期望结果」作为强成功标准。

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 删除本地 helper 后某个调用点忘了改 | 引入时使用别名 (`_update_task_status`)，调用点完全不变 |
| `update_task_status` 写 `updated_at` 改变了 structured_data 旧行为 | 文档化声明；`structured_data` 旧实现缺 `updated_at` 是历史不一致，本次收口是合理变更 |
| 共享模块被多处 import 导致 Celery 启动时 ImportError | 集中 import 路径，确保无循环依赖 |
| 测试数据库初始化在分支上不可用 | 按 `docs/engineering/rules/local-development.md` 用 `make init-test-db` 或 `./dev.sh init-test-db` 幂等初始化 |

## 提交前最终回查（按 `docs/engineering/task-modes.md#通用收尾回查`）

- `current-work.md` 状态与代码实际一致。
- `technical-debt.md` 状态与代码实际一致。
- 验证结果来自真实命令输出。
- 业务行为不变声明已写到 PR 描述 + 本文件。
- 测试覆盖了 4 个 helper 的所有 status 分支。
- PR 范围只包含本任务文件（spec/plan、helper 模块、两 tasks.py、测试文件、3 处文档）。
