# Architecture — 架构实现约束

长期架构地图见 `ARCHITECTURE.md`。本文件只补充实现侧边界和代码定位。

## 系统结构速查

| 区域 | 位置 | 说明 |
|------|------|------|
| Web App | `packages/web` | Vue 前端应用与页面交互 |
| Backend | `packages/server-python/app` | FastAPI、领域服务、任务编排、数据访问 |
| Tests | `packages/server-python/tests` | 后端 pytest 套件 |
| Shared | `packages/shared` | 前端共享 schema / type / helper |
| MCP Server | `packages/mcp-server` | 外部 AI 工具接入层 |

## 后端上下文结构

```text
app/contexts/{context}/
├── application/        # DTO、service、任务编排
├── domain/             # 实体、值对象、仓储接口、领域规则
├── infrastructure/     # ORM model、仓储实现、外部适配
└── interfaces/api/     # router、依赖注入、响应映射
```

长期上下文：`identity`、`knowledge`、`document`、`structured_data`、`template`、`resource`。

## 长期实现约束

- Router 保持轻量：只做认证、参数解析、异常映射和响应映射；复杂流程进 service / repository。
- 多租户隔离是默认前提；查询、写入、后台任务都要带租户边界。
- 新增 ORM model 时，同步 migration、model 注册和数据完整性约束。
- 文档 / 数据集异步链路在删除、重试、重新初始化时必须有派生数据清理与重建策略。
- API DTO、前端 service DTO、shared schema/type 变化时，按 `contracts.md` 同步。

## 详细事实源

| 内容 | 位置 |
|------|------|
| 系统边界、关键流转、质量属性 | `ARCHITECTURE.md` |
| API / DTO / shared schema | `01-rules/contracts.md` |
| 本地启动和命令 | `01-rules/local-development.md` |
| 测试策略 | `01-rules/testing.md` |
| 数据完整性 | `01-rules/data-integrity.md` |
| 当前任务 | `current-work.md` |
| 实际接口 / 数据模型 | router、Pydantic DTO、SQLAlchemy models、Alembic migrations |

## 何时更新 ARCHITECTURE.md

只有系统边界级变化才更新：新增 / 删除 / 重定义 bounded context，改变核心运行单元、主要集成关系、系统级关键流程、长期质量属性或数据所有权边界。

新增端点、字段、索引、表、命令、局部实现细节不更新顶层架构，改对应事实源。

## 新增 API / 模型 / 上下文检查

- API：确认 context；router 轻量；认证、租户、错误语义一致；同步 DTO / shared schema / 前端 service；补测试。
- 模型 / 迁移：明确数据归属；同步 migration、model 注册、完整性约束；影响清理流程时补验证。
- 新上下文：使用 `application / domain / infrastructure / interfaces` 骨架；更新 `ARCHITECTURE.md` 的边界与职责。
