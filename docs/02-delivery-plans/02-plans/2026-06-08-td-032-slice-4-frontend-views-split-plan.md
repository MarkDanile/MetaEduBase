# TD-032 切片 4 拆分 `DatabaseView.vue`（701 行）+ `TemplateModal.vue`（665 行）— Plan

## 任务入口

- Spec: `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-4-frontend-views-split.md`
- 技术债: `docs/03-engineering-governance/technical-debt.md#td-032-治理超大源码文件并建立文件规模拆分原则`
- 任务卡片: `docs/03-engineering-governance/current-work.md` 的 TD-032 卡片
- 当前执行模式: `superpower`（前端视图大改 + 多子组件 + 行为等价矩阵，跨 10+ 文件需 spec 覆盖）
- 分支: `refactor/td-032-slice-4-frontend-views`（已从最新 `main` 切出）
- 完成后 Git 阶段: 提交 → push → PR → 合并 `main`（按 `docs/03-engineering-governance/01-rules/git-workflow.md#快速交付通道`）

## 实施顺序

### 1. 风险探针：6 个子组件的 props 依赖图核对

- [ ] 重新读 `DatabaseView.vue` 模板与 `<script setup>`，列出每个待拆子组件**实际引用**的 state / 函数 / 第三方 prop（不只 spec §1 的 props 表格，要确认 `useToast` / `useDatasetsQuery` / `useDatasetTasksQuery` 等 composable 在子组件内是否被调用，还是仅父级调用后通过 prop 透传）。
- [ ] 关键发现：`useToast` 仅在父级 `doUpload` / `doDelete` / `reinitialize` / `retryTasks` / `rebuildKg` 编排函数中调用 → **子组件不直接持有 toast**；通过 emit 让父级调用。
- [ ] 关键发现：所有 `use*Query` / `use*Mutation` composable 仍在父级 → **子组件不直接持有 Vue Query**；通过 props 传 `isPending` / `data` 等派生值 + emit 让父级 `mutate()`。
- [ ] 关键发现：`useDatasetTasksQuery` 的 `refetchInterval` 行为（每 3s 轮询 running/pending 任务）在 TD-007 已实现；父级保留 `tasksQuery` 引用即可，子组件通过 `tasks: TaskDTO[]` prop 接收。

**验证点**：所有 9 个 composable 调用站点仍位于 `DatabaseView.vue` `<script setup>` 顶层；子组件**不** import `@/views/database/queries`。

### 2. 按 spec §1 + §2 拆出 8 个新文件

按"DatabaseView 先、TemplateModal 后"顺序拆。**每拆一个组件，立刻跑 typecheck**，避免批量失败时难定位。

#### 2.1 DatabaseView 子组件

- [ ] **2.1.1** 写 `views/database/DatasetListPanel.vue`（~90 行）：左侧 260px 面板。`defineProps<{datasets, loading, selectedId, showKgOverview, sortBy, sortDir}>()` + 5 个 emit。内部 module-level 私有：`dsStatusLabel` / `dsStatusTagClass` + `sortOptions` 常量。
- [ ] **2.1.2** 写 `views/database/KgOverviewPanel.vue`（~40 行）：右侧 KG 总览。`defineProps<{nodes, edges, loading, rebuilding}>()` + 2 个 emit。
- [ ] **2.1.3** 写 `views/database/DatasetDetailMetaBar.vue`（~30 行）：meta bar。`defineProps<{selected: DatasetDTO | null}>()` + 2 个 emit。
- [ ] **2.1.4** 写 `views/database/PipelineStatusPanel.vue`（~40 行）：pipeline 状态。`defineProps<{tasks, polling, loading}>()` + 2 个 emit。内部 module-level 私有：`stepStatus` / `stepProgress` / `stepStatusLabel` / `stepIcon` / `stepBgClass` / `stepLabelClass` + `stepIconMap` 常量。
- [ ] **2.1.5** 写 `views/database/DatasetTabsPanel.vue`（~100 行）：tabs 容器。`defineProps<{selected, rows, kgNodes, kgEdges, totalRows, offset, pageSize, loadingRows, loadingKg, activeTab}>()` + 3 个 emit。内部 module-level 私有：`formatCell`。
- [ ] **2.1.6** 写 `views/database/UploadDatasetDialog.vue`（~60 行）：上传对话框。`defineProps<{open, form, uploading}>()` + 4 个 emit。`form` 透传（v-model 模式），子组件不持有 form 副本。

