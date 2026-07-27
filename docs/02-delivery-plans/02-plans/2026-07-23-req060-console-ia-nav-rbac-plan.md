# Plan: REQ-060 企业 Agent 控制台信息架构与权限化导航

> Spec: `docs/02-delivery-plans/01-specs/2026-07-23-req060-console-ia-nav-rbac.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-060-enterprise-console-information-architecture.md`
> Revised: 2026-07-25（R1 review correction）

## 实施策略

R1 修订后按 5 个交付 Gate 实施。每个 Gate 独立 PR，但受保护目标路由、permission meta、403 守卫和旧链接重定向必须在同一 Gate 原子交付。Route Record 是 `path/name/meta` 唯一事实源；`nav.ts` 只做无 Router 反向依赖的纯投影。

## Gate 0：TD-087 模板管理 API 后端 RBAC（✅ 已完成，PR #495）

- [x] 按 `technical-debt.md#td-087-模板管理-api-缺少后端-rbac` 独立实施，不与前端菜单 PR 混合。
- [x] 冻结模板管理 API 端点矩阵；V1 管理 router 的 list/read/write/version/export 全部要求 `HIGH_PRIVILEGE_ROLES`。
- [x] 覆盖匿名 401、4 个普通角色 403、3 个高权角色放行及 tenant isolation。
- [x] TD-087 已关闭（PR #495 `40a7bf46`），Slice 2 可创建 `/data/templates*`。
- **复杂度**：高（认证授权 + 既有模板调用回归）。
- **推荐模型**：GPT-5.6 Sol `high`；独立 RBAC Review 使用 `xhigh`。

## Slice 1：Route meta Foundation + role/permission resolver

- [x] `packages/web/src/app/nav.ts`：NavSection、section descriptors、PermissionKey、FeatureFlagKey、fail-closed resolver 和 `projectNavigation(routes, accessContext)` 纯函数；禁止导入 Router 实例。
- [x] `packages/web/src/app/router.ts` / `env.d.ts`：Vue Router `RouteMeta` augmentation，加入 `title/section/order/permission/hiddenInNav/featureFlag/activeNav/icon`。
- [x] Route Record 是 path/name/meta 唯一事实源；guest/layout/redirect 可省略导航字段，业务 leaf route 必须显式声明访问与投影语义。
- [x] `packages/web/src/constants/maps.ts`：roleMap/roleShortMap 对齐后端 7 个 RoleEnum；删除不存在角色。
- [x] unknown/null role、未知 permission、未知/关闭 feature flag 必须 fail-closed；无 permission 的基础路由只要求已认证。
- [x] 测试放在现有 colocated 约定下：`packages/web/src/app/nav.spec.ts`，覆盖 7 角色 + unknown/null、9 permission key、feature flag 和排序。
- **复杂度**：高（全局契约与后续 Slice 的公共事实源）。
- **推荐模型**：GPT-5.6 Sol `high`；第二模型只读审查循环依赖、默认值和 fail-closed。

## Slice 2：受保护目标路由 + 守卫 + 重定向原子迁移

- [x] 新建目标路由：`/capabilities/skills`、`/capabilities/mcp`、`/data/templates`、`/data/templates/:id`、`/system`；复用既有页面，不实现未交付系统管理子页。
- [x] 同一 PR 新建 `/403`、permission/feature guard 和全部旧链接重定向：`/skill-editor`、`/admin/mcp-servers`、`/admin/skills`、`/admin/template`、`/admin/template/:id`、`/admin`。
- [x] `activeNav` 映射：`file-detail -> resource`、`catalog-detail -> database`、`AiAppEdit -> AiAppsAdmin`、`AiAppDetail/App* -> AiAppsMarketplace`、`template-detail -> templates-list`。
- [x] 所有详情、编辑、redirect、独立应用 shell 和占位 route 设为 `hiddenInNav=true`。
- [x] 测试：低权深链 403、高权访问、unknown role fail-closed、重定向后重新执行目标 route guard、`/403` 不产生循环。
- [x] 后端 API 独立验证：MCP/Skill/AI App 与完成后的 TD-087 均保持 401/403 裁决。
- **复杂度**：高（路由切换与授权必须原子）。
- **推荐模型**：GPT-5.6 Sol `high`；独立 Review `xhigh`。

## Slice 3：Sidebar / Home / Breadcrumb 统一投影

- [ ] `LayoutView.vue` 删除 `navItems/adminItems/aiAppItems` path/permission 数组，使用 Route Record 投影并按 section 渲染。
- [ ] `HomeView.vue` 展示配置只引用 route name；path、permission、hidden 和 feature flag 从 Route Record 解析。
- [ ] 新建或复用全局 Breadcrumb，使用 section + `activeNav`；不得干扰知识库页面内部的数据层级 breadcrumb。
- [ ] 下线“技能编排”；MCP/Skill 归能力中心，模板归知识与数据；未交付 system 子页不显示。
- [ ] 精确高亮：比较 `current.meta.activeNav ?? current.name`，禁止 path `startsWith`。
- [ ] 覆盖 7 角色最小导航矩阵、详情页唯一父高亮、首页无失效/占位入口、section 排序和 feature flag。
- **复杂度**：高（全局布局迁移 + 多入口回归）。
- **推荐模型**：GPT-5.6 Sol `medium/high` 或 Kimi K3 thinking 负责 UI；RBAC Review 使用 Sol `high`。

