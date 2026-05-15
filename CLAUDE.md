# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 核心原则

**Tradeoff:** 谨慎优先于速度。对于简单任务，请自行判断。

### 1. 先想后写
**不要假设。不要隐藏困惑。呈现权衡。**

- 明确陈述假设。不确定时提问。
- 存在多种解读时全部呈现，不静默选择。
- 有更简单方案就说出来。有理由时反驳。
- 有不清楚的地方，停下来。说出困惑所在。

### 2. 极简主义
**解决问题的最少代码。不投机性扩展。**

- 不做超出请求的功能。
- 单次使用不抽象。
- 不做没被要求的"灵活性"或"可配置性"。
- 不处理不可能发生的错误场景。
- 如果写了 200 行而可以用 50 行完成，重写。

自问："高级工程师会说这过于复杂吗？"如果是，简化。

### 3. 手术式改动
**只改必须改的。只清理自己的烂摊子。**

- 不"改善"相邻代码、注释或格式。
- 不重构没坏的东西。
- 匹配现有风格，即使你会用不同方式写。
- 注意到无关的死代码时，说明它——不要删除。

当变更造成孤儿代码时：
- 移除你的变更导致不再使用的 imports/变量/函数。
- 不要移除已有的死代码，除非被要求。

检验标准：每行变更都能追溯到用户需求。

### 4. 目标驱动
**定义成功标准。循环直到验证。**

将任务转化为可验证目标：
- "添加验证" → "为无效输入写测试，然后让测试通过"
- "修复 bug" → "写一个能复现它的测试，然后让测试通过"
- "重构 X" → "确保测试前后都通过"

多步任务先简述计划：
```
1. [步骤] → 验证: [检查方式]
2. [步骤] → 验证: [检查方式]
3. [步骤] → 验证: [检查方式]
```

强成功标准让你独立循环。弱标准（"让它工作"）需要不断确认。

---

**检验原则是否有效：** diff 中不必要的变更更少，重写由于过度复杂化更少，澄清问题在错误之前而非之后出现。

## Commands

### Startup
```bash
./dev.sh                        # Start all services (idempotent)
./dev.sh infra                  # Start only infra (PG/Redis/MinIO)
./dev.sh backend                # Restart backend only
./dev.sh frontend               # Restart frontend only
./dev.sh stop                   # Stop all
./dev.sh status                 # Check status
./dev.sh logs [backend|frontend] # View logs
```

### Backend (Python)
```bash
cd packages/server-python

make install                    # Install all deps (dev + ai)
make dev                        # Run uvicorn --reload on :8000
make lint                       # ruff check + mypy
make test                       # pytest -v (all 49 tests)

# Run a single test file
.venv/bin/pytest tests/contexts/identity/test_auth.py -v

# Run a single test by name
.venv/bin/pytest tests/contexts/knowledge/test_knowledge.py::test_search_nodes -v

# Run tests matching a keyword
.venv/bin/pytest -v -k "test_create"

# Database migrations
make migrate                    # alembic upgrade head
make migrate-create msg="description"  # Generate new migration
make migrate-downgrade          # Rollback one migration
```

### Frontend (Vue/TS)
```bash
cd packages/web

pnpm dev                        # Vite dev server on :3000
npx vue-tsc --noEmit            # Type check (required before commit)
pnpm build                      # Build for production (typecheck + vite build)
pnpm lint                       # ESLint
```

### Full-stack verification (run both before committing)
```bash
cd packages/server-python && make lint && make test
cd packages/web && npx vue-tsc --noEmit
```

## Architecture

AI-Native vocational education knowledge platform. DDD + multi-tenant.

### Tech Stack
| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + SQLAlchemy 2 (async) + Pydantic v2 |
| Database | PostgreSQL 16 + pgvector (1536-dim) + ltree |
| Frontend | Vue 3.5 + Vite 6 + Tailwind CSS 4 + Pinia 3 |
| Auth | JWT (python-jose + bcrypt) + ContextVar multi-tenant |
| LLM | MiniMax M2 / DeepSeek / Qwen (OpenAI-compatible) |
| Embedding | BAAI/bge-m3 via DashScope API |
| Cache/Queue | Redis 7 + Celery |
| Storage | MinIO (local filesystem fallback) |

### DDD Contexts
```
app/contexts/
├── identity/       # Auth: login, register, /me, JWT, multi-tenant ContextVar
├── knowledge/      # Knowledge graph: CRUD, tree (ltree), search, RAG chat
└── resource/       # File management: upload, download, soft-delete
```

Each context follows the same four-layer structure:
```
application/    # DTOs (Pydantic) + service functions
domain/         # Entities, Repository interfaces, enums
infrastructure/ # SQLAlchemy ORM models, repository implementations
interfaces/api/ # FastAPI routers + dependency injection
```

### Key Cross-File Patterns

**Multi-tenant isolation**: `get_current_user()` → `set_tenant_context(tenant_id, domain, clearance)` → `get_tenant_id()` in all queries. ContextVar lives in `app/shared/infrastructure/tenant_context.py`. Every DB query MUST include `tenant_id` filter.

**Auth dependency injection**: `current_user: dict = Depends(get_current_user)` in any router that needs auth. The dependency is in `contexts/identity/interfaces/api/dependencies.py`.

**ORM model registration**: All models must be imported in `app/shared/infrastructure/models.py` so SQLAlchemy metadata registers them. Forgetting this causes `create_all` / Alembic to miss the table.

**RAG pipeline** (`ai_router.py`): `get_embedding_vec()` → 3-channel parallel recall (`asyncio.gather`: pgvector + ILIKE + structured metadata) → `FrequencyFusion` → LLM generation with source citations. LLM fallback chain: minimax → deepseek → qwen.

