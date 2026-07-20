# REQ-044 Implementation Plan: MCP 注册、管理与调用能力

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建设 tenant 级最小 MCP registry（注册 / 启停 / 角色权限 / 凭证引用 / 调用审计 trace）+ 真实 MCP client transport，以企查查 QCC 为首个 server 完成真实调用，并打通 structured_data `MCPAdapter`。

**Architecture:** 新上下文 `app/contexts/mcp_registry/`（domain `MCPServer` / `CredentialRef`，infrastructure `MCPServerRepository` / `MCPClient` / `InvocationAuditRepository`，application `MCPRegistryService` / `MCPInvocationService`，interfaces `mcp_registry_router`）；structured_data `MCPAdapter` 作为消费方经 `MCPInvocationService` 调用；凭证只存 env key 引用，secret 永不落库。

**Tech Stack:** Python 3.14 + FastAPI + SQLAlchemy 2.x async + asyncpg + pytest + pydantic v2；alembic migration；httpx（transport）；官方 `mcp` Python SDK 为首选 client 实现（依赖评审不通过则 httpx 最小 JSON-RPC 2.0 兜底）

## Global Constraints

- 不破坏现有 226+ backend tests（structured_data 套件必须全绿）
- 所有新表带 `tenant_id`；`mcp_servers` 唯一约束 `(tenant_id, code)`
- secret（如 QCC token）只以 env key 引用名存在；DB / API 响应 / 日志 / 审计永不出现值
- 业务代码禁止硬编码 MCP server 配置；只有 `MCPInvocationService` 装配 `MCPClient`
- 未注册 / 禁用 / 无权限的调用显式失败并写审计（ok=False），不得返回空结果冒充成功，也不得继续抛 `CapabilityUnavailableError` 冒充"未接入"（已注册场景）
- pytest 必须在 `packages/server-python/` 下跑；`-W error`
- ruff 0 / check-engineering-docs 0 / `git diff --check` 干净
- 每个 Task 独立可验证、独立 commit

---

## File Structure

### 后端新建（context: mcp_registry）
- `app/contexts/mcp_registry/__init__.py`
- `app/contexts/mcp_registry/domain/mcp_server.py` — `MCPServer` dataclass + `CredentialRef` 值对象 + `CredentialUnavailableError`
- `app/contexts/mcp_registry/infrastructure/mcp_server_models.py` — `MCPServerModel` / `MCPInvocationAuditModel`（metaedu schema）
- `app/contexts/mcp_registry/infrastructure/mcp_server_repository.py` — CRUD + tenant 强制过滤
- `app/contexts/mcp_registry/infrastructure/invocation_audit_repository.py` — 审计写入 / 按 tenant 分页查询
- `app/contexts/mcp_registry/infrastructure/mcp_client.py` — streamable HTTP / sse transport client
- `app/contexts/mcp_registry/application/mcp_registry_service.py` — 注册 / 更新 / 启停 / 删除 + 管理 RBAC
- `app/contexts/mcp_registry/application/mcp_invocation_service.py` — 调用编排 + 审计
- `app/contexts/mcp_registry/interfaces/api/mcp_registry_router.py` — `/api/v1/mcp-servers` REST

### 后端修改
- `alembic/versions/021_mcp_registry.py` — 新 migration（两表 + 约束 + 索引）
- `app/shared/infrastructure/models.py` — 注册新 ORM model
- `app/main.py` — include `mcp_registry_router`
- `app/contexts/structured_data/infrastructure/mcp_adapter.py` — 改为经 registry 调用
- `app/contexts/structured_data/application/query_service.py` — `default_adapter_factory` 的 mcp 分支装配 invocation service
- `.env.example` — 加 `QCC_MCP_TOKEN=` 占位名（不含值）

### 测试新建
- `tests/contexts/mcp_registry/test_registry_service.py` — CRUD / 启停 / RBAC / code 冲突
- `tests/contexts/mcp_registry/test_credential_ref.py` — 引用格式 / resolve / 缺失 fail-closed / 日志无 secret
- `tests/contexts/mcp_registry/test_invocation_audit.py` — 审计字段与 digest 口径（真实 DB）
- `tests/contexts/mcp_registry/test_tenant_isolation.py` — 两 tenant 隔离（真实 DB）
- `tests/contexts/mcp_registry/test_mcp_client.py` — transport 单测（httpx mock）
- `tests/contexts/structured_data/test_mcp_adapter_registry_wiring.py` — adapter 经 registry 接线

