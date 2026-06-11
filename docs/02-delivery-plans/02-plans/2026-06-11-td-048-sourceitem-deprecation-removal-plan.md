# TD-048 `SourceItem` 旧字段下个迭代删除（契约 deprecation 窗口）— Plan

> Plan 入口：[`docs/02-delivery-plans/01-specs/2026-06-11-td-048-sourceitem-deprecation-removal.md`](../01-specs/2026-06-11-td-048-sourceitem-deprecation-removal.md)（spec）。本文件是实施拆分的事实源。
> 分支：`chore/td-048-remove-sourceitem-legacy-contract-2`（基于切片 1 合并后 main `ba7f441`）。
> 切片结构：3 切片（PR-1 docs-only 修事实源 / PR-2 业务代码 / PR-3 docs-only 跨事实源收口），本 plan 覆盖 PR-2 业务代码。

## 步骤 1 — Cherry-pick 业务代码

- 来源：commit `23a54b1`（原分支 `chore/td-048-remove-sourceitem-legacy-contract` 在 [PR #196](https://github.com/MarkDanile/MetaEduBase/pull/196) 切片 1 合并前已被删除/未跟踪；23a54b1 commit hash 在 git reflog 中仍可访问，但本分支基于 main 直接 `git checkout 23a54b1 -- <file>` 拉 5 个目标文件）。
- 目标文件 5 个：
  1. `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`（-147 行）
  2. `packages/server-python/tests/contexts/ai/test_ai_chat.py`（迁 evidence 端点）
  3. `packages/server-python/tests/contexts/ai/test_ai_chat_rag_e2e.py`（迁 evidence 端点）
  4. `packages/server-python/tests/e2e/test_p1_demo.py`（迁 evidence 端点）
  5. `docs/03-engineering-governance/03-matrices/req-006-p1-final-demo-ui.md`（curl + sources 字段清单更新）
- 不 cherry-pick（已由切片 1 + 切片 3 处理）：
  - `docs/02-delivery-plans/01-specs/2026-06-10-req-010-rag-evidence-governance.md`：AC-1 端点 + AC-3 旧 SourceItem 描述由切片 3 收口（避免与 PR #193 / #195 冲突）
  - `docs/02-delivery-plans/02-plans/2026-06-10-req-010-rag-evidence-governance-plan.md`：Step 3.1 + 7.1 旧 SourceItem 描述由切片 3 收口
  - `docs/03-engineering-governance/current-work.md` / `technical-debt.md` / `work-log.md`：由切片 1 / 3 处理

## 步骤 2 — 验证

按 `quality-gates.md#验证矩阵` "后端 Python" 行：

- **必跑**：`cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/ tests/e2e/test_p1_demo.py -q` 退出码 0（mock-based 路径，按 REQ-003 / REQ-007 经验）。
- **必跑**：`cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0（保留 8 个 TD-049 E402 pre-existing 兼容）。
- **视情况**：依赖 PG 的集成测试在沙箱无 PG 时降级为"mock 路径全绿，CI 接力"；沙箱有 PG 时跑全量 `pytest -q`。
- **视情况**：`cd packages/server-python && .venv/bin/python -m mypy app/contexts/knowledge/interfaces/api/ai_router.py`（如 mypy 已配）。

## 步骤 3 — 范围 / 风险 / 文档

- **范围边界**：`git diff --name-status` 仅 5 个目标文件 + 新建 spec/plan；无业务代码 / 无生成物 / 无 gitignore 之外的资产。
- **行为变化声明**：见 [spec §行为变化声明](../01-specs/2026-06-11-td-048-sourceitem-deprecation-removal.md#验收口径)。
- **文档同步**：
  - 本 plan + spec 已新建（`docs/02-delivery-plans/01-specs/2026-06-11-td-048-sourceitem-deprecation-removal.md` + 本文件）。
  - `req-006-p1-final-demo-ui.md` 矩阵已随业务代码 cherry-pick 更新。
  - `current-work.md` / `technical-debt.md` / `work-log.md` 由切片 3 收口。
  - 切片 2 任务卡交付记录（`technical-debt.md#td-048` 任务详情 L2358 的"交付记录"段）由切片 3 收口时补 PR 链接 + merge commit。

## 步骤 4 — 提交 / PR / 合并

- 提交信息：遵循 conventional commits，本切片用 `chore(rag): TD-048 slice 2 — remove SourceItem legacy contract on main`。
- 提交原子性：5 文件合并为 1 个原子 commit；可考虑拆为 2 commit（业务代码 4 文件 + 矩阵 1 文件）但本切片 1 个 commit 也可接受（23a54b1 原本就是 1 commit）。
- PR 描述必含：Summary / Scope / Validation / Risks / Docs。
- 合并前：`gh pr view` 显示 `mergeable=true` + `gh pr checks` 无阻塞（PR 未配 CI 与本切片 1 一致）。
- 合并：squash merge + delete-branch。
- 合并后：本地 main 同步。

## 风险登记（提交前再回看一次）

1. **沙箱无 PG 时 pytest 降级**：必须明确写明"mock-based 路径全绿；CI 接力 PG 集成"——不能写成"全部通过"。
2. **5 文件外的脏改动**：提交前 `git status --short --branch` 确认工作区只有 5 文件 + spec/plan。
3. **历史 PR #193 / #195 已修改 REQ-010 spec/plan**：切片 2 不能动 spec/plan；切片 3 收口时如有冲突以 `gh pr diff` 为准。
4. **DOC-057 pre-existing 验证缺口**：本切片 2 不在范围；`scripts/check-engineering-docs` 仍会报 `current-work.md:38` 提示，按 quality-gates.md 验证表述规范写"未通过 / 历史失败"。

## 任务卡片（切片 3 收口时回填）

切片 2 合并后由切片 3 在 `docs/03-engineering-governance/technical-debt.md#td-048` 任务详情 L2358 的"交付记录"段补：

- 切片 1 PR：#196 / merge `ba7f441`
- 切片 2 PR：（待提）/ merge（待填）
- 切片 3 PR：（待提）/ merge（待填）

## 关联

- 任务卡：`docs/03-engineering-governance/technical-debt.md#td-048`
- spec：`docs/02-delivery-plans/01-specs/2026-06-11-td-048-sourceitem-deprecation-removal.md`
- 切片 1 PR：#196
- 原始 commit：`23a54b1`（未合 main，作为 cherry-pick 来源）
