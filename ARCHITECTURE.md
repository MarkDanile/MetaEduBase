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

| 项目 | 说明 |
|---|---|
| 无 Alembic 迁移 | Schema 变更靠 `create_all`，生产需引入迁移 |
| 直接 SQL 文本 | Router 中大量 `text()` 原生 SQL，未使用 Repository 实现 |
| `datetime.utcnow()` | 全局使用已弃用 API，应改为 `datetime.now(UTC)` |
| `__import__("datetime")` | register 端点中的 hack 写法 |
| 软删除未级联 | 删除 knowledge_node 时未检查/清理关联的 edges 和 resources |
| Celery tasks 空目录 | `celery_app.py` autodiscover `document.application.tasks` 但目录不存在 |
| 前端未实现 | Vue3+Vite+Tailwind4 脚手架已搭建，但无实际页面 |
