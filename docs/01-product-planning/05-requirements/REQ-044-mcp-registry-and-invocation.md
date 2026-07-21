# REQ-044: MCP 注册、管理与调用能力

Status: 🟢 Done
Priority: P0
Milestone: P3
Domain: MCP / Tools / 平台基座
Source: 2026-07-20 REQ-046 Slice 0 决策链（依赖链锁定为 REQ-044 → REQ-045 → REQ-046 串行）
Related: REQ-045 / REQ-046 / REQ-043 / REQ-048 / REQ-052 / REQ-054 / REQ-057

## 背景

REQ-046（企业 360 背调工作台）是产业园区 P0 首个落地场景，其外部事实来源依赖企查查 MCP。当前事实：

- Codex / 本地 AI IDE 能调用企查查 MCP，只说明开发环境具备工具入口；产品后端没有自己的 MCP 注册、权限、调用、审计和错误处理能力。
- REQ-054 已建立 `data_source_config.type = mcp` 的 adapter 占位；REQ-057（PR #433 前序 commit `62aad607`）已将 `MCPAdapter.query` 改为显式抛 `CapabilityUnavailableError`，明确“真实 MCP server 未接入（REQ-044 / REQ-046 承接）”。
- 依赖链已锁定为串行：REQ-044 → REQ-045 → REQ-046。REQ-044 是当前主线。
- 用户将提供首个真实 MCP server（企查查 QCC）凭证（server_url + token），后端必须实现真实 MCP client，不允许继续占位。

本需求建设平台级最小 MCP 注册与调用治理能力：注册 / 启停 / 权限 / 凭证引用 / 调用审计与 trace，并把企查查作为第一个真实接入的 MCP server。这是 REQ-045（Skill）、REQ-046（背调业务编排）、REQ-043（Agentic 编排）共同依赖的可治理工具层。

## 目标

- 建立 tenant 级 MCP server 注册表：CRUD + 启用 / 禁用，`tenant_id` 跨租户隔离为硬安全边界，同 tenant 内 `code` 唯一。
- 凭证只存引用（env key 名 / secret-manager key），永不落库 secret 值，永不进日志。
- 每个 server 可配置允许调用的角色集合（per-server permission），调用时强制校验。
- 所有调用写审计：tool 名、参数摘要、响应摘要、错误、耗时、时间戳、tenant_id、caller。
- 实现真实 MCP client transport（streamable HTTP / SSE，配置驱动），以企查查 QCC 为首个注册 server 完成真实调用验证。
- 打通 structured_data 的 `MCPAdapter`：从 registry 解析 server，未注册 / 未启用 / 无权限时显式失败，不得伪装成功空结果。

## 待塑形决策

| 决策 | 选项 | 当前建议 |
|------|------|----------|
| Registry V1 范围 | 全量 MCP 市场 / 最小注册治理 | 【已定】最小范围：注册 / 启停 / 权限 / 凭证引用 / 调用审计 + trace。不做市场、发现、评分。 |
| 首个真实 server | mock 优先 / 直接接 QCC | 【已定】直接接企查查 QCC，用户提供 server_url + token，后端实现真实 MCP client。 |
| 凭证存储 | 值入库加密 / 只存引用 | 【已定】只存 env key 名引用（如 `QCC_MCP_TOKEN`），调用时解析；secret 值不落库、不进日志（security.md 密钥管理）。 |
| server_url 存储 | 入 registry 配置列 / 也走 env | 【已定】server_url 是配置不是 secret，入 registry 列；token 走 env 引用。 |
| Transport | 仅 streamable HTTP / 配置驱动双模式 | 【已定】配置驱动：V1 支持 streamable HTTP（MCP 现行规范默认），保留 sse 枚举兼容旧 server。 |
| tenant 隔离 | 全局共享 registry / tenant 级 | 【已定】tenant 级注册表，唯一约束 `(tenant_id, code)`，跨租户不可见不可调用（平台惯例硬边界）。 |
| 代码归属 | structured_data 内 / 新上下文 | 【已定】新建 `app/contexts/mcp_registry/` 上下文（application / domain / infrastructure / interfaces 骨架）；structured_data 的 MCPAdapter 作为消费方接线。 |
| 管理 UI | V1 做最小前端 / V1 仅 API | 【已定】V1 做最小管理页（列表 + 注册 / 启停 / 删除 + 审计查询），复用 admin/TemplateListView 模式；凭证字段只填引用名。 |
| 业务页面直连 | 允许页面硬编码 server / 强制走 registry | 【已定】禁止业务页面硬编码 MCP server 配置；一律经 registry + adapter 边界调用。 |
| tool 发现 | V1 调 list_tools 校验 / 仅按配置 tool_name 调用 | 【已定】enable 时可选调用 `list_tools` 做连通性校验并缓存工具清单，调用仍按 tool_name；探活失败不阻塞启用，仅返回警告。 |

