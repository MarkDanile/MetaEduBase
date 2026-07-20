# REQ-045 Spec: Skill 注册、管理与调用能力（最小 Skill registry）

> **Status**: 🔵 Ready
> **Plan**: `docs/02-delivery-plans/02-plans/2026-07-20-req-045-skill-registry-plan.md`
> **Requirement**: `docs/01-product-planning/05-requirements/REQ-045-skill-registry-and-execution.md`
> **Related**: REQ-044（MCP registry，治理骨架 + 执行时工具调用来源）/ REQ-046（背调 Skill 首个消费方）/ REQ-043（Agentic 编排，V2）/ REQ-047（产物归档，V2）

---

## 1. 问题陈述

REQ-044 交付了 MCP registry，解决"拿到事实"（工具调用可注册、可鉴权、可审计）。但 REQ-046 背调场景还需要一层 **SOP 能力**：把"查哪些维度、按什么顺序调哪些 MCP 工具、如何组织成结构稳定的报告"固化为可复用、可治理、可审计的资产。当前这层缺失：

- 背调 SOP 只散落在文档与 AI IDE 提示词里，产品后端无注册、版本、权限、执行入口。
- 各业务页面若各自硬编码"调哪些 QCC 工具 + 怎么拼 prompt"，SOP 失控、无法审计、无法复用到其他合规风控场景（租约预警、招投标合规等）。
- 企查查官方 Skill 市场（`agent.qcc.com/skills`，27 个 skill）提供了可复用的尽调 / 背调 SOP，但产品后端没有"导入 -> 注册 -> 治理 -> 执行"的最小闭环。

需要一个平台级最小 **Skill registry**：以**声明式 SOP 模板**为 Skill 形态，支持导入 / 注册 / 启停 / 角色权限 / 版本 / 执行审计，并提供平台编排执行引擎（按 SOP 步骤经 REQ-044 `MCPInvocationService` 调 MCP 工具收集事实，再由 LLM 按模板合成结构化产物）。首个真实 Skill 为**企业 360 背调 SOP**。

## 2. 目标

- `metaedu.skills` 注册表 + CRUD / 启停 API，唯一约束 `(tenant_id, code, version)`，与 REQ-044 `mcp_servers` 同构。
- Skill 形态为**声明式 SOP 模板**（YAML 定义：元数据 + 步骤 + 工具绑定 + 报告模板）；DB 存模板正文，平台可治理。
- per-skill 角色权限（`allowed_roles`），执行路径强制校验；`enabled` 默认 false。
- `metaedu.skill_execution_audit` 执行审计：skill、版本、subject digest、各步骤 MCP 调用审计引用、LLM 合成 digest、ok / 错误 / 耗时、tenant、caller。
- 平台编排执行引擎 `SkillRunner`：解析 skill -> 校验 enabled / 角色 -> 按 SOP 步骤经 `MCPInvocationService` 调 MCP 工具（复用 REQ-044 审计）-> LLM 按模板合成 -> 写执行审计；业务侧统一入口。
- 版本管理：同 code 多版本，执行固定到具体版本，版本可独立启停。
- 以企业 360 背调 SOP 为首个真实 Skill，用真实 QCC MCP + 真实 LLM 完成端到端执行验收。
- 最小管理页：列表 / 注册（导入模板）/ 启停 / 版本 / 删除 / 执行审计查询 + 试运行调试。

## 3. 非目标

- 不做通用 Skill 市场（发现 / 评分 / 上架下架 / 第三方上传审核）。
- 不做可执行脚本包 / 代码沙箱执行（V1 只做声明式 SOP 模板编排）。
- 不做 Agentic 自主规划 / 多工具重试 / 会话级工具可用性编排（归 REQ-043）。
- 不做背调业务编排、企业主体锚定、报告归档与人工确认闭环（归 REQ-046 / REQ-047）。
- 不做内部业务系统 MCP 契约抽象（归 REQ-048）；首版背调 SOP 只依赖已就绪的 QCC MCP。
- V1 前端只做最小管理页；不做 SOP 可视化编辑器、执行 DAG 图、统计图表（V2）。
- 不做执行配额 / 限流 / 计费（V2）。

---

## 4. 架构设计

### 4.1 组件边界

新上下文 `app/contexts/skill_registry/`（application / domain / infrastructure / interfaces 骨架，与 `mcp_registry` 同模式）：

