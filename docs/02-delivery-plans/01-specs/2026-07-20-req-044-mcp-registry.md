# REQ-044 Spec: MCP 注册、管理与调用能力

> **Status**: 🔵 Ready
> **Plan**: `docs/02-delivery-plans/02-plans/2026-07-20-req-044-mcp-registry-plan.md`
> **Requirement**: `docs/01-product-planning/05-requirements/REQ-044-mcp-registry-and-invocation.md`
> **Related**: REQ-045（Skill registry）/ REQ-046（企业 360 背调，下游驱动）/ REQ-048（内部系统 MCP 契约）/ REQ-054（catalog 数据源 mcp 类型）/ REQ-057（adapter registry + CapabilityUnavailableError）

---

## 1. 问题陈述

产品后端当前没有任何 MCP 治理能力：

- 企查查 MCP 只在 Codex / 本地 AI IDE 可用，生产后端无法注册、鉴权、调用和审计任何 MCP server。
- REQ-054 在 `data_source_config` 里预留了 `type: mcp`，REQ-057 让 `MCPAdapter.query` 显式抛 `CapabilityUnavailableError`——占位边界清晰，但真实调用能力不存在。
- REQ-046（企业 360 背调）已被锁定为依赖链终点（REQ-044 → REQ-045 → REQ-046），没有 registry 就无法把企查查工具调用变成可审计、可追责、可复现的生产能力。
- 如果各业务页面各自硬编码 MCP server 配置，凭证、权限和审计都会失控。

需要一个平台级最小 MCP registry：tenant 级注册 / 启停 / 角色权限 / 凭证引用 / 调用审计与 trace，外加一个真实 MCP client transport，以企查查 QCC 为首个接入 server。

## 2. 目标

- `metaedu.mcp_servers` 注册表 + CRUD / 启停 API，唯一约束 `(tenant_id, code)`。
- 凭证引用模型（CredentialRef）：DB 只存 env key 名，调用时从进程环境解析 secret；secret 永不落库、永不进日志和 API 响应。
- per-server 角色权限（`allowed_roles`），调用路径强制校验。
- `metaedu.mcp_invocation_audit` 调用审计：tool 名、参数 / 响应摘要（digest，非原文）、错误、耗时、tenant、caller。
- 真实 MCP client：streamable HTTP 为默认 transport（MCP 现行规范），`sse` 作为兼容枚举；配置驱动，不硬编码任何 server。
- structured_data `MCPAdapter` 改造为经 registry 解析并调用，接入统一审计。
- 以 QCC 为首个注册 server，用用户提供的凭证完成真实调用验收。

## 3. 非目标

- 不做 MCP 市场 / 发现 / 评分 / 版本管理。
- 不做 Skill registry（REQ-045）、背调业务编排（REQ-046）、Agentic 编排与会话级可用性（REQ-043）、内部系统 MCP 契约（REQ-048）。
- V1 前端只做最小管理页（列表 + 注册 / 启停 / 删除 + 审计查询）；不做工具清单可视化、调用统计图表等增强（V2）。
- V1 不接外部 secret-manager；凭证引用仅解析进程环境变量。
- 不做配额 / 限流 / 计费（V2）。

---

## 4. 架构设计

### 4.1 组件边界

新上下文 `app/contexts/mcp_registry/`（application / domain / infrastructure / interfaces 骨架，与现有 context 约定一致）：

| 组件 | 层 | 职责 |
|------|-----|------|
| `MCPServer` (domain entity) | domain | 注册实体：code / name / transport / server_url / credential_ref / allowed_roles / enabled；纯 Python dataclass，与 `Catalog` 同模式 |
| `CredentialRef` (value object) | domain | 凭证引用：校验 env key 名格式（`^[A-Z][A-Z0-9_]*$`）；`resolve()` 从 `os.environ` 取值，缺失时抛 `CredentialUnavailableError`；永不打印值 |
| `MCPServerRepository` | infrastructure | `mcp_servers` CRUD，所有查询强制 `tenant_id` |
| `MCPRegistryService` | application | 注册 / 更新 / 启停 / 删除编排；管理 RBAC（admin / data_admin / super_admin）；code 冲突 409 |
| `MCPClient` | infrastructure | MCP transport 客户端：streamable HTTP 默认、sse 兼容；`call_tool(server, tool_name, params)` / 可选 `list_tools`；超时与错误归一化 |
| `MCPInvocationService` | application | 调用编排：解析 server → 校验 enabled → 校验 caller role ∈ allowed_roles → 解析 CredentialRef → MCPClient.call_tool → 写审计；业务侧统一入口 |
| `InvocationAuditRepository` | infrastructure | `mcp_invocation_audit` 写入与按 tenant 查询 |
| `mcp_registry_router` | interfaces/api | CRUD / 启停 / 审计查询 REST；轻量，只鉴权 + 参数解析 + 异常映射 |
| `McpServerListView`（前端） | web/views | 最小管理页：列表 + 注册 modal（credential_ref 只填引用名）+ 启停 + 删除 + 审计抽屉；复用 admin/TemplateListView 模式，管理操作按钮按角色显隐 |

