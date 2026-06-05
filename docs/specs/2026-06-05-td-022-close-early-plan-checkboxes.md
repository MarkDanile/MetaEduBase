# TD-022 收口早期已完成计划文件的活动式未勾选项 — Spec

## 背景

`docs/engineering/technical-debt.md#td-022-收口早期已完成计划文件的活动式未勾选项`
指出 TD-021 收口了 `docs/plans/2026-06-05-td-016-ai-router-provider-plan.md`、
`docs/plans/2026-06-05-td-017-filedetailview-vue-query-plan.md`、
`docs/plans/2026-06-05-td-018-filedetailview-remaining-plan.md`、
`docs/plans/2026-06-05-td-019-vue-query-self-reference-plan.md` 4 个 plan 的活动式
未勾选项，但 `rg -n "^- \[ \]" docs/plans` 仍命中 5 个早期已完成任务的 plan：

- `docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md`（PR #23, `b8b34a6`, 2026-06-04）
- `docs/plans/2026-06-05-td-005-task-lifecycle-helpers-plan.md`（PR #34, `e5197a5`, 2026-06-05）
- `docs/plans/2026-06-05-td-006-llm-model-fallback-plan.md`（PR #35, `042e4a9`, 2026-06-05）
- `docs/plans/2026-06-05-td-007-databaseview-vue-query-plan.md`（PR #36, `350acd2`, 2026-06-05）
- `docs/plans/2026-06-05-td-015-databaseview-regressions-plan.md`（PR #38, `f38fbbc`, 2026-06-05）

这些任务在技术债总账中已是 `🟢 完成`；新规则（`docs/engineering/rules/quality-gates.md`）
已要求"已完成 plan 不得残留活动式 `- [ ]` 收尾项"。

## 目标

把 5 个早期已完成 plan 的活动式 `- [ ]` 步骤改为 `- [x]`，并在 plan 顶部补全
「交付历史」段指向真实 PR / merge commit / 完成日期；与 TD-021 处理 TD-016 /
TD-017 / TD-018 / TD-019 的模式完全一致。

## 范围

### In scope

- `docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md`：
  - 顶部添加「交付历史（2026-06-04）」段引用 PR #23 / merge commit `b8b34a6`
  - 把所有未勾选步骤改为 `- [x]`
  - **保留** TD-004 plan 本身在第 5 行的「交付历史」段说明
  - **保留** `<TASK-8 输出>` 占位（PR 描述模板内的 placeholder；TD-013 收口过）
- `docs/plans/2026-06-05-td-005-task-lifecycle-helpers-plan.md`：
  - 顶部添加「交付历史（2026-06-05）」段引用 PR #34 / merge commit `e5197a5`
  - 把所有未勾选步骤改为 `- [x]`
- `docs/plans/2026-06-05-td-006-llm-model-fallback-plan.md`：
  - 顶部添加「交付历史（2026-06-05）」段引用 PR #35 / merge commit `042e4a9`
  - 把所有未勾选步骤改为 `- [x]`
- `docs/plans/2026-06-05-td-007-databaseview-vue-query-plan.md`：
  - 顶部添加「交付历史（2026-06-05）」段引用 PR #36 / merge commit `350acd2`
  - 把所有未勾选步骤改为 `- [x]`
- `docs/plans/2026-06-05-td-015-databaseview-regressions-plan.md`：
  - 顶部添加「交付历史（2026-06-05）」段引用 PR #38 / merge commit `f38fbbc`
  - 把所有未勾选步骤改为 `- [x]`

### Out of scope

- 不动代码、不动其他 plan、不动技术债总账的"完成"备注（备注里已有真实 PR）
- 不动 `current-work.md` 的最近完成区（已有真实 PR 链接）
- 不动 `work-log.md` 索引（已有真实 PR 链接）
- 不动 `quality-gates.md` / `workflow.md` / `task-modes.md` 等规则
- 不重写 plan 的「实施步骤内容」；只把 checkbox 从未勾选改为已勾选

## 设计要点

### 1. 顶部「交付历史」段格式

参考 TD-021 已收口的 4 个 plan（TD-016/017/018/019）：

