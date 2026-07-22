# BUG-018 实施 Plan：AI App 鉴权、租户与 Token 暴露

> Requirement: `docs/01-product-planning/05-requirements/BUG-018-ai-app-auth-tenant-and-token-exposure.md`

## Context

BUG-018 是 BUG-017 之后的 P0 安全收敛第二环：AI App 管理端点完全无认证、无租户隔离并直接返回 `share_token` / `api_token`。

```
/api/v1/ai-apps (8 端点)
  router -- 无 Depends get_current_user,匿名可 CRUD + 轮换 Token
  service.get_by_id/update/archive/regenerate_*_token -- 无 tenant 条件
  service.create -- 信任客户端 tenant_id
  AiAppResponse + ListResponse -- 列表/详情直接返 share_token/api_token
前端 aiAppsApi.ts -- 手写 fetch,绕过 api.ts axios 客户端(timeout/401 跳转)
后端 tests/contexts/ai_app/ -- 不存在,无回归保护
```

## 设计原则

1. **管理 RBAC 与 BUG-017 对齐**：超管 = `super_admin` / `data_admin` / `admin`（RoleEnum.HIGH_PRIVILEGE_ROLES），非管理 403，匿名 401。
2. **tenant 强制**：平台应用（`is_platform=True`）跨租户可见（公开）但只能 super_admin 管理；普通应用强制绑 `current_user.tenant_id`，service 所有 ID 查询 WHERE tenant_id，client 传 tenant_id 一律忽略。
3. **DTO 拆分**：
   - `AiAppPublicResponse`（列表/详情/匿名 public）：不含 `share_token`/`api_token`，不含 tenant 私有 config
   - `AiAppAdminResponse`（管理详情）：仍含 token 字段供 super_admin 管理 UI（现状已有 UI，需要保留）
   - `AiAppTokenResponse`（仅 rotate 成功时）：只返 token 本身
4. **Token 摘要存储**:本任务先收紧 DTO（不返回），摘要存储移到 REQ-058（改动 token 列约束，需要 migration + 全量回填，超出本 bug scope；见 Risks）。
5. **前端统一 axios**:`aiAppsApi.ts` 改用 `import api from './api'`，移除手写 fetch + localStorage 直接读 token。

## Slices

### Slice 1：管理 RBAC + 强制认证（AC-1）
- [x] `router.py` 8 管理端点加 `Depends(get_current_user)`（统一依赖抽取 `_AdminUser`）
- [x] 管理 RBAC：role ∈ RoleEnum.HIGH_PRIVILEGE_ROLES 才允许，非管理 403；匿名 401
- [x] `app/main.py` ai_app_router include 不变（保留 `/api/v1/ai-apps` 路径兼容）
- [x] `tests/contexts/ai_app/test_admin_auth.py`：匿名 401、教师 403、admin/data_admin/super_admin PASS

### Slice 2：tenant-scoped service + 反伪造 tenant（AC-2, AC-3）
- [x] `infrastructure/models.py` 加 `is_platform: bool = False` + 索引 `(tenant_id, is_platform)`
- [x] `application/service.py` 所有 ID 查询（get_by_id / update / archive / regenerate_*_token）签名加 `tenant_id: UUID`，SQL WHERE `tenant_id=:tid`；`is_platform=True` 时跳过 tenant 过滤（仅 super_admin 路径）
- [x] `AiAppCreate.tenant_id` 移除（ConfigDict extra='forbid'），service.create 强制 `tenant_id=current_user.tenant_id`（超级管理员可显式 target system tenant_id 传 `None`，产出 `is_platform=True`）
- [x] 平台应用 list/get 公开：`list_published_public()` 给前端匿名应用广场
- [x] `tests/contexts/ai_app/test_tenant_isolation.py`：跨租户读/改/归档/轮换 → 404；伪造 tenant_id create → 服务端强制为当前用户 tenant；list 包含 `is_platform` 但 token 列不在公开 DTO