消费方：

- `structured_data/infrastructure/mcp_adapter.py`：`MCPAdapter` 从 `data_source_config` 读 `server_code`（替代原 `server_url` 直连占位），委托 `MCPInvocationService` 调用；未注册 / 禁用 / 无权限显式失败。
- REQ-046 的 QCC MCP Adapter、REQ-043 的编排层同样只经 `MCPInvocationService`，不直连 `MCPClient`。

### 4.2 数据模型

`metaedu.mcp_servers`（migration 021）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | default uuid4 |
| `tenant_id` | UUID NOT NULL, index | 跨租户隔离硬边界 |
| `code` | varchar(50) | 英文标识，`^[a-z][a-z0-9_]*$`，如 `qcc`；同 tenant 唯一 |
| `name` | varchar(200) | 显示名，如"企查查" |
| `description` | text nullable | |
| `transport` | varchar(20) | `streamable_http`（默认）/ `sse` |
| `server_url` | varchar(500) | MCP server URL（配置，非 secret） |
| `credential_ref` | varchar(200) nullable | env key 名，如 `QCC_MCP_TOKEN`；**只存引用名，永不存值**；nullable 支持无鉴权 server |
| `allowed_roles` | JSONB | 允许调用的角色列表，如 `["admin", "data_admin"]`；空列表 = 仅 super_admin |
| `enabled` | boolean NOT NULL default false | 注册后默认停用，需显式启用 |
| `timeout_ms` | int NOT NULL default 30000 | 单次调用超时 |
| `is_active` | boolean NOT NULL default true | 软删标记 |
| `created_by` | UUID NOT NULL | |
| `created_at` / `updated_at` | timestamp | naive UTC（项目惯例） |

唯一约束：`uq_mcp_servers_tenant_code (tenant_id, code)`。

`metaedu.mcp_invocation_audit`（migration 021）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `tenant_id` | UUID NOT NULL, index | 与 server 同行隔离 |
| `server_id` | UUID NOT NULL FK → mcp_servers.id | |
| `server_code` | varchar(50) | 冗余，审计可读性（server 软删后仍可追溯） |
| `tool_name` | varchar(200) | 被调用的 MCP tool |
| `caller_type` | varchar(30) | `http_api` / `adapter:structured_data` / `service` |
| `caller_user_id` | UUID nullable | 触发用户（服务内部调用可空） |
| `params_digest` | varchar(64) nullable | 规范化参数 JSON 的 sha256；**原始参数不落库**；nullable 以容纳 pre-call 失败分支（resolve/早期校验前无参数可 digest），正常调用恒有值 |
| `response_digest` | varchar(64) nullable | 响应摘要 sha256；响应体不落库 |
| `ok` | boolean NOT NULL | |
| `error_code` | varchar(50) nullable | 归一化错误码（如 `credential_unavailable` / `disabled` / `forbidden` / `transport_error` / `tool_error` / `timeout`） |
| `error_message` | varchar(500) nullable | 截断，过滤后不含 secret / 原始参数值 |
| `duration_ms` | int NOT NULL | |
| `created_at` | timestamp | |

索引：`(tenant_id, server_id, created_at)`、`(tenant_id, created_at)`。

**摘要口径**：digest = `sha256(canonical_json)`，canonical_json 为排序 key 的紧凑 JSON；审计只证明"用什么参数调、拿到什么响应"的可复现性，不保存内容本体。背调报告证据链（REQ-046）引用审计行 id 即可。

### 4.3 CredentialRef 与密钥边界

- DB / API / 日志只出现引用名（如 `QCC_MCP_TOKEN`）；值仅存在于进程环境，调用瞬间解析注入 Authorization header。
- `resolve()` 失败 → `CredentialUnavailableError` → 审计 `ok=False, error_code=credential_unavailable`，调用不发出。
- 注册 / 更新 API 对 `credential_ref` 做格式校验；**不**在注册时探测 env 是否存在（避免环境耦合，enable 时可选手动 test-call 验证）。
- QCC 凭证：用户在部署环境注入 `QCC_MCP_TOKEN`；`.env` 不入库，`.env.example` 只加占位名。

### 4.4 MCP client transport（QCC 为首个 server）

