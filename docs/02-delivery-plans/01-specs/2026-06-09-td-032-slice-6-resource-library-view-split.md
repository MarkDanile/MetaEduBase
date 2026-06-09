# TD-032 切片 6 拆分 `ResourceLibraryView.vue`（490 行）— Spec

## 背景

`docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` 把
`packages/web/src/views/resource/ResourceLibraryView.vue`（490 行）登记为「⚪ 待切片」，
优先级 P2。

TD-032 切片 1-5 整体收口（[PR #92](https://github.com/MarkDanile/MetaEduBase/pull/92) / `3de4de5` + [PR #93](https://github.com/MarkDanile/MetaEduBase/pull/93) / `7e468fb` + [PR #94](https://github.com/MarkDanile/MetaEduBase/pull/94) / `5beb938` + [PR #95](https://github.com/MarkDanile/MetaEduBase/pull/95) / `d4d2720` + [PR #96](https://github.com/MarkDanile/MetaEduBase/pull/96) / `4b03064`），切片 6 按 baseline 标尺"500 附近高风险候选"顺序推进，沿用切片 4
（`DatabaseView` / `TemplateModal`）**抽子组件**风格。

**重要前置**：
- `ResourceLibraryView` 仅 `packages/web/src/app/router.ts:27` 一处 `import`（lazy import）；保持入口文件名 `@/views/resource/ResourceLibraryView.vue` 不变。
- 切片 4 经验：`v-model` 改 `:value + @input` 显式 emit 链避免 prop mutation 反模式；5 处小修正需要 spec 末尾"实施记录"段显式登记。
- 切片 5 经验：`patches` 路径兼容（`patch("app.contexts.document.interfaces.api.router.parse_document")`）—— 本切片不涉及 backend，**不**适用；但**前端**也可能有同种问题：vitest / unit test 路径依赖。盘点当前 ResourceLibraryView **无 unit test**，无需此顾虑。
- TD-008 / TD-025 / TD-027 / TD-028 已把 `liquid-*` 迁到 `ui-*`；本切片复用 `ui-*` 共享类与 `PageHeader` / `EmptyState` / `LoadingSpinner` / `ConfirmDialog` 共享组件。
- 不动 `coding-style.md` / `tailwind.config` / `main.css` 等基础样式。
- 不动 `queries.ts`（resource 域无 Vue Query 编排——本视图用直接 axios 调 `documentApi`）。

## 目标

1. 把 `ResourceLibraryView.vue` 490 行拆为：主入口 `ResourceLibraryView.vue`（目标 ≤500 行）+ 3 个聚焦子组件 `FolderTreePanel.vue` / `FileListPanel.vue` / `UploadOptionsDialog.vue`（每个 ≤200 行）。
2. **零业务行为变化**：所有用户可见交互（点击 / 输入 / 拖拽 / 路由跳转 / 异步 mutation / 主题色 / 装饰动效）byte-equivalent。
3. **保持外部 import 路径不变**：`router.ts:27` 的 `import("@/views/resource/ResourceLibraryView.vue")` 仍解析。
4. **保持 `@/services/document` 不动**：`documentApi.listFolders` / `createFolder` / `updateFolder` / `deleteFolder` / `listFiles` / `uploadFile` / `deleteFile` 既有契约。
5. **不动 `app/contexts/document/interfaces/api/router.py` 与 4 个子 router 文件**（切片 5 产物）。

## 范围

### In scope

- 新建 `packages/web/src/views/resource/` 下 3 个子组件：
  - `FolderTreePanel.vue`（~110 行）：左侧 240px 面板（"全部文件" + 树状文件夹列表 + inline 新建/重命名 input + 3-dot 菜单）。
  - `FileListPanel.vue`（~95 行）：右侧上传区 + filter bar + 文件表。
  - `UploadOptionsDialog.vue`（~30 行）：上传选项对话框（复用 `ConfirmDialog` slot 模式，包含 doc_type 下拉 + tags input）。
- 精简 `ResourceLibraryView.vue`：
  - 保留：`<script setup>` 顶层 state（folders / loadingFolders / selectedFolderId / showNewFolderInput / newFolderName / activeFolderMenu / inlineRenamingFolderId / inlineRenamingName / files / loadingFiles / filterStatus / showDeleteDialog / deleteTarget / isDragging / fileInput / pendingFiles / showUploadDialog / uploadDocType / uploadTags）+ 7 个编排函数（`loadFolders` / `selectFolder` / `toggleFolderMenu` / `createFolder` / `startRenameFolder` / `commitRename` / `confirmDeleteFolder` / `doDeleteFolder` / `loadFiles` / `goToDetail` / `confirmDeleteFile` / `doDeleteFile` / `triggerUpload` / `handleFileSelect` / `handleDrop` / `doUpload`）+ `onMounted` + `flatFolders` computed + `useRouter` / `useToast`。
  - 删除：模板中左侧 240px 面板（约 108 行）+ 右侧文件表（约 87 行）+ 上传选项对话框（约 22 行）→ 替换为 3 个子组件标签。
  - 删除：模板中简单删除文件 ConfirmDialog（约 6 行）**保留**在主入口（单行 message + 单一 confirm handler，无需独立子组件）。
  - 删除：`<script setup>` 中 `formatSize` / `formatDate` / `statusLabel` / `statusTagClass` 4 个 module-level helper（迁到 `FileListPanel` 内部）。
- 任务卡 `docs/03-engineering-governance/current-work.md` 同步刷新。
- spec / plan 落仓。

### Out of scope

- 不动 `app/router.ts`（保持懒加载字符串路径）。
- 不动 `services/document.ts`（`documentApi` 既有契约）。
- 不动 `components/PageHeader` / `EmptyState` / `LoadingSpinner` / `ConfirmDialog` / `KGGraph` / `KGDetailPanel` / `FieldItem`。
- 不动后端代码（`app/contexts/document/` 任何文件、`app/shared/tasks/lifecycle.py` 等）。
- 不动 `main.css` / `coding-style.md` / 任何 CSS / Tailwind 配置。
- 不动 `tests/` —— 本次为抽子组件零行为变化，不补新测试（与切片 4 风格一致）。
- 不引入新依赖。

## 设计要点

### 1. `ResourceLibraryView.vue` 拆分后的拓扑

```
packages/web/src/views/resource/
├── ResourceLibraryView.vue       # 主入口: 顶层 state + 7 编排函数 + 3 子组件标签 + 删除文件 ConfirmDialog
├── FolderTreePanel.vue           # 左侧 240px 文件夹树面板
├── FileListPanel.vue             # 右侧上传区 + filter bar + 文件表
├── UploadOptionsDialog.vue       # 上传选项对话框（ConfirmDialog slot）
└── FileDetailView.vue            # 既有, 不动
```

子组件 API（props in, events out, 父级 state 仍为唯一来源）：

| 子组件 | Props | Emits |
|--------|-------|-------|
| `FolderTreePanel` | `folders: FolderDTO[]`, `loading: boolean`, `selectedId: string \| null`, `showNewFolderInput: boolean`, `newFolderName: string`, `activeFolderMenu: string \| null`, `inlineRenamingFolderId: string \| null`, `inlineRenamingName: string` | `select: (id: string \| null) => void`, `toggle-menu: (id: string) => void`, `start-rename: (folder?) => void`, `commit-rename: () => void`, `cancel-rename: () => void`, `confirm-delete: (folder?) => void`, `create-folder: () => void`, `toggle-new-folder: (open: boolean) => void`, `update:newFolderName: (val: string) => void`, `update:inlineRenamingName: (val: string) => void` |
| `FileListPanel` | `files: FileDTO[]`, `loading: boolean`, `isDragging: boolean`, `filterStatus: string`, `fileInputRef: Ref<HTMLInputElement \| null>` | `update:filterStatus: (val: string) => void`, `refresh: () => void`, `go-to-detail: (id: string) => void`, `confirm-delete: (file: FileDTO) => void`, `trigger-upload: () => void`, `file-change: (e: Event) => void`, `drop: (e: DragEvent) => void` |
| `UploadOptionsDialog` | `open: boolean`, `docType: string`, `tags: string` | `update:open: (val: boolean) => void`, `update:docType: (val: string) => void`, `update:tags: (val: string) => void`, `confirm: () => void` |

子组件内部 module-level 私有 helper：
- `FolderTreePanel` 不需要额外 helper（树形用 `flatFolders` computed 在父级计算后传 props）。
- `FileListPanel` 内部：`formatSize` / `formatDate` / `statusLabel` / `statusTagClass`（module-level 私有函数）。
- `UploadOptionsDialog` 不需要 helper（`DOC_TYPE_OPTIONS` 从 `@/constants/pipeline` import）。

### 2. 主入口瘦身设计

主入口保留所有 `useRouter` / `useToast` / 7 编排函数 / 19 个 ref（与原文件一致）；仅模板与子组件内部 helper 拆分。`fileInput` ref **由 `FileListPanel` 内部持有**（hidden `<input>` 在子组件模板内），父级只通过 `trigger-upload` / `file-change` / `drop` 事件协调——与切片 4 `UploadDatasetDialog` 同样的子组件 ref 模式。

### 3. 与切片 4 / slice 4 经验一致

- `v-model` 改 `:value + @input` 显式 emit 链（避免 prop mutation）。
- 私有 helper（`formatSize` / `formatDate` / `statusLabel` / `statusTagClass`）放子组件 module-level 私有函数（不抽到独立 `_helpers.ts` 子模块——与切片 4 风格一致）。
- 子组件不互相依赖。
- `v-model` 改显式 emit：例如 `filterStatus` 在 FileListPanel 模板 `v-model="filterStatus"` → 改 `:value="filterStatus" @change="emit('update:filterStatus', $event.target.value)"`。
- `DOC_TYPE_OPTIONS` 从 `@/constants/pipeline` import（与原 ResourceLibraryView 顶部 import 模式一致）。

### 4. 行数目标

- `ResourceLibraryView.vue` ≤500 行（实际预计 ~250 行：模板 ~50 行 + `<script setup>` ~200 行）。
- `FolderTreePanel.vue` ≤200 行（实际预计 ~130 行：模板 ~80 行 + `<script setup>` ~50 行）。
- `FileListPanel.vue` ≤200 行（实际预计 ~110 行：模板 ~70 行 + `<script setup>` ~40 行）。
- `UploadOptionsDialog.vue` ≤100 行（实际预计 ~50 行：模板 ~25 行 + `<script setup>` ~25 行）。

## 完成标准

1. `ResourceLibraryView.vue` ≤500 行；3 个子组件就位，每个 ≤200 行。
2. `app/router.ts:27` 的 `import("@/views/resource/ResourceLibraryView.vue")` 仍解析。
3. `services/document.ts` 9 个 `documentApi.*` 调用全部保留（不变）。
4. 既有共享组件（`PageHeader` / `EmptyState` / `LoadingSpinner` / `ConfirmDialog` / `KGGraph` / `KGDetailPanel` / `FieldItem`）不动。
5. `cd packages/web && pnpm typecheck` 退出码 0。
6. `cd packages/web && pnpm lint` 退出码 0 且无新增 warning。
7. `cd packages/web && pnpm build` 退出码 0。
8. `git diff --name-status` 仅包含 `views/resource/` 下文件 + spec/plan/current-work.md；无业务代码改动（`app/router.ts` / `services/document.ts` / 共享组件 / 后端全部不动）。

## 验证方式

按 `docs/03-engineering-governance/01-rules/quality-gates.md#验证矩阵` 选前端 Vue/TS 行：

```bash
cd packages/web
pnpm typecheck
pnpm lint
pnpm build
```

按 `quality-gates.md#前端请求生命周期等价矩阵` 显式声明：本次为"抽子组件"重构，**不改变**请求生命周期——所有 7 个 `documentApi.*` 调用（listFolders / createFolder / updateFolder / deleteFolder / listFiles / uploadFile / deleteFile）仍由 `ResourceLibraryView.vue` `<script setup>` 编排，**子组件不直接持有 axios 调用**；子组件只接收 props + emit 事件。

按 `quality-gates.md#行为变化声明检查` 显式声明：

> 本次为纯重构（抽 Vue 子组件 + 子组件私有 helper 迁移）。所有用户可见交互（点击 / 输入 / 拖拽 / 路由跳转 / 异步 mutation / 主题色 / 装饰动效）byte-equivalent。
> 所有 `ui-*` 共享类 / `var(--*)` token / `lucide-vue-next` 图标 / `toast.success/error` 文案 / 4 主题（liquid / ink / navy / notion）视觉表现 / TypeScript 类型（`FolderDTO` / `FileDTO`）保持原值。
> 唯一可见变化：`ResourceLibraryView.vue` 490 → 目标 ≤500 行；新增 3 个聚焦子组件；主入口 + 8 个新聚焦子组件就位（沿用切片 4 风格）。

## 风险与后续

- **风险 1**：`v-model` 改 `:value + @input` 显式 emit 链会触发 `vue/no-mutating-props` lint 规则（与切片 4 经验一致）。缓解：spec §1 明确所有 `v-model` 改 emit 链。
- **风险 2**：`goToDetail` 用 `useRouter()` 在主入口持有；子组件 emit `go-to-detail` 让父级调用 `router.push`。子组件**不** import `vue-router`。
- **风险 3**：`flatFolders` computed 涉及 `depth` 计算，**保留在主入口**（子组件只接收已经 flatten 后的列表），避免子组件重复实现 walk 递归。
- **风险 4**：`onMounted` 触发 `loadFolders` + `loadFiles` 在主入口**保留**——子组件不持有 onMounted 生命周期。
- **风险 5**：切片 4 实施时 5 处小修正经验（`v-model` → emit 链 / `ref` 内部触发 / `dead code` 移除 / logger name 硬编码 / hidden input ref）在本切片可能重现 1-2 处。spec 末尾"实施记录"段需预留。
- **后续**：切片 7（`FileDetailView.vue` 416 抽子组件）由独立 spec / plan 启动，沿用切片 4 / 切片 6 风格。
- **后续**：DOC-041（清理 `document_router` 与 `document_task_router` 重复路由）由独立 spec / plan 启动。
- **后续**：TD-032 任务整体保持 `🟢 完成`；本切片不改变任务状态。

## 任务卡片字段

完成后需在 `docs/03-engineering-governance/current-work.md` 把本任务卡「下一步」从「切片 6 实施」改为「切片 6 已合并；切片 7 单独 spec / plan」；`docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` 中 `ResourceLibraryView.vue` 状态从 `⚪ 待切片` 改为 `🟢 已拆分` + 新行数 + 拆出去向；`docs/03-engineering-governance/technical-debt.md#td-032` 备注追加「切片 6 已合并」；`docs/03-engineering-governance/work-log.md` 加一行索引。
