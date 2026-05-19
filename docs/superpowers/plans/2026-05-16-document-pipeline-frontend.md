# A1 Frontend Implementation Plan: Document Pipeline + Database Module

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete frontend for resource library (folder tree + file list + file detail), database module (dataset list + data preview + KG status), and processing status tracking — all matching the A1 spec Section 7.

**Architecture:** Two new top-level views (`ResourceLibraryView` replaces `ResourceView`, `DatabaseView` is new), one new detail view (`FileDetailView`), new API services, new constants, sidebar update. All following existing Vue 3.5 + Pinia 3 + Tailwind CSS 4 + lucide-vue-next patterns.

**Design System:** All styles use CSS variables from `main.css` `@theme` block. Components: `PageHeader`, `EmptyState`, `ConfirmDialog`, `LoadingSpinner`, `ToastContainer` + `useToast`. No hardcoded colors/z-index/font-sizes.

---

## File Structure

### New files

```
packages/web/src/
├── services/
│   ├── document.ts              # Document API service (folders, files, chunks, tasks)
│   └── structured-data.ts       # Structured data API service (datasets, rows, KG)
├── views/
│   ├── resource/
│   │   ├── ResourceLibraryView.vue  # Master-Detail: folder tree + file list (replaces ResourceView)
│   │   └── FileDetailView.vue      # File detail: pipeline status + 3 tabs
│   └── database/
│       └── DatabaseView.vue         # Dataset list + data preview + KG status
└── constants/
    └── pipeline.ts                  # Task type labels, status maps, pipeline step configs
```

### Modified files

```
packages/web/src/app/router.ts          # Add /resource/:id route, /database route
packages/web/src/views/LayoutView.vue   # Add "数据库" nav item, rename "校本资源" to "资源库"
```

---

## Task 1: Add pipeline constants

**Files:**
- Create: `packages/web/src/constants/pipeline.ts`

- [ ] **Step 1: Create `pipeline.ts`**

```ts
// Resource pipeline task types (6 steps)
export const DOC_TASK_STEPS = [
  { type: "parse", label: "文档解析", icon: "FileSearch" },
  { type: "chunk", label: "结构切片", icon: "Scissors" },
  { type: "embed", label: "向量化", icon: "Cpu" },
  { type: "index_tsv", label: "全文索引", icon: "Search" },
  { type: "extract_template", label: "模板抽取", icon: "LayoutTemplate" },
  { type: "extract_kg", label: "知识图谱", icon: "GitBranch" },
] as const

// Dataset pipeline task types (3 steps)
export const DS_TASK_STEPS = [
  { type: "ds_parse", label: "数据解析", icon: "FileSpreadsheet" },
  { type: "ds_embed", label: "向量化", icon: "Cpu" },
  { type: "ds_extract_kg", label: "知识图谱", icon: "GitBranch" },
] as const

// Task status display
export const TASK_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: "等待中", color: "amber" },
  running: { label: "进行中", color: "blue" },
  success: { label: "已完成", color: "green" },
  failed: { label: "失败", color: "red" },
}

// File status display
export const FILE_STATUS_MAP: Record<string, { label: string; color: string }> = {
  uploaded: { label: "已上传", color: "amber" },
  processing: { label: "处理中", color: "blue" },
  processed: { label: "已完成", color: "green" },
  failed: { label: "失败", color: "red" },
}

// KG status display
export const KG_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: "待构建", color: "amber" },
  building: { label: "构建中", color: "blue" },
  done: { label: "已完成", color: "green" },
  failed: { label: "失败", color: "red" },
}

// Doc type options
export const DOC_TYPE_OPTIONS = [
  { value: "教案", label: "教案" },
  { value: "授课计划", label: "授课计划" },
  { value: "课程标准", label: "课程标准" },
  { value: "试卷", label: "试卷" },
  { value: "其他", label: "其他" },
] as const
```

- [ ] **Step 2: Verify imports**

Run: `cd packages/web && npx vue-tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/constants/pipeline.ts
git commit -m "feat(web): add pipeline status and task type constants"
```

---

## Task 2: Create API services

**Files:**
- Create: `packages/web/src/services/document.ts`
- Create: `packages/web/src/services/structured-data.ts`

- [ ] **Step 1: Create `document.ts`**

Follow the existing `knowledge.ts` service pattern. Export a `documentApi` object with typed methods:

