<div align="center">

# MetaEduBase

**AI Native 职业教育知识基座**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

面向职业院校的 AI-Native 知识管理平台。RAG 检索增强生成 · 层级知识图谱 · 文档/数据集处理管道 · 多租户架构

</div>

---

## 特性

- **层级知识图谱** — ltree 树形结构，专业→课程→章节→知识点四级钻取
- **RAG 智能问答** — pgvector 向量检索 + 关键词 fallback + 多 Provider LLM 生成，回答附带溯源
- **资源库与数据集管道** — 文件夹/文件上传、解析、分块、向量化、全文索引、Excel/CSV 数据集与 KG 抽取
- **数据要素模板** — 模板 CRUD、文档类型检查、AI 初始化模板字段
- **多租户隔离** — JWT + ContextVar 行级隔离
- **语义化 UI 体系** — `ui-*` workspace 组件层 + 4 主题，`liquid-*` 保留为兼容别名
- **MCP 工具集成** — 6 个开箱即用的知识操作 Tool
- **一键启动** — `./dev.sh` 幂等启动，已运行服务自动跳过
- **跨 AI IDE 工程规范** — `AGENTS.md` + `docs/engineering/*` 统一任务、计划、质量门禁和 Git 闭环

## 技术架构

```
┌──────────────────────────────────────────────────────────────────┐
│  前端层  Vue 3.5 + TypeScript 5.8                                │
│  ┌──────────┬───────────┬──────────┬──────────┬──────────────┬────────────┬────────────┐│
│  │ 登录      │ 知识库     │ AI 问答   │ 资源库    │ 数据库       │ 技能编辑    │ 系统管理   ││
│  │ /login   │ /knowledge│ /ai-chat  │ /resource │ /database   │ /skill     │ /admin    ││
│  └──────────┴───────────┴──────────┴──────────┴──────────────┴────────────┴────────────┘│
│  Vite 6 · Tailwind CSS 4 · Pinia 3 · Vue Query · Vue Router    │
│  ui-* 语义化 workspace 层 · 4 主题 · lucide-vue-next 图标        │
├──────────────────────────────────────────────────────────────────┤
│  API 网关  FastAPI + JWT 认证 + CORS + 多租户 ContextVar         │
├──────────────────────────────────────────────────────────────────┤
│  业务层  DDD 分层架构 (Application / Domain / Infrastructure)     │
│  ┌──────────┬──────────┬──────────┬──────────────┬────────────┐│
│  │ identity │ knowledge│ document │ structured   │ template   ││
│  │ 登录/JWT │ 知识图谱  │ 文件管道  │ 数据集/KG     │ 数据模板    ││
│  └──────────┴──────────┴──────────┴──────────────┴────────────┘│
│  resource 旧资源管理上下文保留；AI Chat 复用 knowledge + shared LLM │
├──────────────────────────────────────────────────────────────────┤
│  共享基础设施  SQLAlchemy 2 async · Alembic 迁移 · 显式 dev seed   │
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
│  Chat: MiniMax M2 / DeepSeek / Qwen  │ Embedding: bge-m3 / Qwen3│
│  Provider resolver + fallback       │ MCP 工具服务器 (6 tools)  │
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
├── AGENTS.md                  # 跨 AI IDE 统一入口规则
├── deploy/                    # 部署配置 (Docker Compose + Dockerfile + Nginx)
├── docs/                      # 工程规范、spec、plan、技术债和工作台
│   ├── engineering/           # current-work / technical-debt / rules / work-log
│   ├── specs/                 # 插件无关需求事实源
│   └── plans/                 # 插件无关实施计划事实源
├── packages/
│   ├── server-python/         # 后端 (FastAPI + SQLAlchemy 2 + DDD 分层)
│   │   ├── app/contexts/      #   identity / knowledge / document / structured_data / template / resource
│   │   └── tests/             #   pytest 测试套件（当前可收集 152 tests）
│   ├── web/                   # 前端 (Vue 3 + Tailwind 4 + ui-* workspace)
│   ├── shared/                # 前后端共享 TypeScript 类型
│   └── mcp-server/            # MCP 工具服务器
├── scripts/                   # 工程门禁脚本（如 check-engineering-docs）
├── dev.sh                     # 一键开发启动脚本
└── ARCHITECTURE.md            # 完整架构文档
```

## 开发

```bash
# 后端 lint + 测试 (首次需先 `make init-test-db` 初始化测试库)
cd packages/server-python && make lint && make test

# 前端 lint / 类型检查 / build
pnpm --filter @metaedu/web lint
pnpm --filter @metaedu/web typecheck
pnpm --filter @metaedu/web build

# 工程文档门禁
scripts/check-engineering-docs

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
