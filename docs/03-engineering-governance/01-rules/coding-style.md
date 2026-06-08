# Coding Style — 代码风格规范

## 文件规模与职责边界

新增或重构业务源码时，默认单文件不超过 500 行；超过 500 行必须在任务卡、spec 或 plan 中说明拆分理由、临时例外或后续拆分切片。超过 1000 行的文件不得继续承载新职责，除非本次任务就是拆分它或明确登记为例外。

- 一个文件只承担一个主要职责；视图、数据请求、状态编排、领域规则、基础设施适配优先分文件表达。
- 大需求或跨模块开发进入实现前，先给目标目录和文件结构，再生成代码。
- 修改已有超大文件时，优先抽出稳定小单元；如果本次无法拆分，至少不要继续扩大职责边界。
- 例外必须可解释：生成文件、lockfile、快照、静态大数据、数据库迁移、历史兼容样式和明确登记的工程脚本可以不受 500 行目标约束。
- 超大文件治理作为技术债登记和复盘，见 `docs/03-engineering-governance/technical-debt.md#td-032-治理超大源码文件并建立文件规模拆分原则`。
- 行数事实源与拆分状态：见 `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`。每切片交付后必须回写该基线。

### 拆分层级（TD-032）

按"职责 → 边界"提供可选拆法；不强制所有超大文件走同一套执行，但拆分方案至少要能解释为什么这样拆：

| 场景 | 推荐拆法 | 适用例子 |
|------|----------|----------|
| Celery 任务文件（任务编排 + 业务步骤混在一起） | 横切 helper 抽到 `app/shared/tasks/`；任务编排只负责拼装步骤 | `document/tasks.py`、`structured_data/tasks.py` |
| Router 聚合多个 endpoint | 按 `resource_type` 或 `action` 拆 `*_router.py` 子文件，主 router 暴露 namespace | `document/router.py` |
| 单一 Vue 视图承载多个独立 tab / 区块 | 把稳定区块（meta bar、pipeline status、tab content）抽成子组件；视图只剩编排 | `DatabaseView.vue`、`ResourceLibraryView.vue`、`TemplateModal.vue` |
| 大型 Python service 同时承担编排与基础设施调用 | 编排逻辑保留在 service；基础设施调用按 `repository` / `client` 拆出 | 与 TD-005 / TD-006 经验一致 |
| CSS / 工程脚本 | 拆模块文件 + 入口聚合；或拆配置与执行 | `main.css`（按 token / 组件 / 主题分文件） / `check_engineering_docs.py`（按检查类型分文件） |

### 开发顺序硬约束（TD-032）

大需求或跨模块开发进入实现前，**必须**先在 spec / plan 中给出目标目录和文件结构（含每个新文件预计承担什么、是否有横切 helper、是否需要把现有超大文件再切一档），再生成代码。如果发现 spec / plan 阶段没有给出文件结构，回退到 plan 阶段补完再开始写代码。

### 治理与切片记录（TD-032）

- 事实源：`docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`。
- 复盘频率与 `technical-debt.md#定期复盘规范` 一致；复盘输出至少要把 1-3 个 `⚪ 待切片` 推进到具体切片的 spec / plan，或升级为 `🔵 例外已登记` 并写明「后续切片计划」。
- 切片交付后必须回写基线：状态变化 / 行数变化 / 新增文件；不允许连续 2 个复盘周期无更新。

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

当前业务视图和共享组件优先使用语义化 `ui-*` workspace 层；`liquid-*` 类保留为历史兼容别名和少量品牌/装饰例外。新增或修改 UI 时，优先复用 `ui-*` 共享类；涉及 UI foundation 迁移时，先阅读对应设计/计划文档。

#### 迁移说明（TD-008）

`ui-*` 语义化 workspace 层是**新约定的优先选项**，`liquid-*` 类作为**历史兼容保留**。两者并存、不互相替代。

**何时使用 `ui-*`（优先）**

- 新的页面外壳、面板、工具栏、交互行。
- 跨页面共享的工作区结构（`LayoutView`、共享骨架组件）。
- 任何与"calm workspace、token 化、不带装饰动效"目标一致的容器。
- 表单输入、按钮、标签和对话框等跨页面原子控件。

提供以下 17 个共享类（`packages/web/src/assets/css/main.css` 中 `@layer components` 段）。

**容器层（5 个，TD-008）**

| 类 | 用途 |
|------|------|
| `.ui-page-shell` | 页面外壳：`max-width: 1120px; margin: 0 auto; padding: var(--spacing-page); background: var(--color-bg-base)` |
| `.ui-page-section` | 页面内分区：`margin-top: var(--spacing-section)` |
| `.ui-panel` | 通用面板容器：白底、细边框、token 化阴影、克制 hover 反馈 |
| `.ui-toolbar` | 工具栏行：白底、细边框、12px 圆角 |
| `.ui-interactive-row` | 列表/卡片行的统一 hover 状态机 |