```markdown
> **交付历史（YYYY-MM-DD）：** TD-xxx 已通过 PR #N（merge commit `xxxxx`）
> 合并到 `main`。本文保留为历史实施计划；下方清单已按最终交付状态收口，
> 真实交付事实以 `docs/engineering/technical-debt.md#td-xxx-...` 和 PR #N 为准。
```

TD-004 plan 已有类似段（第 5 行），但放在「For agentic workers」之后；
本轮收口时把这段上移或与新「交付历史」段合并（保留现有占位说明即可）。

### 2. 未勾选步骤改写规则

- 文件中所有 `- [ ]` → `- [x]`
- 嵌套缩进保持不变
- 描述文本保持不变（避免改动历史）
- 验证项（`- [ ] pnpm typecheck 退出码 0` 等）同样改为 `- [x]`

### 3. 与 PR 描述模板内的占位的关系

TD-004 plan 末尾 Task 12 内的 PR 描述模板含 `<TASK-8 输出>` 等占位。
TD-013 收口时已处理过该段（参见 `docs/engineering/technical-debt.md#td-013` 备注），
本轮 TD-022 不再触碰 PR 描述模板里的占位，只把 plan 主体步骤的 `- [ ]`
改为 `- [x]`。

### 4. 处理顺序

按 plan 文件名时间顺序：004 → 005 → 006 → 007 → 015。每个 plan：
1. 顶部插入「交付历史」段
2. 把全部 `- [ ]` 改为 `- [x]`（使用 `replace_all` 或一次性脚本）

## 完成标准

1. 5 个 plan 顶部都新增或更新「交付历史」段
2. 5 个 plan 中**不再**有 `- [ ]`
3. 5 个 plan 中代码块（` ``` ` 包围的 YAML/bash/python）内若有 `- [ ]` 形式的内容
   （如 commit 消息模板）保留原状
4. `rg -n "^- \[ \]" docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md docs/plans/2026-06-05-td-005-task-lifecycle-helpers-plan.md docs/plans/2026-06-05-td-006-llm-model-fallback-plan.md docs/plans/2026-06-05-td-007-databaseview-vue-query-plan.md docs/plans/2026-06-05-td-015-databaseview-regressions-plan.md` 命中 0 行
5. 三账一致：技术债总账的完成备注、`current-work.md` 工作台、`work-log.md` 索引都已记录真实 PR / merge commit；plan 文档的「交付历史」段与三者一致
6. PR 描述明确声明：纯文档卫生变更；用户可见行为零变化

## 验证方式

按 `docs/engineering/rules/quality-gates.md#验证矩阵` 文档-only 改动：

```bash
rg -n "^- \[ \]" docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md \
  docs/plans/2026-06-05-td-005-task-lifecycle-helpers-plan.md \
  docs/plans/2026-06-05-td-006-llm-model-fallback-plan.md \
  docs/plans/2026-06-05-td-007-databaseview-vue-query-plan.md \
  docs/plans/2026-06-05-td-015-databaseview-regressions-plan.md
# 期望：0 行命中
```

```bash
rg -n "^- \[x\]" docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md \
  docs/plans/2026-06-05-td-005-task-lifecycle-helpers-plan.md \
  docs/plans/2026-06-05-td-006-llm-model-fallback-plan.md \
  docs/plans/2026-06-05-td-007-databaseview-vue-query-plan.md \
  docs/plans/2026-06-05-td-015-databaseview-regressions-plan.md | wc -l
# 期望：远大于 0（5 个 plan 共约 130+ 行）
```

```bash
rg -n "交付历史" docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md \
  docs/plans/2026-06-05-td-005-task-lifecycle-helpers-plan.md \
  docs/plans/2026-06-05-td-006-llm-model-fallback-plan.md \
  docs/plans/2026-06-05-td-007-databaseview-vue-query-plan.md \
  docs/plans/2026-06-05-td-015-databaseview-regressions-plan.md
# 期望：5 个 plan 各自至少 1 行命中
```

## 风险与后续

- 风险：plan 中如果嵌套缩进的代码块含 `- [ ]` 形式（commit 消息、PR 模板等），
  误改会破坏 plan 的可读性。本轮**不动**代码块内文本。
- 风险：plan 中如果含 `- [ ]` 形式但**实际未完成**的项（极少见但要兜底），
  改为 `- [x]` 会让任务看似完成。需要逐项核对：每个 `- [ ]` 对应的步骤
  在对应技术债总账的「备注」中均有真实 PR / 提交记录，才能改为 `- [x]`。
- 后续：未来新 plan 应在交付完成时立即更新 checkbox 与「交付历史」段，
  避免再次出现"已完成但 plan 未收口"的状态。

## 任务卡片字段

完成后需在 `current-work.md` 把 TD-022 移到「最近完成」并记录 PR 链接，
同时在 `technical-debt.md#td-022-收口早期已完成计划文件的活动式未勾选项`
的备注中追加完成日期、提交信息和验证结果。
