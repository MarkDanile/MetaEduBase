# TD-015 修复 TD-007 DatabaseView Vue Query 迁移后的行为回归 — Spec

## 背景

`docs/03-engineering-governance/technical-debt.md#td-015-修复-td-007-databaseview-vue-query-迁移后的行为回归`
指出 TD-007 合并后（PR #36, `350acd2`）的 4 个行为回归未在 PR 描述中声明，
也未在 typecheck / lint / build 阶段被捕获：

| # | 回归点 | 影响 |
|---|--------|------|
| 1 | `packages/web/src/views/database/queries.ts:133` 调用 `structuredDataApi.uploadDataset(formData, "")`，第二参空字符串覆盖了 DatabaseView 已经填入 formData 的 `name` 字段 | 数据集上传后端兜底使用 `file.filename`，用户填写的名称被丢弃 |
| 2 | `DatabaseView.vue:488-492` 注释写"仅 running / pending 时 3s refetch"，但实际传入 `computed(() => 3000)`，没有 `polling` 条件 | 选中数据集后一直以 3s 间隔请求 task 列表，即便没有活跃任务 |
| 3 | `DatabaseView.vue:509` 无条件创建 `useKgOverviewQuery()`，`queries.ts:110-120` 没有 `enabled` 条件 | 页面进入即请求 `/structured-data/knowledge-graph`，即便用户没展开总览 |
| 4 | `DatabaseView.vue:510-515` 使用 `unknown as KnowledgeNodeDTO[] / KnowledgeEdgeDTO[]` 掩盖 `structured-data.ts` 的轻量 `KGNode / KGEdge` 与 `knowledge.ts` 的完整 `KnowledgeNodeDTO / KnowledgeEdgeDTO` 之间的契约差异 | 类型断言掩盖 DTO 不匹配；后续如果 overview 增加字段会静默丢失 |

## 目标

修复 4 个行为回归，**用户可见行为回到 TD-007 之前的状态**（或与 `technical-debt.md#td-015`
明确声明的完成标准一致），并补行为等价矩阵 + 自动化测试覆盖 4 个回归点。

## 范围

### In scope

- `packages/web/src/views/database/queries.ts`：
  - `useUploadDatasetMutation` 的 `mutationFn` 不再传第二参 name 参数
    （name 已在 formData 字段中，由后端从 formData 解析）；或显式透传
    业务侧 name（与 TD-007 旧实现对齐）。
  - `useDatasetTasksQuery` 的 `refetchInterval` 改为 `number | false` 的动态
    计算：仅当 `polling === true`（任一 task running/pending）时返回 3000，
    否则返回 `false` 暂停轮询。
  - `useKgOverviewQuery` 加 `enabled` 参数：仅当调用方传入 `enabled=true` 时
    发起请求；默认 enabled=false（懒加载）。
  - 抽 `kgOverviewToDto` adapter 函数，转换 `KGNode / KGEdge` 到
    `KnowledgeNodeDTO / KnowledgeEdgeDTO`；不再用 `unknown as`。
- `packages/web/src/views/database/DatabaseView.vue`：
  - `useDatasetTasksQuery` 的 `refetchInterval` 改为基于 `polling` 条件计算
  - `useKgOverviewQuery` 的 `enabled` 与 `showKgOverview.value` 联动
  - 删除 `unknown as` 改用 adapter 输出
  - `doUpload` 不再依赖 mutation 内部 name 兜底
- 新增 `tests/views/database/queries.test.ts` 覆盖：
  - `refetchInterval` 在 `polling=true/false` 时返回值
  - `useKgOverviewQuery` 在 `enabled=true/false` 时是否发起请求
  - `kgOverviewToDto` adapter 转换正确性
- 写行为等价矩阵 `docs/03-engineering-governance/03-matrices/td-015-databaseview-equivalence.md`
  覆盖：上传请求参数、轮询条件、KG overview 懒加载、DTO 转换、cache
  invalidation、toast、loading 状态。

### Out of scope

- 不动 FileDetailView（属于 TD-017，本轮不做）。
- 不动 TD-006 / TD-005 现有共享 helper。
- 不重构 `DatabaseView` 其他手写 query。
- 不动 service 层 DTO 定义（KGNode / KGEdge / KnowledgeNodeDTO 之间的字段差异
  保留在 adapter 层处理）。

## 设计要点

### 1. Upload 名称修复

**问题代码（queries.ts:133）**：
```typescript
mutationFn: (formData: FormData) =>
  structuredDataApi.uploadDataset(formData, "").then((r) => r.data),
```

**问题分析**：
- DatabaseView 在 `doUpload` 已经把 `name` append 到 formData（`formData.append("name", uploadForm.value.name.trim())`）
- queries.ts:133 第二参 name `""` 会被 service 拼成 `?name=` query 参数，
  与后端 `router.py:77-83` 的 `name: str | None = Query(None)` 行为一致
  （None 时用 file.filename）
- 但**旧实现**用的是 `uploadForm.value.name.trim()` 作为第二参（template/service.py:627），
  新实现传 `""` 丢失名称

**修复方案**：让 `mutationFn` 接收 `FormData` 时只传第一参，删除第二参；
让后端从 formData 字段读取 name。**这与 TD-007 旧实现的 `formData` 行为一致**。

