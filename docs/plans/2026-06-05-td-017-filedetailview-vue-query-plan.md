# TD-017 FileDetailView 任务 / mutation 迁到 Vue Query — Plan

> 交付历史（2026-06-05）：TD-017 已通过 PR #40 合并到 `main`，merge commit `5af2793`。本文保留为历史实施计划；下方清单已按最终交付状态收口，真实交付事实以 `docs/engineering/technical-debt.md#td-017-将-vue-query-请求生命周期治理推广到-filedetailview` 和 PR #40 为准。TD-017 后续暴露的 Vue Query 自引用问题已由 TD-019 / PR #42 修复。

## 任务入口

- Spec: `docs/specs/2026-06-05-td-017-filedetailview-vue-query.md`
- 技术债: `docs/engineering/technical-debt.md#td-017-将-vue-query-请求生命周期治理推广到-filedetailview`
- 任务卡片: `docs/engineering/current-work.md` 的 TD-017 卡片
- 当前执行模式: `manual`
- 完成后 Git 阶段: 提交 → push → PR → squash merge `main`

## 实施顺序

### 1. spec/plan 起草 + 行为等价矩阵

- [x] spec 落盘
- [x] plan 落盘
- [x] 行为等价矩阵 `docs/engineering/matrices/td-017-filedetailview-equivalence.md`
  覆盖：轮询条件 / mutation 触发 / refresh 时机 / cache invalidation /
  toast / loading 状态

### 2. 新增 `packages/web/src/views/resource/queries.ts`

- [x] 集中 `useFileTasksQuery(fileId, polling)`：
  - `queryKey`: `["files", fileId, "tasks"]`
  - `queryFn`: `documentApi.listTasks(fileId).then(r => r.data)`
  - `enabled: !!fileId`
  - `refetchInterval: polling.value ? 3000 : false`
- [x] 集中 `useRetryTasksMutation(fileId, onSuccess)`：mutate 后
  `invalidateQueries(["files", fileId, "tasks"])`
- [x] 集中 `useReinitializeFileMutation(fileId, onSuccess)`：mutate 后
  invalidate file detail + tasks
- [x] 集中 `useDeleteFileMutation(fileId, onSuccess)`：无 invalidate（直接跳转）

**验证点**：模块可被 `FileDetailView.vue` import；typecheck 通过。

### 3. 重构 `FileDetailView.vue`

- [x] 删除 `import { onMounted, onUnmounted }` 等未用 import
- [x] 删除 `tasks` ref / `loadingTasks` ref
- [x] 删除 `loadTasks` 函数
- [x] 删除 `pollTimer` / `startPolling` / `stopPolling`
- [x] 删除 `retryTasks` / `reinitialize` / `doDelete` 函数
- [x] 引入 `useFileTasksQuery` 替换 `tasks` / `loadingTasks`
- [x] 引入 3 个 mutation 替换手写函数
- [x] 模板里 `@click` 调用从 `retryTasks` 改为 `retryMutation.mutate()`
- [x] watch `polling` 由 true→false 仍调 `loadFile + loadChunks + loadKg`
- [x] `onMounted` 删除显式 `loadTasks()`（useQuery 自动触发）
- [x] `onUnmounted(() => stopPolling())` 整段删除

**验证点**：`rg -n "loadTasks\|pollTimer\|startPolling\|stopPolling\|async function retryTasks\|async function reinitialize\|async function doDelete" packages/web/src/views/resource/FileDetailView.vue` 命中 0 行（import 之外）。

### 4. 验证

- [x] `pnpm --filter @metaedu/web typecheck` 退出码 0
- [x] `pnpm --filter @metaedu/web build` 退出码 0
- [x] `pnpm --filter @metaedu/web lint` 退出码 0

### 5. Git 闭环

- [x] 分支：`refactor/td-017-filedetailview-vue-query`
- [x] 提交：`refactor(web): TD-017 migrate FileDetailView tasks/mutation to Vue Query`
- [x] push：`git push -u origin refactor/td-017-filedetailview-vue-query`
- [x] PR：#40，包含 Summary / Scope / Validation / Risks / Docs
- [x] 检查 `gh pr checks` 通过
- [x] squash merge：PR #40 合并到 `main`
- [x] 回填 `current-work.md` 最近完成 + `technical-debt.md` 备注 + `work-log.md` 索引

## 任务拆分

1. spec/plan 起草（已完成）
2. 写行为等价矩阵
3. 新增 queries.ts
4. 重构 FileDetailView.vue
5. 跑前端 typecheck / build / lint
6. 走完整 Git 流程
7. 回填三处任务事实源

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 轮询停止后 refresh 其他资源的时机漂移 | watch `polling` 由 true→false 触发；spec 已显式说明 |
| 循环引用（useFileTasksQuery 的 refetchInterval 依赖 query.data） | `useQuery` v5 `refetchInterval` 接受 `RefOrGetter`，按 query.data 派生 polling |
| mutation 错误时全局 onError 双重 toast | queryFn 内部不 throw 业务文案；统一让 QueryCache 处理 |
| 模板里 `@click` 改写遗漏 | spec/plan 阶段已枚举所有调用点 |

## 提交前最终回查

- `current-work.md` 状态与代码实际一致
- `technical-debt.md` 状态与代码实际一致
- 验证结果来自真实命令输出
- 业务行为不变声明已写到 PR 描述
- PR 范围只包含本任务文件
- 不混入其他视图或 service 文件改动
