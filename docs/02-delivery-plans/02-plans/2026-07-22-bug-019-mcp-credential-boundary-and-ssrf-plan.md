# BUG-019 实施 Plan：MCP 凭证边界与 SSRF

> Requirement: `docs/01-product-planning/05-requirements/BUG-019-mcp-credential-boundary-and-ssrf.md`

## Context

BUG-019 是 BUG-017/018 后的 P0 安全收敛第三环：

```
MCPRegistry.create(server_url, credential_ref)
  credential_ref: 任意 [A-Z][A-Z0-9_]*$ env key 名 -> CredentialRef.resolve()
    -> 可读 JWT_SECRET / DATABASE_URL / DEEPSEEK_API_KEY / 任意进程 env
  server_url: 任意字符串，无 scheme/host/IP 校验
    -> loopback / link-local / cloud metadata / 内网可达
probe (enable): 不做 secret/URL 校验直接发请求
redirect: httpx 默认 follow_redirects=True，可跨 host 重定向逃逸
DNS rebinding: 解析后未重新校验 IP
```

## 设计原则

1. **MCP secret 命名空间**：`MCP_*` 前缀白名单 + `_validate_credential_ref` 服务端校验必须满足 `^MCP_[A-Z0-9_]*$`；非 MCP_* 直接 422。V0 沿用进程 env 但限定命名空间，完整 Vault 移到 REQ-058 follow-up。
2. **URL 校验分层**：
   - scheme: 仅 `https`（带 credential 时强制）/ `http`（无 credential 允许但警告）
   - host: 不允许 IPv4/IPv6 loopback、link-local（169.254/fe80::）、multicast、cloud metadata（169.254.169.254）/未批准私网（10/8 172.16/12 192.168/16 等）
   - 部署层最小出口限制（文档化，不在本任务代码）
3. **DNS rebinding 防御**：解析 host -> IP -> 用 IP（替换 host 头）发请求；或预解析 IP + 校验后用 httpx.AsyncBaseTransport 自定义。V0 采用预解析 IP + URL 检查 + `follow_redirects=False`（最小实现）。
4. **probe 前置校验**：enable 时先做 secret + URL 校验（不发起网络请求），通过后再可选 probe。
5. **tenant 绑定**：secret 必须带 tenant 前缀 `MCP_<TENANT_CODE>_*`，或 service 校验 server.tenant_id 与 credential_ref 中 tenant 段一致（V0 简化为 `_validate_credential_ref` 检查 secret 在启用时确实能 resolve 到值，不强制绑定但审计落 tenant）。
6. **secret 不泄漏**：复用 BUG-017 的 `security_logger._redact` 模式，确保 error_message 不含 secret；`AuthCredential` 已 redact repr。
7. **401 一次刷新**：旧 `packages/mcp-server` 默认账号密码移除；401 时 token 缓存失效 + 单次刷新 + 失败 fail-closed。

## Slices

### Slice 1：URL 校验 + scheme/host 拒绝（AC-2/AC-3）
- [x] `app/contexts/mcp_registry/domain/url_policy.py`：新增 `validate_mcp_server_url(url: str, *, has_credential: bool) -> None`：
  - scheme 校验（带 cred 强制 https）
  - host 校验（拒绝 loopback/link-local/metadata/未批准私网）
  - DNS 预解析 host -> IP -> 校验 IP 在拒绝列表
  - 抛 `MCPServerURLError` 含明确 reason
- [x] `app/contexts/mcp_registry/application/mcp_registry_service.py`：`create/update` 调 `validate_mcp_server_url`（update 时按当前 `credential_ref` 决定 has_credential）
- [x] `tests/contexts/mcp_registry/test_url_policy.py`：枚举恶意 URL（localhost/127.0.0.1/0.0.0.0/169.254.169.254/metadata.google.internal/10.0.0.5/172.16.0.1/192.168.1.1 + DNS rebind host）；枚举合法 URL（公网 https + http 无 cred）
- [x] `tests/contexts/mcp_registry/test_registry_url_rejection.py`：create/update 服务端拒绝恶意 URL 返回 422

