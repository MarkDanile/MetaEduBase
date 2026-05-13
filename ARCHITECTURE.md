# MetaEduBase 架构 Wiki

> 本文档供 AI 辅助开发时快速定位代码，避免全盘扫描。最后更新: 2026-05-12

---

## 1. 项目概览

MetaEduBase（元知职教基座）是 AI-Native 职业教育知识平台，采用 **DDD（领域驱动设计）** 分层架构 + **多租户** 隔离。

| 技术栈 | 选型 |
|---|---|
| 后端框架 | FastAPI + SQLAlchemy 2 (async) |
| 数据库 | PostgreSQL 16 + pgvector |
| 异步驱动 | asyncpg |
| 缓存/队列 | Redis 7 + Celery |
| 对象存储 | MinIO（开发环境本地存储 fallback） |
| 认证 | JWT (python-jose + bcrypt) |
| LLM | MiniMax M2 / DeepSeek / Qwen (OpenAI 兼容接口) |
| Embedding | BAAI/bge-m3 via Qwen DashScope API, 1536 维 |
| MCP Server | mcp Python SDK (stdio transport) |
| 测试 | pytest + pytest-asyncio + httpx (NullPool 隔离) |
| Python | 3.14 |

---

## 2. 目录结构速查

```
MetaEduBase/
├── deploy/                          # 部署配置
│   ├── docker-compose.dev.yml       # PostgreSQL(pgvector) + Redis + MinIO
│   ├── init-db.sql                  # CREATE EXTENSION vector/ltree/uuid-ossp
│   └── .env.example
├── packages/
│   ├── server-python/               # ★ 核心后端
│   │   ├── app/
│   │   │   ├── main.py              # FastAPI 入口, 路由注册, lifespan
│   │   │   ├── config.py            # Settings (pydantic-settings, .env)
│   │   │   ├── celery_app.py        # Celery 配置 (autodiscover document tasks)
│   │   │   ├── contexts/            # ★ 业务上下文 (DDD bounded context)
│   │   │   │   ├── identity/        # 认证上下文
│   │   │   │   │   ├── application/auth_service.py   # 密码哈希/JWT 生成解码
│   │   │   │   │   ├── infrastructure/models.py      # UserModel, TenantModel
│   │   │   │   │   └── interfaces/api/
│   │   │   │   │       ├── router.py                 # /login, /register, /me
│   │   │   │   │       └── dependencies.py           # get_current_user 依赖注入
│   │   │   │   ├── knowledge/       # 知识上下文
│   │   │   │   │   ├── application/
│   │   │   │   │   │   ├── dto.py                    # Pydantic DTO (Create/Update/Search)
│   │   │   │   │   │   └── embedding_service.py      # 文本向量化 (DashScope API)
│   │   │   │   │   ├── domain/
│   │   │   │   │   │   ├── entities/knowledge_node.py # KnowledgeNode 聚合根 + 枚举
│   │   │   │   │   │   └── repositories.py            # 抽象 Repository 接口
│   │   │   │   │   ├── infrastructure/models.py      # KnowledgeNodeModel, KnowledgeEdgeModel
│   │   │   │   │   └── interfaces/api/
│   │   │   │   │       ├── router.py                 # CRUD /search /tree
│   │   │   │   │       └── ai_router.py              # /chat (RAG + LLM)
│   │   │   │   └── resource/        # 资源上下文
│   │   │   │       ├── infrastructure/models.py      # ResourceModel
│   │   │   │       └── interfaces/api/router.py      # 上传/列表/下载/删除
│   │   │   └── shared/              # 共享基础设施
│   │   │       ├── domain/          # DDD 基类 (Entity/AggregateRoot/Repository/ValueObject/DomainEvent)
│   │   │       └── infrastructure/
│   │   │           ├── database.py  # engine, get_session, init_db
│   │   │           ├── models.py    # 统一导入所有 ORM Model (确保 metadata 注册)
│   │   │           ├── seed.py      # 默认租户 + admin 种子数据
│   │   │           └── tenant_context.py # ContextVar 多租户上下文
│   │   ├── tests/                   # ★ 测试套件
│   │   │   ├── conftest.py          # 测试基础设施 (NullPool + 独立 test DB)
│   │   │   ├── contexts/
│   │   │   │   ├── identity/        # auth API + auth_service 单元测试
│   │   │   │   ├── knowledge/       # knowledge API + embedding_service mock 测试
│   │   │   │   ├── ai/              # AI chat + _clean_llm_output 测试
│   │   │   │   └── resource/        # 资源 CRUD 测试
│   │   │   └── shared/              # health check 测试
│   │   ├── .env                     # 环境变量 (不入库)
│   │   └── pyproject.toml           # 依赖 + pytest/ruff 配置
│   └── mcp-server/                  # MCP Server (独立进程)
│       └── mcp_server/main.py       # 6 个 Tool: search/tree/get/create/list_resources/generate_quiz
└── .vscode/settings.json            # Python 解释器路径
```

---

## 3. API 端点速查表

### 3.1 Identity 上下文 — `/api/v1/auth`

| 方法 | 路径 | 认证 | 功能 | 关键文件 |
|---|---|---|---|---|
| POST | `/login` | 无 | 登录，返回 JWT | [router.py](packages/server-python/app/contexts/identity/interfaces/api/router.py) |
| POST | `/register` | 无 | 注册新用户 | 同上 |
| GET | `/me` | Bearer | 获取当前用户信息 | 同上 |

### 3.2 Knowledge 上下文 — `/api/v1/knowledge`

| 方法 | 路径 | 认证 | 功能 | 关键文件 |
|---|---|---|---|---|
| GET | `/nodes` | Bearer | 列出知识节点 (支持 domain/parent_id 过滤) | [router.py](packages/server-python/app/contexts/knowledge/interfaces/api/router.py) |
| POST | `/nodes` | Bearer | 创建知识节点 (自动生成 embedding) | 同上 |
| GET | `/nodes/{id}` | Bearer | 获取单个节点 | 同上 |
| PATCH | `/nodes/{id}` | Bearer | 部分更新节点 | 同上 |
| DELETE | `/nodes/{id}` | Bearer | 删除节点 | 同上 |
| POST | `/search` | Bearer | 语义/关键词/混合搜索 | 同上 |
| GET | `/tree/{parent_id}` | Bearer | 获取树形结构 (parent_id="root" 为顶层) | 同上 |

