# DOC-017 Contracts / Task Modes 长期化重构 — Plan

## 对应 Spec

- `docs/specs/2026-06-06-doc-017-contracts-task-modes-long-lived.md`

## 实施步骤

1. 复核 `contracts.md`、`task-modes.md` 及外部对其章节名和锚点的引用。
2. 重写 `contracts.md`，收敛为“所有权 + 变更边界 + 同步步骤 + 验证”的长期契约治理文档。
3. 重写 `task-modes.md`，保留稳定锚点，压缩重复内容，突出通用入口、默认模式路由和各模式差异。
4. 更新必要索引描述，如 `AGENTS.md`、`CLAUDE.md`、`docs.md`。
5. 更新 `current-work.md` / `work-log.md` 状态并运行文档门禁。

## 风险与控制

- 风险：压缩过头，导致规则失去约束力。
  - 控制：保留强约束，只删除重复和解释性噪音。
- 风险：改标题导致旧文档锚点失效。
  - 控制：保留外部已有引用的稳定章节名。
- 风险：`task-modes.md` 与 `workflow.md` 职责再次混叠。
  - 控制：`task-modes.md` 只讲模式入口、必读与完成标准，不重复长流程。

## 验证计划

1. `scripts/check-engineering-docs`
2. `git diff --check`
3. 人工回查：
   - `contracts.md` 是否更像长期治理文档
   - `task-modes.md` 是否更像模式入口文档
   - 已有章节锚点是否仍然存在
