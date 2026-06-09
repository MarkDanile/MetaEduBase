# TD-032 切片 6 拆分 `ResourceLibraryView.vue`（490 行）— Plan

## 任务入口

- Spec: `docs/02-delivery-plans/01-specs/2026-06-09-td-032-slice-6-resource-library-view-split.md`
- 技术债: `docs/03-engineering-governance/technical-debt.md#td-032-治理超大源码文件并建立文件规模拆分原则`
- 任务卡片: `docs/03-engineering-governance/current-work.md` 的 TD-032 切片 6 卡片
- 当前执行模式: `plan-do`（纯重构 + 行为零变化 + 跨 5+ 文件已 spec 覆盖）
- 分支: `refactor/td-032-slice-6-resource-library-view`（已从最新 `main` 切出）
- 完成后 Git 阶段: 提交 → push → PR → 合并 `main`（按 `docs/03-engineering-governance/01-rules/git-workflow.md#快速交付通道`）

## 实施顺序

### 1. 风险探针：核对基线 + 列出所有 `v-model` 用点

- [ ] 跑 baseline `pnpm typecheck / lint / build` 确认 main 干净（已跑：3 项全过）。
- [ ] 列出 ResourceLibraryView 中**所有** `v-model` 用点（`newFolderName` / `inlineRenamingName` / `filterStatus` / `uploadDocType` / `uploadTags` / `showUploadDialog` / `showDeleteDialog`）—— 7 处需改 `:value + @input` 显式 emit 链。
- [ ] 列出子组件内部需要的 props 数量（`FolderTreePanel` 9 props + 10 emits / `FileListPanel` 5 props + 6 emits / `UploadOptionsDialog` 3 props + 4 emits）—— spec §1 已明确。

**验证点**：grep 命中 7 处 `v-model`，与 spec §「风险 1」一致。

### 2. 按 spec §1 拆出 3 个子组件

按"`FileListPanel` 先 / `FolderTreePanel` 后 / `UploadOptionsDialog` 最后"顺序拆。**每拆一个组件，立刻跑 typecheck**，避免批量失败时难定位。

#### 2.1 创建 `FileListPanel.vue`（最右块，独立）

- [ ] 写 `views/resource/FileListPanel.vue`（~110 行）：右侧上传区 + filter bar + 文件表。
- [ ] 子组件内部 helper：`formatSize` / `formatDate` / `statusLabel` / `statusTagClass`（module-level 私有函数，与原 ResourceLibraryView 行为一致）。
- [ ] `fileInput` ref **在子组件内部持有**（hidden `<input>` 在子组件模板内）；emit `trigger-upload` / `file-change` / `drop` 让父级协调。
- [ ] 验证：行数 ≤200；`v-model` 改 `:value + @input` 显式 emit 链（5 处：`filterStatus` / `uploadDocType` / `uploadTags` 等）。

#### 2.2 创建 `FolderTreePanel.vue`（最左块，state 最多）

- [ ] 写 `views/resource/FolderTreePanel.vue`（~130 行）：左侧 240px 面板（"全部文件" + 树状文件夹列表 + inline 新建/重命名 input + 3-dot 菜单）。
- [ ] 接收 props（9 个）+ emit（10 个），按 spec §1 表格。
- [ ] 不实现 `flatFolders` computed（父级 `ResourceLibraryView` 持有，子组件接收已 flatten 后的列表）。
- [ ] 验证：行数 ≤200；`v-model` 改 `:value + @input` 显式 emit 链（2 处：`newFolderName` / `inlineRenamingName`）。

#### 2.3 创建 `UploadOptionsDialog.vue`（上传选项对话框）

- [ ] 写 `views/resource/UploadOptionsDialog.vue`（~50 行）：复用 `ConfirmDialog` slot 模式，包含 doc_type 下拉 + tags input。
- [ ] 验证：行数 ≤100；`v-model` 改 `:value + @input` 显式 emit 链（2 处：`docType` / `tags`）。

#### 2.4 精简 `ResourceLibraryView.vue`

- [ ] 删除模板中左侧 240px 面板（约 108 行）→ 替换为 `<FolderTreePanel ... />` 标签。
- [ ] 删除模板中右侧文件表（约 87 行）→ 替换为 `<FileListPanel ... />` 标签。
- [ ] 删除模板中上传选项对话框（约 22 行）→ 替换为 `<UploadOptionsDialog ... />` 标签。
- [ ] 保留模板中简单删除文件 ConfirmDialog（约 6 行，单行 message + 单一 confirm handler）。
- [ ] 删除 `<script setup>` 中 4 个 module-level helper（`formatSize` / `formatDate` / `statusLabel` / `statusTagClass`，已迁到 `FileListPanel` 内部）。
- [ ] 顶部 import 替换：删除 4 个 lucide-vue-next icon 局部（迁到子组件按需 import）+ 4 个子组件 import + 删除 4 个 `FILE_STATUS_MAP` / `DOC_TYPE_OPTIONS`（迁到子组件）。
- [ ] 保留：所有 state（19 ref）+ 7 编排函数 + `onMounted` + `flatFolders` computed + `useRouter` / `useToast` + 删除文件 ConfirmDialog 处理。
- [ ] 行数目标：~250 行（模板 ~50 + `<script setup>` ~200）。

### 3. 验证

- [ ] **3.1** 行数核对：

  ```bash
  wc -l \
    packages/web/src/views/resource/ResourceLibraryView.vue \
    packages/web/src/views/resource/FolderTreePanel.vue \
    packages/web/src/views/resource/FileListPanel.vue \
    packages/web/src/views/resource/UploadOptionsDialog.vue
  ```

  期望：ResourceLibraryView ≤500；3 个子组件 ≤200。