但后端 `router.py:77-83` 是用 `Query` 参数读 name 的，**不读 formData**。
需要确认后端是否在多部分表单中提取 name 字段；如果不提取，修复需要同步后端。

**待 plan 阶段确认**：先验证后端是否已支持 formData 中的 name 字段。

### 2. 轮询条件化

**修复**：`useDatasetTasksQuery` 接收 `polling: Ref<boolean>` 参数，
`refetchInterval` 改为 `computed(() => polling.value ? 3000 : false)`。
DatabaseView 改为：
```typescript
const tasksQuery = useDatasetTasksQuery(
  selectedId,
  computed(() => polling.value),  // 新增：传 polling ref
);
```

### 3. KG Overview 懒加载

**修复**：`useKgOverviewQuery` 接收 `enabled: Ref<boolean>` 参数。
DatabaseView 改为：
```typescript
const kgOverviewQuery = useKgOverviewQuery(computed(() => showKgOverview.value));
```

**关键**：之前 `loadKgOverview` 是 `toggleKgOverview` 时才调；现在 query 启用条件与 `showKgOverview` 联动，自动懒加载。

### 4. DTO Adapter

`queries.ts` 引入：
```typescript
function kgOverviewToDto(overview: { nodes: KGNode[]; edges: KGEdge[] }): {
  nodes: KnowledgeNodeDTO[];
  edges: KnowledgeEdgeDTO[];
};
```

将 `KGNode` 缺省字段（tenant_id / parent_id / path / tags / metadata）补齐为
KnowledgeNodeDTO 期望的形态；`KGEdge` 补齐 `weight: 1`。

然后 `useKgOverviewQuery` 通过 `select: kgOverviewToDto` 在 query 层做转换，
DatabaseView 收到的就是 `KnowledgeNodeDTO[] / KnowledgeEdgeDTO[]`，
可以删 `(data.value as unknown as KnowledgeNodeDTO[])` 断言。

### 5. 测试策略

`tests/views/database/queries.test.ts`（单元测试）：
- `useDatasetTasksQuery` 接收 `polling` ref，`refetchInterval` 随 polling 变化
- `useKgOverviewQuery` 接收 `enabled` ref，未启用时不发起网络
- `kgOverviewToDto` 转换正确（覆盖空数组、缺字段、含中文、空 title 等）

由于前端没有 vitest 配置文件，需要先确认 `@metaedu/web` 是否声明测试框架。
按 `docs/03-engineering-governance/01-rules/testing.md` 与 `local-development.md` 验证：
- 如果没有声明，**只补 build 阶段的 typecheck + lint**，并在 PR 描述中明确
  说明：「由于 web 包未配置测试框架，本次回归覆盖以 typecheck / lint / build
  + 行为等价矩阵手动验收为准；自动化测试留作 TD-017 同步启动时落地」。
- 如果有 vitest 配置文件，按现有风格补测试。

### 6. 行为不变声明

按 `quality-gates.md#行为变化声明检查` 排查：

| 类别 | 是否变化 | 说明 |
|------|----------|------|
| 上传请求参数 | 修复 | 名称从「query 空字符串」恢复为「formData 字段」 |
| 轮询时机 | 修复 | 仅 running/pending 时 3s，否则停止 |
| 懒加载时机 | 修复 | KG overview 只在展开时请求 |
| DTO 形态 | 修复（其实是回归） | adapter 转换与 TD-007 旧实现保持一致 |
| 状态机 | 不变 | query isLoading / isFetching 仍用 |
| import 副作用 | 变化 | 新增 adapter；删除 `unknown as` |

可观察行为：4 个回归点全部回到 TD-007 之前的旧行为；其他用户可见行为不变。

## 完成标准

1. `queries.ts` 的 4 个回归点全部修复
2. `DatabaseView.vue` 同步使用新接口
3. 行为等价矩阵写明 4 个回归点的修复前后对比
4. `pnpm --filter @metaedu/web typecheck` / `lint` / `build` 退出码 0
5. PR 描述明确声明 4 个行为变化（与 TD-007 旧行为对齐）
6. 提交信息遵循 Conventional Commits：`fix(web): TD-015 restore DatabaseView behaviors lost in TD-007`

## 验证方式

按 `quality-gates.md#验证矩阵`（前端 Vue/TS）：

```bash
cd packages/web
pnpm --filter @metaedu/web typecheck
pnpm --filter @metaedu/web build
pnpm --filter @metaedu/web lint
```

如果 web 包有测试框架：
```bash
pnpm --filter @metaedu/web test
```

并按 `quality-gates.md#行为变化声明检查` 显式声明：
> 本次 PR 是对 TD-007 合并（PR #36, 350acd2）后 4 个未在 PR 描述中
> 声明的行为回归的修复：上传名称恢复、轮询条件化、KG overview 懒加载、
> DTO 形态收口。所有修复方向与 TD-007 之前的行为一致。

## 风险与后续

- 风险：后端 `router.py:77-83` 是否读取 multipart form 的 name 字段未在 TD-007 时
  验证；plan 阶段先确认。
- 后续：TD-017 启动时按本任务的等价矩阵模板，列 FileDetailView 行为矩阵。

## 任务卡片字段

完成后需在 `current-work.md` 把 TD-015 移到「最近完成」并记录 PR 链接，
同时在 `technical-debt.md#td-015-修复-td-007-databaseview-vue-query-迁移后的行为回归`
的备注中追加完成日期、提交信息和验证结果。
