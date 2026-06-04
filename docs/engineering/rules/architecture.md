# Architecture — 系统架构

> 详细文档见 [ARCHITECTURE.md](../../../ARCHITECTURE.md)

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI + SQLAlchemy 2 (async) + Pydantic v2 |
| 数据库 | PostgreSQL 16 + pgvector (1536维) + ltree |
| 前端 | Vue 3.5 + Vite 6 + Tailwind CSS 4 + Pinia 3 |
| 认证 | JWT (python-jose + bcrypt) + ContextVar 多租户 |
| LLM | MiniMax M2 / DeepSeek / Qwen (OpenAI-compatible) |
| Embedding | MiniMax emboir / SiliconFlow Qwen/Qwen3-Embedding-8B |
| 缓存/队列 | Redis 7 + Celery 5 |
| 存储 | MinIO (本地文件系统降级) |

## 包结构

```
packages/
├── server-python/       # FastAPI 后端
│   ├── app/contexts/   # DDD 业务上下文
│   │   ├── identity/    # 认证
│   │   ├── knowledge/  # 知识图谱
│   │   ├── document/   # 资源库（文件/文件夹/切片/管道）
│   │   ├── structured_data/  # 数据库（数据集/行/知识图谱）
│   │   ├── template/   # 数据要素模板
│   │   └── resource/   # 旧资源管理（保留）
│   └── tests/          # 后端测试套件（当前 pytest 可收集 81 tests）
├── web/               # Vue 3 前端
└── mcp-server/       # MCP 服务
```

## DDD 分层

每个上下文四层结构：

```
application/    # DTO (Pydantic) + 服务函数 + Celery 任务
domain/         # 实体、Repository 接口、枚举
infrastructure/ # SQLAlchemy ORM 模型 + Repository 实现
interfaces/api/ # FastAPI 路由 + 依赖注入
```

## API 端点

| 前缀 | 上下文 | 主要端点 |
|------|--------|----------|
| `/api/v1/auth` | 认证 | login, register, /me |
| `/api/v1/knowledge` | 知识 | CRUD, search, tree |
| `/api/v1/document` | 资源库 | folders, files, chunks, tasks |
| `/api/v1/structured-data` | 数据库 | datasets, rows, kg |
| `/api/v1/ai` | AI | /chat (RAG) |
| `/api/v1/templates` | 模板 | CRUD, AI 初始化, doc_type 检查 |

详见 [ARCHITECTURE.md](../../../ARCHITECTURE.md) 第 3 节

## 数据库 Schema

- **Schema**：`metaedu`
- **隔离**：所有表 `tenant_id` 列 + ContextVar 多租户隔离
- **向量**：pgvector 1536 维，HNSW 索引
- **全文**：tsvector (simple 分词器)
- **层级**：ltree 物化路径

详见 [ARCHITECTURE.md](../../../ARCHITECTURE.md) 第 4 节

## 核心流程

### 认证流程
```
请求 → HTTPBearer → get_current_user() → decode_token() → 验证用户 → 返回 current_user
```

### 多租户隔离
```
get_current_user() → set_tenant_context(tenant_id, domain, clearance) → get_tenant_id()
```
ContextVar 在 `app/shared/infrastructure/tenant_context.py`。**所有 DB 查询必须包含 `tenant_id` 过滤。**

### RAG 问答流程
```
用户问题 → Embedding → 3路并行召回 (pgvector + ILIKE + structured metadata)
→ FrequencyFusion → LLM 生成 + 来源引用 → 返回回答
LLM 降级链: minimax → deepseek → qwen
```

### 文档处理管道
```
上传 → parse → chunk → embed → index_tsv → extract_template → extract_kg
```
详见 [PRD](../../superpowers/specs/2026-05-15-document-pipeline-design.md)

## 关键跨文件模式

**Auth 依赖注入**: `current_user: dict = Depends(get_current_user)`，定义在 `contexts/identity/interfaces/api/dependencies.py`

**ORM 模型注册**: 所有模型必须在 `app/shared/infrastructure/models.py` 中 import，否则 `create_all` / Alembic 找不到表

**知识节点路径**: `parent_id` → 查父 `path` → 拼接 `{parent_path}.{node_id[:8]}`。无父节点时 `path = node_id[:8]`

**架构文档不是任务板**: `ARCHITECTURE.md` 维护长期架构、阶段约束和里程碑；当前任务状态统一维护在 `docs/engineering/current-work.md`。

## 新增 API 端点步骤

1. 确定上下文（或在 `app/contexts/` 下新建）
2. 在 `interfaces/api/router.py` 添加路由
3. 新 DB 表 → 在 `infrastructure/models.py` 添加 Model + Alembic migration + 在 `shared/infrastructure/models.py` import
4. 需要认证 → `current_user: dict = Depends(get_current_user)`
5. 需要租户隔离 → `get_tenant_id()`
6. 在 `app/main.py` 中 `app.include_router()`
7. 在 `tests/contexts/` 添加测试

新增端点时避免在 router 中沉积复杂业务逻辑。Router 负责认证、参数解析和响应映射；业务流程优先放在 application service 或 repository 中。

## 新增业务上下文

```
app/contexts/{new_context}/
├── application/        # DTO + Service + Tasks
├── domain/             # Entity + Repository interface
├── infrastructure/     # ORM Model + Repository
└── interfaces/api/     # Router
```
然后在 `main.py` 注册 router，在 `shared/infrastructure/models.py` import model。