### 前端新建（Task 4）
- `packages/web/src/views/mcp-registry/McpServerListView.vue` — 列表 + 注册 modal + 启停 + 删除 + 审计抽屉（复用 admin/TemplateListView 模式）
- `packages/web/src/api/mcpRegistry.ts` — API client（axios）
- 路由注册 + 菜单入口（按现有 router/menu 约定）
- `packages/web/src/views/mcp-registry/__tests__/McpServerListView.spec.ts` — vitest

### 文档修改（Task 5）
- `docs/01-product-planning/05-requirements/REQ-044-mcp-registry-and-invocation.md` — Status + Delivery Record
- `docs/01-product-planning/04-backlog.md` — REQ-044 行状态与链接
- `docs/03-engineering-governance/current-work.md` — TASK card
- `docs/03-engineering-governance/work-log.md` — +1 index row
- `docs/01-product-planning/06-ai-applications/README.md` — REQ-044 候选行状态同步

---

## Task 1: alembic migration 021 + ORM models + 注册

**Files:**
- Create: `alembic/versions/021_mcp_registry.py`
- Create: `app/contexts/mcp_registry/infrastructure/mcp_server_models.py`
- Create: `app/contexts/mcp_registry/domain/mcp_server.py`
- Modify: `app/shared/infrastructure/models.py`（注册 model）
- Test: `tests/contexts/mcp_registry/test_mcp_registry_migration.py`（new）

**Interfaces:**
- Consumes: 现有 `Base` / `_utcnow` 惯例（参考 `catalog_models.py`）
- Produces: `metaedu.mcp_servers` + `metaedu.mcp_invocation_audit` 两表；`MCPServerModel` / `MCPInvocationAuditModel` ORM；`MCPServer` domain dataclass

- [ ] **Step 1: 写 migration 021**

两表结构按 spec §4.2：`mcp_servers`（tenant_id / code / name / transport / server_url / credential_ref / allowed_roles JSONB / enabled default false / timeout_ms default 30000 / is_active / created_by / 时间戳 + `uq_mcp_servers_tenant_code`）；`mcp_invocation_audit`（tenant_id / server_id FK / server_code / tool_name / caller_type / caller_user_id / params_digest / response_digest / ok / error_code / error_message / duration_ms / created_at + 两索引）。`downgrade` 对称 drop。

- [ ] **Step 2: 写 ORM models**

`MCPServerModel` / `MCPInvocationAuditModel`，`__table_args__ = {"schema": "metaedu"}`，naive UTC `_utcnow`，与 `CatalogModel` 同模式；`app/shared/infrastructure/models.py` 注册。

- [ ] **Step 3: 写 domain entity**

`MCPServer` dataclass + `CredentialRef` 值对象（`^[A-Z][A-Z0-9_]*$` 校验 + `resolve()` 读 `os.environ`，缺失抛 `CredentialUnavailableError`）。

- [ ] **Step 4: migration 测试**

upgrade → 断言两表 / 约束 / 索引存在；同 tenant 同 code 插入冲突；不同 tenant 同 code 允许；downgrade 幂等。

- [ ] **Step 5: 跑测试 + commit**

```bash
cd packages/server-python && pytest tests/contexts/mcp_registry/test_mcp_registry_migration.py -v -W error
git commit -m "feat(mcp-registry): REQ-044 migration 021 mcp_servers + mcp_invocation_audit 表与 ORM"
```

---

## Task 2: Registry CRUD API + 管理 RBAC + 凭证引用校验

**Files:**
- Create: `app/contexts/mcp_registry/infrastructure/mcp_server_repository.py`
- Create: `app/contexts/mcp_registry/application/mcp_registry_service.py`
- Create: `app/contexts/mcp_registry/interfaces/api/mcp_registry_router.py`
- Modify: `app/main.py`（include router）
- Test: `tests/contexts/mcp_registry/test_registry_service.py` / `test_credential_ref.py`（new）

**Interfaces:**
- Consumes: `get_current_user`（`app.contexts.identity.interfaces.api.dependencies`）/ `get_session`
- Produces: `/api/v1/mcp-servers` CRUD + enable / disable / delete（spec §4.5 前 7 行端点）

- [ ] **Step 1: Repository** — 所有方法强制 `tenant_id`；`get_by_code` / `get_by_id` / `list_by_tenant` / `create` / `update` / `set_enabled` / `soft_delete`。

- [ ] **Step 2: Service** — 管理操作仅 `admin` / `data_admin` / `super_admin`（仿 `CatalogService` 的 `CatalogPermissionError` 模式：`MCPRegistryPermissionError` / `MCPServerCodeConflictError`）；`credential_ref` 格式校验（非法 → 422）；code 冲突 → 409。