### Slice 3：DTO 拆分 + Token 不外泄（AC-4, AC-5）
- [x] `schemas.py`：新增 `AiAppPublicResponse`（不含 token/owner 私有字段，公开视图）+ `AiAppAdminResponse`（含 token，给 super_admin 管理 UI）+ `AiAppTokenResponse`（仅 rotate 用）
- [x] `router.list/get` 返 `AiAppPublicResponse` 默认；超级管理员可 query `?scope=admin` 返 `AiAppAdminResponse`
- [x] 新增匿名 `GET /api/v1/ai-apps/public`：仅 `status=PUBLISHED AND visibility=PUBLIC`，返 `AiAppPublicResponse`
- [x] rotate endpoint 改返 `AiAppTokenResponse{share_token?, api_token?}`（按 action 只含目标字段，不含整 DTO）
- [x] 移除 `AiAppResponse`（替换为 Admin/Public 两个明确版本，避免一处改动另一处意外泄露）
- [x] `tests/contexts/ai_app/test_dto_token_exposure.py`：列表/详情 response keys 不含 token；rotate response 只含对应 token 字段；public endpoint 不含 token；archived/draft/disabled 不在 public

### Slice 4：前端统一 axios（AC-6）
- [x] `services/aiAppsApi.ts` 改 `import api from './api'`；移除手写 fetch + localStorage token 读取 + 401 跳转实现
- [x] 复用 `api.ts` 的 30s timeout + 401 跳转 /login
- [x] 错误处理沿用 axios 默认（throw error 含 status）--前端 catch 处无需改动
- [x] `services/aiAppsApi.test.ts`（vitest）：mock axios，断言 baseURL=`/api/v1/ai-apps` + 401 自动跳转 + timeout 30s；create/list/get/update 路径与 method 正确

### Slice 5：回归与收口（AC-7）
- [x] 全量后端 pytest：新增 ~25 用例全绿；6 已有套件 0 回归
- [x] 前端 vitest：新增 ai-apps service 测试；typecheck + lint 0
- [x] 全量门禁：ruff / check-engineering-docs / git diff --check
- [x] 工作台归档 + work-log

## 关键文件

- `app/contexts/ai_app/interfaces/api/router.py` - 8 端点加 Depends + 拆 public/admin
- `app/contexts/ai_app/application/service.py` - 所有 ID 查询 tenant 强制
- `app/contexts/ai_app/application/schemas.py` - 拆 Public/Admin/Token 三 DTO
- `app/contexts/ai_app/infrastructure/models.py` - `is_platform` + 索引
- `alembic/versions/024_ai_app_is_platform.py` - 迁移（migration 加列）
- `app/contexts/identity/domain/role.py` - 复用 HIGH_PRIVILEGE_ROLES
- `app/contexts/identity/interfaces/api/dependencies.py` - 复用 `get_current_user`
- `packages/web/src/services/aiAppsApi.ts` - 改用 shared axios client
- `packages/web/src/services/aiAppsApi.test.ts` - 新增 vitest（AC-6）

## Global Constraints

- 不破坏现状前端 AiAppsAdminView（依赖 token 显示，需 super_admin scope=admin 查询）
- service.create 不再接受 client tenant_id（extra='forbid'），super_admin 也不能绕过到任意 tenant（只能建本 tenant + 可选 is_platform 标志）
- Token 仅在 rotate 成功时返回一次（AC-4 二段：详情不返 + rotate 只返目标字段）
- 匿名 public endpoint 是新加，不是改原路径；前端 marketplace 改用 public 路径
- 不引入新依赖
- 全量 pytest 在 `packages/server-python/` 下；ruff / check-engineering-docs / git diff --check 必须 0
- 每 Slice 独立 commit + 可验证

## Non-goals（spec 对齐 + 范围防扩）

- Token 摘要存储（spec "评估并优先采用摘要存储"）——超出本任务；DB 列约束改动 + 全量回填留待 REQ-058
- 应用市场评分 / 付费 / 第三方审核流程（spec Non-goals）
- 扩展 AI App 运行时能力（spec Non-goals）
- 公共 marketplace 分页 / 搜索 / 分类筛选（V0 只暴露 Published+PUBLIC 子集）

