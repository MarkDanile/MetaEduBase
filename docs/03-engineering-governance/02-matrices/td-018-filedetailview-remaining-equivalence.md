# TD-018 行为等价矩阵：FileDetailView 剩余手写 load 迁到 Vue Query

本矩阵覆盖 TD-018（将 FileDetailView 的 `loadFile` / `loadChunks` /
`loadKg` / `loadTemplates` 4 个手写 load 迁到 Vue Query）的行为不变声明。
每行三列：

- **TD-018 前（手写）**：手写 fetch + try/catch + ref 控制的 loading 状态
- **TD-018 后**：Vue Query 迁移后
- **本任务范围**：✅ = 本轮迁；➖ = 不适用

## 1. GET 请求（FileDetailView 全部 5 个 + 1 个 templates）

| 请求 | 旧实现位置 | 本任务 | 备注 |
|------|------------|--------|------|
| `loadFile` (GET file) | line 290-300 | ✅ 迁到 `useFileQuery` | `loading` ref 改为 `fileQuery.isLoading` |
| `loadTasks` (GET tasks) | TD-017 已迁 | ➖ | useFileTasksQuery 维持 |
| `loadChunks` (GET chunks) | line 313-322 | ✅ 迁到 `useFileChunksQuery` | `loadingChunks` ref 改为 `chunksQuery.isFetching`；按 `activeTab === "chunks"` 懒加载 |
| `loadKg` (GET kg) | line 325-339 | ✅ 迁到 `useFileKgQuery` | `loadingKg` ref 改为 `kgQuery.isFetching`；按 `activeTab === "kg"` 懒加载 |
| `loadTemplates` (GET templates) | line 341-348 | ✅ 迁到 `useTemplatesQuery` | **静默失败保留**（queryFn 内 catch 返回 `[]`） |

## 2. 加载状态

| 状态 | 旧实现 | TD-018 后 |
|------|--------|-----------|
| `loading` | `ref(true)`，`loadFile` 内 set | `fileQuery.isLoading.value`（computed） |
| `loadingChunks` | `ref(false)`，`loadChunks` 内 set | `chunksQuery.isFetching.value` |
| `loadingKg` | `ref(false)`，`loadKg` 内 set | `kgQuery.isFetching.value` |
| `loadingTasks` | TD-017 已迁 | `tasksQuery.isFetching.value` |

## 3. 调用时机

| 关注点 | 旧实现 | TD-018 后 |
|--------|--------|-----------|
| `onMounted` 初始化 | `await Promise.all([loadFile(), loadTemplates()])` | `await Promise.all([fileQuery.refetch(), templatesQuery.refetch()])`（或直接依赖 useQuery 自动触发） |
| `refreshAll` 按钮 | 调 `loadFile + loadChunks + loadKg` | `await Promise.all([fileQuery.refetch(), chunksQuery.refetch(), kgQuery.refetch()])` |
| `watch(activeTab)` 切到 structured | `loadFile()` | `void fileQuery.refetch()` |
| `watch(activeTab)` 切到 chunks | `loadChunks()` | `void chunksQuery.refetch()` |
| `watch(activeTab)` 切到 kg | `loadKg()` | `void kgQuery.refetch()` |
| `watch(polling)` 由 true→false | `loadFile + loadChunks + loadKg`（按 activeTab） | `void fileQuery.refetch() + (activeTab === "chunks" ? chunksQuery.refetch() : null) + (activeTab === "kg" ? kgQuery.refetch() : null)` |

## 4. 错误处理

| 关注点 | 旧实现 | TD-018 后 |
|--------|--------|-----------|
| `loadFile` 失败 | `toast.error("加载文件失败")` | 由 `QueryCache.onError` 统一；query error message 兜底 |
| `loadChunks` 失败 | `toast.error("加载切片失败")` | 同上 |
| `loadKg` 失败 | `toast.error("加载知识图谱失败")` | 同上 |
| `loadTemplates` 失败 | **静默吞掉**（不 toast，templates 是可选） | `useTemplatesQuery` queryFn 内 catch 返回 `[]`；`QueryCache.onError` 不被调用（query 没有 error） |

**关键差异**：`loadTemplates` 在 TD-018 后**根本不会触发** `QueryCache.onError`（因为 query 内部吞了 error），从而保留"可选 templates"的语义。

**边缘可见变化**：`loadFile` / `loadChunks` / `loadKg` 的错误文案从「固定字符串」改为「query error message 兜底」。

## 5. 缓存与 staleTime

| 关注点 | 旧实现 | TD-018 后 |
|--------|--------|-----------|
| `loadFile` 缓存 | 手动 `file.value = data` | Vue Query 自动 cache；`fileQuery.data` 即缓存 |
| `loadChunks` 缓存 | 手动 `chunks.value = data` | Vue Query 自动 cache；`enabled: false` 时不拉取 |
| `loadKg` 缓存 | 手动 `kgNodes/kgEdges.value = ...` | Vue Query 自动 cache；`enabled: false` 时不拉取 |
| 手动 refresh 后内存 | 旧 ref 一直保留 | Vue Query 默认保留缓存，可通过 `staleTime` 控制；本轮不显式设 staleTime（行为与旧实现接近） |
| 跨视图复用缓存 | 旧实现不共享 | Vue Query 共享 queryClient；但 FileDetailView 是新 queryKey 树形（`["files", fileId, "chunks"]` 等），不与其他视图冲突 |

## 6. 用户可见行为不变性总览

- ✅ 文件详情加载（进入页面时）
- ✅ 切片懒加载（切到 chunks tab 时）
- ✅ KG 懒加载（切到 kg tab 时）
- ✅ 模板加载（进入页面时；可选 / 静默）
- ✅ 刷新按钮（refreshAll 拉全部 3 个 query）
- ✅ tab 切换（按 activeTab refetch 对应 query）
- ✅ 轮询停止后 refresh（polling true→false 触发 fileQuery + chunks/kg）
- ✅ `loadTemplates` 静默失败（query error 不触发全局 toast）
- ➖ 错误文案从固定字符串改为 query error message 兜底（边缘可见变化）
- ➖ 加载状态由 `loading*` ref 改为 `query.isLoading` / `isFetching`（用户不可见）

## 不变量

- 不动 service 层
- 不动 `QueryCache.onError` 全局处理（`main.ts` 已注册）
- 不动 TD-017 已迁的 `loadTasks` / 3 个 mutation / 轮询
- 不动其他视图
- 不动路由或 store