### 3.3 AI Chat — `/api/v1/ai`

| 方法 | 路径 | 认证 | 功能 | 关键文件 |
|---|---|---|---|---|
| POST | `/chat` | Bearer | RAG 问答 (embedding检索→上下文注入→LLM生成) | [ai_router.py](packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py) |

### 3.4 Resource 上下文 — `/api/v1/resources`

| 方法 | 路径 | 认证 | 功能 | 关键文件 |
|---|---|---|---|---|
| POST | `/upload` | Bearer | 上传资源文件 (multipart) | [router.py](packages/server-python/app/contexts/resource/interfaces/api/router.py) |
| GET | `/` | Bearer | 列出资源 (支持 type/domain 过滤) | 同上 |
| GET | `/{id}` | Bearer | 获取资源详情 | 同上 |
| GET | `/{id}/download` | Bearer | 下载资源文件 | 同上 |
| DELETE | `/{id}` | Bearer | 软删除资源 (is_deleted=true) | 同上 |

### 3.5 Health — `/api/v1/health`

| 方法 | 路径 | 认证 | 功能 |
|---|---|---|---|
| GET | `/health` | 无 | 健康检查 |

---

## 4. 数据库 Schema (metaedu)

### 4.1 表关系图

```
tenants (1) ──< users (N)
tenants (1) ──< knowledge_nodes (N)
tenants (1) ──< knowledge_edges (N)
tenants (1) ──< resources (N)
users (1) ──< resources (N)       [uploaded_by]
knowledge_nodes (1) ──< knowledge_nodes (N)   [parent_id 自引用]
knowledge_nodes (1) ──< knowledge_edges (N)   [source_id / target_id]
```

### 4.2 表字段速查

#### `metaedu.tenants`

| 列名 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | 默认: `00000000-0000-0000-0000-000000000001` |
| name | VARCHAR(200) | 租户名 |
| school_name | VARCHAR(300) | 学校名 |
| isolation | VARCHAR(20) | 隔离模式: shared |
| is_active | BOOLEAN | |
| created_at / updated_at | TIMESTAMP | |

#### `metaedu.users`

| 列名 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | 默认 admin: `...00000002` |
| tenant_id | UUID FK→tenants | |
| username | VARCHAR(50) | UNIQUE(tenant_id, username) |
| email | VARCHAR(200) | nullable |
| password_hash | VARCHAR(200) | bcrypt |
| role | VARCHAR(30) | super_admin / teacher / ... |
| domain | VARCHAR(100) | 专业域, nullable |
| clearance_level | INTEGER | 0-5, 默认 0 |
| is_active | BOOLEAN | |

#### `metaedu.knowledge_nodes`

| 列名 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | |
| title | VARCHAR(200) | |
| description | TEXT | nullable |
| domain | VARCHAR(50) | 见 KnowledgeDomain 枚举 |
| level | VARCHAR(30) | 见 KnowledgeLevel 枚举 |
| parent_id | UUID FK→knowledge_nodes | nullable, 自引用 |
| path | VARCHAR(500) | 物化路径 (如 `abc12345.def67890`) |
| tags | JSONB | |
| metadata | JSONB | |
| embedding | VECTOR(1536) | pgvector, 可为 NULL |
| created_at / updated_at | TIMESTAMP | |

索引: `(tenant_id, domain)`, `(tenant_id, parent_id)`, `(tenant_id, level)`, `(path)`

#### `metaedu.knowledge_edges`

| 列名 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | |
| source_id | UUID FK→knowledge_nodes | |
| target_id | UUID FK→knowledge_nodes | |
| relation_type | VARCHAR(50) | |
| weight | FLOAT | 默认 1.0 |
| metadata | JSONB | |

索引: `(source_id)`, `(target_id)`

#### `metaedu.resources`

| 列名 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK→tenants | |
| title | VARCHAR(300) | |
| description | TEXT | nullable |
| resource_type | VARCHAR(30) | document/video/image/audio/other |
| status | VARCHAR(20) | raw/uploaded/processed |
| domain | VARCHAR(50) | nullable |
| knowledge_point_ids | UUID[] | ARRAY, nullable |
| file_size | INTEGER | nullable |
| file_type | VARCHAR(50) | nullable |
| storage_key | VARCHAR(500) | nullable |
| metadata | JSONB | |
| uploaded_by | UUID FK→users | |
| is_deleted | BOOLEAN | 软删除标记 |
| created_at / updated_at | TIMESTAMP | |

索引: `(tenant_id, resource_type)`, `(tenant_id, domain)`

### 4.3 枚举值

```python
# KnowledgeDomain (knowledge_node.py)
ELECTRONICS_INFO = "electronics_info"      # 电子与信息
SMART_MANUFACTURING = "smart_manufacturing" # 智能制造
FINANCE_COMMERCE = "finance_commerce"       # 财经商贸
MEDICAL_HEALTH = "medical_health"           # 医药健康
EDUCATION_SPORTS = "education_sports"       # 教育与体育
CIVIL_ENGINEERING = "civil_engineering"     # 土木建筑
TRANSPORTATION = "transportation"           # 交通运输
AGRICULTURE = "agriculture"                 # 农林牧渔
ART_DESIGN = "art_design"                   # 文化艺术
PUBLIC_SERVICE = "public_service"           # 公共管理

# KnowledgeLevel
PROFESSIONAL = "professional"               # 专业
COURSE = "course"                           # 课程
CHAPTER = "chapter"                         # 章节
KNOWLEDGE_POINT = "knowledge_point"         # 知识点
SKILL_POINT = "skill_point"                 # 技能点
OPERATION_STEP = "operation_step"           # 操作步骤
```

---