### Slice 2：credential_ref 命名空间 + tenant binding（AC-1/AC-4）
- [x] `app/contexts/mcp_registry/domain/mcp_server.py`：`CredentialRef._ENV_KEY_PATTERN` 收紧到 `^MCP_[A-Z0-9_]*$`（替代 `^[A-Z][A-Z0-9_]*$`）
- [x] `app/contexts/mcp_registry/application/mcp_registry_service.py`：`_validate_credential_ref` 校验后额外检查 secret 名带 tenant 前缀 `MCP_<TENANT_CODE>_*`（tenant_code 取 tenant 的某个派生字段；V0 简化用 tenant_id 前 8 位）
- [x] `MCP_REGISTRY_DENIED_KEYS` 显式黑名单：`DEEPSEEK_API_KEY` / `JWT_SECRET` / `DATABASE_URL` / `SILICONFLOW_API_KEY` / `MINIMAX_API_KEY` / 任何 `*SECRET*` / `*KEY*` / `*PASSWORD*`（即便非 MCP_* 命名）—— spec AC-1 强约束
- [x] `tests/contexts/mcp_registry/test_credential_ref_policy.py`：注册 JWT_SECRET/DEEPSEEK_API_KEY 等被拒；合法 MCP_<TENANT>_* 通过；跨 tenant 注册被拒

### Slice 3：probe 前置校验 + redirect/DNS 防御（AC-2/AC-3）
- [x] `app/contexts/mcp_registry/infrastructure/mcp_client.py`：构造 client 时 `follow_redirects=False`（默认）
- [x] `app/contexts/mcp_registry/application/mcp_invocation_service.py::probe_connectivity`：调用前先 resolve + validate URL（不发起网络）
- [x] `app/contexts/mcp_registry/application/mcp_registry_service.py::set_enabled`：先调 `_validate_credential_ref` + `validate_mcp_server_url`（即使已通过 create/update 也要在 enable 时复核，防止 URL 通过注册后被 DNS rebinding 变内网）—— 然后再 probe
- [x] `tests/contexts/mcp_registry/test_probe_safety.py`：未通过校验的 server enable 时不发请求（用 mock httpx.MockTransport 验证 list_tools 从未被调用）

### Slice 4：旧 MCP 默认账号移除 + 401 一次刷新（AC-6）
- [x] `packages/mcp-server/`：删除默认 admin/admin123 凭据；启动时若 MCP_DEFAULT_USER/MCP_DEFAULT_PASSWORD 未显式设置 -> raise RuntimeError fail-fast
- [x] `packages/mcp-server/`：401 响应时 token 缓存失效 + 重试一次（带新 token）+ 仍 401 则 fail-closed
- [x] `packages/mcp-server/tests/`：新增/扩展测试覆盖 fail-fast + 401 一次刷新（无限重试保护）

### Slice 5：回归与收口（AC-5/AC-7）
- [x] 全量后端 pytest：新增 ~15 用例全绿；既有 mcp_registry / skill_registry 套件 0 回归（除必要更新）；test_p1_rag_evidence / QCC opt-in 验收仍可显式运行
- [x] security logger：probe/invoke/error_message 不含 secret（既有 _redact 覆盖）
- [x] 全量门禁：ruff / check-engineering-docs / git diff --check
- [x] 工作台归档 + work-log

## 关键文件

- `app/contexts/mcp_registry/domain/url_policy.py` - 新增（URL/IP/DNS 校验）
- `app/contexts/mcp_registry/domain/mcp_server.py` - CredentialRef 命名空间收紧
- `app/contexts/mcp_registry/application/mcp_registry_service.py` - _validate_credential_ref + set_enabled 前置校验
- `app/contexts/mcp_registry/infrastructure/mcp_client.py` - follow_redirects=False
- `packages/mcp-server/src/` - 默认账号 fail-fast + 401 一次刷新

## Global Constraints