**原子控件层（12 个，TD-027）**

| 类 | 用途 | 对应 `liquid-*` |
|------|------|----------------|
| `.ui-input` | 表单输入框：白底、细边框、focus 强调环 | `liquid-input` |
| `.ui-btn` | 按钮基类：inline-flex 居中、36px 高、8px 18px 内边距、token 化字体 | `liquid-btn` |
| `.ui-btn-primary` | 主按钮：径向渐变 + 点按泠漪、disabled 半透明 | `liquid-btn-primary` |
| `.ui-btn-ghost` | 次按钮：白底、细边框、hover 强调色填充 | `liquid-btn-ghost` |
| `.ui-btn-danger` | 危险按钮：danger 色背景、hover 加深 | `liquid-btn-danger` |
| `.ui-tag` | 标签基类：inline-flex 居中、2px 8px 内边距、11px 字号 | `liquid-tag` |
| `.ui-tag-blue` | 蓝色标签 | `liquid-tag-blue` |
| `.ui-tag-green` | 绿色标签 | `liquid-tag-green` |
| `.ui-tag-amber` | 琥珀色标签 | `liquid-tag-amber` |
| `.ui-tag-purple` | 紫色标签 | `liquid-tag-purple` |
| `.ui-dialog-overlay` | 对话框遮罩：fixed 全屏、半透明黑、`--z-dialog`、fade-in 动画 | `liquid-dialog-overlay` |
| `.ui-dialog` | 对话框本体：白底、token 化边框阴影、dialog-in 动画 | `liquid-dialog` |

**原子控件层与容器层的关系**：容器层（`ui-panel` / `ui-page-shell` 等）只表达结构，原子控件层（`ui-input` / `ui-btn-*` / `ui-tag-*` / `ui-dialog*`）只表达组件。两者可同时使用，例如：`<div class="ui-panel p-4"><input class="ui-input" /></div>`。

**何时保留 `liquid-*`（兼容）**

- `liquid-*` 在 `main.css` 中保留为兼容别名，避免历史页面或外部引用被破坏。
- `liquid-card` / `liquid-input` / `liquid-btn-*` / `liquid-tag-*` / `liquid-dialog*` 不作为新增代码的默认选择；业务视图和共享组件已通过 TD-025 / TD-028 迁到 `ui-*`。
- 装饰性 `wet-line` / `liquid-card-scan::after` / `liquid-rise-*` 动效保留；新页面不引入。
- 登录页（`LoginView`）的品牌背景与 `brand-gradient` 不参与 workspace 迁移。

**新增/修改 UI 的优先级**

1. 优先复用 `ui-*` 共享类。
2. 其次复用既有页面/组件的局部风格。
3. 不要新增与 `ui-*` 重复的散落样式。
4. 不要在视图文件里硬编码颜色/间距/z-index（见下方禁止项）。
5. 修改任何共享组件（`PageHeader` / `EmptyState` / `LayoutView` / `ui-*` 类）前，先确认所有调用方并补 typecheck 验证。

**第一个迁移目标**

`LayoutView.vue` + `PageHeader.vue` + `EmptyState.vue` 三个共享骨架组件已作为 TD-008 示例交付；业务页面容器层已由 TD-025 迁到 `ui-panel`，原子控件层已由 TD-027 / TD-028 迁到 `ui-*`。

#### 业务页面迁移清单（TD-025）

按业务残留量从高到低分切片迁移。每个切片独立 PR、独立验证。

