# TD-007 收敛 DatabaseView 请求状态到 Vue Query — Spec

## 背景

`docs/03-engineering-governance/technical-debt.md#td-007-减少前端请求状态处理重复` 指出前端请求
生命周期逻辑在多个视图中重复。`packages/web/src/main.ts` 已经注册了
`@tanstack/vue-query` 的 `VueQueryPlugin`，但
`packages/web/src/views/database/DatabaseView.vue`（约 845 行）仍手写大量
loading / error / 轮询 / toast 状态机：

| 手写状态 | 行数 | 来源 |
|----------|------|------|
| `loading`, `loadingDetail`, `loadingTasks`, `loadingRows`, `loadingKg`, `loadingKgOverview` | 451-456 | 6 个独立 ref |
| `uploading`, `rebuildingKg` | 479, 465 | 2 个 mutation 状态 |
| `loadDatasets` / `loadTasks` / `loadRows` / `loadKg` / `loadKgOverview` | 496-599 | 5 个手写 fetch + try/catch/finally + toast.error |
| `doUpload` / `doDelete` / `retryTasks` / `reinitialize` / `doRebuildKg` | 621-710 | 5 个手写 mutation + try/catch + toast |
| `setInterval(pollTimer)` 轮询 | 822-833 | 手写 setInterval 3s 轮询 |
| 5 个 `watch` 监听 tasks 变化联动刷新 | 726-765 | 业务规则实现 |

## 目标

把 `DatabaseView.vue` 的 5 个 fetch + 5 个 mutation + 1 个轮询迁到 Vue Query
（`@tanstack/vue-query`），删除对应的手写 `ref` / `setInterval` / `try/catch` /
`toast.error` 重复，**用户可见行为不变**（loading 显示、错误提示、刷新时机、
重新初始化流程、tab 切换、watch 联动保留）。

## 范围

### In scope

- `packages/web/src/views/database/DatabaseView.vue` 重构：
  - 5 个 `load*` 函数 → `useQuery` 调用（query key 包含依赖参数）
  - 5 个 mutation → `useMutation` 调用，删除手写 try/catch
  - `setInterval` 轮询 → `useQuery` 的 `refetchInterval` 选项
  - 6 个 `loading*` ref → 改为读 query 的 `isLoading` / `isFetching`
  - 2 个 mutation 状态 ref → 改为读 mutation 的 `isPending`
  - 错误 toast：通过 `QueryClient` 全局 `QueryCache.onError` 统一处理
  - 成功 toast：保留在 mutation 的 `onSuccess` 回调里（业务文案）
- `packages/web/src/main.ts` 改造：
  - 新建 `queryClient` 实例并配置 `QueryCache.onError` 统一 toast.error
  - 通过 `VueQueryPlugin` 注入
- 新建 `packages/web/src/views/database/queries.ts` 集中所有 queryKey 与
  queryFn 工厂（避免 DatabaseView 内部堆 helper）。
- 验证前端 typecheck 和 build 通过。
- 验证用户可见行为：列表加载、详情切换、上传、重试、重新初始化、tab 刷新、
  轮询仍在 running/pending 时按 3s 间隔刷新（保留 setInterval 旧行为）。

### Out of scope

- 不动 `FileDetailView.vue`（本轮只收敛 `DatabaseView`，符合总账「选择一个
  高变更页面」的指引；其他页面留作 TD-007-FOLLOWUP）。
- 不重写 `services/structuredData.ts` 等 service 文件（保留原 service API）。
- 不动 `useToast` 实现。
- 不动 `polling` 计算属性（仍由 `tasks` query 数据驱动）。
- 不动 watch 联动逻辑（pipeline 业务规则保留，只把 watch 内部的手写 fetch
  改为调 query.refetch / mutate）。
- 不引入新依赖（`@tanstack/vue-query` 已声明）。

## 设计要点

### 1. Query 键与 queryFn 工厂

`packages/web/src/views/database/queries.ts`：

