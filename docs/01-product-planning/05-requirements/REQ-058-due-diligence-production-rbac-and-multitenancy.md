# REQ-058: 企业背调生产级 RBAC、制审分离与多租户配置

> Status: 🟣 Shaping
> Priority: P0
> Milestone: P3 / Industrial Park Production
> Area: 企业背调 / RBAC / Audit / Multi-tenant
> Created: 2026-07-22
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

- 首期采用现有通用角色映射，还是新增招商/合规岗位角色？
- maker-checker 是否所有报告强制，还是按风险等级配置？
- 任务可见性默认采用本人/团队/全租户哪一级？

## Dependencies

- 必须先完成 `BUG-017`、`BUG-019`。
- 以 REQ-046 / APP-005 为业务基线，不重写现有报告结构。

## Delivery Links

- 实施前补 spec/plan，并冻结角色矩阵、配置模型和迁移策略。
