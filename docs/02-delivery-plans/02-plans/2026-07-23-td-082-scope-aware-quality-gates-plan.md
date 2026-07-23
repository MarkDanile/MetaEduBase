# TD-082 分层质量门禁与 CI 提速实施计划

## Step 1：建立 scope 分类事实源

- 新增可在 macOS/Linux/Windows Git Bash 执行的路径分类脚本。
- 新增工程测试覆盖 docs/backend/frontend/MCP/基础设施/未知路径。
- 验证：分类单测与 shell smoke。

状态：已完成；覆盖空 diff 与 macOS Bash 3.2 `set -u` 兼容。

## Step 2：轻量化本地 hooks

- pre-commit 改为 staged-file Ruff/ESLint/docs gate。
- pre-push 复用 scope 分类，只跑相关静态检查；不运行 pytest。
- 验证：脚本语法、模拟 staged/diff、main 拦截和失败传播。

状态：已完成；真实 staged 变更 pre-commit 1.00s，全范围分支 pre-push 4.43s。

## Step 3：改造 GitHub CI

- 每个 required job 内执行亚秒级 change classification，避免单独分类 job 串行增加等待；三个 required jobs 始终创建。
- Backend/Frontend 对无关改动 no-op；Engineering docs 保持常驻。
- 后端 PR 使用 `not slow`；schedule/manual 使用全量。
- 前端 build 去掉重复 typecheck；治理测试移到 Engineering docs 的条件步骤。
- 验证：workflow 语法、相关本地命令、PR 三路耗时。

状态：实现与本地验证已完成；PR #467 首轮三路通过。任意文件分片实验因 fixture 边界失效和耗时失衡已撤销，稳定名称与串行可靠回归保持不变。

## Step 4：收口 MCP 锁文件

- 提交 `packages/mcp-server/uv.lock`，增加 dev 测试依赖和 frozen Makefile 入口。
- CI 在 MCP scope 下执行 lock check 和测试。
- 验证：`uv lock --check`、frozen sync/test。

状态：已完成；38 个锁定包，Ruff 与 7 个测试通过。

## Step 5：收尾

- 更新 testing、quality-gates、local-development 的分层口径。
- 运行相关门禁、记录时长、提交 PR 并合并。
- full workflow 若仍有高耗时测试，以 durations 证据登记独立 follow-up，不在本任务猜测式重构测试基础设施。

状态：后端影响分析、风险分级、稳定测试边界和慢用例治理已登记为 TD-083，不阻塞 TD-082 收口。

完成：PR #467 已于 2026-07-23 squash merge（`754ca109`）；可靠串行 run `29990314892` 三路通过。
