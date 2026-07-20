# REQ-045 Implementation Plan: Skill 注册、管理与调用能力（最小 Skill registry）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建设 tenant 级最小 Skill registry（声明式 SOP 模板的导入 / 注册 / 启停 / 角色权限 / 版本 / 执行审计）+ 平台编排执行引擎（按 SOP 步骤经 REQ-044 `MCPInvocationService` 调 MCP 工具，再由 LLM 按模板合成结构化产物），以企业 360 背调 SOP 为首个真实 Skill 完成端到端验收。

**Architecture:** 新上下文 `app/contexts/skill_registry/`（domain `Skill` / `SopTemplate`，infrastructure `SkillRepository` / `SkillExecutionAuditRepository`，application `SkillRegistryService` / `SkillRunner`，interfaces `skill_registry_router`）；`SkillRunner` 是唯一装配 REQ-044 `MCPInvocationService` + LLM 入口（`shared/llm/chat.py`）的地方；审计只存 digest，事实与报告正文不落审计库。

**Tech Stack:** Python 3.14 + FastAPI + SQLAlchemy 2.x async + asyncpg + pytest + pydantic v2；alembic migration 022；PyYAML（`safe_load`）；复用 REQ-044 `MCPInvocationService` 与 `shared/llm/chat.py`

## Global Constraints

- 不破坏现有 backend tests（mcp_registry / structured_data 套件必须全绿）
- 所有新表带 `tenant_id`；`skills` 唯一约束 `(tenant_id, code, version)`
- secret 与企业敏感原文只以 digest 存在；DB 审计 / API 响应 / 日志永不出现事实 / 报告正文 / secret 值
- SOP 模板用 `yaml.safe_load`；注册时 schema 校验 + 大小上限；步骤工具引用必须闭合到本 tenant 已注册 `mcp_servers`
- 业务代码禁止自行编排 SOP；只有 `SkillRunner` 装配 invocation service + LLM
- 未注册 / 禁用 / 无权限 / 工具失败的执行显式失败并写审计（ok=False），不得编造事实冒充成功
- pytest 必须在 `packages/server-python/` 下跑；`-W error`
- ruff 0 / check-engineering-docs 0 / `git diff --check` 干净
- 每个 Task 独立可验证、独立 commit

---

## File Structure

### 后端新建（context: skill_registry）
- `app/contexts/skill_registry/__init__.py`
- `app/contexts/skill_registry/domain/skill.py` — `Skill` dataclass + `SopTemplate` 值对象（解析 + 校验）+ `SopTemplateError`
- `app/contexts/skill_registry/infrastructure/skill_models.py` — `SkillModel` / `SkillExecutionAuditModel`（metaedu schema）
- `app/contexts/skill_registry/infrastructure/skill_repository.py` — CRUD + tenant 强制过滤 + 按 `(code, version)` 查询
- `app/contexts/skill_registry/infrastructure/skill_execution_audit_repository.py` — 审计写入 / 按 tenant 分页查询
- `app/contexts/skill_registry/application/skill_registry_service.py` — 注册 / 更新 / 启停 / 版本 / 删除 + 管理 RBAC + 模板校验编排
- `app/contexts/skill_registry/application/skill_runner.py` — 执行编排 + 审计
- `app/contexts/skill_registry/interfaces/api/skill_registry_router.py` — `/api/v1/skills` REST

### 后端修改
- `alembic/versions/022_skill_registry.py` — 新 migration（两表 + 约束 + 索引）
- `app/shared/infrastructure/models.py` — 注册新 ORM model
- `app/main.py` — include `skill_registry_router`

