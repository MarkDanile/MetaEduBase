# TD-019 修复 Vue Query 轮询自引用导致的页面初始化运行时错误 — Plan

## 任务入口

- Spec: `docs/specs/2026-06-05-td-019-vue-query-self-reference.md`
- 技术债: `docs/engineering/technical-debt.md#td-019-修复-vue-query-轮询自引用导致的页面初始化运行时错误`
- 任务卡片: `docs/engineering/current-work.md` 的 TD-019 卡片
- 当前执行模式: `manual`
- 完成后 Git 阶段: 提交 → push → PR → squash merge `main`

## 实施顺序

### 1. spec/plan/总账（已完成）

- [x] TD-019 总账卡片已登记为 🔵 就绪
- [x] spec 落盘到 `docs/specs/2026-06-05-td-019-vue-query-self-reference.md`
- [x] plan 落盘（本文件）

### 2. 行为等价矩阵

- [ ] 写 `docs/engineering/matrices/td-019-vue-query-self-reference-equivalence.md`
- [ ] 矩阵覆盖 polling 计算时机、初始化顺序、watch 时序

### 3. 修复 `packages/web/src/views/database/queries.ts`

- [ ] `useDatasetTasksQuery` 删除 `polling: Ref<boolean>` 参数
- [ ] `refetchInterval` 改用函数形式 `(query) => hasActive ? 3000 : false`
- [ ] 函数内部从 `query.state.data` 派生 `hasActive`

**验证点**：`rg -n "polling" packages/web/src/views/database/queries.ts` 只命中函数形式 refetchInterval 内部。

### 4. 修复 `packages/web/src/views/database/DatabaseView.vue`

- [ ] `useDatasetTasksQuery(selectedId, pollingRef)` 改为 `useDatasetTasksQuery(selectedId)`
- [ ] 删除临时 `pollingRef` 声明
- [ ] 模板 `polling` 改用 `computed(() => (tasksQuery.data.value ?? []).some(...))`（声明 tasksQuery 之后独立定义）
- [ ] 确认 `tasksQuery.data.value` 不再出现在 query hook 调用行

**验证点**：`rg -n "tasksQuery\\.data\\.value" packages/web/src/views/database/DatabaseView.vue` 只命中 `polling` computed 定义行。

### 5. 修复 `packages/web/src/views/resource/queries.ts`

- [ ] `useFileTasksQuery` 删除 `polling: Ref<boolean>` 参数
- [ ] `refetchInterval` 改用函数形式

**验证点**：同上。

### 6. 修复 `packages/web/src/views/resource/FileDetailView.vue`

- [ ] `useFileTasksQuery(fileId, pollingRef)` 改为 `useFileTasksQuery(fileId)`
- [ ] 模板 `polling` 改用声明之后的独立 computed
- [ ] 确认 `tasksQuery.data.value` 不再出现在 query hook 调用行

**验证点**：同上。

### 7. 验证

- [ ] `pnpm --filter @metaedu/web typecheck` 退出码 0
- [ ] `pnpm --filter @metaedu/web build` 退出码 0
- [ ] `pnpm --filter @metaedu/web lint` 退出码 0
- [ ] `rg -n "tasksQuery\\.data\\.value" packages/web/src/views/database/DatabaseView.vue packages/web/src/views/resource/FileDetailView.vue` 不再命中 query hook 调用行

### 8. Git 闭环

- [ ] 分支：`fix/td-019-vue-query-self-reference`（已建）
- [ ] 提交：`fix(web): TD-019 eliminate Vue Query polling self-reference TDZ`
- [ ] push：`git push -u origin fix/td-019-vue-query-self-reference`
- [ ] PR：`gh pr create ...` Summary / Scope / Validation / Risks / Docs
- [ ] 检查 `gh pr checks` 通过
- [ ] squash merge：`gh pr merge --squash --delete-branch`
- [ ] 回填 `current-work.md` 最近完成 + `technical-debt.md` 备注 + `work-log.md` 索引

## 任务拆分

1. spec/plan/总账（已完成）
2. 写行为等价矩阵
3. 修复 database/queries.ts
4. 修复 DatabaseView.vue
5. 修复 resource/queries.ts
6. 修复 FileDetailView.vue
7. 跑前端 typecheck / build / lint
8. 走完整 Git 流程
9. 回填三处任务事实源

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| `refetchInterval` 函数形式时序与旧实现不等价 | 旧实现是 `refetchInterval: computed(() => polling.value ? 3000 : false)`，函数形式在每次 fetch 完成后被调用，行为等价 |
| 删除 `polling: Ref<boolean>` 参数后调用方忘记改 | typecheck 阶段捕获（参数不匹配） |
| 模板 `polling` 仍依赖 `tasksQuery.data.value`，但如果 `tasksQuery` 未声明就访问 | 模板渲染发生在 setup 之后；`polling` 也在 `tasksQuery` 声明之后定义，JS 词法无 TDZ |

## 提交前最终回查

- `current-work.md` 状态与代码实际一致
- `technical-debt.md` 状态与代码实际一致
- 验证结果来自真实命令输出
- 行为不变声明已写到 PR 描述
- PR 范围只包含本任务文件
- 不混入其他视图或 service 文件改动
