# MetaEduBase 项目规则

## 项目概览

- 定位：AI Native 职业教育知识基座
- 技术栈：FastAPI + SQLAlchemy2 (后端) / Vue3 + Vite + Tailwind4 (前端) / PostgreSQL 16 + pgvector (数据库)
- 架构模式：DDD 分层 (contexts/{name}/application + domain + infrastructure + interfaces/api)
- 详细架构参考：项目根目录 ARCHITECTURE.md

## 开发模式选择规则

根据任务复杂度自动选择开发模式：

### Plan-Do 模式（默认）

适用于：bug 修复、小功能迭代、UI 调整、配置变更、单文件改动

流程：
1. **Plan**：输出变更方案，列出影响文件、改动点、风险
2. **等待确认**：用户回复 `ok` / `执行` / 调整意见
3. **Do**：按确认方案实施，逐步标记 todo 完成
4. **验证**：运行 typecheck / lint / test 确认无回归

### Spec 模式（复杂功能）

适用于：新功能模块（>3 个文件）、数据库 schema 变更、API 新端点、跨上下文改动、架构级重构

流程：
1. **Requirements**：输出需求规格 — 用户故事 + 验收标准 + 边界条件
2. **等待确认**
3. **Design**：输出技术设计 — 数据模型 + API 契约 + 模块依赖 + 错误处理策略
4. **等待确认**
5. **Tasks**：输出任务拆解 — 有序任务列表 + 依赖关系 + 预估影响范围
6. **等待确认**
7. **Implement**：按任务顺序逐个实施，每完成一个标记 todo
8. **Verify**：运行 typecheck + lint + test，确认所有通过

触发 Spec 模式的关键词：`spec 模式` / `规格驱动` / `先出 spec`

## 工程行为准则

基于 Karpathy Skills 编码规范，偏向谨慎而非速度。简单任务可酌情放松。

### 1. 先想后写（Think Before Coding）

**不要假设，不要隐藏困惑，暴露权衡。**

实施之前：
- 明确陈述假设。不确定就问。
- 存在多种解读时，全部呈现——不要静默选择。
- 如果有更简单的方案，说出来。必要时反驳。
- 不清楚就停下，指出困惑点，然后问。

### 2. 极简主义（Simplicity First）

**解决问题的最少代码。不做投机性扩展。**

- 不添加未被要求的功能。
- 单次使用的代码不做抽象。
- 不添加未被要求的"灵活性"或"可配置性"。
- 不处理不可能发生的错误场景。
- 如果写了 200 行但 50 行就能搞定，重写。

自问："资深工程师会说这太复杂了吗？"如果是，简化。

### 3. 手术式改动（Surgical Changes）

**只改必须改的。只清理自己弄乱的。**

编辑现有代码时：
- 不"改善"相邻代码、注释或格式。
- 不重构没坏的东西。
- 匹配现有风格，即使你不会这么做。
- 发现无关死代码，提一下——不要删。

你的改动产生孤儿时：
- 删除你的改动使其不再需要的 import / 变量 / 函数。
- 不删除预先存在的死代码，除非被要求。

检验标准：每一行变更都应能追溯到用户的需求。

### 4. 目标驱动执行（Goal-Driven Execution）

**定义成功标准，循环直到验证通过。**

将任务转化为可验证目标：
- "添加校验" → "为无效输入写测试，然后让测试通过"
- "修复 bug" → "写一个能复现的测试，然后让测试通过"
- "重构 X" → "确保重构前后测试都通过"

多步任务，先简述计划：
```
1. [步骤] → 验证: [检查方式]
2. [步骤] → 验证: [检查方式]
3. [步骤] → 验证: [检查方式]
```

强成功标准让你独立循环。弱标准（"让它工作"）需要不断确认。

## 上下文优先规则

新对话或需要重新扫描代码时，**必须先阅读以下两个文档**建立项目全局认知，避免盲目搜索代码：

1. **ARCHITECTURE.md** — 项目根目录，包含完整架构、API 端点、数据库 schema、核心流程、技术债务、演化方案
2. **README.md** — 项目根目录，包含快速开始、技术栈、项目结构、环境变量

优先级：ARCHITECTURE.md > README.md > SearchCodebase 逐文件扫描

## 文档同步规则

每次向 GitHub 提交代码（commit / PR）时，**必须同步检查并更新以下文档**：

| 文档 | 更新时机 |
|---|---|
| ARCHITECTURE.md | 新增/修改 API 端点、数据库 schema 变更、核心流程变化、新增业务上下文、技术栈变更 |
| README.md | 新增特性、启动方式变更、项目结构变化、环境变量增减 |

判断逻辑：
- 改了 router.py → 更新 ARCHITECTURE.md 的 API 端点表
- 改了 models.py → 更新 ARCHITECTURE.md 的数据库 schema
- 改了 config.py / .env → 更新 README.md 的环境变量表 + ARCHITECTURE.md 的配置项表
- 新增业务上下文 → 两个文档都更新项目结构部分
- 纯前端 UI 调整无 API/schema 变化 → 无需更新文档

