<div align="center">

# MetaEduBase

**AI Native 职业教育知识基座**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

面向职业院校的 AI-Native 知识管理平台。RAG 检索增强生成 · 层级知识图谱 · 多租户架构

</div>

---

## 特性

- **层级知识图谱** — ltree 树形结构，专业→课程→章节→知识点四级钻取
- **RAG 智能问答** — pgvector 向量检索 + 语义/关键词/混合搜索 + LLM 生成，回答附带溯源
- **多租户隔离** — JWT + ContextVar 行级隔离
- **Liquid Glass UI** — 教育行业定制毛玻璃设计体系
- **MCP 工具集成** — 6 个开箱即用的知识操作 Tool
- **一键启动** — `./dev.sh` 幂等启动，已运行服务自动跳过

## 技术架构

```
┌──────────────────────────────────────────────────────────────────┐
│  前端层  Vue 3.5 + TypeScript 5.8                                │
│  ┌──────────┬───────────┬──────────┬──────────┬──────────────┬────────────┬────────────┐│
│  │ 登录      │ 知识库     │ AI 问答   │ 资源库    │ 数据库       │ 技能编辑    │ 系统管理   ││
│  │ /login   │ /knowledge│ /ai-chat  │ /resource │ /database   │ /skill     │ /admin    ││
│  └──────────┴───────────┴──────────┴──────────┴──────────────┴────────────┴────────────┘│
│  Vite 6 · Tailwind CSS 4 · Pinia 3 · Vue Router · Radix Vue    │
│  Liquid Glass 毛玻璃设计体系 · lucide-vue-next 图标              │
├──────────────────────────────────────────────────────────────────┤
│  API 网关  FastAPI + JWT 认证 + CORS + 多租户 ContextVar         │
├──────────────────────────────────────────────────────────────────┤
│  业务层  DDD 分层架构 (Application / Domain / Infrastructure)     │
│  ┌────────────┬──────────────┬──────────────┬──────────────────┐│
│  │ 身份上下文   │ 知识上下文     │ 资源上下文    │ AI 问答上下文    ││
│  │ identity   │ knowledge    │ resource     │ ai (RAG)        ││
│  │            │              │              │                 ││
│  │ · 登录/注册  │ · 节点 CRUD   │ · 文件上传    │ · 向量检索       ││
│  │ · JWT 签发  │ · 树形遍历    │ · 下载/删除   │ · Embedding     ││
│  │ · RBAC 权限 │ · 语义搜索    │ · 软删除      │ · LLM 生成      ││
│  └────────────┴──────────────┴──────────────┴──────────────────┘│
├──────────────────────────────────────────────────────────────────┤
│  共享基础设施  SQLAlchemy 2 (async) · Alembic 迁移 · 种子数据      │
├──────────────────────────────────────────────────────────────────┤
│  中间件 / 存储层                                                   │
│  ┌──────────────────┬───────────────────┬───────────────────────┐│
│  │ PostgreSQL 16     │ Redis 7           │ MinIO                 ││
│  │ · pgvector 向量   │ · 缓存             │ · 对象存储             ││
│  │ · ltree 层级路径  │ · Celery 任务队列   │ · 文档/视频/图片       ││
│  │ · JSONB 元数据    │ · Session          │ · 本地存储 fallback    ││
│  └──────────────────┴───────────────────┴───────────────────────┘│
├──────────────────────────────────────────────────────────────────┤
│  AI / LLM 层                                                      │
│  MiniMax M2 (默认) · DeepSeek · Qwen  │  Embedding: bge-m3      │
│  MCP 工具服务器 (6 个知识操作 Tool)        │  DashScope API         │
└──────────────────────────────────────────────────────────────────┘
```

> 完整架构设计见 [ARCHITECTURE.md](ARCHITECTURE.md)

## 快速开始

### 环境要求

- Python 3.12+ / Node.js 20+ / pnpm 9+
- PostgreSQL 16 + pgvector **或** Docker (Colima)

<details>
<summary>Docker 环境安装（macOS 推荐 Colima）</summary>

```bash
brew install colima docker docker-compose
colima start --cpu 2 --memory 4 --disk 60
```

**国内网络加速**：

```bash
# GitHub 加速下载 VM 镜像
curl -L -o /tmp/colima-arm64-docker.qcow2 \
  https://ghfast.top/https://github.com/abiosoft/colima-core/releases/download/v0.10.1/ubuntu-24.04-minimal-cloudimg-arm64-docker.qcow2
colima start --cpu 2 --memory 4 --disk 60 --disk-image /tmp/colima-arm64-docker.qcow2
```

编辑 `~/.colima/default/colima.yaml` 添加 Docker Hub 加速源：

```yaml
docker:
  registry-mirrors:
    - https://docker.1ms.run
    - https://docker.m.daocloud.io
```

然后 `colima stop && colima start` 生效。

</details>

### 一键启动

```bash
git clone https://github.com/MarkDanile/MetaEduBase.git
cd MetaEduBase
pnpm install
cd packages/server-python && make install && cd ../..

./dev.sh init-db
./dev.sh
```

| 命令 | 说明 |
|---|---|
| `./dev.sh` | 启动全部（幂等：已运行则跳过） |
| `./dev.sh infra` | 仅基础设施 (PG/Redis/MinIO) |
| `./dev.sh backend` | 重启后端 |
| `./dev.sh frontend` | 重启前端 |
| `./dev.sh init-db` | 显式初始化开发数据库（迁移 + 默认开发账号） |
| `./dev.sh stop` | 停止全部 |
| `./dev.sh status` | 查看状态 |
| `./dev.sh logs` | 查看后端日志 |
| `./dev.sh logs frontend` | 查看前端日志 |

首次执行 `./dev.sh init-db` 后会创建默认开发账号 `admin` / `admin123`，启动后访问 http://localhost:3000

> 改代码后无需手动重启 — uvicorn `--reload` + Vite HMR 自动生效

## 项目结构

```
MetaEduBase/
├── deploy/                    # 部署配置 (Docker Compose + Dockerfile + Nginx)
├── packages/
│   ├── server-python/         # 后端 (FastAPI + SQLAlchemy 2 + DDD 分层)
│   │   ├── app/contexts/      #   业务上下文 (identity / knowledge / resource)
│   │   └── tests/             #   测试套件 (49 tests)
│   ├── web/                   # 前端 (Vue 3 + Tailwind 4 + Liquid Glass)
│   ├── shared/                # 前后端共享 TypeScript 类型
│   └── mcp-server/            # MCP 工具服务器
├── dev.sh                     # 一键开发启动脚本
└── ARCHITECTURE.md            # 完整架构文档
```

## 开发

```bash
# 后端 lint + 测试 (首次需先 `make init-test-db` 初始化测试库)
cd packages/server-python && make lint && make test

# 前端类型检查
cd packages/web && npx vue-tsc --noEmit

# API 文档 (启动后端后访问)
open http://localhost:8000/docs
```

## 生产部署

```bash
cd deploy
cp .env.production .env        # 编辑: 替换所有 CHANGE_ME 占位符
docker-compose up -d            # 构建镜像 + 启动全部服务
```

生产环境 5 容器：Nginx (反向代理 + 静态文件) → FastAPI (2 workers) → PostgreSQL + Redis + MinIO

> 详见 [ARCHITECTURE.md §14](ARCHITECTURE.md) 和 [deploy/](deploy/)

## License

MIT