| 切片 | 页面 | 状态 | 残留量（迁入前） | 备注 |
|------|------|------|------------------|------|
| 1 | `DatabaseView` | 🟢 完成 | 8 处 | 切片 1，含 1 个上传对话框、5 个内容卡、1 个数据集列表卡、1 个 KG 总览按钮 |
| 1 | `ResourceView` | 🟢 完成 | 1 处 | 切片 1，资源列表卡，保留 `animate-slide-up` + `stagger-N` 装饰动效 |
| 1 | `ResourceLibraryView` | 🟢 完成 | 3 处 | 切片 1，文件夹树、文件夹右键菜单、文件列表区 |
| 2 | `KnowledgeBaseView` | 🟢 完成 | 1 处 | 切片 2（任务卡残留量 16 处为 TD-008 完成时快照；切片 1 之后剩 1 处）。节点列表卡，保留 `ring-1 ring-[var(--color-accent)] ring-offset-2` 选中态、保留 `animate-slide-up` + `stagger-N` 装饰动效 |
| 2 | `FileDetailView` | 🟢 完成 | 3 处 | 切片 2（任务卡残留量 12 处为 TD-008 完成时快照；切片 1 之后剩 3 处）。文件元信息条、流水线状态、Tab 容器；未触动 `liquid-tag-*` / `liquid-btn-*` / 各 Tab 内部的 inline token 容器 |
| 3 | `TemplateModal` | 🟢 完成 | 0 处 | 切片 3（任务卡残留量 8 处为 TD-008 完成时快照；实测 0 处 `liquid-card` 残留。`TemplateModal` 实际只使用 `liquid-btn-*` / `liquid-input` / `liquid-tag-*`，按例外清单保持兼容） |
| 3 | `TemplateEditorView` | 🟢 完成 | 0 处 | 切片 3（任务卡残留量 6 处为 TD-008 完成时快照；实测 0 处 `liquid-card` 残留。`TemplateEditorView` 实际只使用 `liquid-btn-*` / `liquid-input` / `liquid-tag-*`，按例外清单保持兼容） |
| 3 | `AiChatView` | 🟢 完成 | 1 处 | 切片 3（任务卡残留量 4 处为 TD-008 完成时快照；实测 1 处 `liquid-card` 残留）。快速问题按钮卡 |
| 3 | `HomeView` | 🟢 完成 | 3 处 | 切片 3（任务卡残留量 3 处相符）。统计卡 / 导航模块卡 / 右侧活动区；统计卡保留 `liquid-card-scan` + `animationDelay` 装饰动效 |
| 例外 | `LoginView` | 🚫 保持兼容 | 0 处 | 品牌背景与 `--_login-brand-gradient`，按 TD-008 规则不参与 workspace 迁移 |
| 后续 | 共享组件 `FieldEditor` / `KGDetailPanel` / `ConfirmDialog` / `KGGraph` 的 `liquid-card` 残留 | 🟢 完成 | 0 处 | TD-026 实测 0 命中，原 22 处为快照误计 |

**历史例外与后续收口**

TD-025 切片 3 曾显式保留以下例外；其中原子控件类已在 TD-027 / TD-028 收口为 `ui-*`，装饰与品牌类仍保留兼容：

| 类别 | 状态 | 说明 |
|------|------|------|
| `liquid-btn-*` / `liquid-input` / `liquid-tag-*` / `liquid-dialog*` | 🟢 已收口 | TD-027 建 `ui-*` 等价类，TD-028 完成业务视图与共享组件存量替换 |
| `liquid-card-scan` | 🚫 保持兼容 | `HomeView` 统计卡装饰动效；`ui-panel` 提供容器，`liquid-card-scan` 仅提供装饰 |
| `stagger-N` / `animate-slide-up` | 🚫 保持兼容 | 历史入场动画，后续只在明确视觉需求下保留 |
| `LoginView` 品牌背景 | 🚫 保持兼容 | `login-card liquid-card` 与 `--_login-brand-gradient` 不参与 workspace 迁移 |

迁移规则：

- `liquid-card` 容器直接替换为 `ui-panel`，附加类（`group` / `animate-slide-up` / `stagger-N` / `liquid-card-scan` / 自定义 hover）原样保留。
- 业务页面和共享组件的按钮、输入框、标签、对话框优先使用 `ui-btn-*` / `ui-input` / `ui-tag-*` / `ui-dialog*`。
- `LoginView` 品牌背景不参与迁移。
- `liquid-card-scan::after` 装饰动效保留（`HomeView` 等页面仍在用）。
- `liquid` 主题下 `ui-panel` 会自动套用 `:root[data-theme="liquid"] .ui-panel` 玻璃感覆盖（复用 `--_surface-card-bg` + `--_surface-glass-blur`），其他 3 主题维持白底细边框。

#### 共享组件迁移清单（TD-026）

按残留量从高到低对 4 个共享组件做 `liquid-card` 残留验证。每个组件独立 PR、独立验证。**实测全部 0 处 `liquid-card` 残留**——这 4 个组件从未使用 `liquid-card` 容器；其原子控件类已在 TD-028 后迁到 `ui-*`。

| 组件 | 状态 | `liquid-card` 命中 | 备注 |
|------|------|-------------------|------|
| `FieldEditor` | 🟢 完成 | 0 处 | 原子控件已由 TD-028 迁到 `ui-input` / `ui-btn-ghost` |
| `KGDetailPanel` | 🟢 完成 | 0 处 | 原子控件已由 TD-028 迁到 `ui-btn-ghost` / `ui-tag-*` |
| `ConfirmDialog` | 🟢 完成 | 0 处 | 原子控件已由 TD-028 迁到 `ui-dialog*` / `ui-btn*` |
| `KGGraph` | 🟢 完成 | 0 处 | 无 `liquid-*` 用法（任务卡残留量"1 处 `liquid-card`"为误计） |

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

更完整的验证矩阵见 `docs/03-engineering-governance/01-rules/quality-gates.md`。

### 代码审查要点
- 是否遵循命名规范
- 是否有硬编码值需要抽取为常量
- 是否有重复代码可以复用现有实现
- 是否引入不必要的依赖
