# DOC-016 Testing / Local Development 长期化重构 — Plan

## 对应 Spec

- `docs/02-delivery-plans/01-specs/2026-06-06-doc-016-testing-local-development-long-lived.md`

## 实施步骤

1. 复核 `testing.md`、`local-development.md` 以及相关稳定命令入口（`dev.sh`、`Makefile`、pytest 初始化代码）。
2. 重写 `testing.md`，保留测试分层、环境原则、mock 边界、稳定入口和更新条件。
3. 重写 `local-development.md`，保留主入口、常见场景、工作区命令、数据库初始化边界和阻塞记录规范。
4. 必要时同步索引描述，如 `docs.md`、`AGENTS.md`、`CLAUDE.md`。
5. 更新 `current-work.md` / `work-log.md` 状态并运行文档门禁。

## 风险与控制

- 风险：文档变轻后，使用者找不到具体命令。
  - 控制：保留稳定命令入口和常见场景表，不移除核心命令。
- 风险：文档变成抽象策略，失去操作价值。
  - 控制：每份文档都保留“主入口 + 场景 + 恢复方式”。
- 风险：把实现事实写得过细，后续再次快速过时。
  - 控制：避免固定测试数量、一次性统计和脚本内部细节。

## 验证计划

1. `scripts/check-engineering-docs`
2. `git diff --check`
3. 人工回查：
   - `testing.md` 是否更像策略文档
   - `local-development.md` 是否更像入口文档
   - 索引描述是否仍能引导 AI 快速定位
