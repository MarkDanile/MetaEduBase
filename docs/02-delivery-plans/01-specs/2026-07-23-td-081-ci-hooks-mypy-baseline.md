# TD-081 CI、Git Hooks 与 mypy 可执行基线 Spec

> 状态：🟣 待验证
> 任务：[TD-081](../../03-engineering-governance/technical-debt.md#td-081-ci-git-hooks-与-mypy-可执行基线缺失)
> 日期：2026-07-23

## 背景

仓库已有本地质量命令和 `.githooks`，但缺少 GitHub Actions；已提交 hooks 未被 Git 配置启用，且 Ruff 失败会被 `|| true` 吞掉。`mypy app` 还会在 duplicate module 阶段退出，无法提供类型回归信号。结果是 Claude Code、Codex 和人工开发在不同电脑上没有共同的远端执行门禁。

## 目标

1. PR 和 `main` push 自动执行 Backend、Frontend、Engineering docs 三个独立检查。
2. 后端 CI 使用锁文件和真实 PostgreSQL 测试库完成 Ruff、mypy baseline 与 pytest。
3. 提供幂等 hooks 安装入口；同一 clone 内所有 Git 客户端共享 hooks。
4. pre-commit 的 Ruff、TypeScript 和文档失败必须返回非零，不再提供绕过提示。
5. mypy 能检查 `app`；历史错误以文件 + error code 计数形成可审查、可递减基线，新增或增加错误立即失败。
6. GitHub `main` 要求三个 CI checks 通过后才允许合并。

## 非目标

- 本任务不一次性修复全部历史 mypy 错误。
- 不把 hooks 描述为不可绕过的安全边界；远端 CI 与 branch protection 才是最终门禁。
- 不修改业务逻辑、测试断言或工程门禁阈值来制造通过结果。
- 不纳入开工前已存在的 `packages/mcp-server/uv.lock`。

## 设计

### CI

- 单个 workflow，三个并行 job：`Backend`、`Frontend`、`Engineering docs`。
- Backend 固定 Python 3.12，使用 `uv.lock`；PostgreSQL 镜像包含 pgvector、ltree 与 zhparser，运行 `init-test-db` 后执行全量 pytest。
- Frontend 固定 Node 20 / pnpm 9.15.0，使用 `pnpm-lock.yaml --frozen-lockfile`。
- Engineering docs 执行完整文档门禁和工程脚本测试。
- workflow 使用最小只读权限、并发取消和超时，避免重复消耗 runner。

### Git Hooks

- `scripts/install-git-hooks` 幂等设置 `core.hooksPath=.githooks` 并校验可执行文件。
- pre-commit 只在相关 staged 文件变化时运行对应门禁，任何子命令失败都原样失败。
- pre-push 阻止从 `main` / `master` 直接推送；commit-msg 保留 Conventional Commits 校验。
- hooks 不输出 `--no-verify` 使用提示。

### mypy Baseline

- `pyproject.toml` 启用 `explicit_package_bases`，解决重复模块启动错误。
- baseline 记录 `relative_path::error_code -> count`，不记录易漂移的行号或错误文本。
- 校验器拒绝未解析的 mypy fatal error、新增 key、已有 key 计数增加；错误减少允许通过，并提示后续下调 baseline。
- 不使用全局 `ignore_errors`、`follow_imports=skip` 或宽泛 `ignore_missing_imports`。

## 验收标准

1. fresh clone 执行安装入口后 `git config --get core.hooksPath` 返回 `.githooks`。
2. 构造 Ruff 和 TypeScript 失败时 pre-commit 返回非零；pre-push 阻止 main。
3. `mypy app` 进入真实检查，不再出现 duplicate module startup error。
4. baseline 校验对当前历史错误通过，对新增错误或计数增加失败。
5. 后端 Ruff/pytest、前端 typecheck/lint/Vitest/build、工程文档门禁均在 GitHub Actions 可见。
6. GitHub `main` 将三个 job 配置为 required checks；失败 PR 不可合并。

## 风险与回滚

- 首次完整 CI 时间较长：使用 Docker/uv/pnpm 缓存和 job timeout 控制，不削减验证范围。
- GitHub 分支保护需要仓库管理员权限；若 API 权限不足，代码可以合并前保持进行中并明确阻塞点。
- 回滚可移除 workflow 和 hooksPath 配置，但不得以回滚方式规避真实失败。