- [ ] **Step 3: Router** — 7 个端点；轻量只做鉴权 + 参数解析 + 异常映射（403 / 404 / 409 / 422）；响应 DTO 不含任何 secret 字段（本来就没有，加断言防回归）。

- [ ] **Step 4: 测试** — 角色 × 操作矩阵（employee / teacher / student 管理操作 403）；CRUD 全流程；code 冲突 409；`credential_ref` 非法值 422；`CredentialRef.resolve` 缺失 env 时 fail-closed 且日志无 secret（caplog 断言）。

- [ ] **Step 5: 跑测试 + commit**

```bash
cd packages/server-python && pytest tests/contexts/mcp_registry/ -v -W error && ruff check app/ tests/
git commit -m "feat(mcp-registry): REQ-044 registry CRUD API + 管理 RBAC + credential_ref 校验"
```

---

## Task 3: MCP client transport + QCC 接线 + 调用审计 + structured_data MCPAdapter 改造

**Files:**
- Create: `app/contexts/mcp_registry/infrastructure/mcp_client.py`
- Create: `app/contexts/mcp_registry/infrastructure/invocation_audit_repository.py`
- Create: `app/contexts/mcp_registry/application/mcp_invocation_service.py`
- Create: `app/contexts/mcp_registry/interfaces/api/mcp_registry_router.py` 增补 `GET /{id}/invocations`（若 Task 2 未含）
- Modify: `app/contexts/structured_data/infrastructure/mcp_adapter.py`
- Modify: `app/contexts/structured_data/application/query_service.py`（mcp 分支装配 invocation service）
- Modify: `.env.example`（`QCC_MCP_TOKEN=` 占位）
- Test: `tests/contexts/mcp_registry/test_mcp_client.py` / `test_invocation_audit.py` / `test_tenant_isolation.py` / `tests/contexts/structured_data/test_mcp_adapter_registry_wiring.py`（new）

**Interfaces:**
- Consumes: Task 1 / 2 的 repository / domain；httpx
- Produces: `MCPInvocationService.invoke(tenant_id, server_code, tool_name, params, caller) -> dict`；`MCPAdapter` 真实调用路径

- [ ] **Step 1: MCPClient** — streamable HTTP 默认（`initialize` → `tools/call`，JSON-RPC 2.0，响应 json 或 SSE 解析）；`sse` 枚举兼容；`Authorization: Bearer <resolved>`；`asyncio.wait_for(server.timeout_ms)` 硬超时；错误归一化（`timeout` / `transport_error` / `tool_error`）。首选官方 `mcp` SDK，依赖评审不过则 httpx 实现（在 commit message 记录选择）。

- [ ] **Step 2: MCPInvocationService** — 按 spec §4.6 流程：解析 server → enabled → role ∈ allowed_roles → CredentialRef.resolve → client.call_tool → 写审计（digests = sha256 canonical JSON；error_message 截断 500 且不含 secret / 原始参数）。每个失败分支都写审计（ok=False + error_code），未注册除外（无 server 可关联，直接抛 NotFound）。

- [ ] **Step 3: structured_data MCPAdapter 改造** — `data_source_config` 改读 `server_code` + `tool_name`；`query` 委托 `MCPInvocationService`；保留 `validate_query` 校验配置完整；未注册 / 禁用 / 无权限显式失败（不再抛 `CapabilityUnavailableError`）；`default_adapter_factory` mcp 分支注入 invocation service。

- [ ] **Step 4: 测试** — transport 单测（httpx mock：成功 / 超时 / 4xx / 5xx / SSE 响应）；审计集成测试（真实 DB 断言 digest ≠ 原文、字段齐全）；两 tenant 隔离集成测试（互不可见 / 不可调用）；adapter 接线测试（注册 + 启用后 mock client 调用成功并写审计；禁用 / 无角色失败分支）；structured_data 全量回归。

- [ ] **Step 5: 跑测试 + commit**

```bash
cd packages/server-python && pytest tests/contexts/mcp_registry/ tests/contexts/structured_data/ -v -W error && ruff check app/ tests/
git commit -m "feat(mcp-registry): REQ-044 MCP client transport + 调用审计 + structured_data MCPAdapter 经 registry 接线"
```

---

## Task 4: 最小管理 UI（列表 + 注册 + 启停 + 删除 + 审计查询）

**Files:**
- Create: `packages/web/src/views/mcp-registry/McpServerListView.vue`
- Create: `packages/web/src/api/mcpRegistry.ts`
- Modify: 前端路由 + 菜单（按现有约定）
- Test: `packages/web/src/views/mcp-registry/__tests__/McpServerListView.spec.ts`（new）

