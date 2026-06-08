# TD-032 切片 5 拆分 `document/interfaces/api/router.py`（494 行）— Plan

## 任务入口

- Spec: `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-5-document-router-split.md`
- 技术债: `docs/03-engineering-governance/technical-debt.md#td-032-治理超大源码文件并建立文件规模拆分原则`
- 任务卡片: `docs/03-engineering-governance/current-work.md` 的 TD-032 切片 5 卡片
- 当前执行模式: `plan-do`（纯重构 + 行为零变化 + 跨 5+ 文件已 spec 覆盖）
- 分支: `refactor/td-032-slice-5-document-router`（已从最新 `main` 切出）
- 完成后 Git 阶段: 提交 → push → PR → 合并 `main`（按 `docs/03-engineering-governance/01-rules/git-workflow.md#快速交付通道`）

## 实施顺序

### 1. 风险 1 提前探针：pre-existing 重复路由

- [ ] 不尝试启动 FastAPI 验证——按 spec §风险 1，重复路由已存在于 baseline，本切片**不**处理。
- [ ] 实施盘点时已在 spec 中明确登记（`router.py:402` ≡ `task_router.py:36`；`router.py:442` ≡ `task_router.py:53`），登记到 `docs/01-product-planning/04-backlog.md` 作为 follow-up（spec §「任务卡片字段」承诺）。

### 2. 按 spec §1 + §3 创建 4 个子 router

按"chunks / tasks / folders / files"顺序拆。**每拆一个子 router，立刻跑 typecheck + pytest**，避免批量失败时难定位。

#### 2.1 创建 `chunks.py`（最小 1 endpoint）

- [ ] 写 `interfaces/api/chunks.py`（~30 行）：迁 `GET /files/{file_id}/chunks` 端点 + 私有构造 dict-from-row 逻辑。
- [ ] 验证：行数 ≤100；endpoint 字符串 / response_model 不变。

#### 2.2 创建 `tasks.py`

- [ ] 写 `interfaces/api/tasks.py`（~100 行）：迁 `GET /files/{file_id}/tasks` + `POST /files/{file_id}/retry` + `_TASK_TYPE_LABELS` 常量。
- [ ] 函数内 `from sqlalchemy import text`（list_file_tasks L408 + retry_file_tasks L448）保持原位。
- [ ] 验证：endpoint 字符串 / response_model / status_code 不变。

#### 2.3 创建 `folders.py`

- [ ] 写 `interfaces/api/folders.py`（~100 行）：迁 5 个 endpoint（list / create / update / delete / move）+ `_folder_row_to_dto` + `_build_tree` 私有 helper。
- [ ] 验证：endpoint 字符串 / response_model / status_code 不变。

#### 2.4 创建 `files.py`

- [ ] 写 `interfaces/api/files.py`（~190 行）：迁 6 个 endpoint（list / upload / get / delete / update / reinitialize）+ `_file_row_to_dto` 私有 helper。
- [ ] 函数内 `from sqlalchemy import text`（reinitialize_file L308）保持原位。
- [ ] 验证：endpoint 字符串 / response_model / status_code 不变。

#### 2.5 精简 `router.py`

- [ ] 重写 `interfaces/api/router.py`（目标 ≤150 行）：
  - 保留模块级 `from app.contexts.document.application.tasks import parse_document`（顶层 re-export 让 `patch()` 仍工作）；
  - 保留 `router = APIRouter()` 顶级对象；
  - 4 行 `from .X import router as X_router` + 4 行 `router.include_router(X_router)`；
  - 删除所有 `@router.*` endpoint 函数（已迁到子 router 文件）；
  - 删除所有私有 helper（已迁到子 router 文件）；
  - 保留 `__all__ = ["router", "parse_document"]`（明确公开 API）。

### 3. 验证

- [ ] **3.1** 行数核对：

  ```bash
  wc -l \
    packages/server-python/app/contexts/document/interfaces/api/router.py \
    packages/server-python/app/contexts/document/interfaces/api/folders.py \
    packages/server-python/app/contexts/document/interfaces/api/files.py \
    packages/server-python/app/contexts/document/interfaces/api/chunks.py \
    packages/server-python/app/contexts/document/interfaces/api/tasks.py
  ```

  期望：router.py ≤150；4 子 router ≤200。

- [ ] **3.2** 文档门禁：

  ```bash
  scripts/check-engineering-docs
  ```

  退出码 0。

- [ ] **3.3** 外部 import 兼容性探针：

  ```bash
  cd packages/server-python
  .venv/bin/python -c "
  from app.contexts.document.interfaces.api.router import router as document_router
  from app.contexts.document.interfaces.api.router import parse_document
  from app.contexts.document.interfaces.api import folders, files, chunks, tasks
  print('all import OK')
  "
  ```

  期望：all import OK。`tests/conftest.py:24` `patch("app.contexts.document.interfaces.api.router.parse_document")` 仍可解析。

- [ ] **3.4** 13 个 endpoint 字符串核对：

  ```bash
  rg -n "@router\.(get|post|patch|delete|put)" \
    packages/server-python/app/contexts/document/interfaces/api/router.py \
    packages/server-python/app/contexts/document/interfaces/api/folders.py \
    packages/server-python/app/contexts/document/interfaces/api/files.py \
    packages/server-python/app/contexts/document/interfaces/api/chunks.py \
    packages/server-python/app/contexts/document/interfaces/api/tasks.py
  ```

  期望：13 个 endpoint（与 baseline router.py 一致）。

