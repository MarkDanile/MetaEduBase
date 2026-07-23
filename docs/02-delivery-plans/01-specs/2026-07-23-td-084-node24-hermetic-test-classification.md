# TD-084 GitHub Actions Node 24 与 hermetic 测试分类收口 Spec

## 背景

TD-083 已消除普通测试中的真实 Celery / Redis / LLM / HTTP / MCP 连接逃逸，并建立默认禁外网护栏。当前 `slow` 套件只剩 7 passed / 1 skipped，真实耗时 3.89s；继续用 `pytest -m "not slow"` 排除这些确定性 E2E，节省不足 4 秒，却降低 PR / main 回归覆盖。

同时 GitHub run #29995992024 明确警告 6 类 action 仍面向 Node 20。2026-07-23 已通过各项目官方 release 与 `action.yml` 核实 Node 24 版本：checkout `v7.0.1`、setup-node `v7.0.0`、pnpm setup `v6.0.9`、setup-uv `v9.0.0`、setup-buildx `v4.2.0`、build-push `v7.3.0`。

## 目标

1. 将 CI 使用的 6 类 GitHub Action 升级到已核实的 Node 24 major。
2. 移除仓库 `slow` marker 与 `not slow` 默认过滤，把确定性 E2E 纳入普通 hermetic 回归。
3. PR targeted、高风险 PR、main、schedule/workflow_dispatch 统一排除 `external_network`，真实外部服务测试只能显式手工授权执行。
4. 保持三项 required check 名称、风险选择器、本地秒级 hooks、PostgreSQL 真实集成和 MCP lock 行为不变。

## 非目标

- 不在 CI 中调用真实 QCC、LLM 或第三方 MCP。
- 不减少、skip 或删除确定性测试。
- 不以新的 marker 隐藏当前可在数秒内完成的 E2E。
- 不改生产 API、数据库 schema 或业务逻辑。

## 验收标准

- AC-1：`.github/workflows/ci.yml` 全部目标 action 引用升级；最新官方 `action.yml` 均为 `runs.using: node24`。
- AC-2：仓库测试与 pytest 配置中不存在自有 `slow` marker；确定性 E2E 进入普通 hermetic 回归。
- AC-3：所有 CI pytest 路径统一使用 `-m "not external_network"`；真实外部验收仍需 marker + 环境变量双重 opt-in。
- AC-4：`setup-uv@v9` 显式设置 `prune-cache: true`，避免 major 默认值变化导致缓存行为静默漂移。
- AC-5：本地完整 hermetic pytest、Ruff、mypy baseline、工程测试、文档门禁与 lock 检查通过。
- AC-6：PR、main push、workflow_dispatch 三类 CI 全绿，且不再出现本任务六类 action 的 Node 20 deprecated warning。
- AC-7：Codex、Claude Code 与人工终端继续使用同一仓库 workflow / hooks，无 Agent 私有配置。

## 风险与回退

- action major 输入不兼容：逐项核对 release / `action.yml`，PR 失败时回退对应单项 major，不回退测试分类。
- hermetic E2E 暴露顺序污染：修复测试隔离，不恢复 `slow` 隐藏。
- 外部凭证意外出现在 runner：`not external_network` 从收集层排除真实调用，环境变量不再是 CI 唯一防线。
