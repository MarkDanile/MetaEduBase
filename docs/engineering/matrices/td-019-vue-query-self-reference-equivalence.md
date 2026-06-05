# TD-019 行为等价矩阵：修复 Vue Query 轮询自引用 TDZ

本矩阵覆盖 TD-019（修复 DatabaseView / FileDetailView 的
`useDatasetTasksQuery` / `useFileTasksQuery` 调用时把正在声明的
`tasksQuery` 自身作为 polling refetchInterval 数据源引发的 TDZ 运行时错误）
的不变性声明。

每行三列：

- **TD-019 前（TD-015/017/018 现状）**：调用方传入 `polling` computed
  引用 `tasksQuery.data.value`；setup 阶段 Vue Query 同步评估
  `refetchInterval` 触发 TDZ
- **TD-019 后**：query hook 内部用 `refetchInterval: (query) => ...` 函数
  形式，从 `query.state.data` 派生 polling；调用方不再传 polling
- **本任务范围**：✅ = 本轮改；➖ = 不适用

## 1. 调用方式

| 调用 | 旧调用方式 | 新调用方式 | 本任务 |
|------|------------|------------|--------|
| DatabaseView tasks | `useDatasetTasksQuery(selectedId, computed(() => tasksQuery.data.value.some(...)))` | `useDatasetTasksQuery(selectedId)` | ✅ |
| FileDetailView tasks | `useFileTasksQuery(fileId, computed(() => tasksQuery.data.value.some(...)))` | `useFileTasksQuery(fileId)` | ✅ |
| DatabaseView rows | `useDatasetRowsQuery(selectedId, ...)` | 同 | ➖ |
| DatabaseView kg | `useDatasetKgQuery(selectedId)` | 同 | ➖ |
| DatabaseView kg overview | `useKgOverviewQuery(enabledRef)` | 同 | ➖ |

## 2. 初始化时序

| 阶段 | 旧实现 | 新实现 |
|------|--------|--------|
| setup 入口 | `const tasksQuery = useDatasetTasksQuery(selectedId, pollingRef)` | `const tasksQuery = useDatasetTasksQuery(selectedId)` |
| query 内部 | `useQuery` 立刻建立 `refetchInterval` 的 `watchEffect`；effect 同步读 `refetchInterval.value` → 读 `polling.value` → 调外部 computed → 读 `tasksQuery.data.value` → **TDZ ReferenceError** | `useQuery` 立刻建立 `refetchInterval` 的 `watchEffect`；`refetchInterval` 是函数 `(query) => ...`，**不被同步求值**（仅在 fetch 完成后被调用） |
| 模板挂载 | 触发 `[Vue warn]: Unhandled error during execution of watcher callback` | 正常 |
| tasksQuery 声明完成 | (TDZ 命中时此处永远到不了) | ✅ `tasksQuery.data.value` 后续可被 `polling` computed 安全访问 |

## 3. 轮询条件

| 关注点 | 旧实现 | 新实现 |
|--------|--------|--------|
| 轮询间隔 | 3s | 3s |
| 启用条件 | `(tasksQuery.data.value ?? []).some(t => t.status === "running" \|\| t.status === "pending")` | 同：query 内部从 `query.state.data` 派生 |
| 暂停条件 | 不存在 running/pending 时返回 `false` 暂停 | 同：函数返回 `false` 暂停 |
| 评估时机 | 旧 `computed` 在 setup 同步评估 + 每次 data 变化时重新评估 | 新函数仅在每次 fetch 完成后被调用 |

**关键差异**：旧实现在 setup 阶段同步评估（命中 TDZ）；新实现延后到
fetch 完成后评估（无 TDZ）。最终轮询行为完全一致。

## 4. 模板中的 `polling` 变量

| 关注点 | 旧实现 | 新实现 |
|--------|--------|--------|
| DatabaseView `:619` `polling` 声明 | 声明在 `tasksQuery` 之前（作为 `useDatasetTasksQuery` 的第二参数） | 声明在 `tasksQuery` 之后（独立 `computed`），**不参与 query 初始化**，不构成 TDZ |
| DatabaseView `<span v-if="polling">` 模板 | 引用 `polling` | 引用 `polling`（同一变量） |
| FileDetailView `:418-425` `watch(polling, ...)` | 由 polling 驱动 | 由 polling 驱动（同一变量） |

## 5. Watch 与 mutation

| 关注点 | 旧实现 | 新实现 |
|--------|--------|--------|
| `watch` ds_parse / ds_extract_kg 状态变化 | `void datasetsQuery.refetch(); void rowsQuery.refetch();` | 同（未变） |
| `watch(polling)` true→false | 触发 fileQuery / chunksQuery / kgQuery refetch | 同 |
| 3 个 mutation 成功 toast + 后置动作 | `useRetryTasksMutation` / `useReinitializeMutation` / `useDeleteDatasetMutation` | 同（未变） |

## 6. 错误处理

| 关注点 | 旧实现 | 新实现 |
|--------|--------|--------|
| 初始化阶段 console 警告 | `[Vue warn]: Unhandled error during execution of watcher callback` | 无 |
| 用户可见 ReferenceError | 在某些运行时（例如浏览器实测）会冒泡导致 setup 抛错 | 修复 |
| 全局 `QueryCache.onError` toast | 未变 | 未变 |

## 7. 用户可见行为不变性总览

- ✅ 3s 轮询仅在存在 running/pending 任务时启用
- ✅ 任务全部完成时停止轮询
- ✅ `polling` 模板提示（"自动刷新中..."）显示时机一致
- ✅ `watch(polling)` true→false 触发对应 query refetch 一致
- ✅ 模板渲染、loading 派生、mutation 行为全部保留
- ✅ 修复 Runtime ReferenceError（用户可见行为改善）

## 不变量

- 不动 service 层
- 不动 main.ts 全局 `QueryCache.onError`
- 不动其他 query hook（rows / kg / kg overview / file / chunks / kg / templates）
- 不动路由或 store
- 行为变化声明：用户可见行为完全不变；唯一改善是修复 setup 阶段 TDZ
  ReferenceError
