# TD-019 修复 Vue Query 轮询自引用导致的页面初始化运行时错误 — Spec

## 背景

`docs/03-engineering-governance/technical-debt.md#td-019-修复-vue-query-轮询自引用导致的页面初始化运行时错误`
指出 DatabaseView 和 FileDetailView 在调用任务轮询 query hook 时把刚声明的
`tasksQuery` 自身作为 refetchInterval 的 polling 数据源：

- `packages/web/src/views/database/DatabaseView.vue:488-497`：
  `useDatasetTasksQuery(selectedId, computed(() => (tasksQuery.data.value ?? []).some(...)))`
- `packages/web/src/views/resource/FileDetailView.vue:249-258`：
  `useFileTasksQuery(fileId, computed(() => (tasksQuery.data.value ?? []).some(...)))`

`pnpm --filter @metaedu/web lint` / `typecheck` / `build` 均可通过，说明现有
静态门禁没有捕获该运行时问题。最小 Vue 复现脚本输出
`ReferenceError: Cannot access 'tasksQuery' before initialization`。

该问题来自 TD-015（DatabaseView 任务轮询修复） / TD-017（FileDetailView
loadTasks + 3 mutation + 轮询） / TD-018（FileDetailView 剩余 load）这一系列
Vue Query 迁移：把"仅在存在 running/pending 任务时 3s refetch"的旧实现
翻译成 polling 条件时，直接用 `computed(() => tasksQuery.data.value...)`
作为 polling 信号。

## 根本原因

Vue Query 的 `useQuery` 在 `setup` 阶段会同步执行 `refetchInterval` 的初始化
来建立响应式追踪（建立 effect）。这个立即执行会触发传入的 `polling`
computed 被读取；`polling` 的 fn 又访问正在 `const` 声明中的 `tasksQuery`，
命中 ES `const` 临时死区（TDZ），抛 `ReferenceError: Cannot access
'tasksQuery' before initialization`。

最小复现：

```typescript
// setup 体内
const tasksQuery = useFileTasksQuery(
  fileId,
  computed(() => (tasksQuery.data.value ?? []).some(...))
)
```

- 第一次 `useFileTasksQuery` 内部建立 `refetchInterval` 的 `watchEffect`。
- `watchEffect` 立即执行 `refetchInterval.value` → 读取 `polling.value` →
  调用外部 `computed` 的 fn → 读 `tasksQuery.data.value`。
- 此时 `tasksQuery` 还在 `const` 声明初始化阶段（TDZ 中），抛 ReferenceError。
- Vue 把这个错误吞成 `[Vue warn]: Unhandled error during execution of watcher callback`，
  模板挂载和 build 仍能继续，但 polling 状态机已经损坏。

## 目标

让 `DatabaseView` / `FileDetailView` 的 query 初始化参数**不再引用正在声明的
query 变量**；轮询条件改为独立的 ref/computed 或 query 创建后的派生状态；
保留"仅存在 running/pending 任务时 3s refetch"的用户可见行为；补
smoke / mount 或运行时验证覆盖两个页面 setup，确认页面初始化不抛
ReferenceError。

## 范围

### In scope

- `packages/web/src/views/database/queries.ts`：
  - `useDatasetTasksQuery` 新增接收 polling 参数的方式不变（保留 `Ref<boolean>`）
  - 仍由调用方负责提供 polling signal
- `packages/web/src/views/database/DatabaseView.vue`：
  - 把 `tasksQuery` 拆成两步声明：先声明 `tasksQuery`（通过临时 polling
    变量），再把 polling 注入。推荐做法：使用独立的 `ref<boolean>(false)`，
    并在 `watch` 中根据 `tasksQuery.data.value` 派生更新。
  - 或：把 polling 表达式改成基于原始数据源的 ref（已在调用方收集到
    tasks via reactive store）。最简方案：**轮询由 query 内部 derive**，
    即由 `useDatasetTasksQuery` 内部根据 `data` 自驱轮询。
- `packages/web/src/views/resource/queries.ts` / `FileDetailView.vue`：同上
- 新增等价矩阵：`docs/03-engineering-governance/03-matrices/td-019-vue-query-self-reference-equivalence.md`
  覆盖 polling 计算时机、初始化顺序、watch 时序

### Out of scope

- 不动 `useFileQuery` / `useFileChunksQuery` / `useFileKgQuery` / `useTemplatesQuery`
  等无 polling 依赖的 hook
- 不动 service 层
- 不动 main.ts 的 `QueryCache.onError` 全局错误处理
- 不动其他视图

## 设计要点

### 1. 修复策略：让 query 内部从 `data` 自驱轮询

把"是否轮询"的判断从调用方（页面）下沉到 query hook 内部，基于已建立
的 `data` ref：

```typescript
function useDatasetTasksQuery(
  datasetId: Ref<string | null>,
): UseQueryReturnType<TaskDTO[], Error> {
  return useQuery({
    queryKey: computed(() => /* ... */),
    queryFn: () => /* ... */,
    enabled: computed(() => !!datasetId.value),
    // Self-driven polling: when the query has data, derive a polling signal
    // from the data itself. This avoids the page declaring a `polling`
    // computed that references the not-yet-initialized query variable.
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasActive = Array.isArray(data)
        && data.some((t) => t.status === "running" || t.status === "pending");
      return hasActive ? 3000 : false;
    },
  });
}
```

`@tanstack/vue-query` 的 `refetchInterval` 支持两种形式：
- 数字：固定间隔
- 函数 `(query) => number | false`：每次 fetch 之后被调用，函数体内
  可以读 `query.state.data`，**不依赖 setup 阶段未初始化的 ref**。