```ts
import api from "./api"

// Types
export interface FolderDTO {
  id: string
  tenant_id: string
  name: string
  parent_id: string | null
  path: string
  sort_order: number
  created_at: string
  updated_at: string
  children?: FolderDTO[]
}

export interface FileDTO {
  id: string
  tenant_id: string
  folder_id: string | null
  filename: string
  file_type: string
  doc_type: string | null
  file_size: number | null
  tags: string[] | null
  status: string
  structured_data: Record<string, unknown> | null
  uploaded_by: string
  created_at: string
  updated_at: string
}

export interface ChunkDTO {
  id: string
  file_id: string
  chunk_index: number
  content: string
  section_title: string | null
  section_path: string | null
  char_start: number | null
  char_end: number | null
  has_embedding: boolean
  created_at: string
}

export interface TaskDTO {
  id: string
  file_id: string | null
  dataset_id: string | null
  task_type: string
  status: string
  progress: number
  error_message: string | null
  label: string
  started_at: string | null
  completed_at: string | null
  created_at: string
}

export const documentApi = {
  // Folders
  listFolders: () => api.get<FolderDTO[]>("/document/folders"),
  createFolder: (data: { name: string; parent_id?: string; sort_order?: number }) =>
    api.post<FolderDTO>("/document/folders", data),
  updateFolder: (id: string, data: { name?: string; sort_order?: number }) =>
    api.patch<FolderDTO>(`/document/folders/${id}`, data),
  deleteFolder: (id: string) => api.delete(`/document/folders/${id}`),
  moveFolder: (id: string, data: { parent_id: string | null }) =>
    api.patch<FolderDTO>(`/document/folders/${id}/move`, data),

  // Files
  listFiles: (params?: { folder_id?: string; tag?: string; status?: string; offset?: number; limit?: number }) =>
    api.get<FileDTO[]>("/document/files", { params }),
  uploadFile: (formData: FormData) =>
    api.post<FileDTO>("/document/files/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  getFile: (id: string) => api.get<FileDTO>(`/document/files/${id}`),
  deleteFile: (id: string) => api.delete(`/document/files/${id}`),
  updateFile: (id: string, data: { tags?: string[]; doc_type?: string; folder_id?: string }) =>
    api.patch<FileDTO>(`/document/files/${id}`, data),

  // Chunks
  listChunks: (fileId: string) => api.get<ChunkDTO[]>(`/document/files/${fileId}/chunks`),

  // Tasks
  listTasks: (fileId: string) => api.get<TaskDTO[]>(`/document/files/${fileId}/tasks`),
  retryTasks: (fileId: string) => api.post<TaskDTO[]>(`/document/files/${fileId}/retry`),
}
```

- [ ] **Step 2: Create `structured-data.ts`**

Same pattern, with `DatasetDTO`, `DatasetRowDTO`, `TaskDTO`:

```ts
import api from "./api"

export interface DatasetDTO {
  id: string
  tenant_id: string
  name: string
  description: string | null
  column_names: string[] | null
  column_types: string[] | null
  row_count: number
  source_file: string | null
  tags: string[] | null
  status: string
  kg_status: string
  sort_order: number
  created_by: string
  created_at: string
  updated_at: string
}

export interface DatasetRowDTO {
  id: string
  dataset_id: string
  row_index: number
  data: Record<string, unknown>
  created_at: string
}

export interface KGNode {
  id: string
  title: string
  description: string | null
  domain: string
  level: string
  source_dataset_id: string | null
}

export interface KGEdge {
  id: string
  source_id: string
  target_id: string
  relation_type: string
}

export const structuredDataApi = {
  // Datasets
  listDatasets: (params?: { tag?: string; status?: string; offset?: number; limit?: number }) =>
    api.get<DatasetDTO[]>("/structured-data/datasets", { params }),
  uploadDataset: (formData: FormData) =>
    api.post<DatasetDTO>("/structured-data/datasets/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  getDataset: (id: string) => api.get<DatasetDTO>(`/structured-data/datasets/${id}`),
  deleteDataset: (id: string) => api.delete(`/structured-data/datasets/${id}`),
  updateDataset: (id: string, data: { name?: string; description?: string; tags?: string[]; sort_order?: number }) =>
    api.patch<DatasetDTO>(`/structured-data/datasets/${id}`, data),

  // Rows
  listRows: (datasetId: string, params?: { offset?: number; limit?: number }) =>
    api.get<DatasetRowDTO[]>(`/structured-data/datasets/${datasetId}/rows`, { params }),

  // Tasks
  listTasks: (datasetId: string) => api.get<TaskDTO[]>(`/structured-data/datasets/${datasetId}/tasks`),
  retryTasks: (datasetId: string) => api.post<TaskDTO[]>(`/structured-data/datasets/${datasetId}/retry`),

  // Knowledge Graph
  getKgStatus: () => api.get<{ id: string; name: string; kg_status: string }[]>("/structured-data/knowledge-graph/status"),
  getKnowledgeGraph: () => api.get<{ nodes: KGNode[]; edges: KGEdge[] }>("/structured-data/knowledge-graph"),
}
```

