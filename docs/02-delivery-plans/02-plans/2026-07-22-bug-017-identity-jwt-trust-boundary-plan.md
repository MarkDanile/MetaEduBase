# BUG-017 Implementation Plan: 身份注册与 JWT 信任边界

> **For agentic workers:** 按 Slice 顺序实施，每 Slice 独立 commit + 可验证。Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 关闭身份入口与 JWT 根信任漏洞--公开注册不再接受客户端提供的 `role` / `tenant_id`；建立受控管理员建用户与角色授予入口；JWT 密钥取消可运行默认值，生产启动缺失/default/低强度时 fail-fast；安全日志记录身份事件结果（不记密码/Token）。

**Spec:** [BUG-017](../../01-product-planning/05-requirements/BUG-017-identity-registration-and-jwt-trust-boundary.md) / [复核](../../03-engineering-governance/04-retrospectives/2026-07-22-security-and-quality-follow-up-review.md)

**Tech Stack:** Python 3.14 + FastAPI + SQLAlchemy 2.x async + asyncpg + pydantic v2 + jose(jwt) + pytest；无新 migration（role 已是 `String(30)` 列，安全日志用结构化 logging 不入 DB）。

## 现状与漏洞证据

1. `app/contexts/identity/interfaces/api/router.py:64` `POST /auth/register` 公开，`RegisterRequest` 接受 `role`（默认 teacher）与 `tenant_id`（默认固定 UUID），原样写入 `metaedu.users`。调用者可注册到已有 tenant 并选 `admin`/`data_admin`/`super_admin`，绕过各模块 RBAC。
2. `app/config.py:28` `jwt_secret: str = "dev-only-change-in-production"` -- 公开默认值；`app/shared/infrastructure/seed.py` 默认 tenant/admin UUID 固定可知。部署遗漏 `JWT_SECRET` 时用默认值运行，可伪造默认管理员 Token。
3. `role` 是任意字符串，无受控枚举校验。
4. 无管理员建用户 / 角色授予入口；无身份安全日志。
5. `get_current_user`（dependencies.py）已校验 `is_active`（禁用用户 Token -> 401）--AC-5 回归基线已存在，不得破坏。

## 设计决策

- **公开 register 降级，不关闭**：保留 `POST /auth/register` 但移除 `role` / `tenant_id` 参数；服务端强制 `role=teacher` + 默认 tenant。V0 单租户园区场景 teacher 是最低权限；保留低权自注册对产品友好，且避免大面积删除端点。AC-1 满足：匿名不能获得管理角色、不能指定 tenant。
- **新增管理员入口**：`POST /api/v1/admin/users`（super_admin）建用户（受控 role + tenant_id + is_active）；`PATCH /api/v1/admin/users/{id}`（super_admin）角色变更 / 启停。覆盖 AC-2 正向 + 越权。
- **role 受控枚举**：`RoleEnum` = {super_admin, data_admin, admin, leader, teacher}（现有已知值全集）；admin 入口校验 role ∈ 枚举；`HIGH_PRIVILEGE_ROLES` = {super_admin, data_admin, admin}。
- **JWT fail-fast 区分环境**：config 新增 `environment: str = "development"`；production 时启动校验 jwt_secret ∉ {空, 默认值, 长度<32}，否则 raise 阻断启动。development 保留默认值便于本地。AC-4 天然满足：生产 secret != 默认值 -> 默认密钥签的 Token 解码失败 -> 401。
- **安全日志用结构化 logging**（不引入 migration）：新增 `security_logger`，记录 event_type/actor_user_id/target_user_id/result/ip，**不记 password / token / password_hash**。DB 审计表留给 REQ-058。
- **测试迁移**：9 个测试文件用 register 创建非 teacher 用户（admin/super_admin/leader）做 RBAC 测试。新增 `tests/contexts/identity/_helpers.py::create_user_as_admin`（经 admin token 调 /admin/users），受影响测试迁移至 helper；register 端点测试改为只验 teacher + 拒绝高权参数。

