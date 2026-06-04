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