| 组件 | 层 | 职责 |
|------|-----|------|
| `Skill` (domain entity) | domain | 注册实体：code / name / version / description / sop_template / allowed_roles / enabled；纯 Python dataclass |
| `SopTemplate` (value object) | domain | 解析 + 校验 SOP 模板（YAML -> 结构化对象）；`SopTemplateError`（缺字段 / 非法工具引用） |
| `SkillRepository` | infrastructure | `skills` CRUD，所有查询强制 `tenant_id` |
| `SkillRegistryService` | application | 注册 / 更新 / 启停 / 版本 / 删除编排；管理 RBAC（admin / data_admin / super_admin）；`(code, version)` 冲突 409；注册时校验 SOP 模板 + 引用的 MCP server 已注册 |
| `SkillRunner` | application | 执行编排：解析 skill -> 校验 enabled -> 校验 caller role -> 按 SOP 步骤经 `MCPInvocationService` 调工具 -> LLM 按 `report_template` 合成 -> 写执行审计；业务侧统一入口 |
| `SkillExecutionAuditRepository` | infrastructure | `skill_execution_audit` 写入与按 tenant 分页查询 |
| `skill_registry_router` | interfaces/api | CRUD / 启停 / 版本 / 审计查询 / 试运行 REST；轻量，只鉴权 + 参数解析 + 异常映射 |
| `SkillListView`（前端） | web/views | 最小管理页：列表 + 注册 modal（导入模板）+ 启停 + 版本 + 删除 + 审计抽屉 + 试运行；复用 admin/TemplateListView 模式 |

消费方：

- REQ-046 背调工作台：只经 `SkillRunner` 执行背调 SOP，不直连 MCP / LLM；报告产物由 REQ-046 持久化与归档（REQ-047）。
- REQ-043 编排层（V2）：可作为工具发现 / 调用 Skill 的入口。

**装配边界**：`SkillRunner` 是唯一持有 `MCPInvocationService`（REQ-044）+ LLM 入口（`shared/llm/chat.py`）的地方；业务代码不自行编排 SOP。

### 4.2 数据模型

`metaedu.skills`（migration 022）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | default uuid4 |
| `tenant_id` | UUID NOT NULL, index | 跨租户隔离硬边界 |
| `code` | varchar(50) | 英文标识，`^[a-z][a-z0-9_]*$`，如 `enterprise_360_dd` |
| `version` | varchar(20) | 语义化版本，如 `1.0.0`；同 code 多版本并存 |
| `name` | varchar(200) | 显示名，如"企业 360 背调" |
| `description` | text nullable | 做什么 + 何时触发（对齐 agentskills.io `description`） |
| `sop_template` | text NOT NULL | SOP 模板 YAML 正文（见 §4.3）；**不含 secret** |
| `source_ref` | varchar(500) nullable | 模板来源（如企查查官方 skill URL / 导入文件名），可追溯 |
| `allowed_roles` | JSONB | 允许执行的角色列表；空列表 = 仅 super_admin |
| `enabled` | boolean NOT NULL default false | 注册后默认停用，需显式启用 |
| `is_active` | boolean NOT NULL default true | 软删标记 |
| `created_by` | UUID NOT NULL | |
| `created_at` / `updated_at` | timestamp | naive UTC |

唯一约束：`uq_skills_tenant_code_version (tenant_id, code, version)`。

`metaedu.skill_execution_audit`（migration 022）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `tenant_id` | UUID NOT NULL, index | 与 skill 同行隔离 |
| `skill_id` | UUID NOT NULL FK → skills.id | |
| `skill_code` | varchar(50) | 冗余，审计可读性（skill 软删后仍可追溯） |
| `skill_version` | varchar(20) | 执行时固定的版本 |
| `caller_type` | varchar(30) | `http_api` / `adapter:due_diligence` / `service` |
| `caller_user_id` | UUID nullable | 触发用户 |
| `subject_digest` | varchar(64) nullable | 执行主体（如企业名 / 统一社会信用代码）规范化 JSON 的 sha256；**原始主体标识不落审计库** |
| `steps_digest` | varchar(64) nullable | 各步骤结果摘要（步骤 id + 对应 `mcp_invocation_audit.id` 列表）的 sha256；事实本体不落审计库 |
| `report_digest` | varchar(64) nullable | LLM 合成报告的 sha256；报告正文不落审计库（产物归 REQ-046/047） |
| `ok` | boolean NOT NULL | |
| `error_code` | varchar(50) nullable | 归一化错误码（`disabled` / `forbidden` / `template_error` / `tool_unavailable` / `tool_error` / `llm_error` / `timeout`） |
| `error_message` | varchar(500) nullable | 截断，不含 secret / 原始企业敏感数据 |
| `duration_ms` | int NOT NULL | |
| `created_at` | timestamp | |