### 测试新建
- `tests/contexts/skill_registry/test_skill_registry_migration.py` — upgrade/downgrade + 唯一约束
- `tests/contexts/skill_registry/test_sop_template.py` — 模板解析 / 校验（合法 / 缺步骤 / 缺 server·tool / 引用未注册 server）
- `tests/contexts/skill_registry/test_skill_registry_service.py` — CRUD / 启停 / 版本 / RBAC / `(code,version)` 冲突
- `tests/contexts/skill_registry/test_skill_runner.py` — 执行编排（httpx mock transport + mock LLM）：步骤顺序 / 失败分支 / 审计字段
- `tests/contexts/skill_registry/test_skill_execution_audit.py` — 审计 digest 口径（真实 DB）
- `tests/contexts/skill_registry/test_skill_tenant_isolation.py` — 两 tenant 隔离（真实 DB）
- `tests/real_world/test_req045_due_diligence_acceptance.py` — AC-9 真实端到端验收（opt-in）

### 前端新建（Task 4）
- `packages/web/src/views/skill-registry/SkillListView.vue` — 列表 + 注册 modal（导入模板）+ 启停 + 版本 + 删除 + 审计抽屉 + 试运行
- `packages/web/src/services/skillRegistry.ts` — API client
- 路由注册 + 菜单入口
- `packages/web/src/views/skill-registry/SkillListView.spec.ts` — vitest

### 文档修改（Task 5）
- `docs/01-product-planning/05-requirements/REQ-045-skill-registry-and-execution.md` — Status + Delivery Record
- `docs/01-product-planning/04-backlog.md` — REQ-045 行状态与链接
- `docs/03-engineering-governance/current-work.md` — TASK card
- `docs/03-engineering-governance/work-log.md` — +1 index row
- `docs/01-product-planning/06-ai-applications/README.md` — REQ-045 候选行状态同步

---

## Task 1: alembic migration 022 + ORM models + domain（SopTemplate）

**Files:**
- Create: `alembic/versions/022_skill_registry.py`
- Create: `app/contexts/skill_registry/infrastructure/skill_models.py`
- Create: `app/contexts/skill_registry/domain/skill.py`
- Modify: `app/shared/infrastructure/models.py`（注册 model）
- Test: `tests/contexts/skill_registry/test_skill_registry_migration.py` / `test_sop_template.py`（new）

**Interfaces:**
- Consumes: 现有 `Base` / `_utcnow` 惯例（参考 `catalog_models.py` / `mcp_server_models.py`）；PyYAML
- Produces: `metaedu.skills` + `metaedu.skill_execution_audit` 两表；`SkillModel` / `SkillExecutionAuditModel` ORM；`Skill` domain dataclass + `SopTemplate` 值对象

- [ ] **Step 1: 写 migration 022**

两表结构按 spec §4.2：`skills`（tenant_id / code / version / name / description / sop_template / source_ref / allowed_roles JSONB / enabled default false / is_active / created_by / 时间戳 + `uq_skills_tenant_code_version`）；`skill_execution_audit`（tenant_id / skill_id FK / skill_code / skill_version / caller_type / caller_user_id / subject_digest / steps_digest / report_digest / ok / error_code / error_message / duration_ms / created_at + 两索引）。`downgrade` 对称 drop。

- [ ] **Step 2: 写 ORM models**

`SkillModel` / `SkillExecutionAuditModel`，`__table_args__ = {"schema": "metaedu"}`，naive UTC `_utcnow`，与 `MCPServerModel` 同模式；`app/shared/infrastructure/models.py` 注册。

- [ ] **Step 3: 写 domain entity + SopTemplate**

`Skill` dataclass；`SopTemplate` 值对象：`yaml.safe_load` 解析 + `validate()`（spec §4.3 校验规则：A 层 name/description、B 层 steps 非空 / 每步 id 唯一 / server+tool 必填 / mcp_dependencies 与 steps[].server 一致）；非法抛 `SopTemplateError`。注意步骤工具引用"是否已注册 server"的闭合校验放 service 层（需 DB），domain 只做结构校验。

- [ ] **Step 4: migration + 模板测试**

upgrade → 断言两表 / 约束 / 索引存在；同 tenant 同 `(code,version)` 冲突、不同 version 允许、不同 tenant 允许；downgrade 幂等。`test_sop_template.py`：合法模板解析通过；缺步骤 / 缺 server·tool / name 非 kebab-case / description 超长 各抛 `SopTemplateError`。

