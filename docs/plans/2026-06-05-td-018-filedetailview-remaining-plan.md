# TD-018 FileDetailView 剩余手写 load 迁到 Vue Query — Plan

> 交付历史（2026-06-05）：TD-018 已通过 PR #41 合并到 `main`，merge commit `8ad15e6`。本文保留为历史实施计划；下方清单已按最终交付状态收口，真实交付事实以 `docs/engineering/technical-debt.md#td-018-filedetailview-剩余手写-load-迁到-vue-query` 和 PR #41 为准。TD-018 后续暴露的 Vue Query 自引用问题已由 TD-019 / PR #42 修复。

## 任务入口

- Spec: `docs/specs/2026-06-05-td-018-filedetailview-remaining.md`
- 技术债: `docs/engineering/technical-debt.md#td-018-filedetailview-剩余手写-load-迁到-vue-query`
- 任务卡片: `docs/engineering/current-work.md` 的 TD-018 卡片
- 当前执行模式: `manual`
- 完成后 Git 阶段: 提交 → push → PR → squash merge `main`

## 实施顺序

### 1. spec/plan/总账（已完成）

- [x] 补 TD-018 总账卡片（证据 / 完成标准 / 验证方式齐全）并推进为 🔵 就绪
- [x] spec 落盘
- [x] plan 落盘

### 2. 行为等价矩阵

- [x] 写 `docs/engineering/matrices/td-018-filedetailview-remaining-equivalence.md`
- [x] 矩阵覆盖 4 个 load × 3 阶段（手写 / TD-018 修复后）

### 3. 扩展 `packages/web/src/views/resource/queries.ts`

- [x] 扩展 `fileKeys`：增加 `detail / chunks / kg`；新增顶层 `templates` key
- [x] 新增 `useFileQuery(fileId)`：GET file detail
- [x] 新增 `useFileChunksQuery(fileId, enabled)`：GET chunks（懒加载）
- [x] 新增 `useFileKgQuery(fileId, enabled)`：并行 GET listNodes + listEdges
- [x] 新增 `useTemplatesQuery()`：GET templates（catch 返回 `[]` 保持静默失败）

**验证点**：模块可被 `FileDetailView.vue` import；typecheck 通过。

### 4. 重构 `FileDetailView.vue`

- [x] 删除 4 个手写 load 函数
- [x] 删除 3 个 `loading*` ref
- [x] 引入 4 个 query hook 替换
- [x] 模板里 3 个 `<LoadingSpinner>` 改用 query.isFetching
- [x] `refreshAll` 改用 `query.refetch()`
- [x] `watch(activeTab)` 改由 query enabled 自动触发 refetch
- [x] `watch(polling)` 由 true→false 改用 `query.refetch()`
- [x] 原计划保留并简化 `onMounted`；最终实现删除 `onMounted`，由 useQuery 自动触发，详见 TD-018 交付备注

**验证点**：`rg -n "loadFile|loadChunks|loadKg|loadTemplates" packages/web/src/views/resource/FileDetailView.vue` 命中 0 行（import 之外）。

### 5. 验证

- [x] `pnpm --filter @metaedu/web typecheck` 退出码 0
- [x] `pnpm --filter @metaedu/web build` 退出码 0
- [x] `pnpm --filter @metaedu/web lint` 退出码 0

### 6. Git 闭环

- [x] 分支：`refactor/td-018-filedetailview-remaining`
- [x] 提交：`refactor(web): TD-018 migrate FileDetailView remaining loads to Vue Query`
- [x] push：`git push -u origin refactor/td-018-filedetailview-remaining`
- [x] PR：#41，包含 Summary / Scope / Validation / Risks / Docs
- [x] 检查 `gh pr checks` 通过
- [x] squash merge：PR #41 合并到 `main`
- [x] 回填 `current-work.md` 最近完成 + `technical-debt.md` 备注 + `work-log.md` 索引

## 任务拆分

1. spec/plan/总账（已完成）
2. 写行为等价矩阵
3. 扩展 queries.ts
4. 重构 FileDetailView.vue
5. 跑前端 typecheck / build / lint
6. 走完整 Git 流程
7. 回填三处任务事实源

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| `useTemplatesQuery` 静默失败被 queryCache 错误机制吞掉但仍触发 QueryCache.onError toast | queryFn 内 catch 返回 `[]`（方案 B） |
| `watch(activeTab)` 改写后，模板切换时数据 refetch 顺序 | 与旧实现保持一致：`if/else` 三个 tab |
| 模板里 `v-if="loading"` 引用删除的 ref | typecheck 阶段捕获；spec/plan 已枚举 |
| `polling` 由 true→false 时 refetch 顺序 | 与旧实现一致：`fileQuery` 无条件 + chunks/kg 按 activeTab |

## 提交前最终回查

- `current-work.md` 状态与代码实际一致
- `technical-debt.md` 状态与代码实际一致
- 验证结果来自真实命令输出
- 业务行为不变声明已写到 PR 描述
- PR 范围只包含本任务文件
- 不混入其他视图或 service 文件改动