- [ ] **3.5** pytest 聚焦测试（cwd=packages/server-python）：

  ```bash
  .venv/bin/python -m pytest tests/shared/ tests/contexts/document/ tests/contexts/structured_data/ -q
  # → 55 passed (12 + 36 + 7) (baseline 一致)
  ```

- [ ] **3.6** ruff：

  ```bash
  .venv/bin/python -m ruff check app/ tests/
  # → All checks passed!
  ```

- [ ] **3.7** `git diff --name-status` 仅包含：
  - `packages/server-python/app/contexts/document/interfaces/api/{router.py,folders.py,files.py,chunks.py,tasks.py}` (1 改 4 新)
  - `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-5-document-router-split.md` (新)
  - `docs/02-delivery-plans/02-plans/2026-06-08-td-032-slice-5-document-router-split-plan.md` (新)
  - `docs/03-engineering-governance/current-work.md` (改)
  - `docs/01-product-planning/04-backlog.md` (改 - 登记 pre-existing 重复路由 follow-up)
  - 无业务代码改动（`app/main.py` / `task_router.py` / 共享组件 / `tests/` 全部不动）。

### 4. Git 闭环

- [ ] 同步 `docs/03-engineering-governance/current-work.md` 任务卡（TD-032 切片 5 收口）。
- [ ] 暂存相关文件（`git add packages/server-python/app/contexts/document/interfaces/api/` + `docs/02-delivery-plans/{01-specs,02-plans}/` + current-work.md + backlog.md）。
- [ ] 提交：`refactor(server): split document router into folders/files/chunks/tasks sub-routers`。
- [ ] push：`git push -u origin refactor/td-032-slice-5-document-router`。
- [ ] PR：`gh pr create --title "refactor(server): TD-032 slice 5 — split document router" --body ...`，body 含 Summary / Scope / Validation / Risks / Docs。
- [ ] `gh pr view --json state,mergeable,reviewDecision` 确认 `MERGEABLE`；`gh pr checks` 查 CI（PR #92-95 均无 CI 配置；本仓库 gate 走本地 `scripts/check-engineering-docs` + pytest）。
- [ ] squash merge：`gh pr merge --squash --delete-branch`。
- [ ] 合并后回写：
  - `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`：`document/interfaces/api/router.py` 状态 `⚪ 待切片` → `🟢 已拆分` + 新行数 + 拆出去向。
  - `docs/03-engineering-governance/technical-debt.md#td-032`：备注追加「切片 5 已合并」+ PR 链接。
  - `docs/03-engineering-governance/work-log.md`：新增 1 行索引。
  - `docs/03-engineering-governance/current-work.md`：TD-032 任务卡「下一步」改为「切片 6 单独 spec / plan」。
  - 上述 docs-only 回写合并到 1 个原子 backfill commit。

## 任务拆分（按 plan-do 步骤）

1. 风险 1 探针（§1，5 分钟）
2. 4 个子 router 文件（§2.1-§2.4）
3. 精简 router.py 主入口（§2.5）
4. 验证（§3，import + endpoint 数 + pytest + ruff + 行数）
5. 走完整 Git 流程
6. 合并后回写 4 处 docs

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| pre-existing 重复路由（router.py 与 task_router.py） | 本切片**不**处理；登记到 `backlog.md` 作为 follow-up；明确 spec §「风险与后续」 |
| `patch("app.contexts.document.interfaces.api.router.parse_document")` 兼容性 | spec §2 已明确：主 router.py 顶部 re-export `parse_document`（即使不直接使用） |
| 函数内 import（`from sqlalchemy import text`）被错提升 | spec §「设计要点 §4」明确：reinitialize_file / list_file_tasks / retry_file_tasks 三个函数体内 import 保持原位 |
| 子 router 文件互相依赖 | spec §「设计要点 §3」明确：每个子 router 不依赖其他子 router；helper 私有 |
| 切片 3 同样 trade-off（抽 vs 不抽 helper） | 本切片沿用切片 3 风格：helper 放 module-level 私有函数，不抽到 `_helpers.py` |
| 沙箱无 metaedu_test，全量 pytest -q 不可达 | §3.5 标"未运行" + 记录原因；聚焦测试 55/55 覆盖核心行为 |

## 提交前最终回查（按 `docs/03-engineering-governance/task-modes.md#通用收尾回查`）

- [ ] `current-work.md` 任务卡与代码实际状态一致。
- [ ] `technical-debt.md` 任务卡状态与代码实际状态一致。
- [ ] `scripts/check-engineering-docs` 退出码 0。
- [ ] 13 个 pytest 聚焦测试（tests/shared + tests/contexts/document + tests/contexts/structured_data）55/55 通过。
- [ ] `ruff check app/ tests/` 退出码 0。
- [ ] 业务行为不变声明写到 PR 描述 + 本文件 + spec。
- [ ] `git diff --name-status` 只包含本任务文件（5 个 Python + 2 个 docs + 1 个 current-work + 1 个 backlog）；无业务代码、无生成物。
