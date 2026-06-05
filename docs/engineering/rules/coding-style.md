# Coding Style — 代码风格规范

## Python (后端)

### 格式化
```bash
cd packages/server-python && make lint  # ruff check + mypy
```

如果只改了局部文件，可先运行更小范围的 `ruff check <path>` 或相关 mypy 检查；最终收尾仍以任务验证要求为准。

### 命名规范
| 类型 | 规范 | 示例 |
|------|------|------|
| 模块 | `snake_case` | `auth_service.py` |
| 类 | `PascalCase` | `KnowledgeNode` |
| 函数/方法 | `snake_case` | `get_embedding_vec()` |
| 常量 | `SCREAMING_SNAKE` | `JWT_EXPIRE_MINUTES` |
| 私有属性 | `_leading_underscore` | `_session` |

### 类型注解
- 函数参数和返回值必须标注类型
- 使用 `from __future__ import annotations` 避免循环导入问题
- 优先使用 `Protocol` 定义接口

### 导入顺序 (isort)
1. 标准库
2. 第三方库
3. 本地应用（绝对导入）
4. 分组间空行分隔

---

## TypeScript / Vue (前端)

### 格式化
```bash
cd packages/web && pnpm typecheck  # vue-tsc --noEmit
```

### 命名规范
| 类型 | 规范 | 示例 |
|------|------|------|
| 文件 | `PascalCase` (组件) / `camelCase` (其他) | `KnowledgeBaseView.vue` |
| 组件 | `PascalCase` | `PageHeader.vue` |
| 函数/composable | `camelCase` | `useKnowledge()` |
| 常量 | `SCREAMING_SNAKE` | `API_BASE_URL` |
| CSS 类 | `kebab-case` | `liquid-card` |

### 设计系统

当前代码仍以 `liquid-*` 类为主，后续会逐步迁移到语义化 `ui-*` workspace 层。新增或修改 UI 时，优先复用现有页面和组件的局部风格；涉及 UI foundation 迁移时，先阅读对应设计/计划文档。

#### 迁移说明（TD-008）

`ui-*` 语义化 workspace 层是**新约定的优先选项**，`liquid-*` 类作为**历史兼容保留**。两者并存、不互相替代。

**何时使用 `ui-*`（优先）**

- 新的页面外壳、面板、工具栏、交互行。
- 跨页面共享的工作区结构（`LayoutView`、共享骨架组件）。
- 任何与"calm workspace、token 化、不带装饰动效"目标一致的容器。

提供以下 4 个共享类（`packages/web/src/assets/css/main.css` 中 `@layer components` 段）：

| 类 | 用途 |
|------|------|
| `.ui-page-shell` | 页面外壳：`max-width: 1120px; margin: 0 auto; padding: var(--spacing-page); background: var(--color-bg-base)` |
| `.ui-page-section` | 页面内分区：`margin-top: var(--spacing-section)` |
| `.ui-panel` | 通用面板容器：白底、细边框、token 化阴影、克制 hover 反馈 |
| `.ui-toolbar` | 工具栏行：白底、细边框、12px 圆角 |
| `.ui-interactive-row` | 列表/卡片行的统一 hover 状态机 |

**何时保留 `liquid-*`（兼容）**

- 历史视图与组件仍大量使用，按"手术式改动"原则不主动迁移。
- `liquid-btn-primary` / `liquid-btn-ghost` / `liquid-btn-danger` / `liquid-input` / `liquid-tag-*` / `liquid-dialog` / `liquid-card` 全部保留；未迁入 `ui-*` 的页面继续使用。
- 装饰性 `wet-line` / `liquid-card-scan::after` / `liquid-rise-*` 动效保留；新页面不引入。
- 登录页（`LoginView`）的品牌背景与 `brand-gradient` 不参与 workspace 迁移。

**新增/修改 UI 的优先级**

1. 优先复用 `ui-*` 共享类。
2. 其次复用既有页面/组件的局部风格。
3. 不要新增与 `ui-*` 重复的散落样式。
4. 不要在视图文件里硬编码颜色/间距/z-index（见下方禁止项）。
5. 修改任何共享组件（`PageHeader` / `EmptyState` / `LayoutView` / `ui-*` 类）前，先确认所有调用方并补 typecheck 验证。

**第一个迁移目标**

`LayoutView.vue` + `PageHeader.vue` + `EmptyState.vue` 三个共享骨架组件，作为示例（TD-008 交付）。后续页面（`DatabaseView` / `ResourceView` / `KnowledgeBaseView` / `FileDetailView` / `ResourceLibraryView`）按业务需要逐步迁移到 `ui-*`，不在本轮范围。

#### 业务页面迁移清单（TD-025）

按业务残留量从高到低分切片迁移。每个切片独立 PR、独立验证。