#### 2.2 TemplateModal 子组件

- [ ] **2.2.1** 写 `views/admin/TemplateFormFields.vue`（~100 行）：左侧表单。`defineProps<{form, aiGenerated, docTypeInput, typeWarning}>()` + ~10 个 emit。内部 module-level 私有：`ensureIds` / `countFields` / `findNode` / `removeNode` / `addDocType` / `removeDocType` / `checkDocTypeDuplicate` + `FieldItem` import。
- [ ] **2.2.2** 写 `views/admin/TemplateAiPanel.vue`（~85 行）：右侧 AI 面板。`defineProps<{form, aiDocType, uploadFile, uploading, generating, isEdit}>()` + 6 个 emit。内部 module-level 私有：`handleFileSelect` / `regenerateAI`。

#### 2.3 DatabaseView 主入口瘦身

- [ ] **2.3.1** 删除原模板中左侧 260px 面板（约 90 行）→ 替换为 `<DatasetListPanel ... />` 标签。
- [ ] **2.3.2** 删除 KG 总览模板块（约 30 行）→ 替换为 `<KgOverviewPanel ... />`。
- [ ] **2.3.3** 删除 meta bar 模板块（约 25 行）→ 替换为 `<DatasetDetailMetaBar ... />`。
- [ ] **2.3.4** 删除 pipeline 状态模板块（约 40 行）→ 替换为 `<PipelineStatusPanel ... />`。
- [ ] **2.3.5** 删除 tabs 内容模板块（约 100 行）→ 替换为 `<DatasetTabsPanel ... />`。
- [ ] **2.3.6** 删除 upload dialog 模板块（约 60 行）→ 替换为 `<UploadDatasetDialog ... />`。
- [ ] **2.3.7** 删除 `<script setup>` 中 9 个子组件内部 helper（`dsStatusLabel` / `dsStatusTagClass` / `formatCell` / `stepStatus` / `stepProgress` / `stepStatusLabel` / `stepIcon` / `stepBgClass` / `stepLabelClass` + `stepIconMap` 常量）。
- [ ] **2.3.8** 顶部 import 替换：删除 6 个 lucide-vue-next icon（FileSpreadsheet / Trash2 / RefreshCw / GitBranch / ChevronRight / Cpu / Clock / Type / Hash / ArrowUpNarrowWide / ArrowDownWideNarrow → 子组件按需 import）+ 6 个子组件 import + 6 个 emit 声明。

#### 2.4 TemplateModal 主入口瘦身

- [ ] **2.4.1** 删除 Body 模板中左侧表单（约 100 行）→ 替换为 `<TemplateFormFields ... />`。
- [ ] **2.4.2** 删除 Body 模板中右侧 AI 面板（约 85 行）→ 替换为 `<TemplateAiPanel ... />`。
- [ ] **2.4.3** 删除 `<script setup>` 中 8 个子组件内部 helper（`ensureIds` / `countFields` / `findNode` / `removeNode` / `addDocType` / `removeDocType` / `checkDocTypeDuplicate` / `handleFileSelect` / `regenerateAI`）。
- [ ] **2.4.4** 顶部 import 替换：删除 lucide-vue-next icon（X / Zap / Upload / AlertTriangle / Check / CheckCircle / LayoutGrid / Plus → 子组件按需 import）+ 2 个子组件 import + emit 声明。
- [ ] **2.4.5** 保留：`<style scoped>` 中 dialog 壳专用样式（modal-overlay / modal / modal-header / modal-close-btn / modal-body / modal-footer / field-label / ai-panel / ai-generated-banner / manual-add-btn / field-empty-state / empty-add-btn / ai-panel-accent）——这是 dialog 容器专用，子组件不需要。

