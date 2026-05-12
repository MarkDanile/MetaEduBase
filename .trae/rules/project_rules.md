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

## 代码约定

### 后端 (Python)
- 框架：FastAPI + SQLAlchemy 2 (async) + Pydantic v2
- 路由注册：app/main.py 中 include_router，prefix = /api/v1/{context}
- 数据库：schema 名 metaedu，所有表在 metaedu schema 下
- 认证：JWT + ContextVar (tenant_context.py) 多租户隔离
- 测试：pytest-asyncio，NullPool 策略，conftest.py 中统一 fixture
- 运行检查：`cd packages/server-python && make lint && make test`

### 前端 (Vue3)
- 设计体系：Liquid Glass 风格，CSS 变量定义在 src/assets/css/main.css
- 组件类：glass / glass-heavy / glass-subtle / liquid-card / liquid-input / liquid-btn / liquid-tag / liquid-dialog
- 布局：LayoutView.vue 提供左侧栏导航，路由嵌套在 / 下
- API 层：src/services/api.ts (axios + interceptor) + src/services/knowledge.ts (业务 API)
- 状态管理：Pinia stores/auth.ts
- 运行检查：`cd packages/web && npx vue-tsc --noEmit`

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
| 改前端设计体系 | packages/web/src/assets/css/main.css |
| 改前端路由 | packages/web/src/app/router.ts |
| 改前端布局 | packages/web/src/views/LayoutView.vue |

## 验证命令

- 后端类型检查 + 测试：`cd packages/server-python && make lint && make test`
- 前端类型检查：`cd packages/web && npx vue-tsc --noEmit`
- 后端启动：`cd packages/server-python && make dev` (端口 8000)
- 前端启动：`cd packages/web && npm run dev` (端口 3000)
- 基础设施：`cd deploy && docker compose -f docker-compose.dev.yml up -d`