## 5. 核心流程

### 5.1 认证流程

```
请求 → HTTPBearer → get_current_user() → decode_access_token()
                                            ↓ 解析 sub(user_id) + tid(tenant_id)
                                       查 DB 验证用户存在且 is_active
                                            ↓
                                       set_tenant_context(tenant_id, domain, clearance)
                                            ↓ 返回 dict(row)
                                       后续端点通过 get_tenant_id() 获取租户 ID
```

关键文件:
- [dependencies.py](packages/server-python/app/contexts/identity/interfaces/api/dependencies.py) — `get_current_user` 依赖注入
- [auth_service.py](packages/server-python/app/contexts/identity/application/auth_service.py) — `verify_password`, `hash_password`, `create_access_token`, `decode_access_token`
- [tenant_context.py](packages/server-python/app/shared/infrastructure/tenant_context.py) — ContextVar 存租户上下文

### 5.2 RAG 问答流程 (ai_router.py)

```
/chat 请求
  ↓
get_embedding_vec(message)  ← embedding_service.py (DashScope API, 1536维)
  ↓ 成功?
├─ YES → SQL 语义检索: ORDER BY embedding <=> :vec::vector LIMIT 5
│         → 获取 contexts (id, title, desc, domain, level, score)
└─ NO  → 中文关键词拆分 (4-gram 滚动窗口, 最多8关键词)
         → ILIKE OR 模糊匹配 title/description
  ↓
拼接 system_prompt + context_text + 用户问题
  ↓
_call_llm() → 优先级: minimax → deepseek → qwen (OpenAI 兼容接口)
  ↓
_clean_llm_output() → 移除 考量...生成 / 思路...回复 / <think>...</think> 标签
  ↓
返回 ChatResponse(reply=..., sources=[...])
```

### 5.3 知识节点创建流程

```
POST /nodes (title, domain, level, parent_id?)
  ↓
若 parent_id → 查父节点 path → 拼接新 path = {parent_path}.{node_id[:8]}
否则 → path = node_id[:8]
  ↓
get_embedding(f"{title} {description}") → 可能为 None
  ↓
INSERT INTO knowledge_nodes (含/不含 embedding 字段)
  ↓
返回 KnowledgeNodeDTO
```

---

## 6. 上下文依赖关系

```
identity ←── knowledge ←── resource
   │            │
   │            └── ai (依赖 knowledge 的 embedding_service)
   │
   └── 所有认证端点通过 get_current_user 依赖注入
```

跨上下文依赖规则:
- **knowledge → identity**: 使用 `get_current_user` 依赖 (interfaces 层引用)
- **ai → identity**: 同上
- **ai → knowledge.application**: 使用 `get_embedding_vec` (embedding_service)
- **resource → identity**: 同上
- **shared → 无依赖**: 纯基础设施层，被所有上下文依赖

---

## 7. 测试体系

### 7.1 测试基础设施

| 项目 | 说明 |
|---|---|
| 测试数据库 | `metaedu_test` (独立库) |
| 连接策略 | **NullPool** — 每次请求新建连接, 避免 asyncpg 事件循环绑定问题 |
| 数据初始化 | 每个 `client` fixture 内: CREATE SCHEMA + create_all + ensure_seed |
| 种子数据 | 与生产相同: 默认租户 + admin/admin123 |
| 认证测试 | `auth_token` fixture 先 login 获取 token |

### 7.2 测试文件→端点映射

```
tests/
├── conftest.py                  # client, auth_token, auth_headers fixtures
├── contexts/
│   ├── identity/
│   │   ├── test_auth.py         # 9 tests: login/register/me (API)
│   │   └── test_auth_service.py # 5 tests: hash/verify/JWT (unit)
│   ├── knowledge/
│   │   ├── test_knowledge.py    # 15 tests: CRUD/search/tree (API)
│   │   └── test_embedding_service.py # 3 tests: mock (unit)
│   ├── ai/
│   │   └── test_ai_chat.py      # 5 tests: auth/clean/mock_llm
│   └── resource/
│       └── test_resource.py     # 10 tests: upload/list/get/download/delete
└── shared/
    └── test_health.py           # 1 test
```

**共计: 49 tests**

### 7.3 测试注意事项

- 注册测试使用 `uuid4().hex[:8]` 生成唯一用户名，避免测试间冲突
- 搜索测试用短查询词（如"汽车"而非"汽车维修"），因为 ILIKE `%汽车维修%` 无法匹配"汽车检测与维修技术"
- AI chat 测试用 mock 替换 `httpx.AsyncClient` 和 `get_embedding_vec`
- 未认证断言使用 `status_code in (401, 403)` 兼容 HTTPBearer 行为

---

## 8. 配置项速查 (config.py + .env)

| 配置项 | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `database_url` | DATABASE_URL | `postgresql+asyncpg://metaedu@localhost:5432/metaedu` | 异步连接串 |
| `jwt_secret` | JWT_SECRET | `dev-only-change-in-production` | JWT 签名密钥 |
| `jwt_expire_minutes` | JWT_EXPIRE_MINUTES | `1440` (24h) | Token 过期时间 |
| `llm_default_provider` | LLM_DEFAULT_PROVIDER | `minimax` | LLM 提供商 |
| `minimax_api_key` | MINIMAX_API_KEY | (空) | MiniMax Token Plan Key |
| `minimax_model` | - | `MiniMax-M2` | MiniMax 模型 |
| `qwen_api_key` | QWEN_API_KEY / DASHSCOPE_API_KEY | (空) | 用于 Embedding |
| `embedding_model` | - | `BAAI/bge-m3` | Embedding 模型 |
| `minio_endpoint` | - | `localhost:9000` | MinIO 地址 |

---

## 9. 开发新功能时快速定位指南

### "我要加一个新的 API 端点"

