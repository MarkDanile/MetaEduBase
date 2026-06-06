# TD-018 FileDetailView 剩余手写 load 迁到 Vue Query — Spec

## 背景

`docs/03-engineering-governance/technical-debt.md#td-018-filedetailview-剩余手写-load-迁到-vue-query`
指出 TD-017（PR #40, 5af2793）迁移了 FileDetailView 的 `loadTasks` + 3 个
mutation + 轮询，但 4 个手写 load 仍保留：

- `loadFile` (line 290-300)：GET file detail；由 `loading` ref 控制
- `loadChunks` (line 313-322)：GET chunks；由 `loadingChunks` ref 控制
- `loadKg` (line 325-339)：并行 GET listNodes + listEdges；由 `loadingKg` ref 控制
- `loadTemplates` (line 341-348)：GET templates；**静默失败**（try/catch 不 toast）

3 个 `loading*` ref（`loading` / `loadingChunks` / `loadingKg`）仍由手写 load 设置。

调用点：
- `refreshAll()` (line 303-310)：`loadFile + loadChunks + loadKg`
- `watch(activeTab)` (line 444-447)：tab 切换时按需调
- `watch(polling)` 由 true→false (line 456-460)：TD-017 加的，调 `loadFile + loadChunks + loadKg`
- `onMounted` (line 468)：`loadFile + loadTemplates`

## 目标

把 4 个手写 load（`loadFile` / `loadChunks` / `loadKg` / `loadTemplates`）迁到
Vue Query；3 个 `loading*` ref 全部由 query 状态派生；`refreshAll` /
`watch(activeTab)` / `watch(polling)` 全部改用 `query.refetch()`。**用户可见
行为不变**（loading 显示、tab 切换、刷新按钮、静默失败、`polling` 触发
refresh 等）。

## 范围

### In scope

- `packages/web/src/views/resource/queries.ts` 扩展：
  - `useFileQuery(fileId)`：GET file detail
  - `useFileChunksQuery(fileId, enabled)`：GET chunks（按 `enabled` 懒加载）
  - `useFileKgQuery(fileId, enabled)`：并行 GET listNodes + listEdges，返回
    `{ nodes, edges }`；按 `enabled` 懒加载
  - `useTemplatesQuery()`：GET templates（无参数）
  - 扩展 `fileKeys`：增加 `detail / chunks / kg`，新增顶层 `templates` key
- `packages/web/src/views/resource/FileDetailView.vue` 重构：
  - 删除 4 个手写 load 函数（`loadFile` / `loadChunks` / `loadKg` /
    `loadTemplates`）
  - 删除 3 个 `loading*` ref（`loading` / `loadingChunks` / `loadingKg`）；
    改为 `query.isLoading` / `query.isFetching` 派生
  - 模板里 `<LoadingSpinner v-if="loadingChunks">` 等改用 `chunksQuery.isFetching.value`
  - `refreshAll` 改为 `fileQuery.refetch() + chunksQuery.refetch() + kgQuery.refetch()`
  - `watch(activeTab)` 改为 `query.refetch()`（tab=chunks → refetch chunks；
    tab=kg → refetch kg；tab=structured → refetch file）
  - `watch(polling)` 由 true→false 改用 `query.refetch()`
  - `onMounted` 改用 `Promise.all` 调 3 个 refetch（实际上 useQuery 会自动
    触发，保留以兼容未来 mount 时序）
  - `loadTemplates` 的静默失败行为：通过 `enabled: false` + 不挂载 /
    `onError` 内不 toast 来保留
- 行为等价矩阵 `docs/03-engineering-governance/02-matrices/td-018-filedetailview-remaining-equivalence.md`
  覆盖 4 个 load × 3 阶段（手写 / TD-018 修复后）

### Out of scope

- 不动 `loadTasks` / 3 个 mutation / 轮询（TD-017 已完成）
- 不动 service 层
- 不动 `QueryCache.onError` 全局错误处理
- 不动其他视图

## 设计要点

### 1. `useFileQuery` 简单 GET

```typescript
function useFileQuery(fileId: Ref<string>): UseQueryReturnType<FileDTO | null, Error> {
  return useQuery({
    queryKey: computed(() => fileKeys.detail(fileId.value)),
    queryFn: () => documentApi.getFile(fileId.value).then((r) => r.data),
    enabled: computed(() => !!fileId.value),
  });
}
```

### 2. `useFileChunksQuery` 懒加载

```typescript
function useFileChunksQuery(
  fileId: Ref<string>,
  enabled: Ref<boolean>,
): UseQueryReturnType<ChunkDTO[], Error> {
  return useQuery({
    queryKey: computed(() => fileKeys.chunks(fileId.value)),
    queryFn: () => documentApi.listChunks(fileId.value).then((r) => r.data),
    enabled: computed(() => !!fileId.value && enabled.value),
  });
}
```

`enabled` 由 `activeTab === "chunks"` 派生。

### 3. `useFileKgQuery` 并行 GET + 懒加载

```typescript
interface KgBundle { nodes: KnowledgeNodeDTO[]; edges: KnowledgeEdgeDTO[]; }

function useFileKgQuery(
  fileId: Ref<string>,
  enabled: Ref<boolean>,
): UseQueryReturnType<KgBundle, Error> {
  return useQuery({
    queryKey: computed(() => fileKeys.kg(fileId.value)),
    queryFn: async (): Promise<KgBundle> => {
      const [nodesRes, edgesRes] = await Promise.all([
        knowledgeApi.listNodes({ source_file_id: fileId.value }),
        knowledgeApi.listEdges({ source_file_id: fileId.value }),
      ]);
      return { nodes: nodesRes.data, edges: edgesRes.data };
    },
    enabled: computed(() => !!fileId.value && enabled.value),
  });
}
```