## 代码约定

### 后端 (Python)
- 框架：FastAPI + SQLAlchemy 2 (async) + Pydantic v2
- 路由注册：app/main.py 中 include_router，prefix = /api/v1/{context}
- 数据库：schema 名 metaedu，所有表在 metaedu schema 下
- 认证：JWT + ContextVar (tenant_context.py) 多租户隔离
- 测试：pytest-asyncio，NullPool 策略，conftest.py 中统一 fixture
- 运行检查：`cd packages/server-python && make lint && make test`

### 前端 (Vue3) — 综合开发约定

#### 技术栈与运行

- 框架：Vue 3.5 + TypeScript 5.8 + Vite 6
- 样式：Tailwind CSS 4，设计 Token 定义在 `src/assets/css/main.css` 的 `@theme` 块
- 状态管理：Pinia 3 (`src/stores/`)
- 图标：**lucide-vue-next**，禁止新增内联 SVG 图标
- 运行检查：`cd packages/web && npx vue-tsc --noEmit`

#### 设计 Token 体系（main.css @theme）

必须使用 Token，禁止硬编码颜色值。核心 Token 列表：

| Token 类别 | 关键变量 | 用法 |
|---|---|---|
| 颜色 | `--color-ink` / `--color-accent` / `--color-accent-bg` / `--color-accent-glow` | 文字/强调/背景/hover |
| 字号 | `--text-page-title` (24px) / `--text-section-title` (18px) / `--text-body` (14px) / `--text-caption` (13px) / `--text-small` (12px) / `--text-micro` (11px) | 页面标题/区块标题/正文/辅助文字/小字/极小字 |
| 间距 | `--spacing-page` (32px) / `--spacing-section` (24px) / `--spacing-card` (16px) | 页面级/区块级/卡片级 |
| z-index | `--z-sidebar` (10) / `--z-drawer` (30) / `--z-dialog` (40) / `--z-toast` (50) | 侧边栏/抽屉/弹窗/通知 |
| 圆角 | `--radius-sm` / `--radius-md` / `--radius-lg` / `--radius-xl` | 逐级递增 |
| 阴影 | `--shadow-sm` / `--shadow-md` / `--shadow-lg` | 逐级递增 |
| 动效 | `--duration-instant/fast/normal/slow/liquid` + `--ease-out/elastic` | 按交互强度选择 |

**禁止项**：
- ❌ 硬编码 `#3B82F6`、`#EFF6FF`、`#DBEAFE` 等颜色值 → 使用 `var(--color-accent)` / `var(--color-accent-bg)` / `var(--color-accent-glow)`
- ❌ 硬编码 `z-index: 10/40/50` → 使用 `z-[var(--z-sidebar)]` / `z-[var(--z-dialog)]` / `z-[var(--z-toast)]`
- ❌ 任意字号 `text-[17px]` → 使用最接近的 Token 字号

#### 组件复用规则

**已有共享组件必须优先使用，禁止重复实现**：

| 组件 | 路径 | 用途 |
|---|---|---|
| `PageHeader` | `src/components/PageHeader.vue` | 页面标题区（title + subtitle + wet-line + 插槽） |
| `EmptyState` | `src/components/EmptyState.vue` | 空状态（自定义图标 + 标题 + 提示 + 操作插槽） |
| `ConfirmDialog` | `src/components/ConfirmDialog.vue` | 确认弹窗（v-model、danger 样式、ARIA、Escape 关闭、焦点回弹） |
| `LoadingSpinner` | `src/components/LoadingSpinner.vue` | 加载中 Spinner |
| `ToastContainer` | `src/components/ToastContainer.vue` | 全局 Toast 通知容器（已挂载在 App.vue） |

新增页面时，标题区必须使用 `PageHeader`，空状态必须使用 `EmptyState`，加载状态必须使用 `LoadingSpinner`。

#### Composable 复用规则

| Composable | 路径 | 用途 |
|---|---|---|
| `useToast` | `src/composables/useToast.ts` | 全局 Toast 通知 |

使用方式：
```typescript
const { success, error, warning, info } = useToast();
success("操作成功");
error("操作失败");
```

**操作反馈规则**：创建、删除、上传等操作完成后，必须调用 `useToast` 给出反馈。

#### 常量管理规则

**业务映射常量统一定义在 `src/constants/maps.ts`，禁止在视图文件中重复定义**：

| 常量 | 用途 |
|---|---|
| `domainMap` | 专业域映射（10 个域） |
| `levelMap` | 知识层级映射（6 级） |
| `roleMap` | 角色全称映射 |
| `roleShortMap` | 角色简称映射（首页问候语用） |
| `resourceTypeMap` | 资源类型映射 |

#### 图标使用规则

