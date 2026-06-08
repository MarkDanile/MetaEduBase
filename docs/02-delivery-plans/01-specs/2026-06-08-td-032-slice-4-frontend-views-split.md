# TD-032 切片 4 拆分 `DatabaseView.vue`（701 行）+ `TemplateModal.vue`（665 行）— Spec

## 背景

`docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` 把两个前端视图登记为「⚪ 待切片」：

- `packages/web/src/views/database/DatabaseView.vue` 701 行（数据集列表 + KG 总览 + 详情 + Tabs + 上传对话框 + 2 个 ConfirmDialog + 2 个 KGDetailPanel）
- `packages/web/src/views/admin/TemplateModal.vue` 665 行（dialog 壳 + 表单字段编辑 + AI 辅助面板 + 全部 scoped 样式）

切片 1（[PR #92](https://github.com/MarkDanile/MetaEduBase/pull/92) / merge `3de4de5`）、切片 2（[PR #93](https://github.com/MarkDanile/MetaEduBase/pull/93) / merge `7e468fb`）、切片 3（[PR #94](https://github.com/MarkDanile/MetaEduBase/pull/94) / merge `5beb938`）按计划完成。切片 4 是 TD-032 计划（[2026-06-08-td-032-large-source-files-plan.md#切片-4](../02-plans/2026-06-08-td-032-large-source-files-plan.md)）的下一个目标。

**重要前置**：
- `DatabaseView.vue` 仅 `packages/web/src/app/router.ts:37` 一处 `import`（lazy import）；保持入口文件名 `@/views/database/DatabaseView.vue` 不变。
- `TemplateModal.vue` 是 `packages/web/src/views/admin/TemplateListView.vue:71, 95` 显式 `<TemplateModal>` + `import TemplateModal from './TemplateModal.vue'`；**保持入口文件名 `views/admin/TemplateModal.vue` 不变**（这是切片 4 唯一硬约束）。
- TD-008 / TD-025 / TD-027 / TD-028 已把 `liquid-*` 容器迁到 `ui-panel` / `ui-btn-*` / `ui-input` / `ui-tag-*` / `ui-dialog*`；本次切片 4 复用 `ui-*` 共享类与 `PageHeader` / `EmptyState` / `LoadingSpinner` / `ConfirmDialog` / `KGGraph` / `KGDetailPanel` 共享组件。
- 不动 `coding-style.md` / `tailwind.config` / `main.css` 等基础样式。

## 目标

1. 把 `DatabaseView.vue` 701 行拆为：主入口 `DatabaseView.vue`（**目标 ≤500 行**，只做 PageHeader + 6 个子组件编排 + 3 个对话框 + 顶层 state）+ 6 个聚焦子组件（每个 ≤200 行）。
2. 把 `TemplateModal.vue` 665 行拆为：主入口 `TemplateModal.vue`（**目标 ≤500 行**，只做 dialog 壳 + 2 个子组件编排 + 顶层 state + scoped dialog 壳样式）+ 2 个聚焦子组件（每个 ≤150 行）。
3. **零业务行为变化**：所有用户可见交互（点击 / 输入 / 拖拽 / 异步 mutation / 路由导航 / 主题色 / 装饰动效）byte-equivalent。
4. **保持外部 import 路径不变**：`router.ts` 的 `import("@/views/database/DatabaseView.vue")` 仍解析；`TemplateListView.vue` 的 `import TemplateModal from './TemplateModal.vue'` 仍解析。
5. **保持 `@/views/database/queries.ts` 不动**：9 个 `use*Query` / `use*Mutation` 函数对外 API 字节不变，DBView 内部引用方式不变（避免切片 4 与 TD-007 既有契约再耦合）。

## 范围

### In scope

- 新建 `packages/web/src/views/database/` 下 6 个子组件：
  - `DatasetListPanel.vue`（~90 行）：左侧 260px 数据集列表面板（折叠 / 排序 / 列表 / KG 总览按钮）。
  - `KgOverviewPanel.vue`（~40 行）：右侧 KG 总览模式容器（标题 + 重新生成按钮 + 加载 / 空态 / KGGraph）。
  - `DatasetDetailMetaBar.vue`（~30 行）：数据集详情 meta bar（名称 / 行/列 / tags / 删除 / 重新初始化按钮）。
  - `PipelineStatusPanel.vue`（~40 行）：处理流水线 6 步状态面板（步骤进度 + 状态 + 重试按钮）。
  - `DatasetTabsPanel.vue`（~100 行）：Tabs 容器（2 个 tab 块：数据预览 + KG（本表））。
  - `UploadDatasetDialog.vue`（~60 行）：上传数据集对话框（独立 dialog，含 file input + form）。
- 精简 `DatabaseView.vue`：
  - 保留：`<script setup>` 中的 state 声明（selected / selectedKgNode / selectedOverviewKgNode / activeTab / showDelete / showUpload / showKgOverview / showKgRebuildConfirm / datasetListCollapsed / offset / sortBy / sortDir / uploadForm / fileInputRef）+ 9 个 Vue Query 编排（datasetsQuery / tasksQuery / rowsQuery / kgQuery / kgOverviewQuery / 5 个 mutation）+ watch（auto-reload on task success）+ 编排函数（selectDataset / changePage / triggerFileInput / handleFileChange / doUpload / doDelete / retryTasks / reinitialize / doRebuildKg / toggleKgOverview）。
  - 删除：模板中左侧 / 右侧各子块、`<script setup>` 中 `dsStatusLabel` / `dsStatusTagClass` / `formatCell` / `stepStatus` / `stepProgress` / `stepStatusLabel` / `stepIcon` / `stepBgClass` / `stepLabelClass` 等子组件内部 helper。
- 新建 `packages/web/src/views/admin/` 下 2 个子组件：
  - `TemplateFormFields.vue`（~100 行）：左侧表单（名称 / 关联文档类型 / 字段列表 + FieldItem 转发）。
  - `TemplateAiPanel.vue`（~85 行）：右侧 AI 辅助配置面板（文档类型名 / 文件上传 / 补充说明 / 生成按钮 / 警告）。
- 精简 `TemplateModal.vue`：
  - 保留：dialog 壳（Teleport + overlay + header + footer）+ `<script setup>` 中的 state（form / docTypeInput / typeWarning / aiDocType / uploadFile / fileInputRef / uploading / generating / saving / aiGenerated）+ 编排函数（handleClose / handleSave）+ watch（resetForm when open / auto-fill AI doc type）。
  - 删除：模板中左侧 / 右侧子块、`<script setup>` 中 `ensureIds` / `countFields` / `findNode` / `removeNode` / `addDocType` / `removeDocType` / `checkDocTypeDuplicate` / `handleFileSelect` / `regenerateAI` 等子组件内部 helper。
  - 保留：`<style scoped>` 中 dialog 壳专用样式（modal-overlay / modal / modal-header / modal-close-btn / modal-body / modal-footer / field-label / ai-panel / ai-generated-banner / manual-add-btn / field-empty-state / empty-add-btn / ai-panel-accent）。
- 任务卡 `docs/03-engineering-governance/current-work.md` 同步刷新。
- spec / plan 落仓。

### Out of scope

- 不动 `app/router.ts`（DatabaseView 路径保持 `@/views/database/DatabaseView.vue`）。
- 不动 `views/admin/TemplateListView.vue` 的 `import TemplateModal from './TemplateModal.vue'`。
- 不动 `views/database/queries.ts`（9 个 Vue Query composable 既有契约）。
- 不动任何共享组件（`PageHeader` / `EmptyState` / `LoadingSpinner` / `ConfirmDialog` / `KGGraph` / `KGDetailPanel` / `FieldItem`）。
- 不动 `app/contexts/document/application/tasks/extract_template.py` 等后端代码。
- 不动 `main.css` / `coding-style.md` / 任何 CSS / Tailwind 配置。
- 不动 `tests/`——本次只验证既有 `pnpm typecheck / lint / build` 通过；不补新测试（切片 4 性质是"抽子组件 + 行为零变化"，无新行为需要测试）。
- 不引入新依赖。

## 设计要点

### 1. `DatabaseView.vue` 拆分后的拓扑

```
packages/web/src/views/database/
├── DatabaseView.vue              # 主入口: 顶层 state + 9 个 Vue Query 编排 + 编排函数
├── queries.ts                    # 9 个 composable (TD-007 既有产物, 不动)
├── DatasetListPanel.vue          # 左侧 260px 面板
├── KgOverviewPanel.vue           # 右侧 KG 总览模式
├── DatasetDetailMetaBar.vue      # 右侧 meta bar
├── PipelineStatusPanel.vue       # 右侧 pipeline 状态
├── DatasetTabsPanel.vue          # 右侧 tabs 容器
└── UploadDatasetDialog.vue       # 上传对话框
```

子组件 API（props / emits 全 v-model 友好，父级 state 仍为唯一来源）：

| 子组件 | Props | Emits |
|--------|-------|-------|
| `DatasetListPanel` | `datasets: DatasetDTO[]`, `loading: boolean`, `selectedId: string \| null`, `showKgOverview: boolean`, `sortBy: string`, `sortDir: string` | `select: (ds: DatasetDTO) => void`, `toggle-sort: (by: string) => void`, `toggle-sort-dir: () => void`, `toggle-collapse: () => void`, `toggle-kg-overview: () => void` |
| `KgOverviewPanel` | `nodes: KnowledgeNodeDTO[]`, `edges: KnowledgeEdgeDTO[]`, `loading: boolean`, `rebuilding: boolean` | `rebuild: () => void`, `node-click: (node: KnowledgeNodeDTO) => void` |
| `DatasetDetailMetaBar` | `selected: DatasetDTO \| null` | `delete: () => void`, `reinitialize: () => void` |
| `PipelineStatusPanel` | `tasks: TaskDTO[]`, `polling: boolean`, `loading: boolean` | `retry: () => void`, `refresh: () => void` |
| `DatasetTabsPanel` | `selected: DatasetDTO \| null`, `rows: ...[]`, `kgNodes: ...[]`, `kgEdges: ...[]`, `totalRows: number`, `offset: number`, `pageSize: number`, `loadingRows: boolean`, `loadingKg: boolean`, `activeTab: string` | `update:activeTab: (key: string) => void`, `change-page: (delta: number) => void`, `node-click: (node: KnowledgeNodeDTO) => void` |
| `UploadDatasetDialog` | `open: boolean`, `form: {...}`, `uploading: boolean` | `update:open: (val: boolean) => void`, `upload: () => void`, `pick-file: () => void`, `file-change: (e: Event) => void` |

子组件内部 helper（`dsStatusLabel` / `dsStatusTagClass` / `formatCell` / `stepStatus` / `stepProgress` / `stepStatusLabel` / `stepIcon` / `stepBgClass` / `stepLabelClass`）迁到对应子文件内部 module-level 私有函数（不导出）。

### 2. `TemplateModal.vue` 拆分后的拓扑

```
packages/web/src/views/admin/
├── TemplateModal.vue              # 主入口: dialog 壳 + footer + 顶层 state + 编排 + scoped 壳样式
├── TemplateFormFields.vue         # 左侧表单 (名称 / doc_types / fields)
├── TemplateAiPanel.vue            # 右侧 AI 面板
├── FieldItem.vue                  # 既有子组件, 不动
├── ...                            # 其他 admin 视图
```

子组件 API：

| 子组件 | Props | Emits |
|--------|-------|-------|
| `TemplateFormFields` | `form: {...}`, `aiGenerated: boolean`, `docTypeInput: string`, `typeWarning: string` | `update:form: (form) => void`, `update:docTypeInput: (val: string) => void`, `update:typeWarning: (val: string) => void`, `add-doc-type`, `remove-doc-type: (dt: string) => void`, `check-duplicate`, `add-root-field`, `add-child-field: (id: string) => void`, `add-column-field: (id: string) => void`, `remove-field: (id: string) => void`, `remove-column-field: (payload: {id: string, index: number}) => void`, `sync-fields`, `field-add-root` 等 (FieldItem 事件转发) |
| `TemplateAiPanel` | `form: {...}`, `aiDocType: string`, `uploadFile: File \| null`, `uploading: boolean`, `generating: boolean`, `isEdit: boolean` | `update:aiDocType: (val: string) => void`, `update:form: (form) => void`, `update:uploadFile: (val: File \| null) => void`, `regenerate`, `file-select: (e: Event) => void`, `clear-file` |

子组件内部 helper（`ensureIds` / `countFields` / `findNode` / `removeNode` / `addDocType` / `removeDocType` / `checkDocTypeDuplicate` / `handleFileSelect` / `regenerateAI`）迁到对应子文件内部 module-level 私有函数（不导出）；文件上传与 AI 生成两个**异步** helper 留在子组件内。

### 3. 行为不变的具体边界

- 所有 `ui-btn-primary` / `ui-btn-ghost` / `ui-input` / `ui-tag-*` / `ui-panel` / `ui-dialog*` / `liquid-rise-*` / `animate-slide-up` / `stagger-N` 类名保持原值。
- 所有 `var(--color-*)` / `var(--text-*)` / `var(--spacing-*)` / `var(--z-*)` token 引用保持原值。
- 所有 `lucide-vue-next` 图标 import 保持原值（在子组件文件中按需 import）。
- 所有 `toast.success(...)` / `toast.error(...)` 文案保持原值。
- 4 主题（liquid / ink / navy / notion）下视觉表现不退化：类名 token 化保证自动适配；装饰动效（`liquid-card-scan` / `animate-slide-up` / `stagger-N` / `liquid-rise-*`）保留兼容。
- `<Teleport to="body">` / `v-model` / `defineProps` / `defineEmits` / `v-for` / `v-if` 等 Vue 特性使用方式不变。
- TypeScript 类型（`DatasetDTO` / `KnowledgeNodeDTO` / `KnowledgeEdgeDTO` / `TaskDTO` / `Template` / `Field`）保持原值；子组件 props / emits 必须使用同一类型。
- 路由懒加载：DatabaseView 仍 `() => import("@/views/database/DatabaseView.vue")`（保持字符串路径）。

### 4. 行数目标

- `DatabaseView.vue`：目标 ≤500 行（实际预计 ~350 行：模板 ~50 行 + `<script setup>` ~200 行 + scoped 样式 ~0 行——DatabaseView 自身没有 scoped 样式）。
- 6 个子组件：每个 ≤200 行。
- `TemplateModal.vue`：目标 ≤500 行（实际预计 ~300 行：模板 ~50 行 + `<script setup>` ~120 行 + `<style>` ~130 行 dialog 壳样式）。
- 2 个子组件：每个 ≤150 行。

## 完成标准

1. `DatabaseView.vue` ≤500 行；6 个子组件就位，每个 ≤200 行。
2. `TemplateModal.vue` ≤500 行；2 个子组件就位，每个 ≤150 行。
3. `app/router.ts:37` 的 `import("@/views/database/DatabaseView.vue")` 仍解析；`views/admin/TemplateListView.vue:71, 95` 的 `<TemplateModal>` + `import` 仍工作。
4. `views/database/queries.ts` 9 个 composable 不动。
5. 既有共享组件 import / props 不动：`PageHeader` / `EmptyState` / `LoadingSpinner` / `ConfirmDialog` / `KGGraph` / `KGDetailPanel` / `FieldItem`。
6. `cd packages/web && pnpm typecheck` 退出码 0。
7. `cd packages/web && pnpm lint` 退出码 0 且无新增 warning。
8. `cd packages/web && pnpm build` 退出码 0。
9. `git diff --name-status` 仅包含 `views/database/` 与 `views/admin/` 下文件 + spec/plan/current-work.md；无业务代码改动（queries.ts / router.ts / 共享组件 / 全部不受影响）。

## 验证方式

按 `docs/03-engineering-governance/01-rules/quality-gates.md#验证矩阵` 选前端 Vue/TS 行：

```bash
# 行为基线
cd packages/web
pnpm typecheck
pnpm lint
pnpm build

# 视觉对照（4 主题）
./dev.sh frontend
# 浏览器手动验收: 切换 liquid / ink / navy / notion 主题,
# 验收 /admin 模板编辑 (含 AI 辅助生成) 与 /admin 列表,
# 验收 /datasets (含上传 / 解析 / 抽 KG / 跨数据集关系).
# 沙箱无浏览器时降级为 typecheck + lint + build + git diff 自检.
```

按 `quality-gates.md#前端请求生命周期等价矩阵` 显式声明：本次为"抽子组件"重构，**不改变**请求生命周期——所有 5 个 GET / 5 个 mutation 仍由 `views/database/queries.ts` 的 9 个 composable 持有；模板内 `refetch` / `isPending` / `data` 引用方式不变（仅从 `<script setup>` 顶层迁到子组件 props）。

按 `quality-gates.md#行为变化声明检查` 显式声明：

> 本次为纯重构（抽 Vue 子组件 + 子组件私有 helper 迁移）。所有用户可见交互（点击 / 输入 / 拖拽 / 异步 mutation / 路由导航 / 主题色 / 装饰动效）byte-equivalent。
> 所有 `ui-*` 共享类、`var(--*)` token、`lucide-vue-next` 图标 import、`toast.success/error` 文案、4 主题（liquid / ink / navy / notion）视觉表现、TypeScript 类型（`DatasetDTO` / `KnowledgeNodeDTO` / `KnowledgeEdgeDTO` / `TaskDTO` / `Template` / `Field`）保持原值。
> 唯一可见变化：`DatabaseView.vue` 701 → 目标 ≤500 行；`TemplateModal.vue` 665 → 目标 ≤500 行；主入口文件 + 8 个新聚焦子组件就位。

## 风险与后续

- **风险 1**：6 + 2 = 8 个新子组件的 props / emits 设计如果过粗，会让父组件仍需在子组件树间传递多个 ref；过细则子组件复用度低。缓解：spec §1 §2 已用表格明确每个子组件的 props / emits；plan §实施步骤 §3 实施时按表格逐字段核对。
- **风险 2**：`DatasetTabsPanel` 接收 11 个 props（selected / rows / kgNodes / kgEdges / totalRows / offset / pageSize / loadingRows / loadingKg / activeTab + emit update:activeTab / change-page / node-click）；属于"违反单一职责但保持数据流单向"的妥协方案。后续若 tabs 内容继续增长，可拆 `DatasetPreviewTab` + `DatasetKgTab`（属于切片 5+ 范围）。
- **风险 3**：`TemplateAiPanel` 的 5 个 helper（`handleFileSelect` / `regenerateAI` / `addDocType` / `removeDocType` / `checkDocTypeDuplicate`）是异步 + 副作用密集型 helper；保持 module-level 私有函数而非子组件内部 setup 函数。`regenerateAI` 需要 `toast` + `templateApi` + `documentApi`，**不**抽到独立 helper 模块（避免循环 import）。
- **风险 4**：沙箱无浏览器，4 主题视觉对照只能 typecheck + lint + build + git diff 自检；按 `quality-gates.md#验证表述规范` 标"未运行 / 沙箱不可达"。`./dev.sh frontend` 浏览器验收由用户在本地接力。
- **风险 5**：DatabaseView `PipelineStatusPanel` 内部 stepIcon map（FileSpreadsheet / Cpu / GitBranch）需要 `import { Component } from "vue"` + `import { FileSpreadsheet, Cpu, GitBranch } from "lucide-vue-next"`，子组件文件需要单独 import；保持 import 顺序与原 `DatabaseView.vue` 一致。
- **后续**：切片 5+（500 附近候选 `document/router.py` 494 / `ResourceLibraryView.vue` 490 + `main.css` 1343 拆分）由后续任务独立 spec / plan。
- **后续**：TD-032 整体保持 🟡 进行中，待切片 1-4 全部交付后再改为 `🟢 完成`。

## 任务卡片字段

完成后需在 `docs/03-engineering-governance/current-work.md` 把 TD-032 任务卡「下一步」从「切片 4 单独 spec / plan」改为「切片 4 已合并；TD-032 整体收口」；`docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` 中 `DatabaseView.vue` 与 `TemplateModal.vue` 状态从 `⚪ 待切片` 改为 `🟢 已拆分` + 新行数 + 拆出去向；`docs/03-engineering-governance/technical-debt.md#td-032` 备注追加「切片 4 已合并 + TD-032 整体收口」；`docs/03-engineering-governance/work-log.md` 加一行索引。