- [ ] **3.2** 文档门禁：

  ```bash
  scripts/check-engineering-docs
  ```

  退出码 0。

- [ ] **3.3** 外部 import 兼容性探针：

  ```bash
  cd packages/web
  pnpm typecheck
  ```

  期望：vue-tsc 退出码 0；无新 warning。
  - 关键路径：`@/views/resource/ResourceLibraryView.vue`（router.ts:27 lazy import）仍解析。

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

  退出码 0；产物包含 `ResourceLibraryView` chunk（与现状一致）。

- [ ] **3.6** `git diff --name-status` 仅包含：
  - `packages/web/src/views/resource/{ResourceLibraryView.vue,FolderTreePanel.vue,FileListPanel.vue,UploadOptionsDialog.vue}` (1 改 3 新)
  - `docs/02-delivery-plans/01-specs/2026-06-09-td-032-slice-6-resource-library-view-split.md` (新)
  - `docs/02-delivery-plans/02-plans/2026-06-09-td-032-slice-6-resource-library-view-split-plan.md` (新)
  - `docs/03-engineering-governance/current-work.md` (改)
  - 无业务代码改动（`app/router.ts` / `services/document.ts` / 共享组件 / 后端全部不动）。

- [ ] **3.7** 视觉对照（沙箱不可达 → 标"未运行"）：

  ```bash
  cd packages/web
  ./dev.sh frontend
  # 浏览器手动验收: 切换 liquid / ink / navy / notion 主题,验收 /resource 资源库 (文件夹树 + 文件表 + 上传 + 删除)。
  ```

  沙箱无浏览器时按 `quality-gates.md#验证表述规范` 标"未运行 / 沙箱不可达"；typecheck + lint + build 替代证据。

### 4. Git 闭环

- [ ] 同步 `docs/03-engineering-governance/current-work.md` 任务卡（TD-032 切片 6 收口）。
- [ ] 暂存相关文件（`git add packages/web/src/views/resource/` + `docs/02-delivery-plans/{01-specs,02-plans}/` + current-work.md）。
- [ ] 提交：`refactor(web): split ResourceLibraryView into FolderTree + FileList + UploadOptions sub-components`。
- [ ] push：`git push -u origin refactor/td-032-slice-6-resource-library-view`。
- [ ] PR：`gh pr create --title "refactor(web): TD-032 slice 6 — split ResourceLibraryView" --body ...`，body 含 Summary / Scope / Validation / Risks / Docs。
- [ ] `gh pr view --json state,mergeable,reviewDecision` 确认 `MERGEABLE`；`gh pr checks` 查 CI（PR #92-96 均无 CI 配置；本仓库 gate 走本地 `scripts/check-engineering-docs` + pnpm）。
- [ ] squash merge：`gh pr merge --squash --delete-branch`。
- [ ] 合并后回写：
  - `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`：`ResourceLibraryView.vue` 状态 `⚪ 待切片` → `🟢 已拆分` + 新行数 + 拆出去向。
  - `docs/03-engineering-governance/technical-debt.md#td-032`：备注追加「切片 6 已合并」+ PR 链接。
  - `docs/03-engineering-governance/work-log.md`：新增 1 行索引。
  - `docs/03-engineering-governance/current-work.md`：TD-032 任务卡「下一步」改为「切片 7 单独 spec / plan」。
  - 上述 docs-only 回写合并到 1 个原子 backfill commit。

## 任务拆分（按 plan-do 步骤）

1. 风险探针（§1，5 分钟）
2. 3 个子组件（§2.1-§2.3）
3. 精简 ResourceLibraryView.vue（§2.4）
4. 验证（§3，typecheck + lint + build + 行数）
5. 走完整 Git 流程
6. 合并后回写 4 处 docs

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| `v-model` 直接 mutate prop 触发 `vue/no-mutating-props` | 全部改 `:value + @input` 显式 emit 链（spec §风险 1 + plan §1） |
| `goToDetail` 需要 `useRouter` 跨子组件 | 子组件 emit `go-to-detail` 事件；`useRouter` 仍在主入口持有；子组件不 import `vue-router` |
| `flatFolders` computed 重复实现 | 父级 ResourceLibraryView 持有，子组件接收已 flatten 列表（spec §风险 3） |
| 切片 4 / 切片 5 实施时反复出现的小修正（ref 内部触发 / dead code 移除 / hidden input） | spec §风险 5 预留"实施记录"段；plan §3 验证时如发现小修正，记录到 spec 末尾段 |
| 沙箱无浏览器，4 主题视觉对照只能 typecheck + lint + build | §3.7 标"未运行" + 记录原因；浏览器验收由用户在本地接力 |
| 实施时可能错把 `fileInput` ref 提到主入口（违反"hidden input 在子组件内部"原则） | spec §2 明确：ref 在子组件内部持有；plan §2.1 写实施时按此约束 |

## 提交前最终回查（按 `docs/03-engineering-governance/task-modes.md#通用收尾回查`）

- [ ] `current-work.md` 任务卡与代码实际状态一致。
- [ ] `technical-debt.md` 任务卡状态与代码实际状态一致。
- [ ] `scripts/check-engineering-docs` 退出码 0。
- [ ] `pnpm typecheck` 退出码 0。
- [ ] `pnpm lint` 退出码 0 + 无新增 warning。
- [ ] `pnpm build` 退出码 0。
- [ ] 业务行为不变声明写到 PR 描述 + 本文件 + spec。
- [ ] 行为等价矩阵（点击 / 输入 / 拖拽 / mutation 刷新 / 错误处理）覆盖文件夹 CRUD + 文件列表 + 上传 + 删除。
- [ ] `git diff --name-status` 只包含本任务文件（views 包 + spec/plan + current-work）；无业务代码、无生成物。