**Interfaces:**
- Consumes: Task 2 的 `/api/v1/mcp-servers` REST + Task 3 的 `GET /{id}/invocations`
- Produces: 最小管理页（复用 admin/TemplateListView 模式）

- [ ] **Step 1: API client** — `mcpRegistry.ts`：list / create / update / enable / disable / delete / listInvocations；类型与后端 DTO 对齐（无 secret 字段）。

- [ ] **Step 2: 列表页** — 表格展示本 tenant server（code / name / transport / enabled / created_at）；注册 modal（code / name / server_url / transport / credential_ref 只填引用名 + 格式提示 / allowed_roles / timeout_ms）；启停 switch；删除确认；行内"审计"按钮开抽屉分页展示 invocation（tool / ok / duration / error / created_at）。

- [ ] **Step 3: 权限显隐** — 管理按钮（注册 / 启停 / 删除）仅 admin / data_admin / super_admin 可见；其余角色只读列表。

- [ ] **Step 4: vitest** — 渲染列表、注册提交调用 API、启停切换、越权角色按钮隐藏；mock axios。

- [ ] **Step 5: 跑测试 + commit**

```bash
cd packages/web && pnpm vitest run src/views/mcp-registry && pnpm lint && pnpm typecheck
git commit -m "feat(mcp-registry): REQ-044 最小管理 UI（列表 + 注册 + 启停 + 删除 + 审计查询）"
```

---

## Task 5: QCC 真实调用验收 + closeout

**Files:**
- Modify: `docs/01-product-planning/05-requirements/REQ-044-mcp-registry-and-invocation.md`
- Modify: `docs/01-product-planning/04-backlog.md`
- Modify: `docs/03-engineering-governance/current-work.md`
- Modify: `docs/03-engineering-governance/work-log.md`
- Modify: `docs/01-product-planning/06-ai-applications/README.md`

- [ ] **Step 1: QCC 注册** — 用户注入 `QCC_MCP_TOKEN` 后，经 API 或管理页注册 QCC server（code=`qcc`，server_url 由用户提供，credential_ref=`QCC_MCP_TOKEN`）并 enable（可选 list_tools 探活）。

- [ ] **Step 2: 真实调用验收（AC-9，manual / 真实验证）** — 调用至少 1 个 QCC 工具（如企业搜索 / 工商信息）；核验审计行（tool / duration_ms / digests / ok=true）；核验 secret 不出现在响应 / 日志 / DB；写验收记录（不含 secret、不含完整企业敏感数据）。

- [ ] **Step 3: 文档同步** — Requirement Status → 🟢 Done + Delivery Record 补各 Task 事实（commit hash / PR）；backlog REQ-044 行 ⚫ Candidate → 🟢 Done 并补链接；current-work TASK card 收口；work-log +1 行；ai-applications README 候选行状态同步。

- [ ] **Step 4: 跑门禁 + commit**

```bash
python3 scripts/check-engineering-docs && git diff --check
cd packages/server-python && pytest tests/ -q && ruff check app/ tests/
git commit -m "docs(closeout): REQ-044 实施完成 - QCC 真实调用验收 + backlog/current-work/work-log 同步"
```

---

## Self-Review

1. **AC-1**: migration 021 两表 + `(tenant_id, code)` 唯一 + upgrade/downgrade 测试（Task 1）
2. **AC-2**: CRUD + 启停 + 角色矩阵 403（Task 2）
3. **AC-3**: credential_ref 格式校验 + 日志 / 响应无 secret 断言（Task 2）
4. **AC-4 / AC-5**: 禁用 / 越权调用被拒并写审计（Task 3）
5. **AC-6**: 审计字段 + digest 口径真实 DB 集成测试（Task 3）
6. **AC-7**: 两 tenant 隔离集成测试（Task 3）
7. **AC-8**: MCPAdapter 经 registry 接线，显式失败分支不冒充（Task 3）
8. **AC-9**: QCC 真实调用手工验收，单独成行不冒充 CI（Task 5）
9. **AC-10**: 最小管理页可用 + 越权被拒（Task 4）
10. **AC-11**: 文档同步 + 门禁（Task 5）

---

## Execution Handoff

Plan complete. 5 tasks, estimated 3-4 subagent rounds. Task 5 Step 1-2 需要用户提供 QCC 凭证（server_url + token），前序 Task 不阻塞。Task 4 前端依赖 Task 2/3 的 API。

**Two execution options:**
1. **Subagent-Driven (recommended)** - Fresh subagent per task + review between tasks
2. **Inline Execution** - Execute in this session
