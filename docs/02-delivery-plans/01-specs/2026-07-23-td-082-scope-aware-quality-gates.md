# TD-082 分层质量门禁与 CI 提速 Spec

## 背景

TD-081 建立了可执行的三路 CI，但首个纯文档收口 PR 仍无条件运行全量前后端链路：Backend 10m23s、Frontend 1m8s、Engineering docs 7s。质量门禁已从“缺失”进入“需要分层”的阶段。

## 目标

1. 按实际改动范围执行 Backend、Frontend、MCP 和工程治理检查。
2. 保持 `Backend`、`Frontend`、`Engineering docs` 三个 required check 名称稳定，未命中的 job 快速 no-op 成功。
3. 本地 hooks 只承担快速反馈：commit 检查 staged 文件，push 检查相关静态门禁，不运行 pytest。
4. PR 后端执行 `not slow` 回归；完整 slow 套件每日定时和手动执行。
5. 收口独立 MCP Server 的锁文件、frozen 安装与测试入口。

## 非目标

- 不删除 slow 测试，不降低 required checks 数量，不绕过失败。
- 不在本任务引入 pytest-xdist；当前共享 PostgreSQL 测试库尚未提供 worker 隔离。
- 不修改业务代码、API、数据库 schema 或产品行为。
- 不建立 Codex/Claude 各自的私有门禁副本。

## 设计

### Scope 分类

仓库脚本按路径输出 `backend`、`frontend`、`mcp`、`engineering` 四类布尔值。CI/workflow、hooks 和分类脚本自身变化触发全部类别；未知路径同样 fail-safe 触发全部类别。手动/定时运行使用 full 模式。

### 本地门禁

- pre-commit：staged Python 运行 Ruff，staged Vue/TS 运行 ESLint，工程文档变化运行文档门禁。
- pre-push：阻止 main/master；基于 `origin/main` 到 `HEAD` 的净变更运行相关模块静态检查。后端为 Ruff + mypy baseline，前端为 typecheck，MCP 为 lock check，工程治理为 docs gate。
- pytest 不进入 hooks，避免频繁 commit/push 被分钟级任务阻塞。

### CI 分层

- PR/push：相关后端执行 Ruff、mypy、fresh PostgreSQL 和 `pytest -m "not slow"`；相关前端执行 typecheck、lint、Vitest 和仅 bundle build；相关 MCP 执行 frozen lock/test。
- schedule/workflow_dispatch：全部 scope + 后端含 slow 全量 pytest。
- Engineering docs 每次运行主门禁；仅治理脚本/测试变化时追加工程测试。

## 验收标准

- AC-1：docs-only 分类为 engineering，Backend/Frontend job 均 no-op 且成功。
- AC-2：backend/frontend/MCP 变更分别只激活自身；CI/hook/未知路径激活全部。
- AC-3：三个 required check 名称不变，branch protection 无需改名。
- AC-4：pre-commit 不执行全量 typecheck/pytest；pre-push 不执行 pytest。
- AC-5：PR 后端不执行 slow；每日/手动 full 执行 slow。
- AC-6：前端 bundle 不再次运行 typecheck。
- AC-7：MCP `uv.lock` 被跟踪，pyproject、Makefile、CI 使用 frozen 入口。
- AC-8：分类、hooks、前后端、MCP、工程文档验证全部通过，记录实际耗时。

## 风险与回退

- 路径漏分会漏跑检查：未知路径和 CI 基础设施变化默认全跑，并用分类单测锁定。
- PR 快速套件不能替代完整回归：定时/手动 full 保留全量；后续若 nightly 失败必须作为阻塞 follow-up 修复。
- 当前 backend scope 内仍执行全部 `not slow` 测试；按业务上下文选择相关测试、合并前完整验证和慢测试治理独立进入 TD-083，避免在本任务用不稳定的文件分片换取表面提速。
- MCP 锁文件随 pyproject 变更必须同步；`--frozen` 让漂移直接失败。

## 实施测量

- 后端 PR 套件首次分层：1352 pass / 3 skip / 18 deselect，4m33s。
- durations 定位出 18 个 `test_ai_chat_service.py` 用例仍 patch 旧 `_call_llm`，实际调用 `_call_llm_with_tools` 外部 provider；修正后该文件 24 pass / 0.07s，后端套件 3m07s。
- 前端本地：typecheck 3.10s、lint 2.14s、Vitest 3.60s、bundle 4.82s；CI 另含 runner/checkout/pnpm install 固定开销。
- MCP 本地：Ruff 0.06s、7 tests 2.45s；Engineering docs 主门禁 1.87s。
- 本任务 21 个 staged 文件执行 pre-commit：1.00s，未触发 pytest 或前端全量 typecheck。
- 全范围分支执行 pre-push：4.43s，完成后端 Ruff+mypy、前端 typecheck、MCP lock+Ruff、文档门禁，未运行 pytest。
- PR #467 首轮 run `29987875989`：Backend 9m47s、Frontend 1m05s、Engineering docs 12s；CI/Hook 路径本身触发 fail-safe 全范围，耗时用于建立 fresh runner 基线。
- 两 shard 实验 run `29988992837` 出现 fixture 加载失败且耗时为 3m17s / 8m00s，证明当前按 node 数任意分文件既不可靠也不均衡；该实验已从交付范围撤销，后续由 TD-083 基于稳定测试边界治理。
- 可靠串行收口 run `29990314892`：Backend 9m46s、Frontend 1m01s、Engineering docs 13s，三路全部通过；PR #467 squash merge `754ca109`。
