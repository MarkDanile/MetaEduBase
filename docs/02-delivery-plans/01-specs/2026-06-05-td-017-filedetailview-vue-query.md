# TD-017 将 Vue Query 请求生命周期治理推广到 FileDetailView — Spec

## 背景

`docs/03-engineering-governance/technical-debt.md#td-017-将-vue-query-请求生命周期治理推广到-filedetailview`
指出 TD-007 / TD-015 已把 DatabaseView 的请求生命周期迁到 Vue Query，但
`packages/web/src/views/resource/FileDetailView.vue`（495 行）仍保留手写
`tasks / chunks / kgNodes` ref、`loading*` 状态、`pollTimer` 轮询和
mutation 后 `loadTasks()` / `loadFile()` 手动 refresh 模式。

按总账要求：
- 完成标准：列行为等价矩阵，迁移一个稳定请求族，不改用户可见行为
- 备注：先完成 TD-015（前序已完成），避免复制已发现回归模式

## 目标

把 FileDetailView 的 **`loadTasks`（GET + 轮询）+ 3 个 mutation**（retry /
reinitialize / delete）迁到 Vue Query。`loadFile` / `loadChunks` / `loadKg`
/ `loadTemplates` 本轮**保持手写**（不在总账要求的"一个稳定请求族"范围）。
**用户可见行为完全不变**（轮询时机、tab 切换、删除跳转、toast 文案）。

## 范围

### In scope

- `packages/web/src/views/resource/queries.ts` 新增：
  - `useFileTasksQuery(fileId, polling)`：GET 任务列表；`refetchInterval` 由
    `polling` 条件化（与 TD-015 fix 2 一致）
  - `useRetryTasksMutation(fileId, onSuccess)`
  - `useReinitializeFileMutation(fileId, onSuccess)`
  - `useDeleteFileMutation(fileId, onSuccess)`
- `packages/web/src/views/resource/FileDetailView.vue` 重构：
  - 删除 `tasks` ref + `loadingTasks` ref
  - 删除 `loadTasks` 函数
  - 删除 `pollTimer` / `startPolling` / `stopPolling`（替换为 useFileTasksQuery
    的 refetchInterval）
  - 删除 `retryTasks` / `reinitialize` / `doDelete` 函数
  - 删除 `onMounted` 显式 `loadTasks()` 触发
  - 删除 `onUnmounted` 清理
  - watch `polling` 从 true→false 时仍触发 `loadFile + loadChunks + loadKg`（这
    三个仍手写，但轮询停止条件改用 Vue Query 状态）
  - 错误 toast 改由 `QueryCache.onError` 统一处理（main.ts 已注册）
  - 成功 toast 保留在 mutation `onSuccess` 回调内
- 行为等价矩阵 `docs/03-engineering-governance/02-matrices/td-017-filedetailview-equivalence.md`
  覆盖：轮询条件 / mutation 触发 / refresh 时机 / cache invalidation / toast /
  loading 状态。

### Out of scope

- 不动 `loadFile` / `loadChunks` / `loadKg` / `loadTemplates`（保留手写）
- 不动其他视图（DatabaseView / AiChatView / KnowledgeBaseView 等）
- 不动 service 层
- 不动 watch activeTab 联动（loadChunks / loadKg 仍是手写）
- 不动 `onUnmounted` 清理（Vue Query 自动管理）
- 不动 `chunks` / `kgNodes` / `kgEdges` ref（本轮保留）

## 设计要点

### 1. `useFileTasksQuery` 的轮询条件

```typescript
function useFileTasksQuery(
  fileId: Ref<string>,
  polling: Ref<boolean>,
): UseQueryReturnType<TaskDTO[], Error> {
  return useQuery({
    queryKey: computed(() => fileKeys.tasks(fileId.value)),
    queryFn: () => documentApi.listTasks(fileId.value).then((r) => r.data),
    enabled: computed(() => !!fileId.value),
    refetchInterval: computed(() => (polling.value ? 3000 : false)),
  });
}
```

### 2. polling 由 query data 派生

```typescript
const tasksQuery = useFileTasksQuery(
  fileId,
  computed(() =>
    (tasksQuery.data.value ?? []).some(
      (t) => t.status === "running" || t.status === "pending",
    ),
  ),
);
const tasks = computed<TaskDTO[]>(() => tasksQuery.data.value ?? []);
const polling = computed(() =>
  tasks.value.some((t) => t.status === "running" || t.status === "pending"),
);
```

### 3. 任务全部完成时 refresh 其他手写资源

旧实现在 `setInterval` 触发时：先 `loadTasks()`；如果 `polling === false`
（任务全部完成），再 `loadFile + loadChunks + loadKg` 并停止。

新实现：用 `watch(polling, ...)` 监听 `polling` 由 true → false 的一次性
转换：

```typescript
watch(polling, (now, prev) => {
  if (prev && !now) {
    // Tasks just finished — refresh file data + tabs.
    void loadFile();
    if (activeTab.value === "chunks") void loadChunks();
    if (activeTab.value === "kg") void loadKg();
  }
});
```