- 默认 `streamable_http`（MCP 规范现行传输）：单 endpoint POST JSON-RPC 2.0，响应可为 `application/json` 或 SSE 流；初始化 `initialize` → `tools/call`。
- `sse` 作为 legacy 枚举保留（旧式双端点 server），配置驱动选择。
- 实现选型：优先官方 `mcp` Python SDK（`streamablehttp_client`）；若依赖评审不通过，则用 httpx 实现最小 JSON-RPC 2.0 + SSE 解析（决策见 §7，待用户确认）。
- 鉴权：`Authorization: Bearer <resolved credential>`，header 名可配置（默认 `Authorization`）。
- 超时：`server.timeout_ms`，`asyncio.wait_for` 硬超时；超时归一化为 `error_code=timeout`。
- 不硬编码 QCC 任何配置：server_url / token 引用 / tool_name 全部来自 registry 行 + env。

### 4.5 API 端点

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/api/v1/mcp-servers` | admin / data_admin / super_admin | 注册（code 冲突 409；credential_ref 格式校验 422） |
| GET | `/api/v1/mcp-servers` | 所有登录用户（本 tenant） | 列表，**不返回任何 secret**（本来就没有） |
| GET | `/api/v1/mcp-servers/{id}` | 所有登录用户（本 tenant） | 详情 |
| PATCH | `/api/v1/mcp-servers/{id}` | admin / data_admin / super_admin | 更新配置 / allowed_roles |
| POST | `/api/v1/mcp-servers/{id}/enable` | admin / data_admin / super_admin | 启用（可选 list_tools 连通校验，失败仍允许启用但返回警告） |
| POST | `/api/v1/mcp-servers/{id}/disable` | admin / data_admin / super_admin | 禁用 |
| DELETE | `/api/v1/mcp-servers/{id}` | admin / data_admin / super_admin | 软删（is_active=false）；有审计行的 server 不硬删（与 catalog 管理权限集一致） |
| GET | `/api/v1/mcp-servers/{id}/invocations` | admin / data_admin / super_admin | 审计查询（分页，本 tenant） |

业务调用（structured_data 问数、REQ-046 背调）不暴露公开 invoke API，走 `MCPInvocationService` 内部入口；V1 如需调试，用 enable 时的连通校验或测试脚本，不开通用调用端点。

### 4.6 调用与 trace 流程

```text
caller (structured_data MCPAdapter / REQ-046 adapter)
  -> MCPInvocationService.invoke(tenant_id, server_code, tool_name, params, caller)
    -> repo.get_by_code(tenant_id, code)          # 未注册 -> NotFound / 审计不成立，直接失败
    -> check enabled                              # 禁用 -> 审计 ok=False error_code=disabled
    -> check caller.role in allowed_roles         # 越权 -> 审计 ok=False error_code=forbidden
    -> CredentialRef.resolve()                    # 缺失 -> 审计 ok=False error_code=credential_unavailable
    -> MCPClient.call_tool(timeout=server.timeout_ms)
    -> 写审计行（digests / ok / duration_ms / caller / tenant_id）
    -> 返回结构化结果给 caller
