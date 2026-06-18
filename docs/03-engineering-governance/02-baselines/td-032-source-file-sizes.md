# TD-032 源码文件行数基线

本文件是 TD-032 治理超大源码文件的**行数事实源**。与 `technical-debt.md#td-032` 证据段
互为镜像：本文件给"清单 + 状态 + 拆分说明"，技术债总账给"任务卡 + 完成标准 + 验证
方式"。每切片交付后必须回写本文件。

## 维护规则

- 扫描命令（DOC-042 脚本化后以 ``scripts/scan-source-sizes`` 为准）：

  ```bash
  # 脚本化扫描（推荐）
  scripts/scan-source-sizes --threshold 500
  scripts/scan-source-sizes --diff           # 与上次基线对比
  scripts/scan-source-sizes --refresh        # 刷新 JSON 基线 + Markdown 行数列
  ```

  历史手工命令（仅供参考，已被脚本替代）：

  ```bash
  rg --files -0 packages scripts tests \
    -g '*.py' -g '*.ts' -g '*.tsx' -g '*.vue' -g '*.css' -g '*.scss' \
    -g '!**/.venv/**' -g '!**/uploads/**' -g '!**/node_modules/**' -g '!**/dist/**' \
    | xargs -0 wc -l | sort -nr | head -40
  ```

- 4 档分组：>1000 / >500 / 500 附近 / 合规样例。
- 每行至少有 1 句「例外 / 拆分说明」；例外也要写「后续切片计划」，不允许长期 `🔵`。
- 每切片交付后必须回写本文件：状态变化 / 行数变化 / 新增文件；不允许连续 2 个复盘周期
  无更新。
- 行数与 `technical-debt.md#td-032` 证据段如有差异，以本文件最近一次扫描为准，并在
  末尾「扫描历史」段记录。

## 文件清单

### >1000 行（必须明确例外或拆分计划）