## 验收标准

| ID | 内容 |
|----|------|
| AC-1 | `metaedu.mcp_servers` 与 `metaedu.mcp_invocation_audit` 表建成，均带 `tenant_id`；`mcp_servers` 唯一约束 `(tenant_id, code)`；migration 可 upgrade / downgrade。 |
| AC-2 | Registry CRUD + 启用 / 禁用 API 可用；管理操作仅 admin / data_admin / super_admin；其余角色 403。 |
| AC-3 | 凭证字段只接受引用名（env key 格式校验）；secret 值不出现在任何 API 响应、DB 行和日志中（含错误分支）。 |
| AC-4 | 禁用的 server 调用被拒绝并返回稳定错误码；启用后可调用；状态切换写 updated_at。 |
| AC-5 | per-server 角色权限生效：不在 `allowed_roles` 内的角色调用被拒并写审计（ok=False）。 |
| AC-6 | 每次调用写审计行：tool_name、params_digest、response_digest、ok、error、duration_ms、tenant_id、caller（user_id / 调用来源）；原始参数与响应体不落库。 |
| AC-7 | 跨租户隔离：tenant A 的 server 对 tenant B 不可见、不可按 id / code 调用；审计同样按 tenant 隔离。 |
| AC-8 | structured_data `MCPAdapter` 经 registry 解析 server：未注册 / 禁用 / 无权限时显式失败（不抛 CapabilityUnavailableError 冒充“未接入”，也不返回空结果冒充成功）；已注册且启用时走真实 client 调用。 |
| AC-9 | 用用户提供的 QCC 凭证完成至少 1 次真实调用验证（如企业搜索 / 工商信息工具），审计行记录真实耗时与结果摘要；凭证仅经 env 注入。 |
| AC-10 | 最小管理页可用：列表展示本 tenant server、注册（credential_ref 只填引用名）、启停、删除、审计查询；管理操作走与 API 一致的权限。 |
| AC-11 | 完成后同步 Backlog / current-work / work-log，Requirement / Spec / Plan 状态与事实一致。 |

## 非目标

- 不做完整 MCP 市场（发现、评分、版本、上架下架流程）。
- 不做 Skill 注册与执行，归 REQ-045。
- 不做背调业务编排、主体锚定和报告生成，归 REQ-046。
- 不做 AI Chat 会话级工具可用性与自主规划编排，归 REQ-043。
- 不做内部业务系统（资管 / CRM / 合同 / 财务）MCP 契约抽象，归 REQ-048。
- V1 前端只做最小管理页（列表 + 注册 / 启停 / 删除 + 审计查询）；不做工具清单可视化、调用统计图表等增强。
- V1 不接外部 secret-manager 服务，凭证引用仅解析进程环境变量。
- 不做调用配额、限流和计费统计（V2）。

## 验证计划

