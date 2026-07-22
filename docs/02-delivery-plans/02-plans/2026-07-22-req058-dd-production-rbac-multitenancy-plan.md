# REQ-058 实施 Plan：企业背调生产级 RBAC、制审分离与多租户配置

> Requirement: `docs/01-product-planning/05-requirements/REQ-058-due-diligence-production-rbac-and-multitenancy.md`
> Shaping: 2026-07-22 冻结角色矩阵 / 配置模型 / 迁移策略（见 spec Decisions）

## Context

REQ-046 V0 已完成 tenant-scoped 任务/报告/证据链，但：
- 所有认证用户都能 create/run/confirm/archive（`assert_can_run` 只校验状态，不校验角色）
- 报告生成者可自行锁版（无 maker-checker）
- Internal MCP / DD Catalog 用 `settings` 全局单值，不支持多租户

BUG-017/019 已关闭，依赖满足。本 plan 基于 shaping 冻结设计实施。

## 设计原则（来自 spec Decisions）

1. 复用 `RoleEnum` + `HIGH_PRIVILEGE_ROLES`，不新增角色
2. 所有报告强制 maker-checker（confirm/reject 需 admin/data_admin 且 ≠ generated_by）
3. 任务可见性 = 本人 + 分配对象 + 高权；DdTask 加 `assignee_id`
4. 新建 `tenant_scoped_config` 表，Internal MCP/Catalog/Skill binding 迁 DB；settings 作开发 fallback

## Slices

### Slice 1：tenant_scoped_config 表 + 迁移 + 配置 service（AC-4/AC-6）
- [ ] migration 025：`metaedu.tenant_scoped_config`（PK tenant_id+config_key）
- [ ] `app/contexts/identity/application/tenant_config_service.py`：`get_config(tenant_id, key)` / `set_config(tenant_id, key, value, updated_by)` / `list_configs(tenant_id)`
- [ ] `seed_tenant_config.py`：把 `settings.internal_mcp_tenant_id` / `settings.dd_catalog_id` 写入 DEFAULT_TENANT
- [ ] Internal MCP server `_tenant_id()` 改读 `tenant_scoped_config`（按 caller tenant_id），settings fallback
- [ ] DD Catalog resolver 同理改读 tenant config
- [ ] `tests/contexts/identity/test_tenant_config_service.py`：CRUD + 跨 tenant 隔离 + settings fallback
- [ ] `tests/contexts/due_diligence/test_internal_mcp_tenant_binding.py`：tenant A/B 不同 binding，执行不串租户

### Slice 2：DdTask assignee_id + 可见性策略（AC-1/AC-2/AC-5）
- [ ] migration 026：`dd_tasks` 加 `assignee_id UUID NULL`
- [ ] `DdTask` domain 加 `assignee_id` + `visible_to(user_id, role)` 方法
- [ ] `dd_task_service.list` 改 WHERE `created_by=:uid OR assignee_id=:uid OR role IN HIGH_PRIVILEGE`
- [ ] `dd_task_service.get` 跨 tenant/不可见 -> 404
- [ ] super_admin 看 status only（不返 report 原文/evidence）
- [ ] `tests/contexts/due_diligence/test_task_visibility.py`：本人/分配对象/高权/跨 tenant 4 矩阵

### Slice 3：DD 动作权限矩阵 + maker-checker（AC-1/AC-3/AC-6）
- [ ] `app/contexts/due_diligence/application/dd_permissions.py`：`can(action, role, task, user_id, report)` 矩阵
- [ ] `dd_router` 所有端点加 `_require_permission(action, ...)` 守卫
- [ ] `confirm`/`reject` 强制 `role IN (admin,data_admin)` 且 `user_id != report.generated_by`，记录 actor+reason+time
- [ ] `dd_orchestrator.run` 校验 caller 有 run 权限
- [ ] `tests/contexts/due_diligence/test_dd_permissions.py`：矩阵全枚举（leader/admin/data_admin/super_admin/teacher 各动作）
- [ ] `tests/contexts/due_diligence/test_maker_checker.py`：生成者 confirm 拒绝；授权复核 confirm/reject 通过；记录审计

### Slice 4：配置变更审计 + 平台管理员业务原文隔离（AC-5/AC-6）
- [ ] `tenant_config_service.set_config` 写 `dd_evidence` 或专用审计日志（actor+key+old/new digest）
- [ ] super_admin 调 DD read 端点 -> 仅 status，不返 report_content/evidence
- [ ] `tests/contexts/due_diligence/test_platform_admin_isolation.py`：super_admin 看不到报告原文/证据

### Slice 5：REQ-046 真实企业样例回归 + 收口（AC-7）
- [ ] `tests/real_world/test_req058_due_diligence_rbac_e2e.py`：creator(leader) -> runner(leader) -> reviewer(admin) 闭环，新权限模型下通过
- [ ] 既有 REQ-046 测试 fixture 迁移（补角色 + assignee）
- [ ] 全量 pytest / ruff / check-engineering-docs / git diff --check
- [ ] 工作台归档 + work-log

## 关键文件

- `app/contexts/identity/application/tenant_config_service.py` - 新增
- `app/contexts/due_diligence/application/dd_permissions.py` - 新增（动作矩阵）
- `app/contexts/due_diligence/application/dd_task_service.py` - 可见性 + assignee
- `app/contexts/due_diligence/interfaces/api/dd_router.py` - 权限守卫
- `app/internal_mcp/server.py` - tenant_scoped_config 解析
- `alembic/versions/025_tenant_scoped_config.py` - 新增迁移
- `alembic/versions/026_dd_tasks_assignee.py` - 新增迁移
- `scripts/seed_tenant_config.py` - 新增迁移脚本

## Global Constraints

- 不重写 REQ-046 报告结构（spec Dependencies）
- 不新增角色（D-1）
- 不引入 risk_level 字段（D-2 follow-up）
- 复用 BUG-017 `HIGH_PRIVILEGE_ROLES` + BUG-019 `security_logger` 审计模式
- 既有 REQ-046 测试迁移 0 回归（AC-7 真实企业样例仍可跑）

## Non-goals

- 风险等级配置（D-2 follow-up）
- settings 双源收口（D-4 follow-up，本任务保留 fallback）
- 招商/合规专用角色（D-1 排除）
- 完整 Vault 产品（沿用 BUG-019 命名空间）

## 风险与回滚

- **既有 REQ-046 测试用任意角色 run/confirm**：需迁移测试 fixture 补角色 + assignee；可能批量改
- **Internal MCP tenant 解析改动影响 QCC opt-in 验收**：seed 脚本保证 DEFAULT_TENANT 兜底，QCC 验收脚本不受影响
- **maker-checker 强制可能阻断现有自动化**：REQ-046 V0 自动 confirm 流程需改为 leader run + admin confirm 两步
- **回滚**：每 Slice 独立 commit + 迁移可下行

## 验证摘要（shaping 阶段未实施，待 Slice 5 收口时填可复核证据）

- 预期新增 ~25 后端测试 + 既有 REQ-046 套件迁移
- 预期全量后端测试用例 1325+ 项通过（未运行，待实施）
- AC-7 真实企业样例 creator->runner->reviewer 闭环通过（待实施验证）
- 安全闸：AC-1 未经授权角色拒；AC-2 跨 tenant 404；AC-3 maker≠checker；AC-4 tenant A/B 不串；AC-5 平台管理员无业务原文；AC-6 审计链完整（待实施验证）