```

trace 字段与 REQ-046 spec §4.1 对 QCC MCP Adapter 的要求（工具调用名称、参数摘要、返回摘要、错误、耗时、时间戳可追踪）一一对应；REQ-046 报告 evidence_refs 引用 `mcp_invocation_audit.id`。

---

## 5. 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | `mcp_servers` / `mcp_invocation_audit` 建成，唯一约束 `(tenant_id, code)` 生效，migration upgrade / downgrade 幂等 | migration 测试 + 约束冲突用例（integration） |
| AC-2 | CRUD + 启停 API 可用；管理操作仅 admin / data_admin / super_admin，其余 403 | API 测试（角色 × 操作矩阵）（unit / contract） |
| AC-3 | `credential_ref` 只接受合法 env key 名；secret 值不出现在 DB 行、任何 API 响应和日志（含异常分支） | 单测 + 日志捕获断言 + 代码 grep 检查（unit） |
| AC-4 | 禁用 server 调用被拒（稳定 error_code=disabled）并写审计；启用后恢复 | 单测（unit） |
| AC-5 | 不在 `allowed_roles` 的角色调用被拒（error_code=forbidden）并写审计 ok=False | 单测 / API 测试（unit / contract） |
| AC-6 | 审计行含 tool_name / params_digest / response_digest / ok / error / duration_ms / tenant_id / caller；digest 不等于原文，原始参数与响应体不落库 | 真实 DB 集成测试（integration） |
| AC-7 | tenant A 的 server 对 tenant B 不可见、不可按 id / code 调用；审计按 tenant 隔离 | 两 tenant 集成测试（integration） |
| AC-8 | structured_data `MCPAdapter` 经 registry 调用：未注册 / 禁用 / 无权限显式失败（非 CapabilityUnavailableError 冒充、非空结果冒充）；已启用时走 MCPClient 并写审计 | 单测（httpx mock transport）（unit） |
| AC-9 | 用户提供 QCC 凭证（env 注入）后，真实调用至少 1 个 QCC 工具成功，审计行记录真实 duration 与 digest；凭证不出现任何产物中 | 手工真实验收 + 验收记录（manual / 真实验证，不由 CI 冒充） |
| AC-10 | 最小管理页可用：列表（本 tenant）、注册（credential_ref 只填引用名）、启停、删除、审计查询；管理按钮按角色显隐，越权被 API 拒 | 前端 vitest + UI smoke（unit / smoke） |
| AC-11 | Backlog / current-work / work-log / Requirement 状态同步，验证层级如实声明 | 文档门禁（manual） |

---

## 6. 风险控制

| 风险 | 影响 | 缓解 |
|------|------|------|
| secret 泄漏（日志 / 异常 message / 审计） | 高 | 只存引用名；异常 message 白名单化 + 截断；单测断言日志无 secret；安全清单（security.md）纳入完成门禁 |
| QCC transport 细节不确定（鉴权头 / 初始化握手） | 中 | transport 配置驱动；先以官方 MCP SDK 实现，httpx 兜底；真实验收（AC-9）单独成行不冒充 |
| 业务方绕过 registry 直连 | 中 | 只有 `MCPInvocationService` 持有 MCPClient 装配；review 检查业务代码不 new MCPClient；文档明确边界 |
| enabled 默认打开导致未审先调 | 中 | `enabled` 默认 false，注册后必须显式 enable |
| 审计表增长 | 低 | V1 只索引 + 分页查询；保留策略 / 归档归 V2 |
| 新上下文拆分过度 | 低 | 与现有 context 骨架一致；structured_data 仅作为消费方改造，不搬移既有代码 |

---

## 7. 决策记录（本次塑形确认）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| Registry V1 范围 | 最小注册治理（注册 / 启停 / 权限 / 凭证引用 / 审计 trace） | 锁定决策：不做 MCP 市场 |
| 首个 server | 企查查 QCC，真实 client | 锁定决策：用户供凭证，后端必须真实可用 |
| 凭证 | 只存 env key 引用（如 `QCC_MCP_TOKEN`） | security.md 密钥管理；secret 不落库 |
| server_url | registry 配置列 | 配置非 secret；禁止硬编码进业务页面 |
| tenant 模型 | tenant 级注册表 + `(tenant_id, code)` 唯一 | 平台隔离惯例，与 data_catalogs 同模式 |
| 代码归属 | 新上下文 `app/contexts/mcp_registry/` | 被 structured_data / REQ-046 / REQ-043 多方消费，不属于单一业务上下文 |
| Transport | streamable HTTP 默认 + sse 兼容枚举，配置驱动 | MCP 现行规范；保留旧 server 兼容 |
| Client 实现 | 优先官方 `mcp` Python SDK，httpx 最小 JSON-RPC 兜底 | 减少自研协议风险；依赖需评审 |
| 管理 UI | V1 做最小管理页（列表 + 注册 / 启停 / 删除 + 审计查询） | 用户确认；复用 admin/TemplateListView 模式，凭证只填引用名 |
| enable 探活 | enable 时可选调 `list_tools` 连通校验 + 缓存工具清单 | 用户确认；失败不阻塞启用，仅返回警告 |
| 公开 invoke API | 不开放 | 业务调用走内部 service，缩小攻击面 |

---

## 8. 超出范围（V2 留口）

- MCP 市场 / 工具发现缓存治理 / 版本管理
- 外部 secret-manager（Vault / KMS）集成
- 调用配额 / 限流 / 计费 / 审计归档策略
- 前端管理 UI
- 会话级工具可用性（REQ-043）
- stdio transport（本地子进程 MCP，生产后端暂不开放）

---

## 9. 参考

- Requirement: `docs/01-product-planning/05-requirements/REQ-044-mcp-registry-and-invocation.md`
- REQ-046 spec（QCC adapter / trace 要求 §4.1-4.3）: `docs/02-delivery-plans/01-specs/2026-07-03-req-046-enterprise-360-due-diligence-workbench.md`
- REQ-057（adapter registry + CapabilityUnavailableError 现状）: `docs/01-product-planning/05-requirements/REQ-057-catalog-adapter-and-entity-contract-closure.md`
- REQ-054 spec（mcp 数据源类型占位）: `docs/02-delivery-plans/01-specs/2026-07-07-req-054-platform-database-catalog.md`
- 现状代码: `packages/server-python/app/contexts/structured_data/infrastructure/mcp_adapter.py`
- 安全规则: `docs/03-engineering-governance/01-rules/security.md`
- 架构规则: `docs/03-engineering-governance/01-rules/architecture.md`
- QCC MCP Guide: https://agent.qcc.com/guide
- MCP 规范（Streamable HTTP transport）: https://modelcontextprotocol.io/specification
