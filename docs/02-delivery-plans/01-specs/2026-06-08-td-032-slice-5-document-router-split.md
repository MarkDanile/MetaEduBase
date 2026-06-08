# TD-032 切片 5 拆分 `document/interfaces/api/router.py`（494 行）— Spec

## 背景

`docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` 把
`packages/server-python/app/contexts/document/interfaces/api/router.py`（494 行）登记
为「⚪ 待切片」，优先级 P2。

TD-032 切片 1-4 整体收口后（[PR #92](https://github.com/MarkDanile/MetaEduBase/pull/92) / `3de4de5` + [PR #93](https://github.com/MarkDanile/MetaEduBase/pull/93) / `7e468fb` + [PR #94](https://github.com/MarkDanile/MetaEduBase/pull/94) / `5beb938` + [PR #95](https://github.com/MarkDanile/MetaEduBase/pull/95) / `d4d2720`），本切片按
`2026-06-08-td-032-large-source-files-plan.md#切片-3` 中预留的"按 `resource_type` / `action` 拆
`document/router.py` 子文件"路径推进。

**重要前置发现**：
- `packages/server-python/app/contexts/document/interfaces/api/task_router.py`（73 行）已**独立存在**并由 `app/main.py:7` 单独挂载。**该文件不属于本切片范围**。
- 实施盘点时发现 **pre-existing 重复路由**：
  - `router.py:402` `GET /files/{file_id}/tasks` ≡ `task_router.py:36` 同一 path；
  - `router.py:442` `POST /files/{file_id}/retry` ≡ `task_router.py:53` 同一 path；
  - 两个 router 都通过 main.py 不同行挂载到同一 `/api/v1/document` prefix，FastAPI 启动会报"duplicate path"。
  - 切片 5 范围内**不**主动删除任一端（避免功能变化），保持现状（pre-existing duplicate 仍存在）。**新增 follow-up DOC-xxx / TD-xxx 任务**登记到 backlog，由后续切片单独处理。
- `tests/conftest.py:24` 用 `patch("app.contexts.document.interfaces.api.router.parse_document")` —— 主 router 模块名不能变；切片 5 保留 `router.py` 作为**模块**（不是包），子 router 放同目录 `interfaces/api/` 下。
- 切片 3 经验：函数内 import（`from sqlalchemy import text` 在 reinitialize_file / list_file_tasks / retry_file_tasks 三个函数体内）保持原位，**不**提升到模块顶部。
- TD-005 既有产物（`app/shared/tasks/lifecycle.py`）不动；切片 5 仅涉及 document router 拆分。

## 目标

1. 把 `document/interfaces/api/router.py` 494 行拆为：主入口 `router.py`（目标 ≤150 行）+ 4 个聚焦子 router `folders.py` / `files.py` / `chunks.py` / `tasks.py`（每个 ≤200 行）。
2. **零业务行为变化**：所有 13 个 endpoint 字符串、request/response schema、SQL、Celery dispatch、HTTP status 全部 byte-equivalent。
3. **保持外部兼容性**：
   - `app/main.py:6` `from app.contexts.document.interfaces.api.router import router as document_router` 仍解析；
   - `tests/conftest.py:24` `patch("app.contexts.document.interfaces.api.router.parse_document")` 仍工作（主 router 模块顶层 re-export `parse_document`）。
4. **不**触动 `task_router.py`（pre-existing 文件，由 follow-up 处理与主 router 重复路由）。

## 范围

### In scope

- 新建 `packages/server-python/app/contexts/document/interfaces/api/folders.py`（~100 行）：
  - 5 个 endpoint：`GET /folders` / `POST /folders` / `PATCH /folders/{folder_id}` / `DELETE /folders/{folder_id}` / `PATCH /folders/{folder_id}/move`。
  - 私有 helper `_folder_row_to_dto` / `_build_tree` 保留在该文件内（不上主 router 命名空间）。
- 新建 `packages/server-python/app/contexts/document/interfaces/api/files.py`（~190 行）：
  - 6 个 endpoint：`GET /files` / `POST /files/upload` / `GET /files/{file_id}` / `DELETE /files/{file_id}` / `PATCH /files/{file_id}` / `POST /files/{file_id}/reinitialize`。
  - 私有 helper `_file_row_to_dto` 保留在该文件内。
  - 函数内 `from sqlalchemy import text`（reinitialize_file L308）保持原位。
- 新建 `packages/server-python/app/contexts/document/interfaces/api/chunks.py`（~30 行）：
  - 1 个 endpoint：`GET /files/{file_id}/chunks`。
- 新建 `packages/server-python/app/contexts/document/interfaces/api/tasks.py`（~100 行）：
  - 2 个 endpoint：`GET /files/{file_id}/tasks` / `POST /files/{file_id}/retry`。
  - 私有常量 `_TASK_TYPE_LABELS` 保留在该文件内（**不**复用 `app.contexts.document.domain.entities.TASK_TYPE_LABELS`——避免跨上下文耦合；保持与原 router.py 行为一致）。
  - 函数内 `from sqlalchemy import text`（list_file_tasks L408 + retry_file_tasks L448）保持原位。
- 精简 `packages/server-python/app/contexts/document/interfaces/api/router.py`（目标 ≤150 行）：
  - 保留：模块级 import（含 `from app.contexts.document.application.tasks import parse_document` 顶层 re-export）+ `router = APIRouter()` 顶级对象 + 4 个 `from .X import router as X_router` + 4 行 `router.include_router(X_router)`。
  - 删除：所有 `@router.*` 装饰的 endpoint 函数（已迁到子 router 文件）；所有 `_folder_row_to_dto` / `_build_tree` / `_file_row_to_dto` / `_TASK_TYPE_LABELS` 私有 helper（已迁到子 router 文件）。
- 任务卡 `docs/03-engineering-governance/current-work.md` 同步刷新。
- spec / plan 落仓。
- `docs/01-product-planning/04-backlog.md` 登记 pre-existing 重复路由的 follow-up 任务（DOC-xxx / TD-xxx 风格）。

### Out of scope

- 不动 `app/main.py`（main.py 已挂载 `document_router` + `document_task_router` 两条 main.py 路径；切片 5 保持现状）。
- 不动 `task_router.py`（pre-existing 独立文件，由 follow-up 处理重复路由；本切片**不**主动删除或合并）。
- 不动 `app/contexts/document/application/tasks/` 任何文件（切片 3 产物）。
- 不动 `app/shared/tasks/lifecycle.py`（TD-005 产物）。
- 不动任何 `infrastructure/*` repository（`FolderRepository` / `FileRepository` / `ChunkRepository`）。
- 不动 `dto.py` / `domain/*` / `cleanup.py`。
- 不动任何 `tests/` 文件——本切片只验证既有 `pytest tests/contexts/document/ + tests/shared/` 55 个测试 0 改动通过；不补新测试（切片 5 是"拆 router，零行为变化"，不引入新行为）。
- 不动前端 / CSS / Tailwind / `main.css`。
- 不引入新依赖。

## 设计要点

### 1. 文件拓扑

```
packages/server-python/app/contexts/document/interfaces/api/
├── __init__.py                 # 现有, 不动
├── router.py                   # 主入口, 目标 ≤150 行
├── task_router.py              # 73 行, 不动 (本切片 out of scope)
├── folders.py                  # ~100 行 (新增)
├── files.py                    # ~190 行 (新增)
├── chunks.py                   # ~30 行 (新增)
└── tasks.py                    # ~100 行 (新增)
```

主 router.py 是**模块**（不是包）；子 router 文件放同目录。这保持 `from app.contexts.document.interfaces.api.router import router` 路径不变。

### 2. router.py 瘦身设计

```python
"""Document context API router — folders, files, chunks, tasks.

按 `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-5-document-router-split.md`
拆分自原单文件（494 行）。子 router 包含到本 router 后由 main.py 统一挂载。

主 router 模块顶层 re-export `parse_document`，让 `patch("app.contexts.document.interfaces.api.router.parse_document")` 仍工作（tests/conftest.py:24）。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.contexts.document.application.tasks import parse_document  # noqa: F401  (re-export for tests)

from .chunks import router as chunks_router
from .files import router as files_router
from .folders import router as folders_router
from .tasks import router as tasks_router

router = APIRouter()
router.include_router(folders_router)
router.include_router(files_router)
router.include_router(chunks_router)
router.include_router(tasks_router)

__all__ = ["router", "parse_document"]
```

### 3. 子 router 文件设计模式

每个子 router 文件结构：

```python
"""folders router — 5 endpoints for folder CRUD + tree + move."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.document.application.dto import FolderCreate, FolderDTO, FolderMove, FolderUpdate
from app.contexts.document.infrastructure.folder_repository import FolderRepository
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id


# --- Helpers (private to this module) ---
def _folder_row_to_dto(row: dict) -> FolderDTO:
    ...

def _build_tree(flat: list[dict]) -> list[FolderDTO]:
    ...


# --- Endpoints ---
router = APIRouter()

@router.get("/folders", response_model=list[FolderDTO])
async def list_folders(...): ...
# 其它 4 个 endpoint ...
```

每个子 router 文件**不**依赖其他子 router；helper 私有（不上 `__all__`）。

### 4. 与切片 3 风格一致

- 函数内 `import`（如 `from sqlalchemy import text`）保持原位。
- 私有 helper 放 module-level 私有函数（不抽到独立 `_helpers.py` 子模块）。
- 不在 endpoint 函数体内 import 业务 service（仅 SQL/ORM 操作通过现有 repository）。

### 5. 行数目标

- `router.py` ≤150 行（实际预计 ~25 行 + ~10 行 docstring/comment）。
- `folders.py` ≤200 行（5 endpoint + 2 helper）。
- `files.py` ≤200 行（6 endpoint + 1 helper）。
- `chunks.py` ≤100 行（1 endpoint）。
- `tasks.py` ≤200 行（2 endpoint + 1 label dict + 2 函数内 import）。

## 完成标准

1. `router.py` ≤150 行；4 个子 router 文件就位，每个 ≤200 行。
2. `app/main.py:6` 的 `from app.contexts.document.interfaces.api.router import router as document_router` 仍解析；main.py 启动**不**比 baseline 多报错。
3. `tests/conftest.py:24` 的 `patch("app.contexts.document.interfaces.api.router.parse_document")` 仍工作。
4. 13 个 `@router.*` endpoint 全部 byte-equivalent（HTTP method / path / response_model / status_code / function body 不变）。
5. `app/main.py` 不动（pre-existing 重复路由问题不归本切片）。
6. `task_router.py` 不动。
7. 既有 6 个后端测试文件（`tests/shared/test_task_lifecycle.py` 12 + `tests/contexts/document/` 36 + `tests/contexts/structured_data/` 7 = 55 个）0 改动全部通过。
8. `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0。

## 验证方式

按 `docs/03-engineering-governance/01-rules/quality-gates.md#验证矩阵` 选后端 Python 行：

```bash
# 行为基线（拆分前后必须一致）
cd packages/server-python
.venv/bin/python -m pytest tests/shared/ tests/contexts/document/ tests/contexts/structured_data/ -q
# → 55 passed (12 + 36 + 7) (baseline 一致)

.venv/bin/python -m ruff check app/ tests/
# → All checks passed!

# Import 探针
.venv/bin/python -c "
from app.contexts.document.interfaces.api.router import router as document_router
from app.contexts.document.interfaces.api.router import parse_document
from app.contexts.document.interfaces.api import folders, files, chunks, tasks
print('all import OK')
"

# 文档门禁
scripts/check-engineering-docs
# → engineering docs checks passed
```

按 `quality-gates.md#行为变化声明检查` 显式声明：

> 本次为纯重构（拆 router.py）。所有 13 个 `@router.*` endpoint 字符串、HTTP method、
> path、response_model、status_code、SQL、Celery dispatch 全部 byte-equivalent。私有
> helper（`_folder_row_to_dto` / `_build_tree` / `_file_row_to_dto` / `_TASK_TYPE_LABELS`）
> 全部 byte-equivalent 迁到对应子 router 文件。函数内 import（`from sqlalchemy import text`）
> 保持原位。
>
> 唯一可见变化：`document/interfaces/api/router.py` 494 → ≤150 行；新增 4 个聚焦
> 子 router 文件；主 router 顶层 re-export `parse_document` 供 tests 兼容。
>
> **pre-existing 重复路由**（`router.py` 与 `task_router.py` 各定义 `GET /files/{file_id}/tasks` + `POST /files/{file_id}/retry`）**不**在本切片范围内处理；记录到 `docs/01-product-planning/04-backlog.md` 作为 follow-up（DOC-xxx 风格）。

## 风险与后续

- **风险 1**：pre-existing 重复路由（router.py 与 task_router.py）会在 FastAPI 启动时报错或行为未定义。**本切片不**处理；记录为 follow-up。**当前 main 启动行为**即为 baseline（已存在该问题），切片 5 实施后不增加新问题。
- **风险 2**：`patch("app.contexts.document.interfaces.api.router.parse_document")` 通过模块名解析——主 router.py 顶部必须有 `from app.contexts.document.application.tasks import parse_document`（即使不直接使用），让 `app.contexts.document.interfaces.api.router.parse_document` 仍指向同一对象。spec §2 已明确 re-export。
- **风险 3**：切片 3 实施时发现的"`from sqlalchemy import text` 保留函数内 import"约束在 router 拆分时同样适用——`reinitialize_file` / `list_file_tasks` / `retry_file_tasks` 三个函数体内 import 保持原位。
- **风险 4**：拆分后子 router 文件间不互相依赖；但**所有**子 router 仍用 `get_tenant_id()` / `get_current_user()` 等共享依赖。spec 不新增共享 helper（避免 YAGNI）；后续如真出现"helper 在 4 个子 router 重复"，可由独立切片处理。
- **后续**：pre-existing 重复路由清理（`task_router.py` 与主 router 重复 endpoint 合并 / 删除）由独立 follow-up 任务承接（DOC-xxx 或 TD-xxx 风格），登记到 `docs/01-product-planning/04-backlog.md`。
- **后续**：切片 6（`ResourceLibraryView.vue` 490）+ 切片 7（`FileDetailView.vue` 416）由各自独立 spec / plan 承载。
- **后续**：TD-032 任务整体保持 `🟢 完成`；本切片不改变任务状态。

## 任务卡片字段

完成后需在 `docs/03-engineering-governance/current-work.md` 把本任务卡「下一步」从「切片 5 spec / plan / 分支」改为「切片 5 已合并；切片 6 待开工」；`docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` 中 `document/interfaces/api/router.py` 状态从 `⚪ 待切片` 改为 `🟢 已拆分` + 新行数 + 拆出去向；`docs/03-engineering-governance/technical-debt.md#td-032` 备注追加「切片 5 已合并」；`docs/03-engineering-governance/work-log.md` 加一行索引；`docs/01-product-planning/04-backlog.md` 登记 pre-existing 重复路由 follow-up 任务。
