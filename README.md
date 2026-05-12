<div align="center">

# MetaEduBase

**AI Native 职业教育知识基座**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

面向职业院校的 AI-Native 知识管理平台，深度融合 RAG 检索增强生成、层级知识图谱与多租户架构，为教学资源管理、智能问答与课程编排提供一体化基座。

</div>

---

## 特性

- **层级知识图谱** — 基于 PostgreSQL `ltree` 的树形知识体系，支持专业→课程→章节→知识点四级钻取
- **RAG 智能问答** — pgvector 向量检索 + 语义/关键词/混合搜索 + LLM 生成，回答附带知识溯源
- **多租户隔离** — JWT 认证 + ContextVar 租户上下文，数据行级隔离
- **Liquid Glass UI** — Apple 风格毛玻璃设计体系，教育行业定制化视觉体验
- **对象存储** — MinIO / 本地存储双模式，支持文档、视频、图片等多类型资源管理
- **MCP 工具服务器** — 基于 FastMCP 的 LLM 工具集成，6 个开箱即用的知识操作 Tool
- **异步任务** — Celery + Redis 资源处理管道

---

## 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (Vue 3)                     │
│  Vite · Tailwind CSS 4 · Pinia · Vue Router · Radix Vue │
│              Liquid Glass Design System                  │
├─────────────────────────────────────────────────────────┤
│                      API Gateway                         │
│              FastAPI + JWT Authentication                │
├──────────┬──────────────┬──────────────┬────────────────┤
│ Identity │  Knowledge   │   Resource   │   AI Chat      │
│ Context  │   Context    │   Context    │   Context      │
│──────────│──────────────│──────────────│────────────────│
│ Login    │ CRUD / Tree  │ Upload       │ RAG Pipeline   │
│ Register │ Semantic     │ Download     │ Embedding      │
│ RBAC     │ Search       │ Soft Delete  │ LLM Generate   │
├──────────┴──────────────┴──────────────┴────────────────┤
│                   Shared Infrastructure                  │
│      SQLAlchemy 2 (async) · ContextVar · Seed Data      │
├─────────────────────────────────────────────────────────┤
│                       Data Layer                         │
│    PostgreSQL 16 (pgvector + ltree) · Redis 7 · MinIO   │
└─────────────────────────────────────────────────────────┘
```

### 后端技术栈

| 组件 | 选型 |
|---|---|
| Web 框架 | FastAPI 0.115+ (async) |
| ORM | SQLAlchemy 2 (async, asyncpg) |
| 数据库 | PostgreSQL 16 + pgvector + ltree |
| 缓存 / 队列 | Redis 7 + Celery 5 |
| 对象存储 | MinIO (本地存储 fallback) |
| 认证 | JWT (python-jose + bcrypt) |
| LLM | MiniMax M2 / DeepSeek / Qwen (OpenAI 兼容接口) |
| Embedding | BAAI/bge-m3 via DashScope API, 1536 维 |
| MCP Server | mcp Python SDK (stdio transport) |
| 测试 | pytest + pytest-asyncio (49 tests) |

### 前端技术栈

| 组件 | 选型 |
|---|---|
| 框架 | Vue 3.5 + TypeScript 5.8 |
| 构建 | Vite 6 |
| 样式 | Tailwind CSS 4 (Liquid Glass 设计体系) |
| 状态管理 | Pinia 3 |
| UI 组件 | Radix Vue + class-variance-authority |
| 数据可视化 | ECharts + vue-echarts |
| 流程编排 | Vue Flow |
| HTTP | Axios |

---

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 20+
- pnpm 9+
- Docker & Docker Compose (用于数据库/Redis/MinIO)

### 1. 克隆项目

```bash
git clone https://github.com/MarkDanile/MetaEduBase.git
cd MetaEduBase
```

### 2. 启动基础设施

```bash
cd deploy
cp .env.example .env        # 按需修改配置
docker compose -f docker-compose.dev.yml up -d
```

启动后可用服务：

| 服务 | 端口 | 说明 |
|---|---|---|
| PostgreSQL | 5432 | 主数据库 (pgvector + ltree) |
| Redis | 6379 | 缓存 + Celery 队列 |
| MinIO API | 9000 | 对象存储 |
| MinIO Console | 9001 | 存储管理界面 |

### 3. 启动后端

```bash
cd packages/server-python

# 安装依赖
make install

# 初始化数据库 (创建 schema + 种子数据)
make setup-db

# 启动开发服务器
make dev
```

后端运行在 `http://localhost:8000`，API 文档访问 `http://localhost:8000/docs`

### 4. 启动前端

```bash
# 回到项目根目录
cd ../..

# 安装前端依赖
pnpm install

# 启动开发服务器
pnpm dev:web
```

前端运行在 `http://localhost:3000`

### 5. 默认账号

| 用户名 | 密码 | 角色 |
|---|---|---|
| admin | admin123 | super_admin |

> 种子数据在服务首次启动时自动创建

---

## 项目结构