索引：`(tenant_id, skill_id, created_at)`、`(tenant_id, created_at)`。

**摘要口径**：digest = `sha256(canonical_json)`（排序 key 紧凑 JSON），与 REQ-044 一致；审计只证明"用哪个版本对什么主体跑出什么产物"的可复现性，不保存事实 / 报告本体。REQ-046 报告 evidence_refs 可引用 `skill_execution_audit.id` 及其间接关联的 `mcp_invocation_audit.id`。

### 4.3 SOP 模板 schema（两层）

DB `sop_template` 存 YAML 正文，分两层（对齐调研结论）：

**A 层 · 元数据**（对齐 agentskills.io 开放标准，保证生态兼容）：

```yaml
name: enterprise-360-dd            # 必需，kebab-case ≤64（与 code 映射）
description: 企业 360 背调：入驻/投决前核验主体与风险   # 必需 ≤1024
metadata: {version: "1.0.0", category: due-diligence, author: platform}
allowed-tools: [qcc-company, qcc-risk]   # 本平台映射为 MCP server code 列表
```

**B 层 · SOP 正文**（借鉴企查查官方 SKILL.md 范式：工作流维度 -> 工具链 -> 量化阈值 -> 填空式报告骨架）：

```yaml
mcp_dependencies:                  # 必需 MCP server 及用途
  - {server: qcc-company, required: true}
  - {server: qcc-risk, required: true}
principles:                        # 全局执行纪律（如"数据时效明示""不编造缺失值"）
  - 缺失数据显式标注，不编造默认值
steps:                             # 工作流，每步 = 一个分析维度
  - id: subject_verify
    title: 主体工商核验与实控人穿透
    server: qcc-company            # D5：按 server_code 绑定 REQ-044 行
    tool: get_company_registration_info
    analysis_rules: [工商二要素不一致即标记高风险]
    output: 主体身份档案
  - id: risk_scan
    title: 司法与经营风险扫描
    server: qcc-risk
    tool: scan_risk
    analysis_rules: [失信 1 条即标记]
    output: 风险清单
report_template: |                 # 填空式报告骨架（模型只填值、不造结构）
  ## 事实数据
  ...
  ## AI 分析
  ...
  ## 待人工确认项
  ...
params: [{name: company_name, required: true}]
```

**校验规则**（`SopTemplate.validate`，注册时执行，失败 422）：

- A 层：`name` kebab-case、`description` 非空 ≤1024。
- B 层：`steps` 非空；每步 `id` 唯一、`server` + `tool` 必填；`analysis_rules` / `principles` 若存在必须是 list（标量拒绝，不静默拆字符）。
- `mcp_dependencies` **覆盖**语义：`declared ⊇ steps[].server`（超集许可，多声明未用的 server 是良性的）；缺省时按空声明处理并仍走覆盖校验——steps 非空时必然失败，故该字段事实上**必填**（与上文 `# 必需 MCP server 及用途` 一致）。
- 工具引用闭合：注册时校验 `steps[].server` 在本 tenant `mcp_servers` 已注册（不校验 tool 是否存在于远端 server，enable 试运行时经 `list_tools` 探活）。

**V1 不消费的字段**：`params` / `metadata` / `allowed-tools` 仅存档于 DB `sop_template` 正文，V1 `SopTemplate` VO 不解析（执行时 subject 由 caller 整体传入，runner 不强制 params 声明）；后续若需按 params 校验 subject 或展示元数据，再扩 VO 解析。

### 4.4 执行流程（SkillRunner）

```text
caller (REQ-046 adapter / 管理页试运行)
  -> SkillRunner.run(tenant_id, skill_code, version, subject, caller)
    -> repo.get_by_code_version(tenant_id, code, version)  # 未注册 -> NotFound，不审计
    -> check enabled                                       # 禁用 -> 审计 ok=False error_code=disabled
    -> check caller.role in allowed_roles                  # 越权 -> 审计 ok=False error_code=forbidden
    -> SopTemplate.parse + validate                        # 模板损坏 -> 审计 ok=False error_code=template_error
    -> for step in steps:                                  # 逐步经 REQ-044
         MCPInvocationService.invoke(server_code=step.server, tool_name=step.tool, params=subject)
         # 工具未注册/禁用/无权限/失败 -> 按策略：required 步失败即整体失败 error_code=tool_error（不编造事实）
    -> llm.chat(report_template + 收集的 facts)            # LLM 合成，error_code=llm_error
    -> 写执行审计（subject_digest / steps_digest / report_digest / ok / duration_ms）
    -> 返回结构化产物（事实 / AI 分析 / 待人工确认分区）给 caller
```