```typescript
export const datasetKeys = {
  all: ['datasets'] as const,
  list: (params: { sort_by: string; sort_dir: string }) =>
    [...datasetKeys.all, 'list', params] as const,
  detail: (id: string) => [...datasetKeys.all, 'detail', id] as const,
  tasks: (id: string) => [...datasetKeys.all, id, 'tasks'] as const,
  rows: (id: string, params: { offset: number; limit: number }) =>
    [...datasetKeys.all, id, 'rows', params] as const,
  kg: (id: string) => [...datasetKeys.all, id, 'kg'] as const,
  kgOverview: () => [...datasetKeys.all, 'kgOverview'] as const,
};

export const datasetMutations = {
  upload: () => ({ mutationKey: ['dataset', 'upload'] as const }),
  delete: () => ({ mutationKey: ['dataset', 'delete'] as const }),
  retryTasks: () => ({ mutationKey: ['dataset', 'retryTasks'] as const }),
  reinitialize: () => ({ mutationKey: ['dataset', 'reinitialize'] as const }),
  rebuildKg: () => ({ mutationKey: ['dataset', 'rebuildKg'] as const }),
};
```

### 2. Query 调用形态

```typescript
// 替换 loadDatasets()
const datasetsQuery = useQuery({
  queryKey: datasetKeys.list({ sort_by: sortBy.value, sort_dir: sortDir.value }),
  queryFn: () => structuredDataApi.listDatasets({ sort_by: sortBy.value, sort_dir: sortDir.value }).then(r => r.data),
});
const datasets = computed(() => datasetsQuery.data.value ?? []);
const loading = computed(() => datasetsQuery.isLoading.value);
```

其他 query 同样模式。`selectDataset` 改为 set `selectedId.value`，trigger 对应 query 重 fetch。

### 3. 轮询

`loadTasks` → `useQuery` 配置 `refetchInterval: 3000`，在 `polling` computed 为 true 时启用：

```typescript
const tasksQuery = useQuery({
  queryKey: datasetKeys.tasks(selectedId),
  queryFn: () => structuredDataApi.listTasks(selectedId.value!).then(r => r.data),
  enabled: computed(() => !!selectedId.value),
  refetchInterval: computed(() => polling.value ? 3000 : false),
});
```

注：`refetchInterval` 在 `polling=false` 时返回 `false` 即停止轮询，比
`setInterval` 更干净。`onUnmounted` 清理 `pollTimer` 也可以删掉。

### 4. 全局错误处理

`main.ts`：

```typescript
import { QueryCache, QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { toast } from "@/composables/useToast"; // 或类似路径

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      toast.error(error?.message ?? "请求失败");
    },
  }),
});

app.use(VueQueryPlugin, { queryClient });
```

`onError` 兜底覆盖所有未在 queryFn 内部 catch 的错误；现有的 `try/catch`
+ `toast.error("...")` 在迁移时可以全部删除，文案由 query error message
或统一文案承担。

### 5. Mutation 模式

```typescript
const uploadMutation = useMutation({
  mutationFn: (formData: FormData) => structuredDataApi.uploadDataset(formData, ...).then(r => r.data),
  onSuccess: () => {
    toast.success("数据集上传成功");
    showUpload.value = false;
    uploadForm.value = { name: "", description: "", tags: "", file: null };
    datasetsQuery.refetch();
  },
});
const uploading = computed(() => uploadMutation.isPending.value);
```

`doUpload` 改为 `uploadMutation.mutate(formData)`。

### 6. Watch 联动保留

```typescript
// 保留
watch(() => tasks.value.find((t) => t.task_type === 'ds_parse')?.status,
  async (status, prevStatus) => {
    if (status === 'success' && prevStatus !== 'success' && selected.value) {
      // 改为调 query.refetch()
      datasetsQuery.refetch();  // 刷新列表 row_count
      rowsQuery.refetch();      // 重新加载行
    }
  });
```

业务规则的 watch 保留，内部的 fetch 改为 `query.refetch()`。

### 7. 测试策略

前端无 typecheck 失败即可视为「typecheck 通过」；build 通过即可视为「无语法
/ import 错误」。手动验收：
- 列表加载（datasets）
- 详情切换（selectDataset → loadTasks + loadRows + 条件 loadKg）
- 上传（uploadMutation）
- 重试（retryTasksMutation）
- 重新初始化（reinitializeMutation）
- tab 刷新（watch activeTab → loadKg）
- 轮询（running 任务 3s 自动刷新）

