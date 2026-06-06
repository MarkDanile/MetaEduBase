# TD-017 行为等价矩阵：FileDetailView Vue Query 迁移

本矩阵覆盖 TD-017（将 FileDetailView 的 `loadTasks` + 3 个 mutation 迁到
Vue Query）的行为不变声明。每行三列：

- **TD-017 前（旧实现）**：手写 fetch + setInterval + try/catch + toast
- **TD-017 后（PR #...）**：Vue Query 迁移后
- **本任务范围**：✅ = 本轮迁；➖ = 本轮不迁（保持手写）

## 1. GET 请求（FileDetailView 内全部 5 个）

| 请求 | 旧实现位置 | 本任务 | 备注 |
|------|------------|--------|------|
| `loadFile` (GET file) | `loadFile()` line 256-266 | ➖ | 保留手写（不在总账范围） |
| `loadTasks` (GET tasks) | `loadTasks()` line 268-278 | ✅ | 迁到 `useFileTasksQuery` |
| `loadChunks` (GET chunks) | `loadChunks()` line 293-303 | ➖ | 保留手写（不在总账范围） |
| `loadKg` (GET kg) | `loadKg()` line 305-318 | ➖ | 保留手写（不在总账范围） |
| `loadTemplates` (GET templates) | `loadTemplates()` line 321-328 | ➖ | 保留手写（不在总账范围） |

## 2. Mutation（FileDetailView 内全部 3 个）

| Mutation | 旧实现 | TD-017 行为 | 后置动作 |
|----------|--------|--------------|----------|
| `retryTasks` | `await documentApi.retryTasks(fileId)` + `toast.success` + `loadTasks()` | ✅ 迁到 `useRetryTasksMutation`：mutate → invalidate `["files", fileId, "tasks"]` | 成功 toast 不变；列表自动 refetch |
| `reinitialize` | `await documentApi.reinitializeFile(fileId)` + `toast.success` + `loadFile + loadTasks` + 清空 `chunks/kgNodes/kgEdges` + `startPolling()` | ✅ 迁到 `useReinitializeFileMutation`：mutate → invalidate file detail + tasks；onSuccess 仍清空 chunks/kg | 成功 toast 不变；旧 `startPolling` 改为由 useFileTasksQuery 自动启用 refetchInterval |
| `doDelete` | `await documentApi.deleteFile(fileId)` + `toast.success` + `router.push("/resource")` | ✅ 迁到 `useDeleteFileMutation`：无 invalidate（直接跳转） | 成功 toast + 路由跳转不变 |

## 3. 轮询（核心变更点）

| 关注点 | 旧实现 | TD-017 后 |
|--------|--------|-----------|
| 触发条件 | `setInterval(loadTasks, 3000)` 在 `startPolling()` 内无条件启动 | `useFileTasksQuery.refetchInterval: computed(() => polling.value ? 3000 : false)` |
| 启用条件 | `startPolling()` 在 `onMounted` 末尾无条件调用 | 由 query 自动启用；polling 由 query data 派生 |
| 停止条件 | `setInterval` 触发时若 `polling.value === false` → 调 `loadFile + loadChunks + loadKg` + `stopPolling()` | `watch(polling, (now, prev) => { if (prev && !now) { ... } })` 监听 `true → false` 转换；调 `loadFile + loadChunks + loadKg`（仍手写） |
| 任务全部完成时 | `setInterval` 内 `polling` 变 false → 调其他手写 loaders | watch `polling` 由 true→false 触发同样的 loaders |
| `onUnmounted` 清理 | `stopPolling()` | 由 Vue Query 自动管理（query unmounted 时自动停 refetchInterval） |

## 4. 错误处理

| 关注点 | 旧实现 | TD-017 后 |
|--------|--------|-----------|
| `loadTasks` 失败 | `try/catch` + `toast.error("加载任务失败")` | 由 `QueryCache.onError` 统一；query error message 兜底 |
| `retryTasks` 失败 | `try/catch` + `toast.error("重试失败")` | 同上 |
| `reinitialize` 失败 | `try/catch` + `toast.error("重新初始化失败")` | 同上 |
| `doDelete` 失败 | `try/catch` + `toast.error("删除失败")` | 同上 |

**边缘可见变化**：错误文案从「固定字符串」改为「query error message 兜底」（更精确）。

## 5. Loading 状态

| 关注点 | 旧实现 | TD-017 后 |
|--------|--------|-----------|
| `loadingTasks` | `ref(false)`，由 `loadTasks` 内部 set | `tasksQuery.isFetching`（computed） |
| `loading` (file) | `ref(true)`，由 `loadFile` 内部 set | **保留手写**（不归本轮） |
| `loadingChunks` | `ref(false)`，由 `loadChunks` 内部 set | **保留手写**（不归本轮） |
| `loadingKg` | `ref(false)`，由 `loadKg` 内部 set | **保留手写**（不归本轮） |

## 6. 初始化（onMounted）

| 关注点 | 旧实现 | TD-017 后 |
|--------|--------|-----------|
| `onMounted` 调用 | `await Promise.all([loadFile(), loadTasks(), loadTemplates()])` + `startPolling()` | `await Promise.all([loadFile(), loadTemplates()])`；`loadTasks` 由 useFileTasksQuery 自动触发；`startPolling` 删除（query 自动启用） |
| `onUnmounted` 清理 | `stopPolling()` | 删除（Vue Query 自动管理） |

## 7. Cache Invalidation

| 关注点 | 旧实现 | TD-017 后 |
|--------|--------|-----------|
| `retryTasks` 成功 | `await loadTasks()` 手动重 fetch | `qc.invalidateQueries({ queryKey: ["files", fileId, "tasks"] })` |
| `reinitialize` 成功 | `await loadFile(); await loadTasks(); chunks = []; kgNodes = []; kgEdges = [];` | `qc.invalidateQueries({ queryKey: ["files", fileId] })` + onSuccess 内清空 chunks/kg |
| `doDelete` 成功 | `router.push("/resource")`（不重 fetch） | 同上（无 invalidate） |

## 8. 用户可见行为不变性总览

- ✅ 列表加载（tasks）
- ✅ 详情加载（file，**保留手写**）
- ✅ 切片加载（chunks，**保留手写**）
- ✅ KG 加载（kg，**保留手写**）
- ✅ 模板加载（templates，**保留手写**）
- ✅ 轮询 3s 间隔 + 仅 running/pending 时启用
- ✅ 任务全部完成时 refresh 其他资源
- ✅ 重试 toast + 自动刷新
- ✅ 重新初始化 toast + 清空 chunks/kg + 启动轮询
- ✅ 删除 toast + 路由跳转
- ➖ 错误文案从固定字符串改为 query error message（边缘可见变化）
- ➖ `loadChunks` / `loadKg` / `loadFile` / `loadTemplates` 仍手写（后续可做 follow-up）

## 不变量

- 不动 service 层（`documentApi` / `knowledgeApi` / `templateApi`）
- 不动路由或 store
- 不动其他视图
- 不动 `QueryCache.onError` 已在 main.ts 注册的事实