**Knowledge node creation**: If `parent_id` provided → look up parent's `path` → concatenate new path = `{parent_path}.{node_id[:8]}`. Otherwise path = `node_id[:8]`. Embedding generated from `"{title} {description}"`, may be None.

### Adding a New API Endpoint
1. Determine which context (or create new one under `app/contexts/`)
2. Add route in `interfaces/api/router.py`
3. If new DB table: add Model in `infrastructure/models.py` + import in `shared/infrastructure/models.py`
4. If auth needed: add `current_user: dict = Depends(get_current_user)` parameter
5. If tenant isolation: call `get_tenant_id()` for all queries
6. Register router in `app/main.py` via `app.include_router()`
7. Add test in corresponding `tests/contexts/` directory

### Adding a New Business Context
```
app/contexts/{new_context}/
├── application/        # DTO + Service
├── domain/             # Entity + Repository interface (optional)
├── infrastructure/     # ORM Model
└── interfaces/api/     # Router
```
Then: `app.include_router()` in `main.py`, import model in `shared/infrastructure/models.py`.

## Testing

- **Test DB**: `metaedu_test` (isolated), **NullPool** strategy (new connection per request to avoid asyncpg event loop binding)
- **Seed data**: Same as production — default tenant + `admin`/`admin123`
- **Fixtures**: `conftest.py` provides `client`, `auth_token`, `auth_headers`
- **Unique usernames**: Use `uuid4().hex[:8]` in register tests to avoid collisions
- **Short search terms**: Use "汽车" not "汽车维修" (ILIKE `%汽车维修%` won't match "汽车检测与维修技术")
- **Unauthenticated assertions**: Use `status_code in (401, 403)` (HTTPBearer behavior)
- **Mock external services**: Mock `httpx.AsyncClient` for LLM, `get_embedding_vec` for Embedding — never call real APIs

## Frontend Conventions

### Design System (Liquid Glass)
All colors/spacing/z-index use CSS variables from `main.css` `@theme` block. No hardcoded values.

- Colors: `var(--color-ink)`, `var(--color-accent)`, `var(--color-accent-bg)`, `var(--color-accent-glow)`
- Font sizes: `var(--text-page-title)` (24px), `var(--text-section-title)` (18px), `var(--text-body)` (14px), `var(--text-caption)` (13px), `var(--text-small)` (12px), `var(--text-micro)` (11px)
- Z-index: `var(--z-sidebar)` (10), `var(--z-drawer)` (30), `var(--z-dialog)` (40), `var(--z-toast)` (50)
- CSS classes: `liquid-card`, `liquid-btn-primary`, `liquid-btn-ghost`, `liquid-btn-danger`, `liquid-tag-blue/green/amber/purple`, `liquid-dialog-overlay`, `content-bg`, `wet-line`, `animate-slide-up`, `stagger-1`~`stagger-5`

### Icons
**lucide-vue-next only.** No new inline SVGs. Existing ones are grandfathered.

### Shared Components (must use, never reimplement)
| Component | Path | Purpose |
|-----------|------|---------|
| `PageHeader` | `src/components/PageHeader.vue` | Page title area |
| `EmptyState` | `src/components/EmptyState.vue` | Empty state display |
| `ConfirmDialog` | `src/components/ConfirmDialog.vue` | Confirmation for destructive actions |
| `LoadingSpinner` | `src/components/LoadingSpinner.vue` | Loading indicator |
| `ToastContainer` | `src/components/ToastContainer.vue` | Toast notifications |

### Business Constants
All in `src/constants/maps.ts`: `domainMap` (10 domains), `levelMap` (6 levels), `roleMap`, `roleShortMap`, `resourceTypeMap`. Never redefine in view files.

### State Persistence
Auth store persists to localStorage: `metaedu_token`, `metaedu_tenant_id`, `metaedu_role`, `metaedu_domain`.

### Destructive Actions
Must use `ConfirmDialog` — never execute on click.

### Dialogs
Must have `role="dialog"` + `aria-modal="true"` + `@keydown.escape` close + focus trap.

## Work Modes

| Task Type | Mode | Description |
|-----------|------|-------------|
| Bug fix, small feature, UI tweak | **Plan-Do** | Propose change, confirm, implement |
| >3 files, schema change, new endpoint | **Spec** | Requirements → Design → Tasks → Implement |

## Document Sync

When committing, sync these docs if relevant code changed:
- `router.py` changed → update ARCHITECTURE.md API endpoint table
- `models.py` changed → update ARCHITECTURE.md DB schema section
- `config.py` / `.env` changed → update ARCHITECTURE.md config table + README.md env vars
- New business context → update both ARCHITECTURE.md and README.md project structure
- Pure frontend UI changes with no API/schema impact → no doc update needed

## Spec Documents

| Document | Content |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | API endpoints, DB schema, core flows, evolution plan |
| [.claude/rules/codingStyle.md](.claude/rules/codingStyle.md) | Code style, formatting, naming |
| [.claude/rules/testing.md](.claude/rules/testing.md) | Test requirements, mock strategy, coverage |
| [.claude/rules/git-workflow.md](.claude/rules/git-workflow.md) | Branch strategy, commit conventions, PR flow |
| [.claude/rules/security.md](.claude/rules/security.md) | Auth, injection prevention, secret handling |
| [.claude/rules/docs.md](.claude/rules/docs.md) | Doc structure, comment conventions |
| [README.md](README.md) | Quick start, env requirements, deployment |
