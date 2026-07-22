# BUG-018: AI App 无鉴权、无租户隔离并暴露 Token

> Status: 🔵 Ready
> Priority: P0
> Milestone: P3 / Security Foundation
> Area: 后端 / 前端 / AI App / Auth / Tenant
> Created: 2026-07-22
> Source: [2026-07-22 安全与质量复核](../../03-engineering-governance/04-retrospectives/2026-07-22-security-and-quality-follow-up-review.md)

## Problem

`/api/v1/ai-apps` 管理接口没有认证依赖，service 的按 ID 查询和更新不带 tenant 条件，并信任创建请求中的 `tenant_id`。匿名调用者可枚举、修改、归档应用并轮换 Token；列表和详情 DTO 还直接返回 `share_token` / `api_token`。

前端 `aiAppsApi` 另行手写 `fetch`，绕过统一请求超时、401 处理和错误规范。

## Scope

- 管理 API 强制认证、管理 RBAC 和 tenant-scoped repository/service 查询。
- 调用者不得通过请求参数切换管理 tenant；平台级内置应用使用明确的系统作用域策略。
- 拆分 public / management DTO：常规列表和详情不返回任何 Token。
- Token 仅在轮换成功时返回一次；评估并优先采用摘要存储。
- 如需匿名应用广场，建立单独只读 public endpoint，仅暴露 Published 且允许公开的安全字段。
- 前端统一复用共享 Axios client。

## Acceptance

- AC-1：匿名调用所有管理端点均返回 401；非管理角色返回 403。
- AC-2：tenant A 无法读取、修改、归档或轮换 tenant B 的应用。
- AC-3：创建请求不能伪造 tenant；服务层所有 ID 查询强制 tenant 条件。
- AC-4：列表/详情响应不包含 `share_token`、`api_token`；轮换接口只返回一次新值。
- AC-5：public endpoint（若保留）不暴露 Draft/Disabled/Archived、租户私有配置或凭证。
- AC-6：前端请求具有统一超时、401 跳转和错误行为。
- AC-7：补齐后端 AI App API 与前端 service 回归测试。

## Non-goals

- 不在本任务实现应用市场评分、付费或第三方审核流程。
- 不扩展 AI App 运行时能力。

## Validation

- 匿名、角色、跨租户、Token 响应矩阵测试。
- 前端 service 测试、typecheck、lint、Vitest、build。
- 全量后端 pytest、Ruff、工程文档门禁。

## Dependencies

依赖 `BUG-017` 先关闭公开高权注册和默认 JWT 密钥。
