# TD-083 后端风险分级测试选择与性能专项治理实施计划

## Step 1：冻结策略与基线

- 登记风险模型、Context 反向依赖和三层 CI 触发策略。
- 记录 PR #467 的 pytest/Backend durations 与 Celery broker 逃逸证据。
- 将 TD-083 移入工作台当前任务。

状态：已完成设计，等待实现验证。

## Step 2：实现后端测试选择器

- 新增标准库实现的 CLI，支持 git base/head、显式 paths、full 和 GitHub output。
- 输出 mode、reason、pytest paths；未知路径和异常 fail closed 为 full。
- 自动测试覆盖 Context 映射、高风险升级、测试文件和确定性去重。

状态：已完成；选择器与 scope 分类共 29 个工程测试通过。

## Step 3：消除测试外部任务分发等待

- 修正全局 pytest fixture，隔离结构化数据 `celery_app.send_task` 和 document retry alias。
- 增加默认拒绝外部网络的 fail-fast fixture，仅放行测试 PostgreSQL；真实外部验收显式标记 `external_network`。
- 保留测试内局部 spy/异常覆盖能力，并用行为断言锁定 mock 确实生效。
- 对修复前 19/38 秒用例做独立 PostgreSQL 复测。

状态：已完成并通过完整回归；原最慢 6 用例 6 passed / 3.27s，三个完整文件 22 passed / 10.38s；禁网护栏发现并修正 2 个依赖系统 DNS 的 MCP URL policy 用例；embedding timeout 用例改为 mock 异常并移出 slow。最终 `not slow` 为 1365 passed / 3 skipped / 8 deselected / 2m41s，`slow` 为 7 passed / 1 skipped / 3.89s（优化前 33.96s）。

## Step 4：接入 GitHub CI

- PR 使用选择器结果运行 targeted 或 full `not slow`。
- backend push 到 main 使用 full `not slow`；schedule/manual 使用含 slow 全量。
- 保持三个 required check 名称和 docs/frontend/MCP scope 行为不变。

状态：已完成；PR #469 的 Backend `4m53s`、Frontend `1m04s`、Engineering docs `13s` 全绿；main push run #29995992024 的 Backend `5m06s`、Frontend `1m00s`、Engineering docs `16s` 全绿。

## Step 5：验证与收口

- 运行选择器/工程测试、Ruff、mypy、targeted Context、完整 `not slow`、MCP、文档门禁和 diff 检查。
- 用当前 CI 基础设施 PR 验证 full fail-safe；再用最小叶子 Context 探针 PR 验证 targeted wall time。
- 回填真实测试数量、耗时、PR/merge 信息，完成 Git 闭环。

状态：已完成；基础设施 PR #469 已 squash merge `cccb3ff6`，main push run #29995992024 全绿；探针 PR #470 已验证 `context:resource` targeted 选择（15 passed / 4.22s，Backend 1m44s）后关闭且未合并。
