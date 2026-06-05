# TD-015 修复 TD-007 DatabaseView Vue Query 迁移后的行为回归 — Plan

> **交付历史（2026-06-05）：** TD-015 已通过 PR #38（merge commit `f38fbbc`）合并到 `main`。本文保留为历史实施计划；下方清单已按最终交付状态收口，真实交付事实以 `docs/engineering/technical-debt.md#td-015-修复-td-007-databaseview-vue-query-迁移后的行为回归` 和 PR #38 为准。

## 任务入口

- Spec: `docs/specs/2026-06-05-td-015-databaseview-regressions.md`
- 技术债: `docs/engineering/technical-debt.md#td-015-修复-td-007-databaseview-vue-query-迁移后的行为回归`
- 任务卡片: `docs/engineering/current-work.md` 的 TD-015 卡片
- 当前执行模式: `manual`
- 完成后 Git 阶段: 提交 → push → PR → squash merge `main`

## 实施顺序

### 1. 修复 upload 名称丢失（回归点 1）

- [x] spec/plan 起草
- [x] 确认后端 `router.py:80` 的 `name` 是 query 参数（不是 form 字段）
- [x] 修改 `useUploadDatasetMutation` 签名：接收 `{ formData: FormData; name: string }`
- [x] mutationFn 改为 `structuredDataApi.uploadDataset(formData, name)`
- [x] 修改 `DatabaseView.vue:doUpload`：把 name 作为第二参传给 `uploadMutation.mutate({ formData, name })`

**验证点**：`rg -n "uploadDataset\(formData, \"\"\)\|uploadDataset\(formData, ''\)" packages/web/` 命中 0。

### 2. 修复轮询未条件化（回归点 2）

- [x] 修改 `useDatasetTasksQuery` 签名：增加 `polling: Ref<boolean>` 参数
- [x] `refetchInterval` 改为 `computed(() => polling.value ? 3000 : false)`
- [x] 修改 `DatabaseView.vue`：传 `polling` ref（已有的 `polling` computed）

**验证点**：typecheck 通过；`polling` 计算在无任务运行时不再触发 3s 间隔。

### 3. 修复 KG overview 不懒加载（回归点 3）

- [x] 修改 `useKgOverviewQuery` 签名：增加 `enabled: Ref<boolean>` 参数
- [x] `enabled: enabled` 透传给 useQuery
- [x] 修改 `DatabaseView.vue`：传 `computed(() => showKgOverview.value)`

**验证点**：typecheck 通过；`showKgOverview.value === false` 时不发请求。

### 4. 用 DTO adapter 替换 `unknown as`（回归点 4）

- [x] 在 `queries.ts` 加 `kgOverviewToDto(overview)` 函数
- [x] 字段映射（参考原 `loadKgOverview` 旧实现的 580-593 行）：
  - nodes: id / tenant_id="" / title / description / domain / level /
    parent_id=null / path=null / tags=[] / metadata={}
  - edges: id / source_id / target_id / relation_type / weight=1 /
    metadata=raw ?? {}
- [x] `useKgOverviewQuery` 加 `select: kgOverviewToDto` 选项
- [x] 修改 `DatabaseView.vue`：删除 `as unknown as KnowledgeNodeDTO[]`

**验证点**：typecheck 通过；`rg -n "unknown as Knowledge" packages/web/src/views/database/` 命中 0。

### 5. 写行为等价矩阵

- [x] 新增 `docs/engineering/matrices/td-015-databaseview-equivalence.md`
- [x] 矩阵覆盖：上传请求参数 / 轮询条件 / KG overview 懒加载 / DTO 转换
- [x] 每格列「TD-007 前 / TD-007 后（PR #36） / TD-015 修复后」

### 6. 验证

- [x] `cd packages/web && pnpm --filter @metaedu/web typecheck` 退出码 0
- [x] `cd packages/web && pnpm --filter @metaedu/web build` 退出码 0
- [x] `cd packages/web && pnpm --filter @metaedu/web lint` 退出码 0

### 7. Git 闭环

- [x] 分支：`git checkout -b fix/td-015-databaseview-regressions`
- [x] 提交：`fix(web): TD-015 restore DatabaseView behaviors lost in TD-007`
- [x] push：`git push -u origin fix/td-015-databaseview-regressions`
- [x] PR：`gh pr create ...` Summary / Scope / Validation / Risks / Docs
- [x] 检查 `gh pr checks` 通过
- [x] squash merge：`gh pr merge --squash --delete-branch`
- [x] 回填 `current-work.md` 最近完成 + `technical-debt.md` 备注 + `work-log.md` 索引

## 任务拆分

1. spec/plan 起草（已完成）
2. 修 upload 名称
3. 修轮询条件
4. 修 KG overview 懒加载
5. 加 DTO adapter
6. 写行为等价矩阵
7. 跑前端 typecheck / build / lint
8. 走完整 Git 流程
9. 回填三处任务事实源

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 后端 `name` 是 query 参数，前端 formData 字段会被忽略 | mutation 显式把 name 作为 query 参数透传 |
| `polling` 改为 ref 后，watch 内 tasks 状态变化时轮询启动/停止时机 | useQuery 的 `refetchInterval` 是 reactive computed，会自动响应 |
| `enabled` 改为 ref 后，未启用时 query 仍可能因为 queryKey 复用触发 | useQuery v5 的 `enabled=false` 不会发起请求；但 queryKey 仍要稳定 |
| DTO adapter 字段映射与 `loadKgOverview` 旧实现 580-593 行不完全一致 | 按旧实现逐字段映射，并写等价矩阵对照 |

## 提交前最终回查

- `current-work.md` 状态与代码实际一致
- `technical-debt.md` 状态与代码实际一致
- 验证结果来自真实命令输出
- 4 个回归点全部在 PR 描述中显式声明
- 行为等价矩阵完整覆盖完成标准
- PR 范围只包含本任务文件