## Slice 4：移动端、a11y、Playwright 与收口

- [ ] 实现 `<768px` 顶部 Menu 图标按钮和 off-canvas navigation；关闭状态不保留 60px 固定侧栏。
- [ ] 覆盖 backdrop、Escape、route change 关闭，打开/关闭焦点迁移，body scroll lock，`aria-controls`、`aria-expanded`、`aria-current`。
- [ ] 为分组按钮实现键盘导航和稳定展开状态；桌面折叠与移动抽屉状态分离。
- [ ] 仓库当前无 Playwright：新增最小 `@playwright/test` 依赖、配置和可复现脚本；覆盖桌面/移动、浅色/深色、7 角色代表集、403、重定向和详情父高亮截图/断言。
- [ ] 运行前端 lint、typecheck、Vitest、Playwright；PR CI 按 scope 执行，禁止把 mock UI 当后端 RBAC 证据。
- [ ] 用户验收后更新 work-log、Requirement/Backlog/current-work 和本 Plan 验证摘要。
- **复杂度**：高（当前移动端能力缺失，不是纯验收）。
- **推荐模型**：GPT-5.6 Sol `medium` 或 Kimi K3 thinking 实现；Sol `high` 做响应式/RBAC Review。

## 强制顺序

1. Gate 0：TD-087。
2. Slice 1：Foundation。
3. Slice 2：受保护路由原子迁移。
4. Slice 3：可见导航投影迁移。
5. Slice 4：移动端与浏览器收口。

Slice 1 可在 TD-087 实施前完成，但 Slice 2 不得越过 Gate 0。不同模型不得同时修改 `router.ts`、`nav.ts` 或 Layout 全局契约。

## 关键文件

- `packages/web/src/app/nav.ts` - 新增，纯投影与 resolver
- `packages/web/src/app/nav.spec.ts` - 新增，权限/投影矩阵
- `packages/web/src/app/router.ts` - Route Record 与 guard
- `packages/web/env.d.ts` - RouteMeta augmentation
- `packages/web/src/constants/maps.ts` - role label 对齐
- `packages/web/src/views/LayoutView.vue` - Sidebar/移动导航
- `packages/web/src/views/HomeView.vue` - route-name presentation
- `packages/web/src/components/Breadcrumb.vue` - 全局导航 breadcrumb
- `packages/web/src/views/ForbiddenView.vue` - 403
- `packages/web/playwright.config.ts` / `packages/web/e2e/navigation.spec.ts` - 浏览器验收

## Global Constraints

- 不实现 Agent Loop、Runtime、Agent Builder、Workflow 或 system 子页。
- `nav.*` 只控制导航可见性，不是业务 action authorization；API 是最终裁决。
- `authStore.userRole` 当前是本地展示状态，不得称为持续验证身份，不得据此保护敏感 API。
- 未知角色、permission、feature flag 和无完整 meta 的受保护业务 route 一律 fail-closed。
- 首页 presentation 可以维护文案，但不得复制 path、permission、hidden 或 active 规则。
- 旧链接保留一个版本周期；移除时间需由后续稳定任务登记。

## 验证摘要（实施阶段回填）

- Shaping R1：PR #493（squash merge `a0e18b8b`）；`scripts/check-engineering-docs` 通过（31 条 allowlisted known issues），`git diff --check` 通过，三项 required checks 通过。
- Gate 0：模板 API 7 角色 + 匿名 + tenant isolation 后端测试。
- Slice 1-3：Vitest permission/nav/router/Layout/Home 矩阵 + lint + typecheck。
- Slice 4：Playwright desktop/mobile/light/dark + 全量前端门禁。
- mock/fixture 仅证明前端契约，不得宣称后端 RBAC 或真实用户 Pilot 完成。
- Slice 2 收口（2026-07-27，PR #499 复审 P0/P1 = 0/0，P2 修复中）：
  - feature flag 实际来源：`nav.ts#loadFeatureFlags` 从 `localStorage` 读取 `metaedu_feature_<flag>`（`"true"` 为开），`router.ts` guard 调用之，替换原写死空 `FeatureFlags`。flag 缺失仍 fail-closed（system_management 为未交付功能，后端 `LoginResponse` 暂未下发 flags，发布时由登录流程写入）。
  - 旧链接 6/6 覆盖：补 `/admin/template/:id -> /data/templates/:id` 参数保留测试；router.spec 15 tests、nav.spec 43 tests 全绿。
  - 后端 401/403 独立证据（AC-3 第三层，与前端 mock 无关）：`packages/server-python/tests/contexts/template/test_template_rbac.py`（TD-087）、`contexts/mcp_registry/test_registry_service.py`、`contexts/skill_registry/test_skill_registry_service.py`、`contexts/ai_app/test_admin_auth.py`；全量 `cd packages/server-python && uv run pytest -q` -> 213 passed。