1. 确定属于哪个上下文 (identity/knowledge/resource 或新建)
2. 在 `interfaces/api/router.py` 中添加路由
3. 如需新 DB 表: 在 `infrastructure/models.py` 添加 Model + 在 `shared/infrastructure/models.py` 注册 import
4. 如需认证: 参数加 `current_user: dict = Depends(get_current_user)`
5. 如需租户隔离: 调用 `get_tenant_id()` 获取当前租户
6. 在 `main.py` 中 `app.include_router()` 注册路由
7. 在对应 `tests/contexts/` 下添加测试文件

### "我要改数据库 Schema"

1. 修改 `contexts/{name}/infrastructure/models.py` 中的 Model
2. 确保 `shared/infrastructure/models.py` 有 import
3. 运行 `python -c "from app.shared.infrastructure.database import init_db; import asyncio; asyncio.run(init_db())"` 或重启服务
4. **注意**: 当前无 Alembic 迁移，开发环境靠 `Base.metadata.create_all`

### "我要加新的 LLM 提供商"

1. 在 `config.py` 添加 `{provider}_api_key`, `{provider}_base_url`, `{provider}_model`
2. 在 `ai_router.py` 的 `_call_llm()` 函数中添加 provider 分支
3. 在 `.env` 中添加对应的 API Key

### "我要改 RAG 检索逻辑"

- 语义检索: `ai_router.py` 的 `ai_chat()` 中的 SQL 查询
- 关键词 fallback: 同文件中 `else` 分支的 ILIKE 查询
- Embedding 生成: `embedding_service.py` (get_embedding 函数)
- 搜索模式控制: `KnowledgeSearchDTO.search_mode` (semantic/keyword/hybrid)

### "我要加新的业务上下文"

```
app/contexts/{new_context}/
├── application/        # DTO + Service
├── domain/             # Entity + Repository 接口 (可选)
├── infrastructure/     # ORM Model
└── interfaces/api/     # Router
```

然后在 `main.py` 加 `app.include_router()`, 在 `shared/infrastructure/models.py` 加 import。

### "我要修改测试"

- **conftest.py** 是核心 — 修改前理解 NullPool 策略
- 测试数据库: `metaedu_test`, 种子数据与生产相同
- 测试间互不清理数据 → 用 uuid 生成唯一值
- Mock 外部服务（LLM、Embedding）而非调用真实 API

---

## 10. MCP Server

文件: `packages/mcp-server/mcp_server/main.py`

独立进程，通过 HTTP 调用后端 API，提供 6 个 Tool:

| Tool 名 | 功能 | 对应后端 API |
|---|---|---|
| `knowledge_search` | 语义/关键词检索 | POST `/knowledge/search` |
| `get_knowledge_tree` | 获取树形结构 | GET `/knowledge/tree/{parent_id}` |
| `get_knowledge_node` | 获取节点详情 | GET `/knowledge/nodes/{id}` |
| `create_knowledge_node` | 创建知识节点 | POST `/knowledge/nodes` |
| `list_resources` | 获取资源列表 | GET `/resources/` |
| `generate_quiz` | AI 生成测验题目 | 本地拼 prompt (无对应后端接口) |

环境变量: `METAEDU_BACKEND_URL`, `METAEDU_AUTH_USERNAME`, `METAEDU_AUTH_PASSWORD`

---

## 11. 已知技术债务

| 项目 | 说明 | 状态 |
|---|---|---|
| ~~无 Alembic 迁移~~ | ~~Schema 变更靠 `create_all`，生产需引入迁移~~ | ✅ 已修复：引入 Alembic，`init_db()` 优先 `alembic upgrade head`，兼容回退 `create_all` |
| ~~直接 SQL 文本~~ | ~~Router 中大量 `text()` 原生 SQL，未使用 Repository 实现~~ | ✅ 已修复：引入 Repository 层（`UserRepository` / `KnowledgeNodeRepository` / `ResourceRepository`），Router 零 `text()` 调用 |
| ~~`datetime.utcnow()`~~ | ~~全局使用已弃用 API，应改为 `datetime.now(UTC)`~~ | ✅ 已修复：全量替换为 `datetime.now(UTC)`，含 router/service/model/conftest/seed |
| ~~`__import__("datetime")`~~ | ~~register 端点中的 hack 写法~~ | ✅ 已修复：改为顶部 `from datetime import UTC, datetime` |
| ~~软删除未级联~~ | ~~删除 knowledge_node 时未检查/清理关联的 edges 和 resources~~ | ✅ 已修复：删除节点前先清理 edges + 软删除关联 resources |
| ~~Celery tasks 空目录~~ | ~~`celery_app.py` autodiscover `document.application.tasks` 但目录不存在~~ | ✅ 已修复：改为 `autodiscover_tasks(["app.contexts"])`，按上下文自动发现 |
| 前端未实现 | Vue3+Vite+Tailwind4 脚手架已搭建，但无实际页面 | ✅ 已修复：Liquid Glass 设计体系，全部页面已实现 |

---

## 12. 技术架构演化方案

> 核心理念：**渐进式演化，接口先行**。每个阶段用最简方案验证业务假设，同时在代码层预留抽象接口，确保下一阶段可平滑切换。

### 12.1 演化原则

1. **接口抽象优先** — 关键组件通过 Protocol/抽象类 定义接口，具体实现可替换
2. **数据可迁移** — 阶段间数据格式兼容或提供迁移脚本，不丢失历史数据
3. **垂直切片优先** — 先在一个业务上下文中验证新技术，再横向推广
4. **配置驱动切换** — 通过 `.env` / `config.py` 切换实现，不改动业务代码
5. **监控先行** — 引入新组件前先接入指标监控，量化性能瓶颈

### 12.2 总览对比表