- **使用 lucide-vue-next**：`import { BookOpen, Plus, Trash2 } from "lucide-vue-next"`
- **禁止新增内联 SVG**：不允许在模板中写 `<svg>` 或在 JS 中写字符串 SVG 传给 `v-html`
- **已有内联 SVG 可保留**：历史代码中的内联 SVG 不强制迁移，但新增代码必须用 lucide
- **侧边栏导航图标**：已全部迁移为 lucide 组件，通过 `:is` 动态渲染

#### 危险操作规则

删除、批量操作等不可逆操作，**必须使用 `ConfirmDialog` 二次确认**，禁止点击即执行。

#### 布局规则

- 侧边栏：可折叠（60px / 200px），通过 `collapsed` ref 控制
- 主内容区：必须带 `id="main-content"`（供 skip-to-content 链接跳转）
- 页面标准容器：`<div class="p-8 max-w-[1000px] mx-auto">`
- 知识库 Master-Detail：左侧列表 + 右侧 360px 抽屉面板（`drawer-slide` 过渡）

#### 表单交互规则

- 弹窗对话框：必须有 `role="dialog"` + `aria-modal="true"` + `@keydown.escape` 关闭
- 文件上传：必须支持拖拽（`@dragover` / `@dragleave` / `@drop`）+ 进度条
- 长文本输入：使用 `<textarea>` + `autoResize` 自动高度，Enter 提交，Shift+Enter 换行
- LLM 请求：必须提供 AbortController 停止生成按钮

#### 可访问性规则

- 弹窗：`role="dialog"` / `role="alertdialog"` + `aria-modal` + `aria-labelledby` + `@keydown.escape`
- 焦点管理：弹窗打开时 trap 焦点，关闭后回弹到触发元素
- 按钮：危险操作按钮必须有 `aria-label`
- skip-to-content：App.vue 已提供，主内容区必须有 `id="main-content"`
- `prefers-reduced-motion`：动效组件必须提供降级（animation: none）

#### 服务层规则

- **认证 API**：`src/services/auth.ts`（authApi）
- **知识 API**：`src/services/knowledge.ts`（knowledgeApi）
- **通用 HTTP**：`src/services/api.ts`（axios + interceptor）
- 按领域拆分，禁止将无关 API 混在同一文件

#### 状态持久化规则

auth store 的 `userRole` 和 `userDomain` 必须持久化到 localStorage，刷新后不丢失。key 列表：
- `metaedu_token` — JWT Token
- `metaedu_tenant_id` — 租户 ID
- `metaedu_role` — 用户角色
- `metaedu_domain` — 专业域

#### CSS 类名约定

| 类名 | 用途 |
|---|---|
| `liquid-card` | 毛玻璃卡片 |
| `liquid-input` | 输入框 |
| `liquid-btn-primary` | 主按钮（渐变蓝） |
| `liquid-btn-ghost` | 幽灵按钮 |
| `liquid-btn-danger` | 危险按钮（红色） |
| `liquid-tag-blue/green/amber/purple` | 标签 |
| `liquid-dialog-overlay` + `liquid-dialog` | 弹窗 |
| `toast-container` + `toast-item` | Toast 通知 |
| `content-bg` | 内容区点阵背景 |
| `wet-line` | 渐变分割线 |
| `mesh-bg` | 多彩渐变背景 |
| `animate-slide-up` | 入场动画 |
| `stagger-1` ~ `stagger-5` | 交错入场延迟 |

### 通用
- 注释语言跟随用户最新消息语言
- 不主动创建 README / 文档文件
- 不主动 commit，除非用户明确要求
- 修改代码前必须先读取目标文件

## 关键文件定位速查

| 需求 | 定位 |
|---|---|
| 改 API 端点 | app/contexts/{name}/interfaces/api/router.py |
| 改业务逻辑 | app/contexts/{name}/application/ |
| 改数据模型 | app/contexts/{name}/domain/ |
| 改数据库基础设施 | app/shared/infrastructure/database.py, models.py |
| 改种子数据 | app/shared/infrastructure/seed.py |
| 改认证 | app/contexts/identity/application/auth_service.py |
| 改 AI/RAG | app/contexts/knowledge/interfaces/api/ai_router.py + application/embedding_service.py |
| 改前端页面 | packages/web/src/views/ |
| 改前端设计体系 / Token | packages/web/src/assets/css/main.css |
| 改前端路由 | packages/web/src/app/router.ts |
| 改前端布局 / 侧边栏 | packages/web/src/views/LayoutView.vue |
| 改前端共享组件 | packages/web/src/components/ |
| 改前端业务常量 | packages/web/src/constants/maps.ts |
| 改前端 Composable | packages/web/src/composables/ |
| 改前端 API 服务 | packages/web/src/services/ |
| 改前端状态管理 | packages/web/src/stores/ |

## 验证命令

- 后端类型检查 + 测试：`cd packages/server-python && make lint && make test`
- 前端类型检查：`cd packages/web && npx vue-tsc --noEmit`
- 后端启动：`cd packages/server-python && make dev` (端口 8000)
- 前端启动：`cd packages/web && npm run dev` (端口 3000)
- 基础设施：`cd deploy && docker compose -f docker-compose.dev.yml up -d`