```
MetaEduBase/
├── deploy/                          # 部署配置
│   ├── docker-compose.dev.yml       # PostgreSQL + Redis + MinIO
│   ├── init-db.sql                  # 数据库扩展初始化
│   └── .env.example                 # 环境变量模板
├── packages/
│   ├── server-python/               # 后端服务
│   │   ├── app/
│   │   │   ├── main.py              # FastAPI 入口
│   │   │   ├── config.py            # 配置管理
│   │   │   ├── contexts/            # DDD 业务上下文
│   │   │   │   ├── identity/        #   认证 (登录/注册/RBAC)
│   │   │   │   ├── knowledge/       #   知识 (CRUD/搜索/RAG)
│   │   │   │   └── resource/        #   资源 (上传/下载/管理)
│   │   │   └── shared/              # 共享基础设施
│   │   ├── tests/                   # 测试套件 (49 tests)
│   │   └── pyproject.toml
│   ├── web/                         # 前端应用
│   │   ├── src/
│   │   │   ├── views/               # 页面组件
│   │   │   │   ├── auth/            #   登录页
│   │   │   │   ├── knowledge/       #   知识库管理
│   │   │   │   ├── ai-chat/         #   AI 问答
│   │   │   │   ├── resource/        #   资源管理
│   │   │   │   ├── skill/           #   Skill 编排
│   │   │   │   └── admin/           #   系统管理
│   │   │   ├── stores/              # Pinia 状态
│   │   │   ├── services/            # API 服务层
│   │   │   └── assets/css/          # Liquid Glass 设计体系
│   │   └── package.json
│   ├── mcp-server/                  # MCP 工具服务器
│   │   └── mcp_server/main.py       # 6 个知识操作 Tool
│   └── shared/                      # 前后端共享类型定义
├── package.json                     # Monorepo 脚本
├── pnpm-workspace.yaml
└── turbo.json                       # Turborepo 配置
```

---

## API 概览

### 认证 — `POST /api/v1/auth`

| 端点 | 说明 |
|---|---|
| `POST /login` | 登录，返回 JWT Token |
| `POST /register` | 注册新用户 |
| `GET /me` | 获取当前用户信息 |

### 知识 — `/api/v1/knowledge`

| 端点 | 说明 |
|---|---|
| `GET /nodes` | 列出知识节点 (支持 domain/parent_id 过滤) |
| `POST /nodes` | 创建节点 (自动生成 embedding) |
| `GET /nodes/{id}` | 获取节点详情 |
| `PATCH /nodes/{id}` | 更新节点 |
| `DELETE /nodes/{id}` | 删除节点 |
| `POST /search` | 语义 / 关键词 / 混合搜索 |
| `GET /tree/{parent_id}` | 获取树形结构 |

### AI 问答 — `/api/v1/ai`

| 端点 | 说明 |
|---|---|
| `POST /chat` | RAG 问答 (向量检索 → 上下文注入 → LLM 生成) |

### 资源 — `/api/v1/resources`

| 端点 | 说明 |
|---|---|
| `POST /upload` | 上传资源 (multipart) |
| `GET /` | 列出资源 (分页 + 类型/域过滤) |
| `GET /{id}` | 资源详情 |
| `GET /{id}/download` | 下载资源文件 |
| `DELETE /{id}` | 软删除资源 |

完整 API 文档请启动后端后访问 `http://localhost:8000/docs`

---

## 设计体系

前端采用 **Liquid Glass** 设计体系，灵感源自 Apple 毛玻璃美学，针对教育行业调性优化：

| 组件类 | 效果 |
|---|---|
| `.glass` | 标准毛玻璃 (blur 24px) |
| `.glass-heavy` | 重度毛玻璃 (blur 40px) |
| `.glass-subtle` | 轻度毛玻璃 (blur 12px) |
| `.mesh-bg` | 多彩渐变背景 (缓慢漂移动画) |
| `.liquid-card` | 液态卡片 (玻璃 + 悬浮效果) |
| `.liquid-input` | 液态输入框 |
| `.liquid-btn-primary` | 主按钮 (渐变 + 辉光) |
| `.liquid-tag` | 标签徽章 |

设计 Token 定义在 `packages/web/src/assets/css/main.css` 的 `@theme` 指令中。

---

## MCP 工具服务器

基于 [Model Context Protocol](https://modelcontextprotocol.io/) 的工具服务器，提供 6 个知识操作 Tool：

| Tool | 说明 |
|---|---|
| `knowledge_search` | 语义/关键词检索 |
| `get_knowledge_tree` | 获取树形结构 |
| `get_knowledge_node` | 获取节点详情 |
| `create_knowledge_node` | 创建知识节点 |
| `list_resources` | 获取资源列表 |
| `generate_quiz` | AI 生成测验题目 |

```bash
cd packages/mcp-server
pip install -e .
make dev
```

---

## 环境变量

参考 `deploy/.env.example`，主要配置项：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL 连接串 | `postgresql+asyncpg://metaedu@localhost:5432/metaedu` |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `JWT_SECRET` | JWT 签名密钥 | `dev-only-change-in-production` |
| `MINIMAX_API_KEY` | MiniMax LLM API Key | — |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | — |
| `QWEN_API_KEY` | Qwen/DashScope API Key (用于 Embedding) | — |
| `MINIO_ENDPOINT` | MinIO 地址 | `localhost:9000` |

> ⚠️ 生产环境务必修改 `JWT_SECRET` 和数据库密码

---

## 测试

```bash
cd packages/server-python

# 运行全部测试
make test

# 运行单个测试文件
pytest tests/contexts/knowledge/test_knowledge.py -v
```

测试使用独立的 `metaedu_test` 数据库，采用 NullPool 连接策略，种子数据与生产一致。

---

## License

MIT