- [ ] **Step 5: 跑测试 + commit**

```bash
cd packages/server-python && pytest tests/contexts/skill_registry/ -v -W error && ruff check app/ tests/
git commit -m "feat(skill-registry): REQ-045 migration 022 skills + skill_execution_audit 表与 ORM + SopTemplate"
```

---

## Task 2: Registry CRUD API + 管理 RBAC + 版本 + 模板校验编排

**Files:**
- Create: `app/contexts/skill_registry/infrastructure/skill_repository.py`
- Create: `app/contexts/skill_registry/application/skill_registry_service.py`
- Create: `app/contexts/skill_registry/interfaces/api/skill_registry_router.py`
- Modify: `app/main.py`（include router）
- Test: `tests/contexts/skill_registry/test_skill_registry_service.py`（new）

**Interfaces:**
- Consumes: `get_current_user` / `get_session`；Task 1 domain + repository；`mcp_registry` 的 `MCPServerRepository`（校验步骤引用 server 已注册）
- Produces: `/api/v1/skills` CRUD + enable / disable / delete（spec §4.5 前 7 行端点）

- [ ] **Step 1: Repository** — 所有方法强制 `tenant_id`；`get_by_id` / `get_by_code_version` / `list_by_tenant` / `list_versions(code)` / `create` / `update` / `set_enabled` / `soft_delete`。

- [ ] **Step 2: Service** — 管理操作仅 `admin` / `data_admin` / `super_admin`（仿 `MCPRegistryService` 权限模式：`SkillRegistryPermissionError` / `SkillVersionConflictError`）；注册时编排模板校验：`SopTemplate.validate()` + 步骤引用 server 在本 tenant 已注册（查 `mcp_servers`），非法 → 422；`(code, version)` 冲突 → 409；sop_template 改动须走新版本（PATCH 不允许改 sop_template）。

- [ ] **Step 3: Router** — 7 个端点；轻量只做鉴权 + 参数解析 + 异常映射（403 / 404 / 409 / 422）；响应 DTO 不含 secret（本就没有）。

- [ ] **Step 4: 测试** — 角色 × 操作矩阵（employee / teacher / student 管理操作 403）；CRUD + 版本全流程（同 code 多版本并存、list_versions）；`(code,version)` 冲突 409；模板非法（缺步骤 / 引用未注册 server）422；sop_template PATCH 被拒。

- [ ] **Step 5: 跑测试 + commit**

```bash
cd packages/server-python && pytest tests/contexts/skill_registry/ -v -W error && ruff check app/ tests/
git commit -m "feat(skill-registry): REQ-045 registry CRUD API + 管理 RBAC + 版本 + SOP 模板校验编排"
```

---

## Task 3: SkillRunner 执行引擎 + 执行审计 + LLM 合成

**Files:**
- Create: `app/contexts/skill_registry/application/skill_runner.py`
- Create: `app/contexts/skill_registry/infrastructure/skill_execution_audit_repository.py`
- Create: `app/contexts/skill_registry/interfaces/api/skill_registry_router.py` 增补 `GET /{id}/executions` + `POST /{id}/run`
- Test: `tests/contexts/skill_registry/test_skill_runner.py` / `test_skill_execution_audit.py` / `test_skill_tenant_isolation.py`（new）

**Interfaces:**
- Consumes: Task 1/2 domain + repository；REQ-044 `MCPInvocationService` + `InvocationCaller`；`shared/llm/chat.py`
- Produces: `SkillRunner.run(tenant_id, skill_code, version, subject, caller) -> SkillResult`；执行审计