| 切片 | 页面 | 状态 | 残留量（迁入前） | 备注 |
|------|------|------|------------------|------|
| 1 | `DatabaseView` | 🟢 完成 | 8 处 | 切片 1，含 1 个上传对话框、5 个内容卡、1 个数据集列表卡、1 个 KG 总览按钮 |
| 1 | `ResourceView` | 🟢 完成 | 1 处 | 切片 1，资源列表卡，保留 `animate-slide-up` + `stagger-N` 装饰动效 |
| 1 | `ResourceLibraryView` | 🟢 完成 | 3 处 | 切片 1，文件夹树、文件夹右键菜单、文件列表区 |
| 2 | `KnowledgeBaseView` | 🟢 完成 | 1 处 | 切片 2（任务卡残留量 16 处为 TD-008 完成时快照；切片 1 之后剩 1 处）。节点列表卡，保留 `ring-1 ring-[var(--color-accent)] ring-offset-2` 选中态、保留 `animate-slide-up` + `stagger-N` 装饰动效 |
| 2 | `FileDetailView` | 🟢 完成 | 3 处 | 切片 2（任务卡残留量 12 处为 TD-008 完成时快照；切片 1 之后剩 3 处）。文件元信息条、流水线状态、Tab 容器；未触动 `liquid-tag-*` / `liquid-btn-*` / 各 Tab 内部的 inline token 容器 |
| 3 | `TemplateModal` | ⚫ 待办 | 8 处 | 切片 3（业务页 `liquid-btn-*` / `liquid-input` 例外显式登记） |
| 3 | `TemplateEditorView` | ⚫ 待办 | 6 处 | 切片 3 |
| 3 | `AiChatView` | ⚫ 待办 | 4 处 | 切片 3 |
| 3 | `HomeView` | ⚫ 待办 | 3 处 | 切片 3，保留 `stagger-1/2/3` 装饰动效 |
| 例外 | `LoginView` | 🚫 保持兼容 | 4 处 | 品牌背景与 `--_login-brand-gradient`，按 TD-008 规则不参与 workspace 迁移 |
| 后续 | 共享组件 `FieldEditor` / `KGDetailPanel` / `ConfirmDialog` / `KGGraph` 的 `liquid-card` 残留 | ⚫ 待办 | 22 处 | TD-026 候选 |

迁移规则：

- `liquid-card` 容器直接替换为 `ui-panel`，附加类（`group` / `animate-slide-up` / `stagger-N` / 自定义 hover）原样保留。
- 业务页面的 `liquid-btn-primary` / `liquid-btn-ghost` / `liquid-input` / `liquid-tag-*` 按 TD-008 规则保持兼容，**不替换**。
- `LoginView` 品牌背景不参与迁移。
- `liquid-card-scan::after` 装饰动效保留（`HomeView` 等页面仍在用）。
- `liquid` 主题下 `ui-panel` 会自动套用 `:root[data-theme="liquid"] .ui-panel` 玻璃感覆盖（复用 `--_surface-card-bg` + `--_surface-glass-blur`），其他 3 主题维持白底细边框。

所有颜色/间距/z-index 优先使用 CSS 变量，避免引入新的散落硬编码。

**颜色：** `var(--color-ink)`, `var(--color-accent)`, `var(--color-accent-bg)`, `var(--color-accent-glow)`

**字号：** `var(--text-page-title)` (24px), `var(--text-section-title)` (18px), `var(--text-body)` (14px), `var(--text-caption)` (13px), `var(--text-small)` (12px), `var(--text-micro)` (11px)

**Z-index：** `var(--z-sidebar)` (10), `var(--z-drawer)` (30), `var(--z-dialog)` (40), `var(--z-toast)` (50)

**CSS 类：** `liquid-card`, `liquid-btn-primary`, `liquid-btn-ghost`, `liquid-btn-danger`, `liquid-tag-blue/green/amber/purple`, `liquid-dialog-overlay`, `content-bg`, `wet-line`, `animate-slide-up`, `stagger-1`~`stagger-5`

### 图标
**lucide-vue-next only.** 禁止新增内联 SVG。已有内联 SVG 保留。

### 共享组件（必须使用，禁止重新实现）
| Component | Path | Purpose |
|-----------|------|---------|
| `PageHeader` | `src/components/PageHeader.vue` | 页面标题区 |
| `EmptyState` | `src/components/EmptyState.vue` | 空状态展示 |
| `ConfirmDialog` | `src/components/ConfirmDialog.vue` | 危险操作确认 |
| `LoadingSpinner` | `src/components/LoadingSpinner.vue` | 加载指示器 |
| `ToastContainer` | `src/components/ToastContainer.vue` | Toast 通知 |

### 业务常量
统一定义在 `src/constants/maps.ts`：`domainMap` (10领域), `levelMap` (6层次), `roleMap`, `roleShortMap`, `resourceTypeMap`。禁止在视图文件中重复定义。

### 状态持久化
Auth store 持久化到 localStorage：`metaedu_token`, `metaedu_tenant_id`, `metaedu_role`, `metaedu_domain`

### 危险操作
必须使用 `ConfirmDialog` — 禁止点击即执行。

### 对话框
必须包含 `role="dialog"` + `aria-modal="true"`。应支持 Escape 关闭；如果对话框内存在复杂表单或多步交互，再补充 focus 管理。

### 禁止项
- ❌ 新增散落硬编码颜色值 → 优先使用 `var(--color-xxx)`
- ❌ 新增散落硬编码 z-index → 优先使用 `z-[var(--z-dialog)]`
- ❌ 任意新增字号 → 优先使用设计 Token
- ❌ 新增内联 SVG
- ❌ 在视图文件中重复定义业务映射
- ❌ 危险操作点击即执行

---

## 通用

### 提交前检查
- Python: `ruff check` 通过 + `mypy` 无错误
- TypeScript/Vue: `pnpm --filter @metaedu/web typecheck` 通过
- 两类文件同时修改时两个检查都要执行

更完整的验证矩阵见 `docs/engineering/rules/quality-gates.md`。

### 代码审查要点
- 是否遵循命名规范
- 是否有硬编码值需要抽取为常量
- 是否有重复代码可以复用现有实现
- 是否引入不必要的依赖
