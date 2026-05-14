# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作提供指引。

## 常用命令

```bash
# 启动全部服务（幂等 —— 已运行的自动跳过）
./dev.sh              # PostgreSQL + Redis + MinIO + FastAPI + Vite
./dev.sh infra        # 仅基础设施
./dev.sh stop         # 停止全部
./dev.sh status       # 查看运行状态

# 后端
cd packages/server-python && make dev     # uvicorn --reload 监听 8000 端口
cd packages/server-python && make lint    # ruff check + mypy
cd packages/server-python && make test    # pytest -v（49 个测试）
cd packages/server-python && make migrate # alembic upgrade head

# 前端
cd packages/web && pnpm dev              # Vite HMR 监听 3000 端口
cd packages/web && npx vue-tsc --noEmit  # TypeScript 类型检查

# MCP 服务
cd packages/mcp-server && make dev

# 根目录
pnpm install          # 安装所有工作区依赖
turbo run lint        # 全仓库 lint
turbo run build       # 全仓库构建
```

## 架构

基于 pnpm workspaces + Turborepo 的 Monorepo，包含四个包：

```
packages/server-python/   FastAPI + SQLAlchemy 2 (异步) + DDD 分层
packages/web/             Vue 3.5 + Tailwind CSS 4 + Vite 6
packages/shared/          前后端共享 TypeScript 类型（Zod schemas）
packages/mcp-server/      MCP stdio 服务（6 个知识操作 Tool）
```

### 后端：DDD 分层架构

每个业务上下文位于 `app/contexts/{name}/`，四层结构：

```
application/        DTO + 服务函数（无状态业务逻辑）
domain/             实体、Repository 接口、枚举（KnowledgeDomain、KnowledgeLevel）
infrastructure/     SQLAlchemy ORM 模型（表定义）
interfaces/api/     FastAPI 路由 + 依赖注入（get_current_user）
```

**上下文**：`identity`（认证/JWT）、`knowledge`（知识点 CRUD + embedding）、`resource`（文件上传），以及 `ai`（RAG 问答，位于 knowledge 的 interfaces 中）。

**共享基础设施**（`app/shared/`）：数据库引擎、会话工厂、租户上下文（ContextVar）、种子数据、DDD 基类。

- PostgreSQL 16 + `pgvector`（1536 维向量）+ `ltree`（物化路径层级结构）
- 所有表在 `metaedu` schema 下，通过 `tenant_id` 列 + ContextVar 实现多租户行级隔离
- 认证：JWT（`python-jose` + `passlib[bcrypt]`），依赖注入 `get_current_user`
- LLM：兼容 OpenAI 接口的提供商（MiniMax M2 → DeepSeek → Qwen 降级链）
- Embedding：DashScope API（BAAI/bge-m3，1536 维）
- 测试使用 NullPool（每次请求新连接），独立 `metaedu_test` 数据库

### 前端：Vue 3 SPA

- Vite 代理 `/api` → `localhost:8000`
- 状态管理：Pinia stores（auth、knowledge）
- 样式：Tailwind CSS 4，设计 Token 定义在 `src/assets/css/main.css` 的 `@theme` 块
- 设计体系："Liquid Glass" 毛玻璃风格，颜色/间距/z-index/动效全部 Token 化
- 组件自动按需导入（unplugin-vue-components，扫描 `src/components/ui/` 和 `src/components/business/`）
- Vue API 自动导入（unplugin-auto-import：vue、vue-router、pinia、@vueuse/core）

### API 端点速查

| 前缀 | 上下文 |
|---|---|
| `/api/v1/auth` | 登录、注册、`/me` |
| `/api/v1/knowledge` | 知识点 CRUD、搜索、树形结构 |
| `/api/v1/ai` | RAG 对话 |
| `/api/v1/resources` | 文件上传/下载/删除 |
| `/api/v1/health` | 健康检查 |

## 关键约定

### Git 工作流
- **main 分支受保护** — pre-push hook 拦截直接推送，必须通过功能分支 + PR 合入
- **Conventional Commits 强制校验**（`commit-msg` hook）：`type(scope): description`
  - type：feat、fix、docs、style、refactor、perf、test、build、ci、chore、revert
  - scope：web、server、knowledge、identity、resource、deploy、shared、mcp
- pre-commit hook 对暂存的 `.py` 文件执行 `ruff check`，对 `.ts`/`.vue` 文件执行 `vue-tsc --noEmit`

### 开发流程
- **优先阅读 ARCHITECTURE.md** 了解全局 —— 它是 API 端点、数据库 schema、核心流程的权威参考
- 简单任务（bug 修复、小功能、UI 微调）：**Plan-Do 模式** —— 先出变更方案，确认后实施，typecheck/lint/test 验证
- 复杂任务（>3 个文件、schema 变更、新端点）：**Spec 模式** —— 需求规格 → 技术设计 → 任务拆解 → 逐步实施 → 验证
- 修改 router.py / models.py / config.py 后：同步更新 ARCHITECTURE.md 和 README.md

### 前端强制约定
- **使用设计 Token**，禁止硬编码颜色/z-index —— Token 定义在 `src/assets/css/main.css` 的 `@theme` 块
- **复用共享组件**：`PageHeader`、`EmptyState`、`ConfirmDialog`、`LoadingSpinner`、`ToastContainer`
- **危险操作必须经 `ConfirmDialog`** 二次确认，禁止点击即执行
- **操作反馈通过 `useToast()`**：`success()`、`error()`、`warning()`、`info()`
- **图标**：仅使用 `lucide-vue-next`，禁止新增内联 SVG
- **业务常量**统一定义在 `src/constants/maps.ts` —— 专业域映射、层级映射、角色映射、资源类型映射

### 后端强制约定
- Schema：`metaedu`，所有表通过 `tenant_id` 列实现租户隔离
- 认证：路由参数中注入 `current_user = Depends(get_current_user)`，查询时调用 `get_tenant_id()` 获取当前租户
- 路由注册：在 `main.py` 中 `app.include_router(router, prefix="/api/v1/{context}")`
- 测试：conftest.py 使用 NullPool 策略，mock 外部服务（LLM、Embedding），使用 uuid 生成唯一测试数据

## 权威参考文档

| 文件 | 内容 |
|---|---|
| `ARCHITECTURE.md` | 完整 API 端点表、数据库 schema、核心流程（RAG、认证）、枚举值、测试分布、技术债务、演化路线 |
| `.trae/rules/project_rules.md` | 完整编码规范、设计 Token 参考、组件目录、Git 工作流细节 |
| `README.md` | 快速开始、环境要求、部署总览 |
