# 2026-07-22 安全与质量复核 Follow-up

## 范围与结论

基于 `main` commit `14c3ddea` 复核身份、AI App、MCP / Skill、企业背调、上传链路及工程门禁。最近提交已收口 Ruff、依赖锁和大部分测试基线，但原有高风险入口尚未关闭，并出现 MCP 凭证外传与 SSRF 可组合链路。

本报告只登记证据和 follow-up，不修改业务代码。

## 阻塞级证据

1. `identity/interfaces/api/router.py` 的公开注册仍接受调用者提供的 `role` 和 `tenant_id`；`config.py` 仍提供公开 JWT 默认密钥，默认 seed 的 tenant/admin UUID 固定可知。
2. `ai_app/interfaces/api/router.py` 无 `get_current_user`；service 按 ID 查询不带 tenant；通用响应 DTO 暴露 `share_token` / `api_token`。
3. MCP Registry 接受任意 `server_url` 与任意大写环境变量名；`CredentialRef.resolve()` 读取进程环境变量，enable 默认探活会把其值作为 Bearer Token 发往该 URL。该链路同时具备 secret exfiltration 与 SSRF 风险。
4. document / structured-data 上传将原始 `file.filename` 拼入存储路径，并用 `await file.read()` 整体读入内存；Resource 下载仍把认证 Token 拼入 URL。

## 生产化缺口

- 企业背调 API 已按 token 中 tenant 隔离，但所有认证角色均可创建、执行、确认和归档报告，未形成岗位权限与制审分离。
- Internal MCP 与 DD internal query 仍依赖进程级固定 tenant/catalog，只能视为 V0 单租户接线。
- 旧 `packages/mcp-server` 仍带 `admin/admin123` 默认值、永久 Token 缓存和无 401 刷新。

## 实跑证据

| 命令 | 结果 |
|------|------|
| `.venv/bin/ruff check app tests` | 通过 |
| `pnpm --filter @metaedu/web typecheck` | 通过 |
| `pnpm --filter @metaedu/web lint` | 通过，0 error / 16 warning |
| `pnpm --filter @metaedu/web test -- --run` | 166 / 166 通过 |
| `pnpm --filter @metaedu/web build` | 通过；存在 KGGraph 大 chunk warning |
| `.venv/bin/pytest -q`（沙箱外本机 PG） | 1198 passed / 1 failed / 4 skipped / 29 warnings |
| 失败用例单独复跑 | 1 passed，确认是套件顺序污染或全局状态泄漏 |
| `.venv/bin/mypy app` | 未启动检查；重复模块路径错误 |
| `scripts/check-engineering-docs --full` | 通过，32 个 known issues allowlisted |
| `.venv/bin/alembic heads` | 单一 head `023_dd_workbench` |

## 登记结果与顺序

1. `BUG-017`：身份注册与 JWT 信任边界。
2. `BUG-018`：AI App 鉴权、租户隔离与 Token 响应。
3. `BUG-019`：MCP 凭证边界、SSRF 与旧 MCP 默认凭据。
4. `BUG-020`：上传路径、大小/类型与下载认证传输。
5. `REQ-058`：企业背调生产级 RBAC、制审分离与多租户配置。
6. `TD-080`：全量测试顺序污染与 coroutine warning。
7. `TD-081`：CI、Git hooks 与 mypy 可执行基线。

在 `BUG-017` / `BUG-018` / `BUG-019` 关闭前，不扩大 Agentic 工具调用和外部 MCP 暴露范围。