| 组件 | 阶段一（验证期 · 当前） | 阶段二（增长期） | 阶段三（规模化） |
|---|---|---|---|
| 向量数据库 | pgvector (PostgreSQL 内) | pgvector + 缓存优化 | 独立 Milvus/Qdrant 集群 |
| 图数据库 | JSONB + ltree 物化路径 | JSONB + 邻接表 + 缓存 | Neo4j 知识图谱引擎 |
| 全文搜索 | pgvector 语义 + ILIKE 关键词 | pgvector + PostgreSQL tsvector | Elasticsearch 集群 |
| 实体识别 | 知识域枚举规则匹配 | 规则 + LLM 混合 NER | 专用 NER 模型 / LLM Function Calling |
| 召回编排 | PostgreSQL 内 asyncio.gather 3 通道并行 | 应用层 4 通道并行 + 降级 | 4 通道专用引擎 + 熔断 |
| 结果融合 | 多通道取并集 + 出现频次排序 | RRF (Reciprocal Rank Fusion) | RRF + 可配置权重 + Reranker |
| 溯源标注 | sources 扁平列表 | 按通道分段 + 内联标注 | 结构化标注 + 可信度评分 |
| 消息队列 | Celery + Redis | Celery + RabbitMQ | Celery + RabbitMQ + 死信队列 |
| 对象存储 | MinIO (本地) | MinIO (集群) | S3 / OSS 云存储 |
| 多模态处理 | 纯文本 Embedding | Whisper 语音 + 文档解析 | Whisper + LLaVA 视觉理解 |
| LLM 调用 | 直连 OpenAI 兼容 API | LiteLLM 统一代理 | 自部署 vLLM 推理集群 |
| 缓存 | 无 | Redis 热点缓存 | Redis Cluster + CDN |
| 前端 SSR | SPA (Vite dev) | SPA + 预渲染关键页 | Nuxt SSR / ISR |
| 监控 | 无 | Prometheus + Grafana | Full Observability (Trace/Metric/Log) |

### 12.3 逐组件演化路径

#### 12.3.1 向量数据库：pgvector → Milvus/Qdrant

**阶段一（当前）**：pgvector 作为 PostgreSQL 扩展，与业务数据同库存放

- 优势：零运维、事务一致性、JOIN 查询
- 瓶颈：百万级向量后 HNSW 索引内存占用大、检索延迟上升
- 当前接口预留：`embedding_service.py` 的 `get_embedding_vec()` 已封装为独立函数

**阶段二**：pgvector + 缓存优化

- 引入查询结果缓存（Redis），对高频查询短路
- HNSW 索引参数调优（`ef_construction` / `m`）
- 评估向量数据量与延迟关系，确定迁移阈值

**阶段三**：独立向量数据库

- 迁移到 Milvus（分布式）或 Qdrant（轻量级）
- 通过抽象接口切换：

```python
# 预留的抽象接口（阶段三实现）
class VectorStore(Protocol):
    async def upsert(self, id: str, vector: list[float], metadata: dict) -> None: ...
    async def search(self, vector: list[float], top_k: int, filter: dict | None) -> list[SearchResult]: ...
    async def delete(self, ids: list[str]) -> None: ...
```

- 数据迁移：pgvector → Milvus 批量导出/导入脚本
- 切换方式：`config.py` 新增 `VECTOR_STORE_BACKEND = "pgvector" | "milvus" | "qdrant"`

#### 12.3.2 图数据库：JSONB + ltree → Neo4j

**阶段一（当前）**：ltree 物化路径 + JSONB 存储简单关系

- 优势：无需额外组件、SQL 原生查询、与租户隔离天然兼容
- 瓶颈：多跳关系查询需递归 CTE（性能差）、关系类型缺乏语义、无图算法支持
- 当前接口预留：`knowledge_edges` 表已独立于 `knowledge_nodes`，关系模型可独立演化

**阶段二**：JSONB + 邻接表 + Redis 缓存

- 扩展 `knowledge_edges` 的 `metadata` 字段存储关系属性（权重/方向/时间）
- Redis 缓存常用子图查询结果
- 引入基础图算法（最短路径、社区发现）在应用层实现
- 当前扩展性预留：`knowledge_edges.metadata` JSONB 字段可自由扩展 schema

**阶段三**：Neo4j 知识图谱引擎

- 知识关系写入 Neo4j（主），PostgreSQL 作为业务主库（辅）
- 通过 CDC（Change Data Capture）同步两张写入
- 解锁图算法：PageRank、Community Detection、Similarity
- 抽象接口：

```python
class GraphStore(Protocol):
    async def add_node(self, id: str, labels: list[str], properties: dict) -> None: ...
    async def add_edge(self, source: str, target: str, rel_type: str, properties: dict) -> None: ...
    async def traverse(self, start: str, depth: int, rel_filter: str | None) -> list[GraphPath]: ...
    async def algorithm(self, name: str, params: dict) -> Any: ...
```

#### 12.3.3 全文搜索：ILIKE → tsvector → Elasticsearch

**阶段一（当前）**：pgvector 语义搜索 + ILIKE 关键词 fallback

- 优势：零组件、简单直接
- 瓶颈：ILIKE 无索引优化、中文分词依赖应用层拆分、无相关性排序

**阶段二**：PostgreSQL tsvector + pgvector 混合

- 启用 PostgreSQL 中文分词（zhparser / pg_jieba 扩展）
- 为 `title` / `description` 创建 GIN 索引
- 混合搜索：tsvector 分数 × 向量距离 加权融合
- 当前扩展性预留：`KnowledgeSearchDTO.search_mode` 已支持 `semantic` / `keyword` / `hybrid` 三种模式

**阶段三**：Elasticsearch 集群

- 通过 CDC 同步数据到 ES
- 支持拼音搜索、同义词、聚合分析
- 抽象接口：

```python
class SearchEngine(Protocol):
    async def index(self, doc_id: str, content: str, metadata: dict) -> None: ...
    async def search(self, query: str, filter: dict | None, top_k: int) -> list[SearchResult]: ...
    async def hybrid_search(self, query: str, vector: list[float], top_k: int) -> list[SearchResult]: ...
```

#### 12.3.4 消息队列：Redis → RabbitMQ

**阶段一（当前）**：Celery + Redis as Broker

- 优势：零额外组件、够用
- 瓶颈：Redis 无消息确认机制、无路由/优先级、无死信队列
- 当前扩展性预留：`celery_app.py` 仅配置 broker URL，切换 RabbitMQ 只需改环境变量

**阶段二**：Celery + RabbitMQ