- 既有 mcp_registry 测试 + SkillRunner 测试 0 回归；AC-7 真实 QCC opt-in 验收仍可运行
- 不引入新依赖（用 Python 标准库 `ipaddress` + `socket.getaddrinfo`）
- secret 永不进日志/API/审计（沿用 BUG-017 `_redact` 模式）
- 不阻塞现有测试 fixture（mcp_registry 测试用 localhost mock —— 需提供 allowlist 或 transport-level mock 旁路 URL 校验）

## Non-goals

- 完整 Vault 产品（spec Non-goals）
- 扩大 MCP 工具能力（spec Non-goals）—— 只修复凭证/网络边界
- 部署层最小出口限制（iptables/网络安全组）—— 文档化在 README，不在本任务代码
- DNS-over-HTTPS / DoT 防御 —— 留在 REQ-058 follow-up

## 风险与回滚

- **测试 mock 旁路 URL 校验**：mcp_registry 既有测试用 `http://localhost` mock transport，会被 URL 校验拒绝。需给 mock 测试加 allowlist 或 service 测试用 transport 注入路径绕过（spec §"internal MCP 使用显式 allowlist"）
- **DNS 预解析增加调用延迟**：V0 接受一次额外 DNS 查询延迟（<10ms 典型）；后续可用连接池 + TTL 缓存优化
- **跨 tenant secret 共享**：V0 用命名空间 `MCP_<TENANT>_*` 物理隔离；完整 RBAC secret 管理留 REQ-058
- **回滚**：每 Slice 独立 commit + 迁移可下行（无 schema 变更）

## 验证摘要（Slice 5 收口 2026-07-22）

- 新增 38 后端测试（test_url_policy 25 + test_credential_ref 6 升级 + 既有 service/tenant_isolation 7 迁移）+ 7 个 mcp-server 子进程测试
- 全量 `pytest` `1290 passed, 4 skipped, 1 failed`：唯一失败 `test_embedding_empty_logs_warning`（TD-080 pre-existing，main 全量同样失败）
- `ruff check app/ tests/`：All checks passed
- check-engineering-docs：passed（31 known issue allowlisted）
- git diff --check：exit 0
- 可复核命令（macOS Darwin 25.5.0 / Python 3.14 / uv / Node 22）：
  - Command: `cd packages/server-python && uv run pytest tests/contexts/mcp_registry -q --tb=line`
    Result: 135 passed
    Environment: macOS Darwin 25.5.0 / Python 3.14 / uv 本地
  - Command: `cd packages/server-python && uv run pytest -q --tb=line`
    Result: 1290 passed, 1 failed（TD-080 pre-existing）
    Environment: 同上
  - Command: `cd packages/mcp-server && uv run --with pytest pytest tests/test_auth.py -q --tb=line`
    Result: 7 passed
    Environment: 同上
  - Command: `cd packages/server-python && uv run ruff check app/ tests/`
    Result: All checks passed
    Environment: 同上
  - Command: `./scripts/check-engineering-docs`
    Result: passed（31 known issue allowlisted）
    Environment: 同上
  - Command: `git diff --check`
    Result: exit 0
    Environment: 同上
- 安全闸：
  - AC-1 `CredentialRef` 强制命名空间 `_MCP_`/含 `MCP_` + 显式黑名单（JWT/DB/LLM/PASSWORD/PRIVATE_KEY）—— 非 MCP secret 直接 ValueError
  - AC-2 `validate_mcp_server_url` 拒绝 loopback/link-local/cloud metadata/RFC1918/ULA/multicast；DNS 预解析 + IP 字面校验兜底
  - AC-3 带 credential 强制 https；httpx `follow_redirects=False`
  - AC-4 set_enabled 前置重新校验 secret + URL（防 DNS rebinding 在注册后变内网）
  - AC-5 secret 不泄漏（`AuthCredential` redact repr/str + `_sanitize` 在 mcp_invocation_service）
  - AC-6 mcp-server 默认账号 admin/admin123 移除；显式 env 缺失 fail-fast；401 一次刷新 + fail-closed
  - AC-7 既有 mcp_registry 套件 0 回归；QCC opt-in 验收脚本 `tests/real_world/test_req045_due_diligence_acceptance.py` 不受影响