### 3. 验证

- [ ] **3.1** 行数核对：

  ```bash
  wc -l \
    packages/web/src/views/database/DatabaseView.vue \
    packages/web/src/views/database/DatasetListPanel.vue \
    packages/web/src/views/database/KgOverviewPanel.vue \
    packages/web/src/views/database/DatasetDetailMetaBar.vue \
    packages/web/src/views/database/PipelineStatusPanel.vue \
    packages/web/src/views/database/DatasetTabsPanel.vue \
    packages/web/src/views/database/UploadDatasetDialog.vue \
    packages/web/src/views/admin/TemplateModal.vue \
    packages/web/src/views/admin/TemplateFormFields.vue \
    packages/web/src/views/admin/TemplateAiPanel.vue
  ```

  期望：DatabaseView ≤500；TemplateModal ≤500；所有子组件 ≤200 / ≤150。

- [ ] **3.2** 文档门禁：

  ```bash
  scripts/check-engineering-docs
  ```

  退出码 0。

- [ ] **3.3** 外部 import 兼容性探针：

  ```bash
  cd packages/web
  pnpm typecheck   # 含 TS 模块解析
  ```

  期望：vue-tsc 退出码 0；无新 warning。

  - 关键路径：`@/views/database/DatabaseView.vue` (router lazy import) + `TemplateModal` (TemplateListView 显式 import) 全部解析。

- [ ] **3.4** lint：

  ```bash
  cd packages/web
  pnpm lint
  ```

  退出码 0；无新增 warning（与 baseline 比较）。

- [ ] **3.5** build：

  ```bash
  cd packages/web
  pnpm build
  ```

  退出码 0；产物包含 `views/database/DatabaseView` + `views/admin/TemplateModal` chunk（与现状一致）。

- [ ] **3.6** `git diff --name-status` 仅包含：
  - `packages/web/src/views/database/{DatabaseView.vue,DatasetListPanel.vue,KgOverviewPanel.vue,DatasetDetailMetaBar.vue,PipelineStatusPanel.vue,DatasetTabsPanel.vue,UploadDatasetDialog.vue}` (1 改 6 新)
  - `packages/web/src/views/admin/{TemplateModal.vue,TemplateFormFields.vue,TemplateAiPanel.vue}` (1 改 2 新)
  - `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-4-frontend-views-split.md` (新)
  - `docs/02-delivery-plans/02-plans/2026-06-08-td-032-slice-4-frontend-views-split-plan.md` (新)
  - `docs/03-engineering-governance/current-work.md` (改)
  - 无业务代码改动（`app/router.ts` / `views/database/queries.ts` / 共享组件 / `FieldItem` 全部不动）。

- [ ] **3.7** 视觉对照（沙箱不可达 → 标"未运行"）：

  ```bash
  cd packages/web
  ./dev.sh frontend
  # 浏览器手动验收: 切换 liquid / ink / navy / notion 主题,验收 /admin 模板编辑 + /datasets。
  ```

  沙箱无浏览器时按 `quality-gates.md#验证表述规范` 标"未运行 / 沙箱不可达"；typecheck + lint + build 替代证据。

### 4. Git 闭环