- RabbitMQ 支持消息持久化、ACK、路由、死信队列
- 适合资源处理管道（上传 → 解析 → 向量化 → 入库）的级联任务
- 切换方式：`CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//`
- 任务拆分补建：创建 `app/contexts/document/application/tasks.py`（当前空目录待填充）

**阶段三**：RabbitMQ + 死信队列 + 监控

- 死信队列处理失败任务
- Prometheus 采集队列深度、任务耗时
- 延迟队列支持定时重试

#### 12.3.5 多模态数据处理：文本 → 语音/文档 → 视觉

**阶段一（当前）**：纯文本 Embedding

- 仅支持文本输入，资源上传后手动关联知识点
- Embedding 通过 DashScope API (BAAI/bge-m3) 生成 1536 维向量

**阶段二**：语音 + 文档解析

- **语音**：接入 Whisper（OpenAI API / 本地部署），音频上传后自动转文字 → Embedding
- **文档**：PDF/Word 解析（PyMuPDF / python-docx），提取文本/表格/图片引用
- 资源处理管道：`上传 → MIME 检测 → 分流处理(音频/文档/视频) → 文本提取 → Embedding → 关联知识点`
- 当前扩展性预留：`resources.resource_type` 已支持 `document / video / image / audio / other`，`resources.status` 已支持 `raw / uploaded / processed` 三态

**阶段三**：视觉理解

- **图像/视频关键帧**：LLaVA (Visual Language Model) 生成描述文本 → Embedding
- **视频**：关键帧提取 (FFmpeg) → LLaVA 描述 → Embedding
- 多模态 RAG：文本/图片/音频混合检索与生成
- 抽象接口：

```python
class MediaProcessor(Protocol):
    async def extract_text(self, file_path: str, mime_type: str) -> str: ...
    async def extract_frames(self, file_path: str, interval_sec: int) -> list[bytes]: ...
    async def generate_caption(self, image_bytes: bytes) -> str: ...

class EmbeddingService(Protocol):
    async def embed_text(self, text: str) -> list[float]: ...
    async def embed_multimodal(self, text: str, image: bytes | None) -> list[float]: ...
```

#### 12.3.6 LLM 调用：直连 → 统一代理 → 自部署

**阶段一（当前）**：直连 OpenAI 兼容 API（MiniMax / DeepSeek / Qwen）

- `_call_llm()` 中硬编码 provider 优先级
- 瓶颈：无 fallback 重试、无 Token 计量、无负载均衡

**阶段二**：LiteLLM 统一代理

- 100+ LLM 提供商统一接口，自动 fallback
- Token 消耗计量与限流
- 切换方式：`LLM_BACKEND=litellm` + `LITELLM_PROXY_URL`

**阶段三**：自部署推理集群

- vLLM / TGI 部署开源模型（Qwen2.5 / DeepSeek-V3）
- 私有化部署满足数据安全合规
- GPU 集群调度与弹性伸缩

#### 12.3.7 对象存储：本地 MinIO → 集群 → 云存储

**阶段一（当前）**：MinIO 单节点本地存储（已实现本地文件系统 fallback）

- 当前扩展性预留：`resource/router.py` 中存储操作通过 `storage_key` 抽象，切换后端只需改生成/读取逻辑

**阶段二**：MinIO 集群

- 多节点纠删码、数据高可用
- 适合教学视频等大文件场景

**阶段三**：S3 / 阿里云 OSS

- 无限容量、按量付费
- 抽象接口：

```python
class ObjectStorage(Protocol):
    async def upload(self, key: str, data: bytes, content_type: str) -> str: ...
    async def download(self, key: str) -> bytes: ...
    async def get_presigned_url(self, key: str, expires: int) -> str: ...
    async def delete(self, key: str) -> None: ...
```

#### 12.3.8 实体识别：枚举规则 → 混合 NER → 专用模型

**阶段一（当前）**：知识域枚举规则匹配

- 利用已有的 `KnowledgeDomain`（10 个专业大类）、`KnowledgeLevel`（6 级分类）枚举做字符串匹配
- 实现方式：将用户问题与枚举值做归一化匹配（去空格、全半角、别名映射表）
- 覆盖率预估：60-70%（精确匹配专业名 / 课程名等有限枚举集）
- 零新组件，纯 Python 代码实现

```python
# 阶段一实现（规划）
class RuleBasedNER:
    """枚举规则实体识别"""

    def __init__(self):
        self.domain_aliases: dict[str, str] = {
            "电子信息": "electronics_info", "电子与信息": "electronics_info",
            "智能制造": "smart_manufacturing", "财经商贸": "finance_commerce",
            ...
        }
        self.level_keywords: dict[str, str] = {
            "专业": "professional", "课程": "course",
            "知识点": "knowledge_point", "技能点": "skill_point",
            ...
        }

    def extract(self, query: str) -> NERResult:
        domains = [v for k, v in self.domain_aliases.items() if k in query]
        levels = [v for k, v in self.level_keywords.items() if k in query]
        return NERResult(domains=domains, levels=levels, raw_entities=[])
```

**阶段二**：规则 + LLM 混合 NER

- 先走规则匹配（快速、低成本），未命中则调用 LLM 提取实体
- LLM Prompt 模板：从问题中提取 `{专业名, 课程名, 知识点, 技能点, 操作步骤}`
- 覆盖率预估：85-90%
- 零新基础设施，多一次 LLM 调用

**阶段三**：专用 NER 模型 / LLM Function Calling

- 微调职教领域 NER 模型（基于 BERT / Qwen）
- 或使用 LLM structured output (Function Calling) 强制输出实体结构
- 覆盖率预估：95%+
- 需模型部署

#### 12.3.9 多源混合召回编排：PostgreSQL 并行 → 应用层编排 → 专用引擎

**阶段一（当前）**：PostgreSQL 内 3 通道 asyncio.gather 并行