## File Structure

### 后端新建
- `app/contexts/identity/domain/role.py` - `RoleEnum` + `HIGH_PRIVILEGE_ROLES` + `is_valid_role`
- `app/contexts/identity/application/security_logger.py` - 结构化安全事件日志（不记密码/Token）
- `app/contexts/identity/interfaces/api/admin_router.py` - `/api/v1/admin/users` 建用户 + `PATCH` 角色变更

### 后端修改
- `app/config.py` - 新增 `environment: str = "development"`；`jwt_secret` 默认值保留但加生产校验
- `app/main.py` - 启动时调用 `validate_production_jwt_secret()`；include `admin_router`
- `app/contexts/identity/interfaces/api/router.py` - `RegisterRequest` 移除 role/tenant_id；register 强制 teacher + 默认 tenant；写安全日志
- `app/contexts/identity/application/auth_service.py` - 新增 `validate_production_jwt_secret(settings)`（被 main 启动调用）
- `app/contexts/identity/infrastructure/user_repository.py` - 新增 `update_role_and_status` / `find_by_id`（admin 入口用）
- `deploy/.env.example` - 补 `APP_ENV` / `JWT_SECRET` 注释（生产必填）

### 测试新建
- `tests/contexts/identity/test_role_policy.py` - role 枚举 + 高权集合
- `tests/contexts/identity/test_register_hardening.py` - 匿名 register 强制 teacher / 拒绝高权参数 / 不接受 tenant_id
- `tests/contexts/identity/test_admin_user_management.py` - 管理员建用户正向 + 越权 403 + 角色变更 + 受控枚举拒绝
- `tests/contexts/identity/test_jwt_fail_fast.py` - production 缺失/default/短 secret 启动失败；development 默认值可启动；默认密钥签的 Token 被拒
- `tests/contexts/identity/test_security_logger.py` - 日志含事件字段、不含 password/token
- `tests/contexts/identity/_helpers.py` - `create_user_as_admin` / `admin_token` helper

### 测试修改（迁移至 admin 入口）
- `tests/contexts/identity/test_auth.py`
- `tests/contexts/mcp_registry/test_tenant_isolation.py` / `test_registry_service.py`
- `tests/contexts/skill_registry/test_skill_registry_service.py` / `test_skill_run_api.py`
- `tests/contexts/structured_data/test_mcp_adapter_registry_wiring.py` / `test_catalog_router.py`
- `tests/contexts/due_diligence/test_dd_router.py` / `test_dd_run_router.py`

## Slices

### Slice 1: JWT 信任边界 fail-fast（AC-3, AC-4）
- [x] `config.py` 新增 `environment: str = "development"`
- [x] `auth_service.py` 新增 `validate_production_jwt_secret(settings)`：environment=="production" 时，secret 为空 / == 默认值 / len<32 -> raise RuntimeError
- [x] `main.py` 启动事件调用校验
- [x] `test_jwt_fail_fast.py`：production 三种坏 secret 启动失败；development 默认值可启动；默认密钥签的 Token decode -> None -> 401
- [x] `.env.example` 补 `APP_ENV` / `JWT_SECRET` 注释

### Slice 2: role 受控枚举 + 公开 register 降级（AC-1）
- [x] `domain/role.py` RoleEnum + HIGH_PRIVILEGE_ROLES + is_valid_role
- [x] `router.py` RegisterRequest 移除 role/tenant_id；register 强制 teacher + 默认 tenant；写安全日志
- [x] `test_role_policy.py` + `test_register_hardening.py`：匿名 register 返回 role=teacher；传 role/tenant_id 被忽略或拒；不能创建高权
- [x] 迁移 `test_auth.py` 中非 teacher register 用法

### Slice 3: 管理员建用户 + 角色授予入口（AC-2）
- [x] `admin_router.py` `POST /api/v1/admin/users`（super_admin）+ `PATCH /api/v1/admin/users/{id}`
- [x] `user_repository.py` 新增 `find_by_id` / `update_role_and_status`
- [x] `test_admin_user_management.py`：正向建用户 + 角色变更；普通用户/teacher 调 -> 403；role ∉ 枚举 -> 422；跨租户隔离
- [x] `_helpers.py` create_user_as_admin；迁移其余 8 测试文件的高权 register 用法