### 4. `useTemplatesQuery` 静默失败

`loadTemplates` 旧实现 try/catch 但不 toast。**Vue Query 默认全局 onError 会
toast** — 要保留静默失败，需要在 query 内吞掉 error。两种方案：

**方案 A（推荐）**：`onError` callback 显式 `return undefined`，覆盖全局 onError。

```typescript
function useTemplatesQuery(): UseQueryReturnType<Template[], Error> {
  return useQuery({
    queryKey: ["templates"],
    queryFn: () => templateApi.list().then((r) => r.data),
    // Legacy `loadTemplates` silently failed; suppress the global QueryCache
    // toast so we keep that behavior. Errors still surface via `error` and
    // can be retried by the user.
    meta: { suppressErrorToast: true },
  });
}
```

但 `QueryCache.onError` 默认会处理 — 需要 main.ts 读取 meta 决定是否 toast：

```typescript
// main.ts
new QueryCache({
  onError: (error, query) => {
    if (query.meta?.suppressErrorToast) return;
    toast.error(error?.message ?? "请求失败");
  },
}),
```

**方案 B（更轻）**：`useTemplatesQuery` 内部不抛错（catch 后返回 `[]`）。

```typescript
queryFn: async () => {
  try {
    return (await templateApi.list()).data;
  } catch {
    return [];
  }
},
```

**采用方案 B**：更轻、不动 `main.ts` 全局行为。`templates` 数据可能是 `[]`，
但 `templates.value.length === 0` 已经是模板"未找到"的回退路径。

### 5. 模板里 loading 改写

```html
<LoadingSpinner v-if="loading" text="加载中..." />
<!-- 改： -->
<LoadingSpinner v-if="fileQuery.isFetching.value" text="加载中..." />
```

### 6. 调用点改写

```typescript
async function refreshAll() {
  await Promise.all([
    fileQuery.refetch(),
    chunksQuery.refetch(),
    kgQuery.refetch(),
  ]);
}

watch(activeTab, (newTab) => {
  if (newTab === "structured") void fileQuery.refetch();
  if (newTab === "chunks") void chunksQuery.refetch();
  if (newTab === "kg") void kgQuery.refetch();
});

watch(polling, (now, prev) => {
  if (prev && !now) {
    void fileQuery.refetch();
    if (activeTab.value === "chunks") void chunksQuery.refetch();
    if (activeTab.value === "kg") void kgQuery.refetch();
  }
});
```

### 7. 测试策略

与 TD-017 一致：前端无 vitest 配置，本轮不补单元测试。验证：
- typecheck / build / lint 全部退出码 0
- 行为等价矩阵覆盖完成标准
- PR 描述显式声明行为不变

### 8. 行为不变声明

按 `quality-gates.md#行为变化声明检查`：

| 类别 | 是否变化 | 说明 |
|------|----------|------|
| 加载时机 | 不变 | chunks / kg 仍按 `activeTab` 懒加载 |
| 刷新时机 | 不变 | `refreshAll` / tab 切换 / polling true→false 仍触发对应 query 重 fetch |
| loading 显示 | 不变 | 由 `query.isFetching` 派生 |
| `loadTemplates` 静默失败 | 不变 | queryFn 内 catch，返回 `[]` |
| 错误文案 | 边缘变化 | 4 个 load 的失败文案从「固定字符串」改为「query error message 兜底」（与 TD-015/TD-017 一致） |
| import 副作用 | 变化 | 删除 4 个手写 load + 3 个 ref；新增 4 个 query hook |

可观察行为：4 个 load 的所有调用时机、loading 显示、静默失败全部保留。

## 完成标准

1. `queries.ts` 扩展 4 个 hook（`useFileQuery` / `useFileChunksQuery` /
   `useFileKgQuery` / `useTemplatesQuery`）
2. `FileDetailView.vue` 重构：删除 4 个手写 load + 3 个 `loading*` ref
3. 行为等价矩阵覆盖 4 个 load × 3 阶段
4. `pnpm --filter @metaedu/web typecheck` / `lint` / `build` 退出码 0
5. PR 描述明确声明行为不变 + 错误文案边缘变化
6. 提交信息遵循 Conventional Commits：
   `refactor(web): TD-018 migrate FileDetailView remaining loads to Vue Query`

## 验证方式

按 `quality-gates.md#验证矩阵`：

```bash
cd packages/web
pnpm --filter @metaedu/web typecheck
pnpm --filter @metaedu/web build
pnpm --filter @metaedu/web lint
```

按 `quality-gates.md#行为变化声明检查` 显式声明：
> 本次重构以把 FileDetailView 剩余 4 个手写 load（loadFile / loadChunks /
> loadKg / loadTemplates）迁到 Vue Query 为主，**用户可见行为不变**：
> 加载时机、刷新时机、loading 显示、`loadTemplates` 静默失败、tab
> 切换、`polling` 触发 refresh 全部保留。错误文案从「固定字符串」改为
> 「query error message 兜底」是边缘可见变化（与 TD-015/TD-017 一致）。

## 风险与后续

- 风险：`useTemplatesQuery` 用 catch 返回 `[]` 方案，templates 错误时模板标签
  静默退化；如未来需要明确报错，需要改为方案 A。
- 后续：FileDetailView 完成 Vue Query 全量迁移后，前端大页面（DatabaseView /
  FileDetailView）均已统一，剩余小页面（KnowledgeBaseView / ResourceLibraryView
  等）按需迁移。

## 任务卡片字段

完成后需在 `current-work.md` 把 TD-018 移到「最近完成」并记录 PR 链接，
同时在 `technical-debt.md#td-018-filedetailview-剩余手写-load-迁到-vue-query`
的备注中追加完成日期、提交信息和验证结果。