- 所有召回通道均为 PostgreSQL 查询，共享同一连接池，`asyncio.gather` 并行执行
- 3 个召回通道：
  1. **语义向量召回**：pgvector `ORDER BY embedding <=> :vec LIMIT K`
  2. **关键词召回**：ILIKE 模糊匹配（阶段二升级 tsvector）
  3. **结构化元数据召回**：`WHERE domain = ? AND level = ? AND tenant_id = ?`
- 阶段一无图召回通道（`knowledge_edges` 1 跳查询可在阶段一后期加入）
- 超时控制：单条 SQL `statement_timeout`

```python
# 阶段一实现（规划）
async def parallel_recall(query: str, ner_result: NERResult) -> list[RecallResult]:
    vector_coro = vector_recall(query_embedding, top_k=5)
    keyword_coro = keyword_recall(query, top_k=5)
    metadata_coro = metadata_recall(ner_result, top_k=5)

    results = await asyncio.gather(
        vector_coro, keyword_coro, metadata_coro,
        return_exceptions=True,
    )
    # 收集成功通道的结果
    ...
```

**阶段二**：应用层 4 通道并行 + 降级

- 新增图召回通道（PostgreSQL `knowledge_edges` 1-2 跳）
- 每通道独立超时 + 降级策略（超时/失败则跳过该通道）
- 通道抽象为 `RecallChannel` 接口

**阶段三**：4 通道专用引擎 + 熔断

- 语义 → Milvus/Qdrant，关键词 → Elasticsearch，结构化 → PostgreSQL，图 → Neo4j
- 熔断器模式（circuit breaker）：连续 N 次失败则短路该通道
- 动态通道选择：根据查询类型决定启用哪些通道

#### 12.3.10 结果融合排序：并集排序 → RRF → RRF + Reranker

**阶段一（当前）**：多通道取并集 + 出现频次排序

- 按 `node_id` 去重
- 出现在越多通道的文档排名越前（出现频次排序 = RRF 的直觉简化版）
- 通道内按原始分数排序
- 零新组件，纯 Python 代码

```python
# 阶段一实现（规划）
def simple_fusion(channel_results: list[list[RecallResult]]) -> list[RecallResult]:
    freq: dict[str, int] = {}
    by_id: dict[str, RecallResult] = {}
    for results in channel_results:
        for r in results:
            if r.node_id not in by_id:
                by_id[r.node_id] = r
            freq[r.node_id] = freq.get(r.node_id, 0) + 1
    sorted_ids = sorted(freq, key=lambda x: freq[x], reverse=True)
    return [by_id[nid] for nid in sorted_ids]
```

**阶段二**：RRF (Reciprocal Rank Fusion)

- 公式：`score = Σ_i weight_i / (k + rank_i)`（k 通常取 60）
- 每通道可配置权重，如 `{vector: 0.4, keyword: 0.25, metadata: 0.15, graph: 0.2}`
- 权重在 `config.py` 中静态配置

**阶段三**：RRF + 可配置权重 + Reranker

- 动态权重：基于查询类型（事实型 / 概念型 / 操作型）自动调整通道权重
- 可选 Reranker 二次排序：Cohere Reranker / BGE-Reranker
- 语义去重：相似度 > 0.95 的结果合并

### 12.4 接口抽象层预留清单

以下抽象接口应在**阶段一后期（当前阶段末）**定义 Protocol，为阶段二/三切换铺路：

| 抽象 | 文件位置（规划） | 阶段一实现 | 阶段三实现 |
|---|---|---|---|
| `VectorStore` | `app/shared/domain/vector_store.py` | `PgVectorStore` | `MilvusVectorStore` |
| `GraphStore` | `app/shared/domain/graph_store.py` | `LtreeGraphStore` | `Neo4jGraphStore` |
| `SearchEngine` | `app/shared/domain/search_engine.py` | `PgSearchEngine` | `ElasticSearchEngine` |
| `MediaProcessor` | `app/shared/domain/media_processor.py` | `TextOnlyProcessor` | `WhisperLLaVAProcessor` |
| `EmbeddingService` | `app/shared/domain/embedding_service.py` | `DashScopeEmbedding` | `MultiModalEmbedding` |
| `ObjectStorage` | `app/shared/domain/object_storage.py` | `LocalStorage` | `S3Storage` |
| `NERPipeline` | `app/shared/domain/ner_pipeline.py` | `RuleBasedNER` | `LLMFunctionCallNER` |
| `RecallChannel` | `app/shared/domain/recall_channel.py` | `PgRecallChannel` | `EngineRecallChannel` |
| `ResultFusion` | `app/shared/domain/result_fusion.py` | `FrequencyFusion` | `RRFFusion + Reranker` |

所有 Protocol 通过 `config.py` 配置 + 工厂函数注入，业务代码零改动：

```python
# 工厂函数模式（阶段二实现）
def get_vector_store() -> VectorStore:
    backend = settings.vector_store_backend  # "pgvector" | "milvus" | "qdrant"
    match backend:
        case "pgvector": return PgVectorStore(...)
        case "milvus":   return MilvusVectorStore(...)
        case "qdrant":   return QdrantVectorStore(...)

# 混合检索新增 Protocol（阶段一后期定义）
class NERPipeline(Protocol):
    async def extract(self, query: str) -> NERResult: ...

class RecallChannel(Protocol):
    @property
    def name(self) -> str: ...
    async def recall(self, query: str, ner_result: NERResult, top_k: int) -> list[RecallResult]: ...

class ResultFusion(Protocol):
    def fuse(self, channel_results: dict[str, list[RecallResult]], top_k: int) -> list[RecallResult]: ...

# 工厂函数
def get_ner_pipeline() -> NERPipeline:
    match settings.ner_backend:
        case "rule":  return RuleBasedNER(...)
        case "llm":   return LLMNER(...)
        case "model": return ModelNER(...)

def get_recall_channels() -> list[RecallChannel]:
    match settings.recall_mode:
        case "pg_parallel": return [PgVectorRecall(...), PgKeywordRecall(...), PgMetadataRecall(...)]
        case "multi_engine": return [EngineVectorRecall(...), EngineKeywordRecall(...), EngineMetadataRecall(...), EngineGraphRecall(...)]

def get_result_fusion() -> ResultFusion:
    match settings.fusion_backend:
        case "frequency": return FrequencyFusion()
        case "rrf":       return RRFFusion(weights=settings.rrf_weights)
        case "rrf_rerank": return RRFRerankFusion(weights=settings.rrf_weights, reranker=get_reranker())
```