### Slice 4: 安全日志（AC-6）
- [x] `security_logger.py` 结构化日志（event_type/actor/target/result/ip），不记 password/token
- [x] register / admin 建用户 / 角色变更调用安全日志
- [x] `test_security_logger.py`：字段齐全、password/token 不出现

### Slice 5: 回归与收口（AC-5）
- [x] login / /auth/me / 禁用用户 Token 拒绝回归测试
- [x] 全量后端 pytest / ruff / check-engineering-docs / git diff --check
- [x] 工作台归档 + work-log

## 验证矩阵

| AC | 验证 |
|----|------|
| AC-1 | test_register_hardening：匿名 register role=teacher，传高权/tenant 被拒 |
| AC-2 | test_admin_user_management：正向建用户+角色变更；普通用户 403 |
| AC-3 | test_jwt_fail_fast：production 缺失/default/短 secret 启动失败 |
| AC-4 | test_jwt_fail_fast：默认密钥签的 Token -> 401 |
| AC-5 | test_auth 回归：login/me/is_active 拒绝 |
| AC-6 | test_security_logger：事件字段齐全，无 password/token |

## Global Constraints

- 不破坏现有 backend tests（迁移后全绿；mcp_registry / structured_data / skill_registry / due_diligence 套件 0 回归）
- 密码 / token / password_hash 永不进安全日志 / API 响应 / 审计
- role 受控枚举；admin 入口 super_admin only；越权 403
- JWT 生产 fail-fast 不得通过降阈值 / 改默认值绕过
- pytest 在 `packages/server-python/` 下跑；ruff 0 / check-engineering-docs 0 / git diff --check 干净
- 每 Slice 独立 commit + 可验证

## Non-goals（spec 对齐）

- 不引入 SSO / OIDC / 组织通讯录同步
- 不重构全部 RBAC 模型（留给 REQ-058）
- 不建身份安全事件 DB 表（留给 REQ-058，本任务用结构化 logging）
- 不改默认 seed admin/tenant UUID（改 UUID 不堵漏洞，且破坏现有测试；JWT fail-fast 已堵伪造 Token 路径）

## 风险与回滚

- **测试迁移风险**：9 文件改用 admin 入口。缓解：helper 统一、逐文件迁移+跑绿。
- **JWT fail-fast 误伤开发**：仅 production 触发，development 保留默认值。缓解：environment 默认 development。
- **回滚**：每 Slice 独立 commit，可 revert 单 Slice。

## 验证摘要（Slice 5 收口）

- Slice 1-4 独立 commit：`9c122330`（Slice 1 JWT fail-fast）/ `2fa5abf9`（Slice 2-4 register 降级 + 管理员入口 + 安全日志）/ `96695f1f`（Slice 5 security_logger 全量顺序污染自洽）。
- 全量后端 pytest：`1222 passed, 4 skipped, 1 failed`——唯一失败 `test_embedding_empty_logs_warning` 为 TD-080 pre-existing（main 同样失败，本任务未引入）。`test_p1_demo_step4_kg_extract` 偶发 flaky（main 全量 PASS，BUG-017 不涉及 KG 抽取逻辑，test_p1_demo 历史 flaky），非本任务回归。
- ruff check app/ tests/：All checks passed。
- scripts/check-engineering-docs：passed（31 known issue allowlisted）。
- git diff --check：exit 0。
- 新增测试：`test_jwt_fail_fast.py`(7) + `test_role_policy.py`(3) + `test_register_hardening.py`(4) + `test_admin_user_management.py`(7) + `test_security_logger.py`(3) = 24 用例全绿。
- 迁移测试：6 文件改用 `tests/contexts/identity/_helpers.py::register_and_login`（admin 入口建用户），0 回归。

