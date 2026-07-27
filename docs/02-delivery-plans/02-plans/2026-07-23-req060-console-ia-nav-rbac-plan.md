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

- [x] `LayoutView.vue` 删除 `navItems/adminItems/aiAppItems` path/permission 数组，使用 Route Record 投影并按 section 渲染（`projectNavigation(router.getRoutes(), ctx)` 唯一事实源）。
- [x] `HomeView.vue` 展示配置只引用 route name；path、permission、hidden 和 feature flag 从 Route Record 解析。`HOME_CARD_SPECS` 是纯展示配置（`routeName + presentation`，0 RBAC 字段），与 `projectNavigation` 可见名称集合求交集 = 最终 `homeCards`；shortcut 由 `(section, itemName)` 映射 + projection 可见性过滤。
- [x] 新建全局 `NavBreadcrumb` 组件（`packages/web/src/components/NavBreadcrumb.vue`），沿当前 route 的 `meta.activeNav` 链向上追溯到 home；每步校验父项 `meta.section` 与当前 route 同 section，任一缺失或不相等均 fail-closed（Plan "无完整 meta 一律 fail-closed"）；hiddenInNav route 仍出现 crumb（仅 sidebar 过滤 breadcrumb 不过滤）。
- [x] 下线"技能编排"（其 route 在 Slice 2 已 redirect 到 capabilities-skills，按 plan 不再列入 HOME_CARD_SPECS）；MCP/Skill 归能力中心，模板归知识与数据；未交付 system 子页不显示（hiddenInNav=true，sidebar 永不出现）。
- [x] 精确高亮：比较 `current.meta.activeNav ?? current.name`，禁止 path `startsWith`（详见 LayoutView `isActive()`）。
- [x] 覆盖 7 角色最小导航矩阵（LayoutView.spec.ts 7 角色 × section label 集合断言）、详情页唯一父高亮（5 条）、首页无失效/占位入口（HomeView.spec.ts 13 条）、section 排序（nav.spec.ts 既有）、feature flag（LayoutView.spec.ts）。
- **复杂度**：高（全局布局迁移 + 多入口回归）。
- **完成 commit**：`62002cf7`（修订-3：section 一致性 fail-closed + 独立 memory router 测试隔离 + 文档/PR 收口）。
- **验证摘要**：vue-tsc 0 errors / eslint 0 errors（20 warnings = 本 PR 新增 spec 4 个 + 既有 CatalogDetailPage 16 个）/ vitest canonical **296/296 passed** / docs gate passed / `git diff --check` exit 0 / 三路 CI 全绿。
- **测试分布**：LayoutView.spec.ts 32 + NavBreadcrumb.spec.ts 18 + HomeView.spec.ts 13 = 63 个 Slice 3 新增测试。
- **推荐模型**：GPT-5.6 Sol `medium/high` 或 Kimi K3 thinking 负责 UI；RBAC Review 使用 Sol `high`。

## Slice 4：移动端、a11y、Playwright 与收口

