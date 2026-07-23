# REQ-058: 企业背调生产级 RBAC、制审分离与多租户配置

> Status: 🟢 Done
> Priority: P0
> Milestone: P3 / Industrial Park Production
> Area: 企业背调 / RBAC / Audit / Multi-tenant
> Created: 2026-07-22
> Shaped: 2026-07-22（角色矩阵 / 配置模型 / 迁移策略已冻结，见 Decisions）
> Completed: 2026-07-22（5 Slice via PR #459~#463）
> Source: [2026-07-22 安全与质量复核](../../03-engineering-governance/04-retrospectives/2026-07-22-security-and-quality-follow-up-review.md)

## Problem

REQ-046 V0 已完成 tenant-scoped 任务、报告和证据链，但所有认证用户都可创建、执行、确认和归档报告；报告生成者可以自行锁版。Internal MCP 和 DD internal query 又分别使用进程级固定 tenant/catalog，无法支撑多个园区/集团安全共用平台。

## Users / Scenarios

- 招商人员创建并执行背调任务，但不能自行完成最终合规确认。
- 合规/法务复核报告、查看证据并确认或退回。
- 租户管理员配置本 tenant 的内部 MCP、问数 Catalog 和可执行 Skill。
- 平台管理员运维公共能力，但默认不能读取租户业务原文。

## Scope

- 定义 DD 动作权限矩阵：create/read/run/confirm/archive/evidence/configure。
- 支持任务所有者、分配对象和 tenant 范围的可见性策略。
- 对最终确认实施 maker-checker 制审分离；确认和退回均记录 actor、时间和理由。
- 将 Internal MCP tenant、DD Catalog 与 Skill 绑定改为 tenant-scoped 配置，不再使用全局单值。
- 配置变更、运行、确认、归档进入统一审计链。

## Acceptance

- AC-1：未经授权角色不能创建、运行、确认、归档或查看证据。
- AC-2：跨 tenant 的任务、报告、证据和配置均不可见、不可操作。
- AC-3：报告生成者默认不能确认自己生成的报告；授权复核人可以确认或退回。
- AC-4：tenant A/B 可绑定不同 Internal MCP、Catalog 和 Skill，执行结果不串租户。
- AC-5：平台管理员无业务授权时不能读取报告原文，仅能查看必要运行状态。
- AC-6：所有关键动作和配置变更具备可查询审计记录。
- AC-7：REQ-046 真实企业样例在新权限模型下完成 creator -> runner -> reviewer 闭环。

## Open Questions

> 2026-07-22 shaping 已冻结，决策见下；保留原问题供追溯。

- 首期采用现有通用角色映射，还是新增招商/合规岗位角色？
- maker-checker 是否所有报告强制，还是按风险等级配置？
- 任务可见性默认采用本人/团队/全租户哪一级？

## Decisions（2026-07-22 shaping 冻结）

### D-1 角色映射：复用现有通用角色（不改 RoleEnum）

| 业务岗位 | 系统角色 | DD 能力 |
|----------|----------|---------|
| 招商创建者 | `leader` | create / run（own+allotted）/ read（own+allotted）/ evidence |
| 合规复核 | `admin` / `data_admin` | read（tenant all）/ confirm-reject（checker）/ archive / evidence |
| 平台运维 | `super_admin` | read status only（无业务原文）/ configure tenant |
| 其他（teacher/employee/student） | - | 仅被分配时 read+run allotted |

依据：复用 BUG-017 已冻结的 `RoleEnum` + `HIGH_PRIVILEGE_ROLES`，不改角色枚举边界，迁移成本最低；语义通过 DD 动作矩阵表达而非新角色。

### D-2 maker-checker：所有报告强制制审分离

- 报告 `confirm` 必须由 `admin`/`data_admin` 角色且 `user_id != report.generated_by`。
- 生成者（任何角色 run 产报告）一律不能确认自己的报告。
- `reject` 同样需授权复核人，记录 actor + reason + 时间。
- 风险等级配置留 follow-up（本任务不引入 risk_level 字段）。

### D-3 任务可见性：本人 + 分配对象 + 高权

- `DdTask` 加 `assignee_id` 字段（nullable；创建时可选分配）。
- list 查询 WHERE `created_by = :uid OR assignee_id = :uid OR role IN HIGH_PRIVILEGE_ROLES`。
- 平台运维（super_admin）仅看运行状态（无报告原文/证据）。

### D-4 配置模型：新建 tenant_scoped_config 表 + 迁移脚本

- 新建 `metaedu.tenant_scoped_config`（`tenant_id, config_key, config_value jsonb, updated_by, updated_at`，PK `(tenant_id, config_key)`）。
- Internal MCP binding / DD Catalog binding / Skill binding 从 `settings` 全局单值迁到 DB，按 caller `tenant_id` 解析。
- 迁移脚本把现有 `settings.internal_mcp_tenant_id` / `settings.dd_catalog_id` 等值写入 `DEFAULT_TENANT` 行作为兜底。
- `settings` 保留作开发期默认 fallback（生产以 DB 为准），双源在 follow-up 收口。

## Frozen Design

### DD 动作权限矩阵

| 动作 | leader | admin/data_admin | super_admin | 被分配其他角色 |
|------|--------|------------------|-------------|----------------|
| create | ✓ | ✓ | ✗ | ✗ |
| read | own+allotted | tenant all | status only | allotted |
| run | own+allotted | ✗ | ✗ | allotted |
| confirm | ✗（maker） | ✓（checker, ≠generated_by） | ✗ | ✗ |
| reject | ✗ | ✓（checker, ≠generated_by） | ✗ | ✗ |
| archive | ✗ | ✓ | ✗ | ✗ |
| evidence | own+allotted | ✓ | ✗ | allotted |
| configure tenant | ✗ | ✗ | ✓ | ✗ |

### 配置模型

```
metaedu.tenant_scoped_config
  tenant_id      UUID NOT NULL REFERENCES metaedu.tenants(id)
  config_key     VARCHAR(100) NOT NULL   -- 如 internal_mcp_binding / dd_catalog_binding
  config_value   JSONB NOT NULL
  updated_by     UUID
  updated_at     TIMESTAMPTZ
  PRIMARY KEY (tenant_id, config_key)
```

支持 key：`internal_mcp_binding`（{server_id}）/ `dd_catalog_binding`（{catalog_id}）/ `skill_bindings`（[skill_id...]）。后续可扩展。

### 迁移策略

1. migration 025 建 `tenant_scoped_config` 表。
2. `seed_tenant_config.py` 把 `settings.internal_mcp_tenant_id` / `settings.dd_catalog_id` 写入 DEFAULT_TENANT 行。
3. Internal MCP server / DD Catalog resolver 改读 `tenant_scoped_config`（按 caller tenant_id），settings 作开发 fallback。
4. DdTask 加 `assignee_id` 列（migration 026）。
5. 审计：配置变更 / confirm / reject / archive 进既有 `dd_evidence` + `mcp_invocation_audit` 链，不新建审计表。

## Dependencies

- 必须先完成 `BUG-017`、`BUG-019`（已 🟢 Done）。
- 以 REQ-046 / APP-005 为业务基线，不重写现有报告结构。

## Delivery Links

- 实施前补 spec/plan，并冻结角色矩阵、配置模型和迁移策略。✅ 2026-07-22 shaping 完成。
- Plan: `docs/02-delivery-plans/02-plans/2026-07-22-req058-dd-production-rbac-multitenancy-plan.md`