- [ ] 同步 `docs/03-engineering-governance/current-work.md` 任务卡（TD-032 切片 4 收口）。
- [ ] 暂存相关文件（`git add packages/web/src/views/{database,admin}/` + `docs/02-delivery-plans/{01-specs,02-plans}/` + current-work.md）。
- [ ] 提交：`refactor(web): split DatabaseView + TemplateModal into focused child components`。
- [ ] push：`git push -u origin refactor/td-032-slice-4-frontend-views`。
- [ ] PR：`gh pr create --title "refactor(web): TD-032 slice 4 — split DatabaseView + TemplateModal" --body ...`，body 含 Summary / Scope / Validation / Risks / Docs。
- [ ] `gh pr view --json state,mergeable,reviewDecision` 确认 `MERGEABLE`；`gh pr checks` 查 CI（PR #92-94 均无 CI 配置；本仓库 gate 走本地 `scripts/check-engineering-docs` + pnpm）。
- [ ] squash merge：`gh pr merge --squash --delete-branch`。
- [ ] 合并后回写：
  - `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`：`DatabaseView.vue` 与 `TemplateModal.vue` 状态 `⚪ 待切片` → `🟢 已拆分` + 新行数 + 拆出去向。
  - `docs/03-engineering-governance/technical-debt.md#td-032`：备注追加「切片 4 已合并 + TD-032 整体收口」+ PR 链接。
  - `docs/03-engineering-governance/work-log.md`：新增 1 行索引。
  - `docs/03-engineering-governance/current-work.md`：TD-032 任务卡「下一步」改为「TD-032 整体收口；进入下一项技术债」；状态 `🟡 进行中` → `🟢 完成`。
  - 上述 docs-only 回写合并到 1 个原子 backfill commit。

## 任务拆分（按 plan-do 步骤）

1. 风险 1 探针（§1，10 分钟）
2. DatabaseView 6 个子组件（§2.1）
3. TemplateModal 2 个子组件（§2.2）
4. DatabaseView 主入口瘦身（§2.3）
5. TemplateModal 主入口瘦身（§2.4）
6. 验证（§3，typecheck + lint + build + 行数）
7. 走完整 Git 流程
8. 合并后回写 4 处 docs

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 子组件 props / emit 设计过粗，父级仍需在子组件树间传 ref | spec §1 §2 已用表格明确每个子组件的 props / emits；plan §实施步骤 §1 探针先核对依赖图 |
| 子组件的 helper 函数仍引用父级 state / 上下文（toast / query） | helper 全部 module-level 私有；子组件 emit 让父级统一调用 |
| `TemplateAiPanel` 异步 helper（`regenerateAI`）需要 `toast` + `templateApi` + `documentApi`；与父级 `useToast` 重复 | `useToast` 在子组件内独立调用（toast composable 无状态）；helper 内部独立 `toast` |
| `DatasetTabsPanel` 11 个 props 违反单一职责 | 妥协方案；后续 tabs 继续增长可拆 `DatasetPreviewTab` + `DatasetKgTab`（切片 5+ 范围） |
| 沙箱无浏览器，4 主题视觉对照只能 typecheck + lint + build | §3.7 标"未运行" + 记录原因；浏览器验收由用户在本地接力 |
| 旧 `PipelineStatusPanel` 内 `stepIconMap` 需要 import `Component` 类型 + `FileSpreadsheet` / `Cpu` / `GitBranch` icon | 子文件按需 import；保持 import 顺序与原 DatabaseView 一致 |

## 提交前最终回查（按 `docs/03-engineering-governance/task-modes.md#通用收尾回查`）

- [ ] `current-work.md` 任务卡与代码实际状态一致。
- [ ] `technical-debt.md` 任务卡状态与代码实际状态一致。
- [ ] `scripts/check-engineering-docs` 退出码 0。
- [ ] `pnpm typecheck` 退出码 0。
- [ ] `pnpm lint` 退出码 0 + 无新增 warning。
- [ ] `pnpm build` 退出码 0。
- [ ] 业务行为不变声明写到 PR 描述 + 本文件 + spec。
- [ ] 行为等价矩阵（请求生命周期 / mutation 刷新 / 错误处理）覆盖上传 / 解析 / 抽 KG / 跨数据集关系 / 模板编辑 / AI 生成。
- [ ] `git diff --name-status` 只包含本任务文件（views 包 + spec/plan + current-work）；无业务代码、无生成物。