- 步骤执行顺序按 `steps` 数组顺序；required 步失败即整体失败并写审计，optional 步失败降级为"该维度缺失标注"（V1 全部按 required 处理，降级策略留 V2）。
- 每个 MCP 步骤调用已在 REQ-044 `mcp_invocation_audit` 留痕；`skill_execution_audit.steps_digest` 关联这些审计行 id。
- LLM 入口复用 `shared/llm/chat.py`（统一 chat + provider fallback），不新造 LLM client。

### 4.5 API 端点

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/api/v1/skills` | admin / data_admin / super_admin | 注册（含 SOP 模板校验；`(code,version)` 冲突 409；模板非法 422；引用未注册 server 422） |
| GET | `/api/v1/skills` | 所有登录用户（本 tenant） | 列表（不含 secret，本就没有） |
| GET | `/api/v1/skills/{id}` | 所有登录用户（本 tenant） | 详情（含 sop_template 正文） |
| PATCH | `/api/v1/skills/{id}` | admin / data_admin / super_admin | 更新元数据 / allowed_roles（sop_template 改动须走新版本） |
| POST | `/api/v1/skills/{id}/enable` | admin / data_admin / super_admin | 启用（可选 list_tools 探活引用 server，失败仍允许启用但返回警告） |
| POST | `/api/v1/skills/{id}/disable` | admin / data_admin / super_admin | 禁用该版本 |
| DELETE | `/api/v1/skills/{id}` | admin / data_admin / super_admin | 软删（is_active=false）；有审计行的版本不硬删 |
| GET | `/api/v1/skills/{id}/executions` | admin / data_admin / super_admin | 执行审计查询（分页，本 tenant） |
| POST | `/api/v1/skills/{id}/run` | admin / data_admin / super_admin | 试运行（调试入口，受 RBAC + 审计约束；返回结构化产物 + execution_audit_id） |

业务执行（REQ-046 背调）不走公开 API，走 `SkillRunner` 内部入口；`/run` 仅为管理页调试保留，与 REQ-044"不开通用 invoke API"一致地收敛在管理角色。

---

## 5. 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | `skills` / `skill_execution_audit` 建成，唯一约束 `(tenant_id, code, version)` 生效，migration upgrade / downgrade 幂等 | migration 测试 + 约束冲突用例（integration） |
| AC-2 | CRUD + 启停 + 版本 API 可用；管理操作仅 admin / data_admin / super_admin，其余 403 | API 测试（角色 × 操作矩阵）（unit / contract） |
| AC-3 | SOP 模板 schema 校验：缺步骤 / 缺 server·tool / 引用未注册 server 的模板被拒（422，稳定错误） | 单测（unit） |
| AC-4 | 禁用 skill 执行被拒（error_code=disabled）并写审计；启用后恢复 | 单测（unit） |
| AC-5 | 不在 `allowed_roles` 的角色执行被拒（error_code=forbidden）并写审计 ok=False | 单测 / API 测试（unit / contract） |
| AC-6 | 执行审计含 skill_code / version / subject_digest / steps_digest / report_digest / ok / error / duration_ms / tenant / caller；digest ≠ 原文，事实与报告正文不落审计库 | 真实 DB 集成测试（integration） |
| AC-7 | tenant A 的 skill 对 tenant B 不可见、不可执行；审计按 tenant 隔离 | 两 tenant 集成测试（integration） |
| AC-8 | 执行引擎按 SOP 步骤经 `MCPInvocationService` 调 MCP 工具；步骤工具未注册 / 禁用 / 无权限 / 失败时整体显式失败并写审计，不编造事实 | 单测（httpx mock transport + mock LLM）（unit） |
| AC-9 | 用真实 QCC MCP + 真实 LLM，对 1 个样例企业完成背调 SOP 端到端执行：产出结构稳定报告草案（事实 / AI 分析 / 待人工确认分区），执行审计齐备；secret 与企业敏感原文不进审计 | 手工真实验收 + 验收记录（manual / 真实验证，不由 CI 冒充） |
| AC-10 | 最小管理页可用：列表（本 tenant）、注册（导入模板）、启停、版本、删除、执行审计查询、试运行；管理按钮按角色显隐，越权被 API 拒 | 前端 vitest + UI smoke（unit / smoke） |
| AC-11 | 版本管理：同 code 可注册多版本，执行固定到指定版本，切换后新执行走新版本 | 集成测试（integration） |
| AC-12 | Backlog / current-work / work-log / Requirement 状态同步，验证层级如实声明 | 文档门禁（manual） |

---

## 6. 风险控制

| 风险 | 影响 | 缓解 |
|------|------|------|
| 企业敏感数据 / secret 泄漏进审计或日志 | 高 | 审计只存 digest；error_message 白名单化 + 截断；单测断言日志无 secret / 原始主体；安全清单纳入完成门禁 |
| LLM 编造事实 / 结构与模板漂移 | 高 | 填空式 `report_template`（模型只填值不造结构）；required 步失败即整体失败不编造；事实 / 分析 / 待确认分区（对齐 REQ-046 AC-5） |
| 步骤引用的 MCP server 变更导致执行漂移 | 中 | 执行固定 `version` + `skill_version` 落审计；注册时校验 server 已注册；enable 探活 |
| 业务方绕过 SkillRunner 自行编排 | 中 | 只有 `SkillRunner` 装配 invocation service + LLM；review 检查业务代码不直连；文档明确边界 |
| 模板 YAML 注入 / 超大模板 | 中 | 注册时 schema 校验 + 大小上限；YAML 安全加载（`safe_load`） |
| 执行耗时长（多步 MCP + LLM） | 低 | 步骤级超时复用 server.timeout_ms；整体时长记审计；异步执行 / 进度留 V2 |
| 新上下文拆分过度 | 低 | 与 mcp_registry 骨架一致；REQ-046 仅作为消费方 |

---

## 7. 决策记录（本次塑形确认）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| Skill 形态 | 声明式 SOP 模板 | 用户确认；可治理 / 可审计 / 安全，契合背调报告场景 |
| 执行模型 | 平台编排：MCP 工具 + LLM 合成 | 用户确认；每步可审计，复用 REQ-044，对齐 REQ-046 AC-5 |
| 代码归属 | 新上下文 `skill_registry`，背调 SOP 为首个 Skill | 用户确认；被 REQ-046 / REQ-043 多方消费 |
| 模板 schema | 两层：A 层对齐 agentskills.io，B 层借鉴企查查官方 SKILL.md 范式 | 调研确认三家收敛同形态；企查查范式正合报告场景 |
| 工具引用 | `server_code.tool_name` 绑定 REQ-044 registry 行 | 与 structured_data MCPAdapter 同口径；权限与审计复用 |
| 版本模型 | 同 code 多版本，执行固定版本 | 背调 SOP 会迭代；执行可复现要求固定版本 |
| 输出契约 | 结构化产物（事实 / 分析 / 待确认分区） | 对齐 REQ-046 AC-5，不混写 |
| 执行入口 | 内部 `SkillRunner` + 管理页试运行；不开通用公开 invoke API | 缩小攻击面，与 REQ-044 一致 |

---

## 8. 超出范围（V2 留口）

- 通用 Skill 市场 / 第三方上传审核 / 评分
- 可执行脚本包 / 代码沙箱执行
- Agentic 自主规划 / 多步重试 / 会话级编排（REQ-043）
- optional 步失败降级策略、条件分支、循环等复杂 SOP 控制流
- 执行异步化 / 进度跟踪 / 配额限流计费
- SOP 可视化编辑器 / 执行 DAG 图 / 统计
- 报告产物持久化与归档（REQ-046 / REQ-047）

---

## 9. 参考

- Requirement: `docs/01-product-planning/05-requirements/REQ-045-skill-registry-and-execution.md`
- REQ-044 spec（治理骨架 + MCPInvocationService + 审计口径）: `docs/02-delivery-plans/01-specs/2026-07-20-req-044-mcp-registry.md`
- REQ-046 requirement（背调 SOP 诉求 + 报告结构 §报告结构）: `docs/01-product-planning/05-requirements/REQ-046-enterprise-360-due-diligence-workbench.md`
- 现状代码（server_code.tool_name 调用口径）: `packages/server-python/app/contexts/structured_data/infrastructure/mcp_adapter.py`
- LLM 入口: `packages/server-python/app/shared/llm/chat.py`
- 企查查 Skill 市场: https://agent.qcc.com/skills （SKILL.md 分发 `agent.qcc.com/skill/v1/{category}/{id}/SKILL.md`）
- agentskills.io 开放标准: https://agentskills.io/specification
- 安全规则: `docs/03-engineering-governance/01-rules/security.md`
- 架构规则: `docs/03-engineering-governance/01-rules/architecture.md`