- [ ] **Step 1: SkillRunner** — 按 spec §4.4 流程：解析 skill -> enabled -> role ∈ allowed_roles -> SopTemplate.parse+validate -> 逐步经 `MCPInvocationService.invoke(server_code=step.server, tool_name=step.tool, params=subject)` 收集 facts -> `llm.chat(report_template + facts)` 合成 -> 写执行审计。required 步工具失败即整体失败 `error_code=tool_error`（不编造事实）；LLM 失败 `error_code=llm_error`。digest = sha256 canonical JSON（与 REQ-044 同口径）；`steps_digest` 关联各 `mcp_invocation_audit.id`。

- [ ] **Step 2: 执行审计** — 每个失败分支写审计（ok=False + error_code），未注册除外（无 skill 可关联，直接抛 NotFound）；error_message 截断 500 且不含 secret / 原始企业敏感数据。

- [ ] **Step 3: 试运行端点** — `POST /{id}/run`（管理角色）：调 `SkillRunner.run` 返回结构化产物 + execution_audit_id；`GET /{id}/executions` 分页查审计。

- [ ] **Step 4: 测试** — runner 单测（httpx mock MCP transport + mock LLM：成功路径步骤顺序 / 工具失败整体失败不编造 / LLM 失败 / 禁用 / 越权）；审计集成测试（真实 DB 断言 digest ≠ 原文、字段齐全、steps_digest 关联 mcp 审计 id）；两 tenant 隔离集成测试（互不可见 / 不可执行）；mcp_registry + structured_data 全量回归。

- [ ] **Step 5: 跑测试 + commit**

```bash
cd packages/server-python && pytest tests/contexts/skill_registry/ tests/contexts/mcp_registry/ tests/contexts/structured_data/ -v -W error && ruff check app/ tests/
git commit -m "feat(skill-registry): REQ-045 SkillRunner 执行引擎 + 执行审计 + LLM 合成"
```

---

## Task 4: 最小管理 UI（列表 + 注册导入 + 启停 + 版本 + 删除 + 审计 + 试运行）

**Files:**
- Create: `packages/web/src/views/skill-registry/SkillListView.vue`
- Create: `packages/web/src/services/skillRegistry.ts`
- Modify: 前端路由 + 菜单（按现有约定）
- Test: `packages/web/src/views/skill-registry/SkillListView.spec.ts`（new）

**Interfaces:**
- Consumes: Task 2 的 `/api/v1/skills` REST + Task 3 的 `GET /{id}/executions` + `POST /{id}/run`
- Produces: 最小管理页（复用 admin/TemplateListView 模式）

- [ ] **Step 1: API client** — `skillRegistry.ts`：list / create / update / enable / disable / delete / listVersions / listExecutions / run；类型与后端 DTO 对齐（无 secret 字段）。

- [ ] **Step 2: 列表页** — 表格展示本 tenant skill（code / version / name / enabled / created_at）；注册 modal（code / version / name / description / sop_template YAML 导入 textarea + 格式提示 / source_ref / allowed_roles）；启停 switch；版本切换查看；删除确认；行内"审计"按钮开抽屉分页展示 execution（version / ok / duration / error / created_at）；"试运行"按钮开 modal（填 subject，调 run，展示结构化产物分区）。

- [ ] **Step 3: 权限显隐** — 管理按钮（注册 / 启停 / 删除 / 试运行）仅 admin / data_admin / super_admin 可见；其余角色只读列表。

- [ ] **Step 4: vitest** — 渲染列表、注册提交调用 API、启停切换、版本切换、越权角色按钮隐藏、试运行调用 run；mock axios + auth store + toast（仿 McpServerListView.spec.ts 模式）。

- [ ] **Step 5: 跑测试 + commit**

```bash
cd packages/web && pnpm vitest run src/views/skill-registry && pnpm lint && pnpm typecheck
git commit -m "feat(skill-registry): REQ-045 最小管理 UI（列表 + 注册导入 + 启停 + 版本 + 删除 + 审计 + 试运行）"
```

---

## Task 5: 企业 360 背调 SOP 真实端到端验收 + closeout