- [x] 实现 `<768px` 顶部 Menu 图标按钮和 off-canvas navigation；关闭状态不保留 60px 固定侧栏。LayoutView 加 `mobileOpenerRef` + `useMobileDrawer` composable；drawer open 时 aside `translate-x-0`，关闭时 `-translate-x-full`；desktopCollapsed 与 mobileDrawerOpen 独立 ref。
- [x] 覆盖 backdrop、Escape、route change 关闭，打开/关闭焦点迁移，body scroll lock，`aria-controls`、`aria-expanded`、`aria-current`。`useMobileDrawer` 封装：document 级 Escape 监听 + watch(route.fullPath) 自动关闭 + body overflow lock/unlock + 焦点回到 opener + Tab/Shift+Tab 循环焦点；opener `aria-controls="mobile-drawer"` + `:aria-expanded`；nav-item `:aria-current="isActive(item.name) ? 'page' : undefined"`。
- [x] 为分组按钮实现键盘导航和稳定展开状态；桌面折叠与移动抽屉状态分离。desktop `desktopCollapsed` (toggle 桌面 collapse button, `md:flex` only) 与 mobile `mobileDrawer.open` (opener `md:hidden` only) 完全独立；`@media (prefers-reduced-motion: reduce)` 取消所有 transition；skip-link `<a href="#main-content">` 视觉隐藏 + focus 显示。
- [x] 仓库当前无 Playwright：新增 `@playwright/test` 依赖、配置和可复现脚本；覆盖桌面/移动、浅色/深色、7 角色代表集、403、重定向和详情父高亮。`packages/web/playwright.config.ts` + `e2e/navigation-shared.spec.ts` + `e2e/navigation-desktop.spec.ts` + `e2e/navigation-mobile.spec.ts` + `e2e/fixtures.ts` + `e2e/README.md`；2 projects (chromium-desktop 1280×800 + chromium-mobile Pixel 5) 用 testMatch glob 分流；`setupE2E(page, role)` = injectAuth + installApiMocks（拦截 /api/v1/* 防 ECONNREFUSED）；结构视觉断言替代 toHaveScreenshot（跨平台）；覆盖 7 角色 sidebar / activeNav 高亮 / 详情父高亮 / mobile drawer 状态机 + a11y / 主题 / 旧链接重定向 / 403 / breadcrumb / skip-link 键盘验收。
- [x] 运行前端 lint、typecheck、Vitest、Playwright；PR CI 按 scope 执行，禁止把 mock UI 当后端 RBAC 证据。`vitest.config.ts` 排除 `e2e/**`（`configDefaults.exclude` 追加）；`tsconfig.e2e.json` 独立类型门禁；`package.json` lint 纳入 `e2e/**/*.ts` + `playwright.config.ts`；`ci.yml` 接入 Playwright install + test:e2e。最终验证：vitest canonical 326/326 passed；Playwright 55/55（仅 desktop 跑 skip-link 键盘用例）；typecheck 0 / lint 0 errors 28 warnings / docs gate / diff check exit 0；三路 CI 全绿（Frontend 2m30s / Backend 8m05s / Engineering docs）。六轮复审收口（r1: mobile drawer + focus trap + project 分流 + CI；r2: active-not-in-set + API mocks + 结构断言；r3: skip-link to shared + lint scope；r4: skip-link to desktop + e2e typecheck；r5: drawer inert + 路由焦点 + skip-link CSS；r6: 单一 skip-link 所有权收口）。
- [x] 用户验收后更新 work-log、Requirement/Backlog/current-work 和本 Plan 验证摘要。已提交 work-log closeout commit `43baf71e` + current-work 收口 + scorecard 95 分 + Backlog REQ-060 状态切 Done + 候选区登记 REQ-041/047 R1 / REQ-042 / REQ-047 C1。
- **复杂度**：高（移动端 + a11y + Playwright 浏览器验收合一）。
- **完成 commit**：`6d1ce65f`（PR #503 squash merge `b924bddc` + docs closeout `43baf71e`；六轮 Codex 复审 P0/P1/P2 = 0/0/1 最终通过；已合并归档，REQ-060 Done）。
- **测试分布**：useMobileDrawer.spec.ts 15 + LayoutView.spec.ts 47（+15 Slice 4）= Slice 4 新增 30 vitest tests；Playwright e2e 三组 spec 55/55（shared × 2 projects + desktop + mobile）。合计仓库 canonical 326/326 + Playwright 55/55。
- **焦点返回契约**（Spec D-10 收口）：
  - Escape / backdrop / opener 二次点击 关闭 -> 焦点回到 opener
  - 路由导航关闭 drawer -> 焦点移到新页面 `#main-content`（避免停留在已移出视口的 nav-link）
  - 关闭态 drawer 加 `inert` + `aria-hidden="true"`（防止 Tab 序列 + AT 树进入）
- **推荐模型**：GPT-5.6 Sol `high` 做响应式 + a11y + 焦点语义返修；Kimi K3 thinking 实现 UI 改动。

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
- `packages/web/src/components/NavBreadcrumb.vue` - 全局导航 breadcrumb（activeNav 链 + 同 section 一致性 fail-closed）
- `packages/web/src/views/ForbiddenView.vue` - 403
- `packages/web/playwright.config.ts` / `packages/web/e2e/navigation-{shared,desktop,mobile}.spec.ts` - 浏览器验收（testMatch 分流 desktop/mobile）

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
- Slice 2 收口（2026-07-27，PR #499 复审 P0/P1 = 0/0，P2 修复已提交，待最终复审）：
  - feature flag 实际来源：`nav.ts#loadFeatureFlags` 从 `localStorage` 读取 `metaedu_feature_<flag>`（`"true"` 为开），`router.ts` guard 调用之，替换原写死空 `FeatureFlags`。flag 缺失仍 fail-closed（system_management 为未交付功能，后端 `LoginResponse` 暂未下发 flags，发布时由登录流程写入）。
  - 旧链接 6/6 覆盖：补 `/admin/template/:id -> /data/templates/:id` 参数保留测试；router.spec 15 tests、nav.spec 43 tests 全绿。
  - 后端 401/403 独立证据（AC-3 第三层，与前端 mock 无关）：
    ```bash
    cd packages/server-python
    .venv/bin/pytest \
      tests/contexts/template/test_template_rbac.py \
      tests/contexts/mcp_registry/test_registry_service.py \
      tests/contexts/skill_registry/test_skill_registry_service.py \
      tests/contexts/ai_app/test_admin_auth.py -q
    ```
    结果：`213 passed in 111.71s`。