### 12.5 阶段切换触发指标

| 组件 | 当前容量阈值 | 性能阈值 | 切换信号 |
|---|---|---|---|
| pgvector | 100 万+ 向量 | p99 检索 > 500ms | 迁移 Milvus |
| ltree + JSONB | 10 万+ 边 / 3 跳以上查询 | 递归 CTE > 1s | 迁移 Neo4j |
| ILIKE / tsvector | 50 万+ 文档 | 关键词搜索 > 300ms | 迁移 Elasticsearch |
| Celery + Redis | 队列堆积 / 任务丢失 | 队列深度持续 > 100 | 迁移 RabbitMQ |
| DashScope Embedding | API 限频 | QPS 不足 | 自部署 Embedding 模型 |
| MinIO 单节点 | 存储 > 500GB | 可用性要求 99.9% | MinIO 集群 / S3 |
| 规则 NER | 覆盖率不足 | 规则命中率 < 70% | 引入 LLM 混合 NER |
| 频次融合 | 排序质量不足 | 用户对结果满意度低 | 引入 RRF 融合 |
| PostgreSQL 并行召回 | 通道数增加 / 跨引擎 | 单一引擎成瓶颈 | 切换多引擎编排 |

## 13. 开发里程碑

> **当前阶段：阶段一（验证期）** 🔄 进行中
> 
> 目标：验证核心流程可用，所有功能基于 PostgreSQL 单引擎实现，零额外基础设施

### 阶段一：验证期（当前 · 2026 W20 周内完成）

**目标**：端到端验证「用户提问 → 多源召回 → LLM 回答」核心流程

| 里程碑项 | 状态 | 说明 |
|---|---|---|
| 基础架构搭建 | ✅ 已完成 | FastAPI + Vue3 + PostgreSQL + pgvector |
| Identity 认证上下文 | ✅ 已完成 | JWT + 多租户 ContextVar |
| Knowledge 知识图谱上下文 | ✅ 已完成 | CRUD + 知识树 + ltree 物化路径 |
| Resource 资源上下文 | ✅ 已完成 | 文件上传/下载 + MinIO 本地存储 |
| AI Chat 基础对话 | ✅ 已完成 | 单通道向量检索 + LLM 生成 |
| Liquid Glass 设计体系 | ✅ 已完成 | 全套组件 + 5 个页面 |
| MCP Server | ✅ 已完成 | 知识库查询工具 |
| 前端 Markdown 渲染 | ✅ 已完成 | marked + highlight.js 代码高亮 |
| NER 实体识别（枚举规则） | 🔲 待开发 | `RuleBasedNER` — 领域枚举 + 别名映射 |
| 多源并行召回（3 通道） | 🔲 待开发 | pgvector + ILIKE + 结构化过滤，asyncio.gather |
| 结果融合（频次排序） | 🔲 待开发 | 多通道取并集 + 出现频次排序 |
| 溯源上下文组装增强 | 🔲 待开发 | sources 扩展为 `{channel, node_id, title, score}` |
| Protocol 接口定义 | 🔲 待开发 | `NERPipeline` / `RecallChannel` / `ResultFusion` Protocol |
| 49 个测试回归 | 🔲 待验证 | 全部 pytest 通过 |

**阶段一完成标准**：
- 用户输入问题 → NER 识别领域/级别 → 3 通道并行召回 → 融合排序 → LLM 带来源标注回答
- 所有 49 个测试通过
- 无新增基础设施依赖（全部用 PostgreSQL）

---

### 阶段二：增长期（需用户确认后启动）

**目标**：性能优化 + 搜索质量提升 + 多模态预处理

| 里程碑项 | 说明 |
|---|---|
| Redis 热点缓存 | 向量查询结果缓存 + NER 结果缓存 |
| PostgreSQL tsvector + zhparser | 中文分词全文搜索，替代 ILIKE |
| LLM 混合 NER | 规则未命中时调用 LLM 提取实体 |
| 4 通道并行召回 | 新增图谱关系召回通道（PostgreSQL `knowledge_edges`） |
| RRF 融合排序 | Reciprocal Rank Fusion + 可配置通道权重 |
| Celery + RabbitMQ | 替换 Redis 作为消息代理 |
| Whisper 语音转写 | 音频文件 → 文本 → Embedding |
| 文档解析增强 | PDF/Word 结构化提取 |
| LiteLLM 统一代理 | 多 LLM 提供商 fallback + Token 计量 |
| MinIO 集群 | 多节点纠删码 |

**阶段二完成标准**：
- 召回覆盖率 ≥ 85%（NER 命中率）
- 搜索响应 p99 ≤ 2s
- 4 通道并行降级无单点故障

---

### 阶段三：规模化（需用户确认后启动）

**目标**：水平扩展 + 企业级可靠性 + 多模态全流程

| 里程碑项 | 说明 |
|---|---|
| Milvus / Qdrant | 独立向量数据库，水平扩展 |
| Neo4j | 知识图谱引擎，支持图算法 |
| Elasticsearch | 全文搜索集群，中文分词 + 同义词 + 拼音 |
| 专用 NER 模型 | 微调职教领域实体识别，覆盖率 95%+ |
| RRF + Reranker | 动态权重 + 可选二次排序 |
| LLaVA 视觉理解 | 图像/视频 → 多模态 Embedding |
| vLLM 自部署 | 私有化 LLM 推理集群 |
| S3 / OSS 云存储 | 替代 MinIO |
| Prometheus + Grafana | 全链路监控 |
| Circuit Breaker | 召回通道熔断器 |

**阶段三完成标准**：
- 百万级向量检索 p99 ≤ 200ms
- 系统可用性 ≥ 99.9%
- 多模态（文本+语音+图像）端到端检索
