# TD-081 CI、Git Hooks 与 mypy 可执行基线实施计划

> 状态：🟢 完成
> Spec：[2026-07-23-td-081-ci-hooks-mypy-baseline.md](../01-specs/2026-07-23-td-081-ci-hooks-mypy-baseline.md)

## Task 1：开工与事实源

- [x] 从候选区移入当前进行中并切独立分支。
- [x] 复现 hooks 未启用、Ruff 被吞和 mypy duplicate module。
- [x] 建立 spec / plan，锁定非目标和验收标准。

## Task 2：CI

- [x] 新增 `.github/workflows/ci.yml`，拆分 Backend / Frontend / Engineering docs。
- [x] 为 CI 可复现准备固定来源的 zhparser PostgreSQL 构建输入。
- [x] 后端通过锁文件安装、初始化测试库并执行 Ruff、mypy baseline、pytest。
- [x] 前端通过锁文件执行 typecheck、lint、Vitest、build。
- [x] 文档 job 执行 full gate 与工程脚本测试。

## Task 3：Git Hooks

- [x] 新增幂等安装入口并在 README 暴露。
- [x] 修复 pre-commit fail-open 和路径处理。
- [x] 清除 hooks 中的绕过提示并补失败注入测试。
- [x] 在当前 clone 安装并验证 `core.hooksPath=.githooks`。

## Task 4：mypy Baseline

- [x] 配置 `explicit_package_bases`，确认真实检查可启动。
- [x] 新增 baseline 校验器、历史基线和单元测试。
- [x] 验证当前基线通过，注入新增错误时失败。

## Task 5：验证与 Git 闭环

- [x] 执行 Backend / Frontend / Engineering docs 本地等价命令。
- [x] push 并确认三个 GitHub Actions job 通过（run `29982970071`）。
- [x] 配置 `main` required checks，并验证 branch protection 返回配置一致。
- [x] PR #465 合并后更新 TD、工作台、work-log，并通过独立 closeout PR 收口。

## 交付结果

- 实现 PR：[PR #465](https://github.com/MarkDanile/MetaEduBase/pull/465)，merge commit `a37a7e51`。
- Required checks：`Backend`、`Frontend`、`Engineering docs`；strict + `enforce_admins=true`。
- 最终 Backend：`1368 passed / 5 skipped / 28 warnings`，工程测试 `49 passed`，mypy 0 regression。
