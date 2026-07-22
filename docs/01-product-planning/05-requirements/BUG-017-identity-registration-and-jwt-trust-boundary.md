# BUG-017: 身份注册与 JWT 信任边界可被绕过

> Status: 🔵 Ready
> Priority: P0
> Milestone: P3 / Security Foundation
> Area: 后端 / Identity / Auth / Deploy
> Created: 2026-07-22
> Source: [2026-07-22 安全与质量复核](../../03-engineering-governance/04-retrospectives/2026-07-22-security-and-quality-follow-up-review.md)

## Problem

公开注册接口允许请求方自行提交 `role` 和 `tenant_id`，并将两者原样写入用户表。调用者可注册到已有租户并选择 `admin` / `data_admin` / `super_admin`，从而绕过 MCP、Skill、Catalog 等模块的 RBAC。

后端同时提供公开的 JWT 默认密钥 `dev-only-change-in-production`；默认 seed 的 tenant/admin UUID 固定可知，部署遗漏 `JWT_SECRET` 时可伪造默认管理员 Token。

## Scope

- 公开注册默认关闭或改为只创建最低权限主体，禁止客户端指定已有 tenant 和高权 role。
- 管理员建用户、邀请加入租户和角色授予必须走已认证、已授权入口。
- `role` 使用受控枚举/策略，不接受任意字符串。
- JWT 密钥取消可运行默认值；部署缺失、过短或仍为开发值时启动失败。
- 更新部署示例和启动检查；轮换密钥后旧 Token 失效。

## Acceptance

- AC-1：匿名请求不能注册进调用者指定的已有 tenant，也不能获得管理角色。
- AC-2：普通用户不能授予或提升自己/他人的角色；管理员入口覆盖正向和越权测试。
- AC-3：生产启动缺失 JWT 密钥、使用公开默认值或低强度密钥时 fail-fast。
- AC-4：使用公开默认密钥伪造的默认管理员 Token 被拒绝。
- AC-5：正常登录、`/auth/me`、禁用用户 Token 拒绝逻辑无回归。
- AC-6：安全日志记录注册/邀请/角色变更结果，但不记录密码和 Token。

## Non-goals

- 本任务不引入完整 SSO、OIDC 或组织通讯录同步。
- 不重构全部 RBAC 模型；只关闭身份入口和 JWT 根信任漏洞。

## Validation

- Identity API 负向/正向 pytest。
- 配置启动测试覆盖缺失/default/有效 JWT secret。
- 全量后端 pytest、Ruff、工程文档门禁。

## Dependencies

无。该任务必须先于 `BUG-018`、`BUG-019` 和后续 Agentic 工具扩展完成。