第二种形式由 Vue Query 内部在每次 fetch 完成后调用，**不参与 setup 阶段的
TDZ 同步评估**，所以可以安全读取 `query.state.data`。

DatabaseView / FileDetailView 调用方改造：

```typescript
// 旧（TDZ 风险）：
const tasksQuery = useDatasetTasksQuery(
  selectedId,
  computed(() => (tasksQuery.data.value ?? []).some(...))
)

// 新（query 内部自驱）：
const tasksQuery = useDatasetTasksQuery(selectedId)
```

### 2. `polling` ref 仍由调用方暴露给模板

DatabaseView / FileDetailView 模板中使用了 `polling` 变量（"自动刷新中..."
提示）。改造为：

```typescript
const polling = computed(() =>
  (tasksQuery.data.value ?? []).some(
    (t) => t.status === "running" || t.status === "pending",
  ),
)
```

注意：此处的 `polling` 是 `tasksQuery` 声明**之后**独立定义的 computed，
**不参与** `useDatasetTasksQuery` 的初始化参数；它依赖的 `tasksQuery` 在
自身声明前已经是初始化完成状态。JS 词法上不构成 TDZ。

### 3. `useDatasetTasksQuery` / `useFileTasksQuery` 函数签名变化

**删除** `polling: Ref<boolean>` 参数。`polling` 的判断逻辑下沉到
`refetchInterval` 函数内部，由 query 内部从 `query.state.data` 派生。

调用方调用方式从 `useDatasetTasksQuery(selectedId, pollingRef)` 改为
`useDatasetTasksQuery(selectedId)`。

### 4. 行为等价保留

| 旧实现 | 新实现 |
|--------|--------|
| 页面声明 `polling = computed(() => tasksQuery.data.value...)` 并传入 query hook | 页面不再传 polling，query hook 内部在 `refetchInterval` 回调里读 `query.state.data` |
| 3s 间隔仅在存在 running/pending 任务时启用 | 同：query 内部 `hasActive ? 3000 : false` |
| 模板 `polling` 仍由页面 computed 暴露 | 模板 `polling` 由独立 `tasksQuery` 声明之后的 computed 暴露（用户不可见差异） |

### 5. 测试策略

前端无 vitest 配置（参考 TD-015/TD-017/TD-018），本轮不补单元测试。验证：
- typecheck / build / lint 全部退出码 0
- 写一个独立 Node 脚本复现 + 修复对照（自包含在 PR 描述中）
- 行为等价矩阵覆盖 polling 计算时机、初始化顺序、watch 时序
- PR 描述显式声明行为不变

## 完成标准

1. `DatabaseView.vue` / `FileDetailView.vue` 的 `useDatasetTasksQuery` /
   `useFileTasksQuery` 调用参数中**不再引用正在声明的 `tasksQuery`**
2. `refetchInterval` 改用函数形式，由 query 内部从 `query.state.data` 派生
3. 模板 `polling` computed 仍由调用方暴露（基于 `tasksQuery.data.value`）
4. 行为等价矩阵 `docs/03-engineering-governance/03-matrices/td-019-vue-query-self-reference-equivalence.md`
   覆盖 polling 计算时机、初始化顺序、watch 时序
5. `rg -n "tasksQuery\\.data\\.value" packages/web/src/views/database/DatabaseView.vue packages/web/src/views/resource/FileDetailView.vue`
   不再命中 query hook 调用行（声明之后的 computed `polling` 是允许的）
6. `pnpm --filter @metaedu/web typecheck` / `lint` / `build` 退出码 0
7. PR 描述明确声明：用户可见行为不变；唯一行为差异是 query 内部从
   `query.state.data` 派生 polling（与旧实现语义一致）

## 验证方式

按 `docs/03-engineering-governance/01-rules/quality-gates.md#验证矩阵`：

```bash
cd packages/web
pnpm --filter @metaedu/web typecheck
pnpm --filter @metaedu/web build
pnpm --filter @metaedu/web lint
```

补充验证：
```bash
# 确认 query hook 调用行不再自引用 tasksQuery
rg -n "tasksQuery\.data\.value" packages/web/src/views/database/DatabaseView.vue packages/web/src/views/resource/FileDetailView.vue
# 只应命中声明之后的 polling computed 定义行（见"## 3. 行为等价保留"）
```

按 `quality-gates.md#前端请求生命周期等价矩阵` 覆盖：
- 请求参数：未变
- lazy-load / enabled：未变
- 轮询条件：3s / 仅 running/pending 时启用（与旧实现等价）
- mutation 刷新：未变
- UI 状态：loading / polling 提示 / 错误文案全部保留
- DTO / adapter：未变

## 风险与后续

- 风险：`@tanstack/vue-query` 5.x 的 `refetchInterval` 函数形式返回
  `false` 时确实暂停轮询；但函数本身在每次 fetch 完成后被调用，与旧
  实现"watch(polling) + refetchInterval computed"在时序上等价。
- 后续：前端 Vue Query 治理范围（DatabaseView / FileDetailView）已完成。
  任何新增 composable / query hook 都应避免"query 初始化时引用 query 自身"。

## 任务卡片字段

完成后需在 `current-work.md` 把 TD-019 移到「最近完成」并记录 PR 链接，
同时在 `technical-debt.md#td-019-修复-vue-query-轮询自引用导致的页面初始化运行时错误`
的备注中追加完成日期、提交信息和验证结果。