- migration 测试：upgrade / downgrade + 唯一约束冲突用例。
- Registry service / API 单测与契约测试（CRUD / 启停 / RBAC 矩阵 / 凭证引用格式校验）。
- 调用审计集成测试：真实 DB 断言审计行字段与摘要口径（digest 非原文）。
- 跨租户隔离集成测试（两 tenant 互不可见 / 不可调用）。
- MCP client transport 单测（httpx mock 层）+ structured_data MCPAdapter 接线测试。
- QCC 真实调用手工验收（用户提供凭证，env 注入，验收报告记录 tool / 耗时 / 摘要，不记录 secret）。
- `scripts/check-engineering-docs`、`git diff --check`、`ruff`、structured_data 回归测试。

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-07-20 | 登记 / 塑形 | REQ-046 Slice 0 决策链锁定 REQ-044 → REQ-045 → REQ-046 串行，REQ-044 升为主线；用户确认首个真实 MCP server 为企查查 QCC（凭证由用户提供）；按最小 registry 范围塑形，产出 spec / plan。 |
| 2026-07-20 | 塑形确认 -> Ready | 用户确认 6 项塑形决策：新上下文 `mcp_registry`、官方 mcp SDK 优先（httpx 兜底）、V1 带最小管理 UI、enable 可选 list_tools 探活、凭证只存引用、server_url 入配置列；AC 增补最小管理页（AC-10）；Status 🟣 Shaping -> 🔵 Ready。 |
| 2026-07-20 | Task 1: migration 021 + ORM + domain | migration 021 建 `metaedu.mcp_servers`（tenant 隔离 + `(tenant_id, code)` 唯一 + 软删）与 `metaedu.mcp_invocation_audit`（digest 口径，绝不存原文）；`MCPServer` / `CredentialRef` / `MCPServerModel`；commits `d02bc21f` / `5d188077`；复审 APPROVED。 |
| 2026-07-20 | Task 2: registry CRUD API + 管理 RBAC | 7 endpoint（注册 / 列表 / 详情 / 启停 / 删除 / 审计查询），管理操作限 `MCP_REGISTRY_ADMIN_ROLES`，`credential_ref` 引用名校验；软删后同 code 重注册 IntegrityError 映射 409；commits `2a2b859d` / `66e013bd`；复审 APPROVED w/ fixes。 |
| 2026-07-20 | Task 3: MCP client + 调用审计 + structured_data 接线 | httpx streamable_http client（initialize handshake + tools/call，JSON + SSE 双解析，`asyncio.wait_for` 硬超时）；`MCPInvocationService.invoke`（resolve -> enabled 门 -> 角色门 -> CredentialRef.resolve -> call_tool -> 审计，稳定 error_code 集）；`MCPAdapter` 经 registry 解析（AC-8：未注册/禁用/无权限显式失败）；commits `a9563119` / `3d197550`；复审 APPROVED w/ fixes。 |
| 2026-07-20 | Task 4: 最小管理 UI (AC-10) | `services/mcpRegistry.ts` + `views/mcp-registry/McpServerListView.vue`（列表 / 注册 modal / 启停（探活警告 toast）/ 删除 / 审计分页查询）；管理操作限 `["admin","data_admin","super_admin"]`，与后端 RBAC 一致；router + Layout 导航；6 vitest；commits `03efe7ca` / `80e51f94`；复审 APPROVED w/ fixes。 |
| 2026-07-20 | Task 5 / AC-9: QCC 真实调用验收 + closeout | `tests/real_world/test_req044_qcc_acceptance.py`（`RUN_QCC_AC9=1` + `QCC_MCP_TOKEN` 显式 opt-in，默认 skip 不进 CI）。**AC-9 通过（真实 QCC）**：注册 qcc-company server（streamable_http）-> `list_tools` 发现 16 个工具 -> `get_company_by_query` 真实调用 ok=True，duration_ms=275，params_digest=`07b431600e81…` / response_digest=`c21d05d2d68f…` 齐备；**token（bare 与 `Bearer` 两种形态）不出现在任何审计列 / invoke 结果**。**安全修复**：`AuthCredential` 不透明值对象（redacted repr）+ `resolve()` 防御性剥离冗余 `Bearer ` 前缀，杜绝 pytest `--tb=long` frame-locals 泄漏 secret（commit `c7ac0add`）；AC-9 scaffolding `0859f905`。凭证仅经 env 注入，DB 只存引用名。335 backend tests pass / ruff 0。 |
