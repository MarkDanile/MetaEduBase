# TD-015 行为等价矩阵：DatabaseView Vue Query 迁移后回归

本矩阵覆盖 TD-007（PR #36, `350acd2`）合并后 Codex 复核发现的 4 个行为
回归，以及 TD-015 修复后的目标行为。

每行三列：
- **TD-007 前（旧实现）**：DatabaseView 手写 fetch / setInterval 时的行为
- **TD-007 后（PR #36）**：Vue Query 迁移后、TD-015 修复前的行为
- **TD-015 修复后**：本次 PR 修复后的目标行为

## 1. 上传数据集请求参数

| 关注点 | TD-007 前 | TD-007 后（PR #36） | TD-015 修复后 |
|--------|-----------|---------------------|---------------|
| `name` 来源 | `doUpload` 用 `uploadForm.value.name.trim()` 作 service 第二参（query 参数） | `useUploadDatasetMutation.mutationFn` 写死 `uploadDataset(formData, "")` | mutation 接收 `{ formData, name }`，把 `uploadForm.value.name.trim()` 透传 |
| `name` 取值 | 用户 trim 后的字符串 | 空字符串 `""` | 用户 trim 后的字符串（与旧实现一致） |
| 后端 fallback | 当 name 为空时，`router.py:101` 用 `file.filename.rsplit(".", 1)[0]` 兜底 | 永远走 fallback，丢弃用户填的名称 | 仅当用户没填才走 fallback |
| 实际可见影响 | 用户填的名称被正确保存 | 用户填的名称丢失，使用文件名 | 用户填的名称被正确保存（**恢复**） |

## 2. 任务列表轮询

| 关注点 | TD-007 前 | TD-007 后（PR #36） | TD-015 修复后 |
|--------|-----------|---------------------|---------------|
| 轮询触发条件 | `polling` computed 为 true 时（任一 task running/pending）才 `setInterval(loadTasks, 3000)` | `useDatasetTasksQuery.refetchInterval: computed(() => 3000)`，**无条件 3s 间隔** | `useDatasetTasksQuery.refetchInterval: computed(() => polling.value ? 3000 : false)` |
| 无活跃任务时 | 暂停轮询 | 仍然每 3s 请求一次 | 暂停轮询（**恢复**） |
| 实际可见影响 | 网络 / 服务端负载最小化 | 选中数据集后一直在拉 `/structured-data/datasets/{id}/tasks`，即使无任务运行 | 仅在有活跃任务时拉（**恢复**） |

## 3. KG overview 懒加载

| 关注点 | TD-007 前 | TD-007 后（PR #36） | TD-015 修复后 |
|--------|-----------|---------------------|---------------|
| 触发时机 | `toggleKgOverview` 时，如果 `kgOverviewNodes.length === 0` 才调 `loadKgOverview` | `useKgOverviewQuery()` 无 `enabled` 条件，进入页面即调用 | `useKgOverviewQuery(enabled: computed(() => showKgOverview.value))`，仅展开时才请求 |
| 实际可见影响 | 仅展开总览面板才请求 | 进入页面就请求 `/structured-data/knowledge-graph` | 仅展开面板才请求（**恢复**） |

## 4. KG overview DTO 形态

| 关注点 | TD-007 前 | TD-007 后（PR #36） | TD-015 修复后 |
|--------|-----------|---------------------|---------------|
| 类型断言 | `loadKgOverview` 显式 map：`tenant_id=""` / `parent_id=null` / `path=null` / `tags=[]` / `metadata={}` / `weight=1` | `(data.value?.nodes as unknown as KnowledgeNodeDTO[])` 用 `unknown as` 强行转换 | `kgOverviewToDto(overview)` 显式 adapter，转换逻辑与旧实现一致 |
| 字段完整性 | nodes / edges 字段完整 | 类型断言掩盖 DTO 字段差异；KGNode 缺字段被当作 KnowledgeNodeDTO 处理 | adapter 显式补齐（**恢复**） |
| 后续扩展 | 新增字段需改 adapter | 新增字段会被静默吞掉（缺字段 = undefined） | 新增字段会触发 typecheck 错误（**类型安全**） |

## 5. 其他（保持不变）

| 关注点 | 三阶段一致行为 |
|--------|-----------------|
| 列表 / 详情 / 重试 / 重新初始化 / tab 切换 loading | `query.isLoading` / `isFetching` 驱动 |
| mutation 成功 toast | `onSuccess` 回调内 `toast.success(...)` |
| 错误 toast | `QueryCache.onError` 统一 |
| cache invalidation | mutation `onSuccess` 调 `qc.invalidateQueries({ queryKey: datasetKeys.all })` |
| `useDatasetKgQuery`（单数据集）enabled 条件 | `enabled: computed(() => !!selectedId.value)`，选中数据集即拉 |
| `useDatasetRowsQuery` enabled 条件 | 同上 |

## 验证矩阵

| 验证手段 | 关注点 |
|----------|--------|
| 浏览器 DevTools Network 面板 | 上传请求携带 `?name=<用户填的名称>`；无 running/pending 任务时不发 `/tasks` 轮询；未展开 KG overview 不发 `/knowledge-graph` |
| `pnpm --filter @metaedu/web typecheck` | `unknown as` 已被删除；adapter 输出与 DTO 类型一致 |
| `pnpm --filter @metaedu/web build` | 同上 + 构建产物无回归 |
| `pnpm --filter @metaedu/web lint` | 无新增 warning |

## 不变量

- 所有用户可见的 success / error toast 文案保持与 TD-007 一致
- 数据库表 / 后端 SQL 不动
- 其他视图（FileDetailView 等）不动
- `app/shared/llm/*` 等共享模块不动