Note: Import `TaskDTO` from `./document` for reuse.

- [ ] **Step 3: Verify type check**

Run: `cd packages/web && npx vue-tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/services/document.ts src/services/structured-data.ts
git commit -m "feat(web): add document and structured-data API services"
```

---

## Task 3: Update router + sidebar

**Files:**
- Modify: `packages/web/src/app/router.ts`
- Modify: `packages/web/src/views/LayoutView.vue`

- [ ] **Step 1: Update `router.ts`**

Add routes:
- `/resource` → `ResourceLibraryView.vue` (replace the current ResourceView)
- `/resource/:id` → `FileDetailView.vue` (new detail page)
- `/database` → `DatabaseView.vue` (new)

```ts
// Replace the resource route:
{ path: "/resource", name: "resource", component: () => import("../views/resource/ResourceLibraryView.vue") },
{ path: "/resource/:id", name: "file-detail", component: () => import("../views/resource/FileDetailView.vue") },
// Add database route:
{ path: "/database", name: "database", component: () => import("../views/database/DatabaseView.vue") },
```

- [ ] **Step 2: Update `LayoutView.vue`**

Change sidebar navItems:
- Rename "校本资源" to "资源库"
- Add "数据库" between "资源库" and "AI 问答"

```ts
const navItems = [
  { title: "总览", route: "/", icon: LayoutGrid },
  { title: "知识库", route: "/knowledge", icon: BookOpen },
  { title: "资源库", route: "/resource", icon: FolderOpen },
  { title: "数据库", route: "/database", icon: Database },
  { title: "AI 问答", route: "/ai-chat", icon: MessageSquare },
  { title: "技能编排", route: "/skill-editor", icon: Settings },
  { title: "系统管理", route: "/admin", icon: Cog },
]
```

Add `Database` and `FolderOpen` to the lucide-vue-next import.

- [ ] **Step 3: Verify type check and app loads**

