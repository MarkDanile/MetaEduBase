# Architecture — 架构实现约束

> 长期架构地图见 [ARCHITECTURE.md](../../../ARCHITECTURE.md)。本文件补充实现侧约束、代码定位方式和修改边界。

## 本文件关注什么

- 代码层面的上下文划分与目录定位
- 跨模块实现约束
- 什么时候应该更新 `ARCHITECTURE.md`
- 新增上下文、端点、模型时的最小检查项

不在这里维护全量 API 表、数据库字段清单或固定测试数量。

## 系统结构速查

| 区域 | 位置 | 说明 |
|------|------|------|
| Web App | `packages/web` | Vue 前端应用与页面交互 |
| Backend | `packages/server-python/app` | FastAPI、领域服务、任务编排、数据访问 |
| Tests | `packages/server-python/tests` | 后端 pytest 套件 |
| Shared | `packages/shared` | 前端共享 schema / type / helper |
| MCP Server | `packages/mcp-server` | 外部 AI 工具接入层 |

## 后端上下文结构

后端默认按 bounded context 组织：

```text
app/contexts/{context}/
├── application/        # DTO、service、任务编排
├── domain/             # 实体、值对象、仓储接口、领域规则
├── infrastructure/     # ORM model、仓储实现、外部适配
└── interfaces/api/     # router、依赖注入、响应映射
```

当前长期存在的上下文包括：

- `identity`
- `knowledge`
- `document`
- `structured_data`
- `template`
- `resource`（历史兼容上下文）

## 长期实现约束

### 1. Router 保持轻量

router 负责认证、参数解析、异常映射和响应映射；复杂业务流程优先放到 application service 或 repository，不要把业务编排堆在路由层。

### 2. 多租户隔离是默认前提

所有查询、写入和后台任务都必须带着租户边界思考。不要把隔离逻辑留给调用方“自己记得做”。

### 3. 模型注册必须完整

新增 ORM model 时，除了定义 model 和 migration，还要确保共享模型注册入口可见；否则迁移和 metadata 装配会不完整。

### 4. 异步任务要有清理边界

文档 / 数据集等异步处理链路在删除、重试、重新初始化时必须有一致的派生数据清理与重建策略。

### 5. 契约变更要显式同步

API DTO、前端 service DTO、shared schema/type 之间有任意一处变化时，按 `docs/engineering/rules/contracts.md` 同步，而不是只在某一端静默修改。

## 详细事实源在哪里

| 你想查的内容 | 去哪里看 |
|--------------|----------|
| 系统边界、关键流转、质量属性 | `ARCHITECTURE.md` |
| API / DTO / shared schema 规则 | `docs/engineering/rules/contracts.md` |
| 本地启动和常用命令 | `docs/engineering/rules/local-development.md` |
| 测试策略 | `docs/engineering/rules/testing.md` |
| 数据完整性与级联清理 | `docs/engineering/rules/data-integrity.md` |
| 当前任务与交接状态 | `docs/engineering/current-work.md` |
| 实际接口清单 | router、Pydantic DTO、OpenAPI 文档 |
| 实际数据模型 | SQLAlchemy models、Alembic migrations |

## 何时更新 ARCHITECTURE.md

只有下面这些变化，才应该同步顶层 `ARCHITECTURE.md`：

- 新增、删除或重定义 bounded context
- 改变核心运行单元或主要集成关系
- 改变系统级关键流程
- 改变长期质量属性或数据所有权边界

如果只是新增端点、字段、索引、表、命令或局部实现细节，不更新 `ARCHITECTURE.md`，改对应事实源即可。

## 新增 API / 模型 / 上下文的最小检查项

### 新增 API

1. 先确认属于哪个 context。
2. router 只承载入口职责，不沉积复杂业务编排。
3. 认证、租户边界和错误语义保持一致。
4. 同步相关 DTO / shared schema / 前端 service。
5. 补相关测试与验证记录。

### 新增模型或迁移

1. 明确数据归属属于哪个 context。
2. 同步 migration、model 注册和数据完整性约束。
3. 如果影响删除、重试、重新初始化流程，补清理验证。
4. 若只是局部结构变化，不更新顶层架构文档。

### 新增业务上下文

1. 使用统一的 `application / domain / infrastructure / interfaces` 目录骨架。
2. 在 `ARCHITECTURE.md` 更新新的系统边界与职责。
3. 在必要时更新 `README.md` 的仓库导航或系统快照。
