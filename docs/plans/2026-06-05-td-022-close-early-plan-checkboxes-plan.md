# TD-022 收口早期已完成计划文件的活动式未勾选项 — Plan

## 任务入口

- Spec: `docs/specs/2026-06-05-td-022-close-early-plan-checkboxes.md`
- 技术债: `docs/engineering/technical-debt.md#td-022-收口早期已完成计划文件的活动式未勾选项`
- 任务卡片: `docs/engineering/current-work.md` 的 TD-022 卡片
- 当前执行模式: `manual`
- 完成后 Git 阶段: 提交 → push → PR → squash merge `main`

## 实施顺序

### 1. spec/plan/总账（已完成）

- [x] TD-022 总账卡片已登记为 🔵 就绪
- [x] spec 落盘到 `docs/specs/2026-06-05-td-022-close-early-plan-checkboxes.md`
- [x] plan 落盘（本文件）

### 2. 收口 `docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md`

- [ ] 确认顶部已有「交付历史」段（实际在第 5 行已有，不上移）
- [ ] 全部 `- [ ]` 改为 `- [x]`
- [ ] **保留** PR 描述模板内的 `<TASK-8 输出>` 占位

### 3. 收口 `docs/plans/2026-06-05-td-005-task-lifecycle-helpers-plan.md`

- [ ] 顶部插入「交付历史（2026-06-05）」段（PR #34, `e5197a5`）
- [ ] 全部 `- [ ]` 改为 `- [x]`

### 4. 收口 `docs/plans/2026-06-05-td-006-llm-model-fallback-plan.md`

- [ ] 顶部插入「交付历史（2026-06-05）」段（PR #35, `042e4a9`）
- [ ] 全部 `- [ ]` 改为 `- [x]`

### 5. 收口 `docs/plans/2026-06-05-td-007-databaseview-vue-query-plan.md`

- [ ] 顶部插入「交付历史（2026-06-05）」段（PR #36, `350acd2`）
- [ ] 全部 `- [ ]` 改为 `- [x]`

### 6. 收口 `docs/plans/2026-06-05-td-015-databaseview-regressions-plan.md`

- [ ] 顶部插入「交付历史（2026-06-05）」段（PR #38, `f38fbbc`）
- [ ] 全部 `- [ ]` 改为 `- [x]`

### 7. 验证

- [ ] `rg -n "^- \[ \]" docs/plans/2026-06-04-td-004-test-database-reproducibility-plan.md docs/plans/2026-06-05-td-005-task-lifecycle-helpers-plan.md docs/plans/2026-06-05-td-006-llm-model-fallback-plan.md docs/plans/2026-06-05-td-007-databaseview-vue-query-plan.md docs/plans/2026-06-05-td-015-databaseview-regressions-plan.md` 命中 0 行
- [ ] `rg -n "^- \[x\]" ...` 命中行数符合预期（> 0）
- [ ] `rg -n "交付历史" ...` 5 个 plan 各自至少 1 行命中

### 8. Git 闭环

- [ ] 分支：`docs/td-022-close-early-plan-checkboxes`（已建）
- [ ] 提交：`docs(engineering): TD-022 close remaining - [ ] in early completed plans`
- [ ] push：`git push -u origin docs/td-022-close-early-plan-checkboxes`
- [ ] PR：`gh pr create ...` Summary / Scope / Validation / Risks / Docs
- [ ] 检查 `gh pr checks` 通过
- [ ] squash merge：`gh pr merge --squash --delete-branch`
- [ ] 回填 `current-work.md` 最近完成 + `technical-debt.md` 备注 + `work-log.md` 索引

## 任务拆分

1. spec/plan/总账（已完成）
2. 收口 TD-004 plan
3. 收口 TD-005 plan
4. 收口 TD-006 plan
5. 收口 TD-007 plan
6. 收口 TD-015 plan
7. 跑 rg 验证
8. 走完整 Git 流程
9. 回填三处任务事实源

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 代码块内 `- [ ]` 形式（commit 消息、PR 模板）被误改 | 人工 review 每个 plan；不修改代码块内文本 |
| 实际未完成的项被误勾 | 每个 `- [ ]` 对应的步骤在技术债总账的「备注」中均有真实 PR / 提交记录才能改为 `- [x]` |
| TD-004 plan 的 PR 描述模板占位被误改 | 保留 `<TASK-8 输出>` 等占位；只改 plan 主体步骤 |

## 提交前最终回查

- `current-work.md` 状态与代码实际一致
- `technical-debt.md` 状态与代码实际一致
- 验证结果来自真实 `rg` 命令输出
- 业务行为不变声明已写到 PR 描述
- PR 范围只包含 5 个 plan + spec/plan + current-work/technical-debt/work-log 状态同步