**Files:**
- Create: `tests/real_world/test_req045_due_diligence_acceptance.py`（opt-in 手工验收）
- Create: 首个背调 SOP 模板 seed（随验收脚本内联或 `app/contexts/skill_registry/templates/enterprise_360_dd.yaml`）
- Modify: `docs/01-product-planning/05-requirements/REQ-045-skill-registry-and-execution.md`
- Modify: `docs/01-product-planning/04-backlog.md`
- Modify: `docs/03-engineering-governance/current-work.md`
- Modify: `docs/03-engineering-governance/work-log.md`
- Modify: `docs/01-product-planning/06-ai-applications/README.md`

- [ ] **Step 1: 背调 SOP 模板落地** — 基于企查查官方 SKILL.md 范式 + 通用尽调维度，写首个 `enterprise_360_dd` SOP 模板（步骤绑定已注册的 QCC server 工具：主体核验 / 股权穿透 / 司法风险 / 经营风险 / 财务底盘 / 高管背调 -> report_template 填空骨架，事实 / AI 分析 / 待人工确认分区）。模板只引用 REQ-044 已注册且启用的 QCC server。

- [ ] **Step 2: 真实端到端验收（AC-9，manual / 真实验证）** — opt-in（`RUN_QCC_AC9=1` + `QCC_MCP_TOKEN` + LLM provider key）：注册并 enable 背调 skill -> 对 1 个公开样例企业 `SkillRunner.run` -> 核验结构化产物分区稳定、执行审计齐备（subject/steps/report digest、duration、ok=true）、secret 与企业敏感原文不进审计；写验收记录（不含 secret、不含完整企业敏感数据）。

- [ ] **Step 3: 文档同步** — Requirement Status → 🟢 Done + Delivery Record 补各 Task 事实（commit hash / PR）；backlog REQ-045 行 ⚫ Candidate → 🟢 Done 并补链接；current-work TASK card 收口；work-log +1 行；ai-applications README 候选行状态同步。

- [ ] **Step 4: 跑门禁 + commit**

```bash
python3 scripts/check-engineering-docs && git diff --check
cd packages/server-python && pytest tests/ -q && ruff check app/ tests/
git commit -m "docs(closeout): REQ-045 实施完成 - 背调 SOP 真实端到端验收 + backlog/current-work/work-log 同步"
```

---

## Self-Review

1. **AC-1**: migration 022 两表 + `(tenant_id, code, version)` 唯一 + upgrade/downgrade 测试（Task 1）
2. **AC-2**: CRUD + 启停 + 版本 + 角色矩阵 403（Task 2）
3. **AC-3**: SOP 模板 schema 校验（缺步骤 / 缺 server·tool / 引用未注册 server 422）（Task 1/2）
4. **AC-4 / AC-5**: 禁用 / 越权执行被拒并写审计（Task 3）
5. **AC-6**: 执行审计字段 + digest 口径真实 DB 集成测试（Task 3）
6. **AC-7**: 两 tenant 隔离集成测试（Task 3）
7. **AC-8**: SkillRunner 经 MCPInvocationService 调用，工具失败整体失败不编造（Task 3）
8. **AC-9**: 背调 SOP 真实端到端手工验收，单独成行不冒充 CI（Task 5）
9. **AC-10**: 最小管理页可用 + 越权被拒（Task 4）
10. **AC-11**: 版本管理（同 code 多版本 + 执行固定版本）（Task 2/3）
11. **AC-12**: 文档同步 + 门禁（Task 5）

---

## Execution Handoff

Plan complete. 5 tasks, estimated 3-4 subagent rounds. Task 5 需要 QCC 凭证（`QCC_MCP_TOKEN`，已在 `.env`）+ LLM provider key（已在 `.env`），前序 Task 不阻塞。Task 3 依赖 REQ-044 已就绪的 `MCPInvocationService`；Task 4 前端依赖 Task 2/3 的 API；Task 5 背调 SOP 依赖 Task 1-3 + 已注册 QCC server。

**Two execution options:**
1. **Subagent-Driven (recommended)** - Fresh subagent per task + review between tasks
2. **Inline Execution** - Execute in this session