| 文件 | 行数 | 状态 | 例外 / 拆分说明 |
|------|------|------|-----------------|
| `packages/server-python/tests/contexts/knowledge/test_ai_chat_service.py` | 1037 | 🟢 已登记（待拆分） | REQ-016 / REQ-018 合并后该测试文件超过 1000 行硬限制；本次只登记新增风险，不在视觉主题任务中拆测试。后续应按 AI Chat service 核心行为、context packer / diagnostics、graph edge recall、query understanding 等测试主题拆成多个聚焦文件，目标单文件 ≤500 行。 |
| `packages/web/src/assets/css/main.css` | 9 | 🟢 已拆分 | TD-033 完成（[PR #103](https://github.com/MarkDanile/MetaEduBase/pull/103) / merge `25ca165`）：原 1343 行单文件拆为入口 `main.css`（9 行 `@import` 聚合）+ 8 个模块文件：`tokens.css`（119 行 `@theme` token） / `themes.css`（256 行 4 主题变量） / `base.css`（35 行 `@layer base` reset） / `components.css`（281 行 `ui-*` + `liquid-card*` + `sidebar-shell` + liquid `ui-panel` 覆盖） / `compat-liquid.css`（313 行 `liquid-input/btn/tag/dialog` + Notion 主题 `liquid-*` 覆盖） / `animations.css`（86 行 `@keyframes` + `stagger-*` + `liquid-rise` + `reduced-motion`） / `markdown.css`（214 行 `.markdown-body` + `content-bg` + `mesh-bg` + `wet-line`） / `toast.css`（52 行 `.toast-container` + `.toast-item`）；全部 ≤500 行；以 `pnpm typecheck / lint / build` 退出码 0 + `git diff --check` 退出码 0 为依据（Vite 产物 CSS diff / hash 未做机械对比，"build output identical" 仅基于 import 顺序与级联分析推断，详见 DOC-045） |
| `scripts/engineering/check_engineering_docs.py` | 72 | 🟢 已拆分 | 切片 2 已合并 ([PR #93](https://github.com/MarkDanile/MetaEduBase/pull/93) / merge `7e468fb`)：原 1003 行单文件拆为入口主文件 72 行 + 8 个聚焦 `checks/*.py` 模块（38-233 行）+ `checks/__init__.py` 注册表 `KNOWN_CHECKS`；入口脚本 `scripts/check-engineering-docs` (17 行 `runpy.run_path`) 不动；16 个 pytest 行为零变化 |

### >500 行业务 / 工程源码

| 文件 | 行数 | 状态 | 例外 / 拆分说明 |
|------|------|------|-----------------|
| `packages/server-python/app/contexts/document/application/tasks.py` | 0 (0) → tasks/ 包 1000 行 | 🟢 已拆分 | 切片 3 已合并 ([PR #94](https://github.com/MarkDanile/MetaEduBase/pull/94) / merge `5beb938`)：原 929 行单文件拆为 `tasks/` 包（9 文件，27-217 行/个）：`__init__.py` re-export 6 task + 2 helper；`pipeline_guard.py`（53 行）+ `extract_template_prompts.py`（88 行）+ 6 个 task 子文件（`parse.py` 138 / `chunk.py` 160 / `embed.py` 145 / `index.py` 94 / `extract_template.py` 217 / `extract_knowledge_graph.py` 178）；所有子文件 ≤500 行；`@shared_task(name=...)` 10 个名字全部 byte-equivalent；`app/shared/tasks/lifecycle.py`（TD-005 产物）未动；`app/contexts/document/tasks.py` Celery autodiscover 代理未动；55 个 pytest 聚焦测试 0 改动通过 |
| `packages/web/src/views/database/DatabaseView.vue` | 320 | 🟢 已拆分 | 切片 4 已合并 ([PR #95](https://github.com/MarkDanile/MetaEduBase/pull/95) / merge `d4d2720`)：原 701 行单文件拆为 `views/database/` 包 7 文件：`DatabaseView.vue` 320 行（主入口：顶层 state + 9 个 Vue Query 编排 + 编排函数 + 6 个子组件标签 + 3 个对话框）；6 个聚焦子组件 `DatasetListPanel.vue` 132 / `KgOverviewPanel.vue` 52 / `DatasetDetailMetaBar.vue` 40 / `PipelineStatusPanel.vue` 101 / `DatasetTabsPanel.vue` 139 / `UploadDatasetDialog.vue` 116（每个 ≤200 行）；所有 `ui-*` 共享类 / `var(--*)` token / 4 主题视觉表现 byte-equivalent；`v-model` 改 `:value + @input` 显式 emit 链避免 prop mutation；`router.ts:37` lazy import 仍解析；`queries.ts` 9 个 composable 不动 |
| `packages/server-python/app/contexts/structured_data/application/tasks.py` | 0 (0) → tasks/ 包 746 行 | 🟢 已拆分 | 切片 3 已合并 ([PR #94](https://github.com/MarkDanile/MetaEduBase/pull/94) / merge `5beb938`)：原 671 行单文件拆为 `tasks/` 包（5 文件，23-282 行/个）：`__init__.py` re-export 4 task + 4 个 task 子文件（`ds_parse.py` 118 / `ds_embed.py` 149 / `ds_extract_kg.py` 282 / `ds_cross_dataset_edges.py` 174）；所有子文件 ≤500 行；`@shared_task(name=...)` 4 个名字全部 byte-equivalent；`app/shared/tasks/lifecycle.py` 未动；`app/contexts/structured_data/tasks.py` Celery autodiscover 代理未动 |
| `packages/web/src/views/admin/TemplateModal.vue` | 333 | 🟢 已拆分 | 切片 4 已合并 ([PR #95](https://github.com/MarkDanile/MetaEduBase/pull/95) / merge `d4d2720`)：原 665 行单文件拆为 `views/admin/` 包 3 文件：`TemplateModal.vue` 333 行（主入口：dialog 壳 + header/footer + 顶层 state + resetForm/handleSave/handleClose + scoped 壳样式）；2 个聚焦子组件 `TemplateFormFields.vue` 255 / `TemplateAiPanel.vue` 207（每个 ≤260 行）；`v-model` 改 `:value + @input` 显式 emit 链；`TemplateListView.vue:71, 95` 显式 import `./TemplateModal.vue` 仍解析；`FieldItem.vue` 不动；`regenerateAI` + `handleFileSelect` + `ensureIds` 全部迁到 `TemplateAiPanel` 内部 |

### 500 行附近高风险候选

| 文件 | 行数 | 状态 | 例外 / 拆分说明 |
|------|------|------|-----------------|
| `packages/server-python/app/contexts/document/interfaces/api/router.py` | 29 | 🟢 已拆分 | 切片 5 已合并 ([PR #96](https://github.com/MarkDanile/MetaEduBase/pull/96) / merge `4b03064`)：原 494 行单文件拆为 5 个聚焦子 router 文件（位于 `interfaces/api/` 同目录）：`router.py` 29 行（主入口：4 行 `router.include_router(X_router)` + 顶层 re-export `parse_document` 让 `patch("app.contexts.document.interfaces.api.router.parse_document")` 仍工作，tests/conftest.py:24）；`folders.py` 123 行（5 endpoint + 2 helper `_folder_row_to_dto` / `_build_tree`）；`files.py` 231 行（6 endpoint + 1 helper `_file_row_to_dto` + reinitialize_file 函数内 `from sqlalchemy import text` 保持原位）；`chunks.py` 43 行（1 endpoint）；`tasks.py` 121 行（2 endpoint + `_TASK_TYPE_LABELS` 常量 + list_file_tasks / retry_file_tasks 函数内 import 保持原位）；13 个 `@router.*` endpoint 字符串 / HTTP method / path / response_model / status_code 全部 byte-equivalent；`app/main.py:6` 的 `from app.contexts.document.interfaces.api.router import router as document_router` 仍解析；`pytest tests/shared/ tests/contexts/document/ tests/contexts/structured_data/ -q` 115 passed；`ruff check` All checks passed!；**pre-existing 重复路由**（`router.py:402` ≡ `task_router.py:36` 都注册 `GET /files/{file_id}/tasks` + `router.py:442` ≡ `task_router.py:53` 都注册 `POST /files/{file_id}/retry`）**不**在本切片处理；已登记为 `DOC-041` 候选 |
| `packages/web/src/views/resource/ResourceLibraryView.vue` | 286 | 🟢 已拆分 | 切片 6 已合并 ([PR #97](https://github.com/MarkDanile/MetaEduBase/pull/97) / merge `6728151`)：原 490 行单文件拆为 `views/resource/` 包 4 文件：`ResourceLibraryView.vue` 286 行（主入口：19 ref + 7 编排函数 + 3 子组件标签 + 删除文件 ConfirmDialog + `flatFolders` computed + `onMounted`）；3 个聚焦子组件 `FolderTreePanel.vue` 142 / `FileListPanel.vue` 160 / `UploadOptionsDialog.vue` 51（每个 ≤200 行）；`fileInput` ref 在 `FileListPanel` 内部持有（沿用切片 4 模式）；emit 名 kebab-case 化（`update:new-folder-name` / `update:inline-renaming-name` / `update:filter-status` / `update:doc-type`）匹配 `vue/v-on-event-hyphenation` lint 规则；7 个 `documentApi.*` 调用（listFolders / createFolder / updateFolder / deleteFolder / listFiles / uploadFile / deleteFile）仍由 ResourceLibraryView 编排；`router.ts:27` lazy import 仍解析；`pnpm typecheck / lint / build` 3 项全过 |
| `packages/web/src/views/resource/FileDetailView.vue` | 181 | 🟢 已拆分 | 切片 7 已合并 ([PR #98](https://github.com/MarkDanile/MetaEduBase/pull/98) / merge `3e7f827`)：原 416 行单文件拆为 `views/resource/` 包 4 文件：`FileDetailView.vue` 181 行（主入口：顶层 state + 5 Vue Query 编排 + 3 mutation + 3 子组件标签 + 删除/返回 action + watch(polling)）；3 个聚焦子组件 `FileMetaBar.vue` 41 / `FileDetailPipelineStatusPanel.vue` 97 / `FileTabsPanel.vue` 171（每个 ≤200 行）；所有 helper（statusLabel / statusTagClass / formatSize / templateFieldLabel / getFieldLabel + stepIcon/stepBgClass 6 helper）迁到对应子组件内部；emit 名 kebab-case 化（update:active-tab / node-click）；`router.ts:32` lazy import 仍解析；`views/resource/queries.ts` 8 composable 不动 |

### 切片 5+ 候选清单（已全部收口）

| 优先级 | 候选文件 | 当前行数 | 状态 |
|--------|----------|----------|------|
| - | ~~全部完成~~ | - | TD-032 7 切片 + TD-033（`main.css` 模块化）全部合并，500 附近已全部拆分到位 |

> TD-033 完成后的 8 个 CSS 子模块 + main.css 入口均 ≤500 行，TD-032 整体目标达成。

### 合规样例（≤500 行，证明原则可被满足）

| 文件 | 行数 | 状态 | 备注 |
|------|------|------|------|
| `packages/web/src/views/LayoutView.vue` | 387 | 🟢 已合规 | 共享骨架组件，按 TD-008 / TD-025 已收敛 |
| `packages/web/src/views/auth/LoginView.vue` | 377 | 🟢 已合规 | 品牌背景例外保留，文件规模符合原则 |
| `packages/web/src/views/admin/FieldCard.vue` | 368 | 🟢 已合规 | 共享字段卡组件，TD-028 后规模合理 |
| `packages/web/src/views/admin/TemplateModal.vue` | 333 | 🟢 已合规（**切片 4 收口**） | 主入口 + 2 子组件；规模 ≤500 |
| `packages/web/src/views/database/DatabaseView.vue` | 320 | 🟢 已合规（**切片 4 收口**） | 主入口 + 6 子组件；规模 ≤500 |
| `packages/server-python/app/shared/parsing/chunker.py` | 320 | 🟢 已合规 | TD-005 范围外的共享解析模块，规模合理 |
| `packages/web/src/views/resource/ResourceView.vue` | 305 | 🟢 已合规 | 资源视图，TD-025 切片 1 收口 |
| `packages/web/src/views/ai-chat/AiChatView.vue` | 304 | 🟢 已合规 | AI 聊天视图，TD-025 切片 1 收口 |
| `docs/03-engineering-governance/01-rules/coding-style.md` | n/a | 🟢 已合规 | 规则文档，规模可被维护 |

> 行数随交付滚动；本表只列"治理后仍在 ≤500 的代表性共享 / 入口文件"作为基线对照。

## 治理节奏

- 复盘频率：与 `technical-debt.md#定期复盘规范` 一致（每周或每两周一次）。
- 复盘必读：1) 本文件；2) `technical-debt.md#td-032`；3) 最近一次扫描输出。
- 复盘输出：把 1-3 个 `⚪ 待切片` 推进到具体切片的 spec / plan，或升级为 `🔵 例外已登记`
  并写明「后续切片计划」。

## 扫描历史
- 2026-06-10：`scripts/scan-source-sizes --refresh`（DOC-055 收口）刷新 baseline — `--diff` 恢复 `(no differences from baseline)`；本轮 refresh 吸收了 PR #143 squash merge 时带入的 TD-034 代码行数变化（`extract_template_prompts.py` 88 → 93；`test_extract_template_prompts.py` 263 → 261），原 baseline 由 DOC-042 收口时建立（彼时 `--diff` 在 PR #143 合并后即报 2 个差异但被遗漏）。

- 2026-06-08：与 `technical-debt.md#td-032` 证据段同步，基线建立。
- 2026-06-08（切片 4 收口后回写）：5 个 >500 / 500 附近文件全部转 `🟢 已拆分` 或维持 `⚪ 待切片` 标记；新增 `FileDetailView.vue` 416 为 500 附近候选；新增「切片 5+ 候选清单」段；扩展「合规样例」段加入 `TemplateModal.vue` 333 / `DatabaseView.vue` 320 / `chunker.py` 320 / `ResourceView.vue` 305 / `AiChatView.vue` 304。本次回写由 DOC-xxx 任务承接。
- 2026-06-09（TD-032 评审后回写）：扫描命令改为 `rg --files -0 ... | xargs -0 wc -l`，并显式排除 `.venv` / `uploads` / `node_modules` / `dist`，避免本地未跟踪文件或带空格路径污染行数基线；脚本化候选入账 `DOC-042`。
- 2026-06-09：`main.css` 设计系统级 CSS 模块化从 TD-032 例外转为独立就绪任务 `TD-033`。
- 2026-06-09：TD-033 完成（[PR #103](https://github.com/MarkDanile/MetaEduBase/pull/103) / merge `25ca165`）：`main.css` 1343 → 9 行（`@import` 入口）+ 8 个 CSS 模块（全部 ≤500 行）；以 `pnpm typecheck / lint / build` 退出码 0 与 `git diff --check` 退出码 0 为依据（Vite 产物未做 hash / diff 机械对比，详见 DOC-045）；TD-032 >1000 / >500 / 500 附近全部收口。
