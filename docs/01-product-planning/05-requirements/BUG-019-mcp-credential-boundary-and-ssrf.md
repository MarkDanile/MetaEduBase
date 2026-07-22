# BUG-019: MCP 凭证可外传且 server_url 存在 SSRF

> Status: 🔵 Ready
> Priority: P0
> Milestone: P3 / Security Foundation
> Area: 后端 / MCP / Secrets / Network Egress
> Created: 2026-07-22
> Source: [2026-07-22 安全与质量复核](../../03-engineering-governance/04-retrospectives/2026-07-22-security-and-quality-follow-up-review.md)

## Problem

MCP Registry 允许管理者填写任意 `server_url` 和任意符合大写格式的 `credential_ref`。调用时 `CredentialRef.resolve()` 可读取后端进程任意环境变量，enable 默认探活再把该值作为 Bearer Token 发给所填 URL。

这意味着高权账号可将 LLM、JWT、数据库或其他服务密钥发送到攻击者服务；任意 URL 还可访问 loopback、内网和云 metadata。当前公开高权注册使攻击成本进一步降低。

旧 `packages/mcp-server` 同时仍使用 `admin/admin123` 默认凭据，Token 永久缓存且 401 不刷新。

## Scope

- `credential_ref` 改为服务端受控、tenant-scoped 的 MCP secret ID/专用命名空间，禁止读取任意进程环境变量。
- secret 必须与 tenant、目标 MCP server 绑定；普通读取接口不返回可用于枚举的敏感引用。
- URL 只接受明确 transport/scheme；携带凭证时默认要求 HTTPS。
- 连接前和 DNS 解析后阻止 loopback、link-local、multicast、metadata 与未批准私网地址；内部 MCP 使用显式 allowlist。
- 禁止跨 host 重定向和 DNS 重绑定逃逸；部署层补最小出口限制。
- enable/probe 在凭证和目标校验完成前不得发起网络请求。
- 移除旧 MCP 默认账号密码；必须显式配置，401 时最多刷新重试一次。

## Acceptance

- AC-1：`DEEPSEEK_API_KEY`、`JWT_SECRET`、`DATABASE_URL` 等非 MCP secret 不能作为 credential 注册或解析。
- AC-2：`localhost`、IPv4/IPv6 loopback、link-local、metadata、未授权私网和 DNS 重绑定目标被拒绝。
- AC-3：外部带凭证 MCP 只允许可信 HTTPS 目标；重定向不能改变安全边界。
- AC-4：tenant A 的 MCP secret 不能由 tenant B 注册、探活或调用。
- AC-5：probe、调用、审计和异常均不泄漏 secret；保留现有 digest-only 审计。
- AC-6：旧 MCP 缺失显式账号密码时 fail-fast；401 刷新路径有测试且无无限重试。
- AC-7：真实 QCC 验收在新凭证边界下仍可显式 opt-in 运行。

## Non-goals

- 不在本任务实现完整企业 Vault 产品。
- 不扩大 MCP 工具能力；只修复凭证和网络信任边界。

## Validation

- URL/IP/DNS/redirect/secret binding 单元与集成测试。
- MockTransport canary 测试证明未批准 secret 不会进入 Authorization header。
- MCP Registry、Skill Runner、QCC opt-in 验收、全量后端 pytest、Ruff。

## Dependencies

依赖 `BUG-017`；完成前不得新增外部 MCP 或扩大 Agentic 自动调用范围。
