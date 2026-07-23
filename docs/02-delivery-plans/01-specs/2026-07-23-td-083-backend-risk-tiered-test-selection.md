# TD-083 后端风险分级测试选择与性能专项治理 Spec

## 背景

TD-082 已把本地 hooks 收敛到 0-4 秒，并让 docs-only PR 的 Backend/Frontend 在 8-10 秒内 no-op；剩余瓶颈是任何 backend scope PR 都执行全部 `not slow`。PR #467 的可靠基线为 Backend 9m46s，其中 pytest 1351 passed / 4 skipped / 18 deselected 用时 8m19s。

真实 durations 显示 13 个测试占约 4m47s：结构化数据上传相关用例以 19 秒整齐累积，两个双上传用例为 38 秒；`test_retry_file_tasks_returns_pending_tasks` 同样约 19 秒。代码复核确认测试全局 fixture patch 了已不再被上传端点调用的 `router.ds_parse`，却未 patch `celery_app.send_task`，且 document retry 端点的 `parse_document` alias 也未隔离，导致单测连接真实 Celery broker 并等待超时。

## 目标

1. PR 按稳定 Context 所有权和反向依赖选择相关测试，不再因任意叶子后端改动运行全部后端测试。
2. shared、identity、迁移、应用装配、依赖、全局 fixture、CI 和未知路径 fail-safe 执行完整 `not slow`。
3. backend push 到 `main` 执行完整 `not slow`；schedule/workflow_dispatch 执行包含 slow 的全量回归。
4. 修复测试中的真实 Celery broker 逃逸，消除 19/38 秒固定等待，不修改生产任务分发行为。
5. 保持 `Backend`、`Frontend`、`Engineering docs` required check 名称和本地 hooks 行为不变。

## 非目标

- 不引入 pytest-xdist，不按文件数、node 数或 LOC 任意分片。
- 不以改动行数判断风险；一行 identity/shared/migration 改动仍属于高风险。
- 不减少测试用例、不新增 skip/xfail、不把失败测试移出 required check。
- 不在本地 pre-commit/pre-push 增加 pytest、数据库或外部服务。
- 不在本任务启用 merge queue；仓库当前 branch protection 只有三个 required checks，ruleset 为空。

## 风险模型

### 完整 `not slow`

- `app/shared/**`、`app/main.py`、`app/config.py`、`app/celery_app.py`。
- `app/contexts/identity/**`：认证、角色、租户影响所有业务 Context。
- `alembic/**`、`pyproject.toml`、`uv.lock`、根测试 `conftest.py`。
- CI/workflow、选择器自身、PostgreSQL 镜像和无法识别的新后端路径。

### Context 相关测试

选择器维护显式反向依赖映射：

| 改动 Context | 测试范围 |
|--------------|----------|
| `ai_app` | `ai_app` |
| `resource` | `resource` |
| `due_diligence` | `due_diligence` |
| `skill_registry` | `skill_registry` + `due_diligence` |
| `mcp_registry` | `mcp_registry` + `skill_registry` + `due_diligence` + `structured_data` |
| `structured_data` | `structured_data` + `skill_registry` + `knowledge` + legacy `ai` + `internal_mcp` |
| `knowledge` | `knowledge` + legacy `ai` + `document` + `structured_data` |
| `document` | `document` + `knowledge` + legacy `ai` + `structured_data` + `template` |
| `template` | `template` + `document` |

每个 targeted run 固定追加应用启动/健康检查和数据库不可用处理 smoke。测试文件自身变化优先运行该文件；context `conftest.py` 变化运行整个 context；e2e、real_world 和无法归属的测试基础设施变化升级完整回归。

## CI 分层

1. 本地 hooks：保持 TD-082 行为，只做 staged/static 秒级检查。
2. PR：叶子 Context 运行相关测试 + smoke；高风险路径完整 `not slow`。
3. `main` push：backend scope 完整 `not slow`，捕获保守映射仍可能遗漏的远距离回归。
4. schedule/manual：全 scope + 包含 slow 的完整回归。

## 验收标准

- AC-1：选择器输出 `targeted/full`、可审计 reason 和确定性 pytest paths。
- AC-2：9 个 Context 映射、identity/shared/migration/global fixture/CI/未知路径升级、直接测试文件选择均有自动测试。
- AC-3：PR targeted/full、main full-not-slow、schedule/manual full 三层接入，`Backend` required check 名称不变。
- AC-4：structured upload 和 document retry 测试不再访问真实 Celery broker；既有分发行为断言仍成立。
- AC-5：可靠完整 `not slow` 结果不减少；slow 仍由 schedule/manual 执行。
- AC-6：至少一个真实叶子 Context PR 验证 targeted reason、测试集合、CI wall time；CI/测试基础设施改动验证 full fail-safe。
- AC-7：记录修复前后最慢用例与 Backend wall time；不以未实测推算值声明完成。
- AC-8：Codex、Claude Code、终端 Git 和 Windows Git Bash 继续使用同一仓库脚本，无 Agent 私有配置。

## 风险与回退

- 映射漏依赖：显式反向依赖表 + 未知路径 full + main 完整 `not slow` + nightly full 四层兜底；发现遗漏先补映射和回归测试。
- targeted 路径被 marker 全部 deselect：固定 smoke 保证至少有测试执行；slow 测试变化仍由 nightly 验证。
- 选择器异常：fail closed 为 full，不允许静默返回空测试集。
- 回退时可恢复 PR 全部 `not slow`，但不得把 pytest 放回本地 hooks。