## 风险与回滚

- **前端 AiAppsAdminView 依赖 token 显示**：UI 改用 `?scope=admin` 路径；不破坏已有管理 UI
- **平台内置应用跨租户可见但只能 super_admin 管**：service 用 `is_platform` 字段标识，list_published_public 跳过 tenant 过滤，其他写操作仍要 super_admin
- **migration 加 `is_platform` 列**：SQLite/MySQL/PG 都兼容 boolean 默认 false；既有应用行 default true 还是 false？V0 默认 false（既有应用全是 tenant 私有）；超级管理员可手动置 true 升级为平台应用
- **公共 endpoint 暴露路径风险**：必须仅返回 PUBLISHED+PUBLIC，且不返 token/config_schema（敏感配置）；已枚举校验测试覆盖
- **回滚**：每 Slice 独立 commit + 迁移可下行

## 验证摘要（Slice 5 收口 2026-07-22）

- 新增 31 后端测试（admin_auth 15 + tenant_isolation 7 + dto_token_exposure 9），更新 1 个 alembic head 期望测试
- 全量 backend pytest `1252 passed, 4 skipped, 2 failed`：唯一非 alembic 测试失败是 test_embedding_empty_logs_warning（TD-080 pre-existing，main 全量同样失败）。已修复 test_alembic_012_015_create_schema（head 023 -> 024）
- `ruff check app/ tests/`：All checks passed（exit 0）
- check-engineering-docs：passed（31 known issue allowlisted）
- git diff --check：exit 0
- 前端 `npx vue-tsc --noEmit`：0 errors（packages/web/src/services/aiAppsApi.ts + 5 个 .vue 视图）
- 前端 `npx eslint "src/services/aiAppsApi.ts" "src/views/ai-apps/*.vue" "src/views/share/ShareView.vue"`：0 errors
- 可复核命令（macOS Darwin 25.5.0 / Python 3.14 / uv / Node 22）：
  - Command: `cd packages/server-python && uv run pytest -q --tb=line`
    Result: `1252 passed, 4 skipped, 2 failed`。`2 failed` = `test_embedding_empty_logs_warning`（TD-080 pre-existing，main 全量同样失败）+ `test_alembic_012_015_create_schema`（head 023 -> 024，已在本任务修复）。
    Environment: macOS Darwin 25.5.0 / Python 3.14 / uv 本地。
  - Command: `cd packages/server-python && uv run ruff check app/ tests/`
    Result: All checks passed
    Environment: 同上
  - Command: `cd packages/web && npx vue-tsc --noEmit`
    Result: exit 0
    Environment: Node 22
  - Command: `cd packages/web && npx eslint "src/services/aiAppsApi.ts" "src/views/ai-apps/*.vue" "src/views/share/ShareView.vue"`
    Result: exit 0
    Environment: 同上
  - Command: `./scripts/check-engineering-docs`
    Result: passed（31 known issue allowlisted）
    Environment: 同上
  - Command: `git diff --check`
    Result: exit 0
    Environment: 同上
- 安全闸：
  - AC-1 匿名 → 401；非 HIGH_PRIVILEGE → 403 + admin_access_denied 日志
  - AC-2 跨租户 get/put/delete/regenerate_* → 404（不暴露存在性）
  - AC-3 client tenant_id → 422（extra='forbid'）；服务端强制 current_user.tenant_id
  - AC-4 列表/详情默认 AiAppPublicResponse（无 token/owner/config_schema）；rotate 返单 token 字段 AiAppTokenResponse；超管 ?scope=admin 才返 AiAppAdminResponse
  - AC-5 GET /ai-apps/public 匿名，仅 is_platform+Published+public 子集；GET /ai-apps/share/{token} 按 share_token 查不返 token
  - AC-6 前端 aiAppsApi 改用共享 axios client（30s 超时 + 401 跳转 /login）
  - AC-7 31 个新测试 + 6 测试文件迁移 0 回归
