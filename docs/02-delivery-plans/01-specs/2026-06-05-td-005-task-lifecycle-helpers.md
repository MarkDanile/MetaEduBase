# TD-005 抽取后端任务生命周期 helper — Spec

## 背景

`docs/03-engineering-governance/technical-debt.md#td-005-拆分大型后端任务流水线文件` 记录了两份大型
Celery 任务编排文件：

- `packages/server-python/app/contexts/document/application/tasks.py`（约 994 行）
- `packages/server-python/app/contexts/structured_data/application/tasks.py`（约 731 行）

两份文件都重复实现了同组「任务生命周期」横切逻辑：

| 函数 | document/tasks.py | structured_data/tasks.py | 重复度 |
|------|-------------------|--------------------------|--------|
| `_get_sync_session` | 21 行 | 19 行 | 几乎逐字相同 |
| `_run_in_session` | 10 行 | 9 行 | 完全相同（仅参数名） |
| `_update_task_status` | 22 行 | 22 行 | 几乎逐字相同（document 版多一列 `updated_at`） |
| `_create_task` | 14 行 | 14 行 | 结构相同，差异在 `file_id` vs `dataset_id` 列 |

两边的 Celery 任务编排（`parse_document`/`chunk_document`/…/`ds_parse`/…）只关心真正的
业务步骤；这部分本身不属于本任务范围，留给后续技术债处理。

## 目标

把上述四个「任务生命周期 helper」抽到共享模块 `app/shared/tasks/lifecycle.py`，
让 `document/tasks.py` 与 `structured_data/tasks.py` 通过 import 使用共享版本，
**业务行为不变**。

## 范围

### In scope

- 新增 `packages/server-python/app/shared/tasks/__init__.py`
- 新增 `packages/server-python/app/shared/tasks/lifecycle.py`，集中以下 helper：
  - `get_sync_session()`：在 Celery worker 的独立事件循环中创建一次性 AsyncSession
  - `run_in_session(coro)`：包一层 commit / rollback / 异常重抛
  - `update_task_status(session, task_id, status, progress, error_message)`：写入
    `metaedu.document_tasks` 表，统一维护 `started_at` / `completed_at` / `error_message`
  - `create_task(session, tenant_id, *, file_id=None, dataset_id=None, task_type)`：
    插入一行 `document_tasks` 记录，返回 task_id
- 重构 `document/tasks.py` 与 `structured_data/tasks.py`，删除本地 helper 副本，
  改为 import 共享版本；调用点签名保持兼容。
- 新增 `tests/shared/test_task_lifecycle.py`，对抽出的 helper 做聚焦测试：
  - `get_sync_session` 在 context manager 内/外行为、commit/rollback 分支
  - `update_task_status` 写入的列集合与值（按 status 不同分支覆盖）
  - `create_task` 写入 `file_id` 或 `dataset_id` 时的差异
  - 业务层调用点（`parse_document`、`ds_parse` 等）通过现有后端 pytest 间接覆盖
- `document/tasks.py` 与 `structured_data/tasks.py` 自身的行数应有可观察下降（目标
  是 helper 部分的 60~80 行被替换为 import + 兼容别名）。

### Out of scope

- 不动 Celery 任务编排流程本身（不重排 6 步 document pipeline、不重排 4 步
  structured_data pipeline）。
- 不动横切以外的本地逻辑（解析器分发、prompt 构造、KG 写入）。
- 不动 `factory.py` / `template/service.py` / `chat.py` 等 LLM 相关代码（属于 TD-006）。
- 不重构 prompt 构造、解析器分发等其他横切逻辑（这些是 TD-005 后续可选项，
  留到下一轮）。

## 设计要点

### 1. 共享 helper 模块结构

`app/shared/tasks/lifecycle.py` 暴露 4 个公共函数（不再以下划线开头）：

```python
async def get_sync_session() -> AsyncIterator[AsyncSession]: ...
async def run_in_session(coro): ...
async def update_task_status(
    session: AsyncSession,
    task_id: uuid.UUID,
    status: str,
    progress: int = 0,
    error_message: str | None = None,
) -> None: ...
async def create_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    file_id: uuid.UUID | None = None,
    dataset_id: uuid.UUID | None = None,
    task_type: str,
) -> uuid.UUID: ...
```

`update_task_status` 统一保留 `updated_at` 列（document 旧版就带，structured_data
旧版没带，合并到共享版时统一为「始终写 `updated_at`」，对 structured_data 是
`True→True` 的扩展，不改变可观察行为）。这个扩展点会在 PR 描述中明确说明。

`create_task` 采用 keyword-only `file_id` / `dataset_id`，并校验**至少一个非空**，
避免空指针写入。

### 2. 兼容导入别名

为了让 `document/tasks.py` 与 `structured_data/tasks.py` 的内部命名尽量不变化，
helper 模块同时导出以下别名：