按 `docs/03-engineering-governance/01-rules/quality-gates.md#验证矩阵`：

```bash
cd packages/web
pnpm --filter @metaedu/web typecheck
pnpm --filter @metaedu/web build
```

### 8. 行为不变声明

按 `quality-gates.md#行为变化声明检查` 排查：

| 类别 | 是否变化 | 说明 |
|------|----------|------|
| 用户可见文案 | 错误文案由 query error message 决定 | 与旧实现差异极小（之前 catch 后 toast.error("加载数据集列表失败") 固定文案；现在可能带具体错误） |
| 加载时机 | 不变 | onMounted / selectDataset 仍触发；watch 仍生效 |
| 轮询时机 | 不变 | running/pending 时 3s 间隔 |
| 状态机 | 变化 | 6 个 loading* ref 改为 query.isLoading / isFetching；2 个 mutation 状态改为 mutation.isPending |
| import 副作用 | 变化 | 新增 queries.ts、queryClient 实例；删除 useToast 在 loading 路径上的所有显式调用 |

可观察行为：列表 / 详情 / 上传 / 重试 / 重新初始化 / tab 切换 / 轮询 全部保留。

## 完成标准

1. `packages/web/src/main.ts` 创建 `QueryClient` 并注册到 `VueQueryPlugin`，
   `QueryCache.onError` 统一 toast。
2. `packages/web/src/views/database/queries.ts` 新增，集中 queryKey 与 queryFn。
3. `DatabaseView.vue` 重构：
   - 删除 5 个 `load*` 函数 + 5 个 mutation 函数 + 6 个 `loading*` ref + 1 个
     `uploading` ref + 1 个 `rebuildingKg` ref + 1 个 `pollTimer` + 1 个
     `startPolling` + 1 个 `stopPolling`
   - 替换为 5 个 `useQuery` + 5 个 `useMutation`
   - watch 联动保留，内部 fetch 改为 `query.refetch()` / `mutation.mutate()`
4. `pnpm --filter @metaedu/web typecheck` 退出码 0
5. `pnpm --filter @metaedu/web build` 退出码 0
6. `pnpm --filter @metaedu/web lint` 退出码 0（无新增 warning）
7. 提交信息遵循 Conventional Commits：`refactor(web): TD-007 migrate DatabaseView requests to Vue Query`

## 验证方式

按 `quality-gates.md#验证矩阵`（前端 Vue/TS）：

```bash
cd packages/web
pnpm --filter @metaedu/web typecheck
pnpm --filter @metaedu/web build
pnpm --filter @metaedu/web lint
```

并按 `quality-gates.md#行为变化声明检查` 声明：
> 本次重构以把 DatabaseView 的请求生命周期迁到 Vue Query 为主。
> 用户可见行为：列表加载 / 详情切换 / 上传 / 重试 / 重新初始化 /
> tab 刷新 / 轮询 时机均不变；错误提示文案从「固定字符串」改为
> 「由 query error message 兜底」属于边缘可见变化（具体报错更精确）。

## 风险与后续

- 风险：Vue Query 默认缓存（staleTime: 0）可能让用户从「列表」切到「详情」
  再切回时重新请求。这是预期行为，与原 setInterval/手动 refetch 一致。
- 风险：mutation 失败时，全局 `QueryCache.onError` 也会触发一次 toast，
  而 `onSuccess` 不触发。需要在 mutation 内部 try/catch 防止双重 toast。
  解决：mutation 不在 `mutate` 端 try/catch；onError 由 `QueryCache` 统一。
- 后续：TD-007-FOLLOWUP：把同样的迁移模式应用到 `FileDetailView.vue`。

## 任务卡片字段

完成后需在 `current-work.md` 把 TD-007 移到「最近完成」并记录 PR 链接，
同时在 `technical-debt.md#td-007-减少前端请求状态处理重复` 的备注中追加
完成日期、提交信息和验证结果。
