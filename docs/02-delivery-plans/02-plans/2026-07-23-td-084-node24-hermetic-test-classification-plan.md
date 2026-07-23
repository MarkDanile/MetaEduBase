# TD-084 GitHub Actions Node 24 与 hermetic 测试分类收口实施计划

## Step 1：冻结版本与测试语义

- 记录 6 类 action 的官方最新 release 和 `runs.using: node24` 证据。
- 记录现有 slow 套件 7 passed / 1 skipped / 3.89s 基线。
- 将 TD-084 移入工作台进行中。

状态：已完成。

## Step 2：升级 CI actions

- checkout v4 -> v7；setup-node v4 -> v7；pnpm setup v4 -> v6。
- setup-uv v6 -> v9.0.0，并显式保留 `prune-cache: true`；官方未提供 `v9` major tag，使用可解析的精确 release。
- setup-buildx v3 -> v4；build-push v6 -> v7。

状态：已完成。PR 首轮验证发现 setup-uv 无 `v9` major tag，修正为 `v9.0.0` 后 PR、main push 与 workflow_dispatch 均通过。

## Step 3：收口 hermetic 测试分类

- 移除 `test_p1_demo.py` 与 REQ-046 real-world 文件的模块级 slow marker。
- 删除 pytest slow marker 注册。
- CI targeted / full / schedule/manual 统一过滤 `external_network`。
- 更新测试规则、质量门禁和工程回归断言。

状态：已完成。PR、main push 与 workflow_dispatch 均执行完整 hermetic 回归并通过。

## Step 4：验证与 Git 闭环

- 本地运行完整 hermetic pytest、Ruff、mypy baseline、工程测试、docs gate、lock 与 diff 检查。
- PR 验证 required checks；合并后验证 main push；再触发 workflow_dispatch 验证手动路径。
- 检查 annotations，不允许保留本任务目标 action 的 Node 20 warning。
- 回填 durations、测试数量、PR / merge / run 后收口工作台与技术债。

状态：已完成。

- Command: `cd packages/server-python && .venv/bin/pytest -q -m 'not external_network' --durations=20`
- Result: 退出码 0；1372 passed / 4 external deselected / 2m48s；Ruff、mypy baseline、工程测试 79 passed、docs gate、YAML、lock 与 diff check 均为退出码 0。
- Environment: macOS 本机，真实 `metaedu_test` PostgreSQL；LLM、Celery、Redis、HTTP、MCP 外部连接由 mock / 默认禁网 fixture 隔离。
- PR evidence: [run #29998631061](https://github.com/MarkDanile/MetaEduBase/actions/runs/29998631061) 中 Frontend 通过；Backend 与 Engineering docs 在加载 `astral-sh/setup-uv@v9` 时分别于 2s / 3s 失败，尚未执行项目检查。官方 Git refs 复核确认其余 5 个 major tag 存在，setup-uv 仅 `v9.0.0` 存在，故改用精确 release。
- PR success: [PR #472](https://github.com/MarkDanile/MetaEduBase/pull/472) squash merge `beb7c6fd`；[run #29998945591](https://github.com/MarkDanile/MetaEduBase/actions/runs/29998945591) Backend 5m06s（1371 passed / 1 skipped / 4 external deselected / 3m21s，MCP 7 passed）、Frontend 1m10s、Engineering docs 16s。
- Main/manual: main push [run #29999345037](https://github.com/MarkDanile/MetaEduBase/actions/runs/29999345037) Backend 5m09s / Frontend 1m01s / Engineering docs 13s；workflow_dispatch [run #29999714011](https://github.com/MarkDanile/MetaEduBase/actions/runs/29999714011) Backend 5m08s / Frontend 1m10s / Engineering docs 12s，三路均通过。
- Annotations: PR Backend 与 Engineering docs 均为 0；Frontend 仅保留 10 条既有测试文件 lint warning，三类运行均未出现本任务 6 类 action 的 Node 20 deprecated warning。