- `get_sync_session` / `run_in_session` / `update_task_status` / `create_task`（公共名）
- `_get_sync_session` / `_run_in_session` / `_update_task_status` / `_create_task`
  （带下划线别名，保留对内调用点的兼容；后续逐步迁移到公共名）

两文件把本地实现替换为 `from app.shared.tasks.lifecycle import (...,)` 即可。

### 3. 测试策略

- `tests/shared/test_task_lifecycle.py`：直接对共享 helper 做集成测试，连接
  `metaedu_test`，验证写入列、commit/rollback、`file_id` vs `dataset_id` 两种
  `create_task` 路径。
- 业务测试（`test_datasets.py`、`test_files.py`、`test_cascade_cleanup.py` 等）
  不需要修改，它们走 `pytest` 间接覆盖了 Celery 任务调用的 helper 链路。
- 验证流程按 `docs/03-engineering-governance/01-rules/quality-gates.md`：先
  `pytest tests/shared/test_task_lifecycle.py`，再 `pytest -q` 全量，再
  `ruff check app/ tests/`。

### 4. 行为不变声明

按 `docs/03-engineering-governance/01-rules/quality-gates.md#行为变化声明检查` 排查：

| 类别 | 是否变化 | 说明 |
|------|----------|------|
| 函数签名 / API | 不变 | 4 个 helper 签名一致；调用点无需修改 |
| 条件判断 / 循环 | 不变 | 只复制实现，未改逻辑 |
| 异常处理 | 不变 | commit / rollback / raise 流程未变 |
| 校验规则 | 加严 | `create_task` 加 keyword-only + 至少一个非空校验（不影响现有调用） |
| SQL / ORM 查询 | 文本变化但语义不变 | `update_task_status` 的 SET 列表仍由 status/progress 决定 |
| 字符串内容 | 不变 | 状态字符串、日志不变 |
| import 副作用 | 变化 | 新增 `app.shared.tasks.lifecycle` 模块，Celery task 注册顺序不变 |

可观察的、唯一的变化是 `update_task_status` 在 `structured_data` 路径上多写一列
`updated_at`（之前是 document 路径写，structured_data 不写）。这是把两边对齐到
「`update_task_status` 永远维护 `updated_at`」的合理收口，不影响业务行为。

## 完成标准

1. `app/shared/tasks/lifecycle.py` 存在并实现 4 个公共 helper。
2. `document/tasks.py` 与 `structured_data/tasks.py` 删除本地 helper 实现，改用
   共享版本；两文件本地不再出现 `_get_sync_session` / `_run_in_session` /
   `_update_task_status` / `_create_task` 四个函数的定义。
3. `tests/shared/test_task_lifecycle.py` 新增并通过，覆盖：
   - `update_task_status` 三种 status 分支（running / success / failed）
   - `update_task_status` 写 / 不写 `started_at` / `completed_at` 的边界
   - `create_task` 在 `file_id` / `dataset_id` 两种模式下都正确写入
   - `create_task` 拒绝 `file_id` 与 `dataset_id` 同时缺失
4. `pytest -q` 全量通过（baseline 期望与 `technical-debt.md` 收尾的 114 passed
   一致或更多，因为新增了 helper 测试）。
5. `ruff check app/ tests/` 退出码 0。
6. 提交信息遵循 Conventional Commits：`refactor(server): extract task lifecycle helpers`。

## 验证方式

按 `docs/03-engineering-governance/01-rules/quality-gates.md#验证矩阵` 选后端 Python 行：

```bash
cd packages/server-python
.venv/bin/python -m pytest tests/shared/test_task_lifecycle.py -v
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app/ tests/
```

并按 `#行为变化声明检查` 显式声明：
> 本次重构以提取重复 helper 为主，行为变化仅限于
> `structured_data` 路径下 `update_task_status` 现在会写 `updated_at` 列
> （与 `document` 路径对齐）。所有可观察业务行为不变。

## 风险与后续

- 风险：合并 helper 时如果漏改某个调用点，Celery 任务会在启动时
  `ImportError`。已用 `from app.shared.tasks.lifecycle import (...)` 集中引入，
  并保留下划线别名缓解。
- 后续：TD-005 的剩余候选 helper（解析器分发、prompt 构造、KG 写入）可在下一轮
  重新评估是否仍值得抽；当前任务只交付生命周期一组。
- 后续：TD-006 集中 LLM provider / fallback 策略是独立任务，不在本次范围。

## 任务卡片字段

完成后需在 `docs/03-engineering-governance/current-work.md` 把 TD-005 移到「最近完成」并记录
PR 链接，同时在 `docs/03-engineering-governance/technical-debt.md#td-005-拆分大型后端任务流水线文件`
的备注中追加完成日期、提交信息和验证结果。
