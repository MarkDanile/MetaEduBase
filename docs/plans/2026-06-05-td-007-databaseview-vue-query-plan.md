# TD-007 收敛 DatabaseView 请求状态到 Vue Query — Plan

## 任务入口

- Spec: `docs/specs/2026-06-05-td-007-databaseview-vue-query.md`
- 技术债: `docs/engineering/technical-debt.md#td-007-减少前端请求状态处理重复`
- 任务卡片: `docs/engineering/current-work.md` 的 TD-007 卡片
- 当前执行模式: `manual`
- 完成后 Git 阶段: 提交 → push → PR → squash merge `main`

## 实施顺序

### 1. 摸清现有结构（已完成）

- [x] spec/plan 起草
- [x] 摸清 `DatabaseView.vue` 的 5 个 `load*` + 5 个 mutation + 1 个轮询 + 6 个 loading ref 的具体位置
- [x] 确认 `main.ts` 已注册 `VueQueryPlugin`（无 queryClient）
- [x] 确认 `@tanstack/vue-query` 在 `packages/web/package.json` 已声明

### 2. 改造 `main.ts`：注册 queryClient 与全局 onError

- [ ] 引入 `QueryClient` / `QueryCache` / `VueQueryPlugin`
- [ ] 构造 `queryClient`：
  ```typescript
  const queryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => toast.error(error?.message ?? "请求失败"),
    }),
  });
  ```
- [ ] `app.use(VueQueryPlugin, { queryClient })`
- [ ] 确认 import 路径：`@tanstack/vue-query` 与 `useToast` 都在 web 包

**验证点**：`pnpm --filter @metaedu/web typecheck` 通过。

### 3. 新增 `packages/web/src/views/database/queries.ts`

- [ ] 集中 `datasetKeys` 树形 query key
- [ ] 集中 `useDatasetsQuery` / `useDatasetTasksQuery` / `useDatasetRowsQuery` /
  `useDatasetKgQuery` / `useKgOverviewQuery` 五个 useQuery 封装
- [ ] 集中 `useUploadDatasetMutation` / `useDeleteDatasetMutation` /
  `useRetryTasksMutation` / `useReinitializeMutation` / `useRebuildKgMutation`
  五个 useMutation 封装
- [ ] 所有 query 的 queryFn 调对应的 `structuredDataApi` / `knowledgeApi`，
  返回 `.data`（不再返回 axios response）
- [ ] 错误统一交给 `QueryCache.onError` 处理，query 内部不重复 toast

**验证点**：文件可以被 `DatabaseView.vue` import；typecheck 通过。

### 4. 重构 `DatabaseView.vue`

- [ ] 删除 6 个 `loading*` ref、1 个 `uploading` ref、1 个 `rebuildingKg` ref
- [ ] 删除 5 个 `load*` 函数（loadDatasets / loadTasks / loadRows / loadKg /
  loadKgOverview）
- [ ] 删除 5 个 mutation 函数（doUpload / doDelete / retryTasks /
  reinitialize / doRebuildKg）
- [ ] 删除 `pollTimer` / `startPolling` / `stopPolling`（替换为
  `useDatasetTasksQuery` 的 `refetchInterval`）
- [ ] 引入 5 个 `useXxxQuery` + 5 个 `useXxxMutation` 替换
- [ ] `loading` 等模板内 `v-if` 改为读 `query.isLoading.value` /
  `query.isFetching.value` / `mutation.isPending.value`
- [ ] watch 联动保留：内部 fetch 改为 `query.refetch()` 或
  `mutation.mutate()`
- [ ] `onMounted` 移除显式 `loadDatasets()`（`useDatasetsQuery` 自动触发）
- [ ] `onUnmounted` 移除 `stopPolling()`（Vue Query 自动清理）
- [ ] `selectDataset` 改为只 set `selectedId.value`，由 query 自动重 fetch

**验证点**：typecheck / build / lint 通过；模板内的 `v-if="loading"` 等
数据绑定全部有来源；行为不变。

### 5. 验证

- [ ] `cd packages/web && pnpm --filter @metaedu/web typecheck` 退出码 0
- [ ] `cd packages/web && pnpm --filter @metaedu/web build` 退出码 0
- [ ] `cd packages/web && pnpm --filter @metaedu/web lint` 退出码 0（无新增 warning）
- [ ] 手动核对模板中 v-if 数据源全部对应到 query/mutation 状态

### 6. Git 闭环

- [ ] 同步 `docs/engineering/current-work.md` 任务卡片状态
- [ ] 分支：`git checkout -b refactor/td-007-databaseview-vue-query`
- [ ] 提交：`refactor(web): TD-007 migrate DatabaseView requests to Vue Query`
- [ ] push：`git push -u origin refactor/td-007-databaseview-vue-query`
- [ ] PR：`gh pr create ...` Summary / Scope / Validation / Risks / Docs
- [ ] 检查 `gh pr checks` 通过
- [ ] squash merge：`gh pr merge --squash --delete-branch`
- [ ] 回填 `current-work.md` 最近完成 + `technical-debt.md` 备注 + `work-log.md` 索引

## 任务拆分

1. spec/plan 起草（已完成）
2. 改造 main.ts 注册 queryClient
3. 新增 queries.ts 集中 query/mutation
4. 重构 DatabaseView.vue
5. 跑前端 typecheck / build / lint
6. 走完整 Git 流程
7. 回填三处任务事实源

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| Vue Query 默认 staleTime=0 导致频繁 refetch | 列表类 query 用 `staleTime: 30_000`（30s）减少抖动；详情类保持默认 |
| mutation 失败时全局 onError 双重 toast | queryFn 内部不 throw 业务文案；统一让 QueryCache 处理 |
| refetchInterval 与 onUnmounted 清理冲突 | Vue Query v5 自动管理，删 `stopPolling` 即可 |
| 模板中 v-if 误读 undefined | 改用 `?? []` / `?? false` 兜底 |
| `useToast` 在 main.ts 引入导致循环依赖 | useToast 应该是无状态 composable；如果有 store 依赖，导入到 main.ts 之前 |

## 提交前最终回查

- `current-work.md` 状态与代码实际一致
- `technical-debt.md` 状态与代码实际一致
- 验证结果来自真实命令输出
- 业务行为不变声明已写到 PR 描述
- PR 范围只包含本任务文件（main.ts / queries.ts / DatabaseView.vue / spec/plan / 文档状态）
- 不混入其他视图或 service 文件改动