Run: `cd packages/web && npx vue-tsc --noEmit`
Expected: No errors (the views don't exist yet, but they're lazy-loaded so TS won't error)

- [ ] **Step 4: Commit**

```bash
git add src/app/router.ts src/views/LayoutView.vue
git commit -m "feat(web): add database route and update sidebar navigation"
```

---

## Task 4: Create ResourceLibraryView

**Files:**
- Create: `packages/web/src/views/resource/ResourceLibraryView.vue`

- [ ] **Step 1: Create the view**

Master-Detail layout: left sidebar (folder tree, ~240px) + right content (file list).

Key features per spec 7.2:
- **Left panel**: Folder tree with click-to-select, create/rename/delete/move actions, tag filter area at bottom
- **Right panel**: File table (filename, doc_type, tags, status, size, upload time), upload button + drag zone, operation menu (⋯) per row
- **Upload dialog**: Select folder, fill tags, select doc_type, file picker
- **All destructive actions** use ConfirmDialog
- **Status badges** use `liquid-tag-*` classes from pipeline constants
- **Folder CRUD** via `documentApi`
- **File CRUD** via `documentApi`
- Uses: `PageHeader`, `EmptyState`, `ConfirmDialog`, `LoadingSpinner`, `useToast`

Layout structure:
```
┌──────────────────────────────────────────────────┐
│ PageHeader: 资源库                                │
├──────────┬───────────────────────────────────────┤
│ Folders  │  Upload area (drag zone + button)     │
│ tree     │  ─────────────────────────────────     │
│          │  File table                            │
│ [新建]   │  ┌────────────────────────────────┐    │
│ [删除]   │  │ filename | type | tags | status│    │
│          │  │ ...      | ...  | ...  | ...    │    │
│ ─────── │  └────────────────────────────────┘    │
│ Tags:    │  Pagination                            │
│ [tag1]   │                                        │
└──────────┴───────────────────────────────────────┘
```

- [ ] **Step 2: Verify type check**

Run: `cd packages/web && npx vue-tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add src/views/resource/ResourceLibraryView.vue
git commit -m "feat(web): add ResourceLibraryView with folder tree and file list"
```

---

## Task 5: Create FileDetailView

**Files:**
- Create: `packages/web/src/views/resource/FileDetailView.vue`

- [ ] **Step 1: Create the view**

Per spec 7.3:
- **Top bar**: filename, type icon, file size, uploader, tags, download/delete buttons
- **Pipeline status**: Horizontal 6-step progress bar, each step shows icon + label + status (pending/running/success/failed), progress percentage, manual refresh button, auto-poll every 3s while any task is running
- **3 Tabs**:
  1. **结构化抽取**: Display structured_data JSON fields in a clean card layout (based on doc_type template)
  2. **切片列表**: Table of chunks with section_title, section_path, char count, has_embedding badge
  3. **知识图谱**: Simple list of knowledge nodes and relations extracted from this file (read from knowledge API with source_file_id filter, or from task data)

- **Delete** uses ConfirmDialog
- **Retry** button for failed tasks
- Uses: `PageHeader`, `ConfirmDialog`, `LoadingSpinner`, `useToast`, `DOC_TASK_STEPS` from pipeline constants
- Route params: `route.params.id` → `documentApi.getFile(id)` + `documentApi.listTasks(id)`

- [ ] **Step 2: Verify type check**

Run: `cd packages/web && npx vue-tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add src/views/resource/FileDetailView.vue
git commit -m "feat(web): add FileDetailView with pipeline status and 3-tab layout"
```

---

## Task 6: Create DatabaseView

**Files:**
- Create: `packages/web/src/views/database/DatabaseView.vue`

- [ ] **Step 1: Create the view**

Per spec 7.4:
- **Left panel** (~260px): Dataset list, each showing name + row count + status badge, click to select, upload button, rename/delete in context menu
- **Right panel** (when a dataset is selected):
  - Top bar: dataset name, column/row count, tags, delete button
  - 3-step pipeline progress bar (ds_parse → ds_embed → ds_extract_kg), same pattern as FileDetailView
  - 2 Tabs:
    1. **数据预览**: Table with dataset_rows, paginated, column headers from dataset.column_names
    2. **知识图谱(本表)**: List of knowledge nodes/edges from this dataset (from structured-data KG endpoint, filtered by source_dataset_id)
- **Bottom of left panel**: "知识图谱总览" link/button → shows all-datasets KG (spec 7.5)
- **Upload dialog**: File picker for Excel, name input, tags, description
- **All destructive actions** use ConfirmDialog
- Uses: `PageHeader`, `EmptyState`, `ConfirmDialog`, `LoadingSpinner`, `useToast`, `DS_TASK_STEPS` from pipeline constants

- [ ] **Step 2: Verify type check**

Run: `cd packages/web && npx vue-tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add src/views/database/DatabaseView.vue
git commit -m "feat(web): add DatabaseView with dataset list and data preview"
```

---

## Task 7: Update HomeView to use new routes

**Files:**
- Modify: `packages/web/src/views/HomeView.vue`

- [ ] **Step 1: Update the module navigation grid**

In the existing module grid, update:
- "校本资源" → "资源库" with route `/resource` and `FolderOpen` icon
- Add "数据库" card with route `/database` and `Database` icon

- [ ] **Step 2: Verify type check**

Run: `cd packages/web && npx vue-tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add src/views/HomeView.vue
git commit -m "feat(web): update HomeView with resource library and database module cards"
```

---

## Task 8: Full frontend verification

**Files:** None (verification only)

- [ ] **Step 1: Run type check**

Run: `cd packages/web && npx vue-tsc --noEmit`
Expected: No errors

- [ ] **Step 2: Run lint**

Run: `cd packages/web && pnpm lint`
Expected: No errors

- [ ] **Step 3: Run build**

Run: `cd packages/web && pnpm build`
Expected: Build succeeds

- [ ] **Step 4: Fix any issues found**

If typecheck/lint/build fail, fix and re-run.

- [ ] **Step 5: Commit any fixes**

```bash
git add -A && git commit -m "fix(web): address typecheck/lint/build issues from A1 frontend implementation"
```

---

## Self-Review

**1. Spec coverage (Section 7):**
- 7.1 Sidebar update: Task 3
- 7.2 Resource library main: Task 4
- 7.3 File detail: Task 5
- 7.4 Database main: Task 6
- 7.5 KG overview: Task 6 (embedded in DatabaseView left panel)
- 7.6 Component reuse: All tasks use PageHeader, EmptyState, ConfirmDialog, LoadingSpinner, ToastContainer
- 7.7 Chinese status mapping: Task 1 (pipeline.ts constants)

**2. Placeholder scan:** No TBD/TODO. All steps have concrete code or descriptions.

**3. Design system compliance:** All colors use `var(--*)`, all z-index use `var(--z-*)`, all font sizes use design tokens. Icons: lucide-vue-next only. No inline SVGs.

**4. Gap:** The old `ResourceView.vue` is replaced by `ResourceLibraryView.vue` but the file is not deleted in this plan (to avoid confusion with git). It should be removed or kept as a fallback. Decision: keep the old file, update the route to point to the new one. Old file can be deleted in a cleanup PR.