不直接调用 `tasksQuery.refetch()`，因为它会触发另一次 queryFn 执行；
我们想要的是"任务完成后的额外数据刷新"，所以走 `loadFile + loadChunks +
loadKg` 路径。

### 4. Mutation 模式

```typescript
const retryMutation = useRetryTasksMutation(fileId, () => {
  toast.success("已重新提交任务");
});

const reinitializeMutation = useReinitializeFileMutation(fileId, () => {
  toast.success("已开始重新初始化");
  // 清空旧 chunks / kg 数据（与旧实现一致）
  chunks.value = [];
  kgNodes.value = [];
  kgEdges.value = [];
});

const deleteMutation = useDeleteFileMutation(fileId, () => {
  toast.success("文件已删除");
  router.push("/resource");
});
```

调用点：`<button @click="retryMutation.mutate()">` 等。

### 5. `onMounted` 改动

旧：
```typescript
onMounted(async () => {
  await Promise.all([loadFile(), loadTasks(), loadTemplates()]);
  startPolling();
});
```

新：
```typescript
onMounted(async () => {
  await Promise.all([loadFile(), loadTemplates()]);
  // tasksQuery 自动触发（useQuery 启用条件为 !!fileId）
});
```

`onUnmounted(() => stopPolling())` 整段删除（Vue Query 自动清理）。

### 6. 测试策略

由于 web 包目前没有 vitest 配置（TD-015 验证时确认过），本轮不补单元测试。
**TD-017 验证**：
- typecheck / build / lint 全部退出码 0
- 行为等价矩阵覆盖完成标准
- PR 描述显式声明行为不变

### 7. 行为不变声明

按 `quality-gates.md#行为变化声明检查`：

| 类别 | 是否变化 | 说明 |
|------|----------|------|
| 轮询时机 | 不变 | 仍按 3s 间隔；`polling === true` 时启用，否则停止 |
| 轮询停止时机 | 不变 | 任务全部完成（无 running/pending）后停止 |
| 任务完成时 refresh | 不变 | polling 由 true→false 时仍调 `loadFile + loadChunks + loadKg` |
| mutation 行为 | 不变 | retry / reinitialize / delete 的成功 toast + 后置动作（清空 chunks/kg、跳转路由）保留 |
| 错误 toast | 不变 | 由 `QueryCache.onError` 统一；具体文案从 `toast.error("...")` 改为 query error message 兜底 |
| 加载状态 | 不变 | `loadingTasks` 改由 `tasksQuery.isFetching` 派生 |
| import 副作用 | 变化 | 新增 `useFileTasksQuery` 等；删除 `pollTimer` / `startPolling` / `stopPolling` |

可观察行为：轮询 / refresh / 三个 mutation / toast 全部保留。

## 完成标准

1. `queries.ts` 新增并导出 4 个 hook（1 query + 3 mutation）
2. `FileDetailView.vue` 重构：删除 `tasks` / `loadingTasks` / `loadTasks` /
   `pollTimer` / `startPolling` / `stopPolling` / 3 个手写 mutation 函数
3. 行为等价矩阵覆盖轮询 / mutation / refresh / loading 6 个维度
4. `pnpm --filter @metaedu/web typecheck` / `lint` / `build` 退出码 0
5. PR 描述明确声明行为不变（5 类已声明）
6. 提交信息遵循 Conventional Commits：
   `refactor(web): TD-017 migrate FileDetailView tasks/mutation to Vue Query`

## 验证方式

按 `quality-gates.md#验证矩阵`：

```bash
cd packages/web
pnpm --filter @metaedu/web typecheck
pnpm --filter @metaedu/web build
pnpm --filter @metaedu/web lint
```

按 `quality-gates.md#行为变化声明检查` 显式声明：
> 本次重构以把 FileDetailView 的 `loadTasks` + 3 个 mutation 迁到 Vue Query
> 为主，**用户可见行为不变**：轮询时机、轮询停止条件、任务完成时 refresh
> 其他资源、3 个 mutation 的成功 toast 和后置动作全部保留。错误文案从
> 「固定字符串」改为「query error message 兜底」是边缘可见变化（更精确）。

## 风险与后续

- 风险：`polling` 由 query data 派生，循环依赖靠 `useQuery` 的 `refetchInterval`
  接受 `RefOrGetter` 而非 reactive ref 来化解；template 端 `polling` computed
  是同一个 `tasksQuery.data.value` 派生。
- 风险：watch `polling` 的转换时机，依赖 query data 实际 fetch 完成；如果
  query 因网络错误未拿到 data，可能不会触发 refresh。其他 view 同样会受影响。
- 后续：FileDetailView 的 `loadChunks` / `loadKg` / `loadFile` 仍手写，可作为
  下一轮 follow-up。

## 任务卡片字段

完成后需在 `current-work.md` 把 TD-017 移到「最近完成」并记录 PR 链接，
同时在 `technical-debt.md#td-017-将-vue-query-请求生命周期治理推广到-filedetailview`
的备注中追加完成日期、提交信息和验证结果。
