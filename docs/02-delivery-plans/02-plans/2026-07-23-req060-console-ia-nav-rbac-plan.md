# Plan: REQ-060 企业 Agent 控制台信息架构与权限化导航

> Spec: `docs/02-delivery-plans/01-specs/2026-07-23-req060-console-ia-nav-rbac.md`
> Requirement: `docs/01-product-planning/05-requirements/REQ-060-enterprise-console-information-architecture.md`

## 实施策略

只塑形 + 契约设计，不改业务代码（本 PR 仅 docs）。实施分 5 Slice，每 Slice 独立 PR。迁移按"先建事实源 -> 迁移菜单 -> 下线旧入口 -> 守卫加固 -> 回归"顺序，每步可回滚。

## Slices

### Slice 1：导航事实源 + route meta 类型化（AC-4）
- [ ] `packages/web/src/app/nav.ts`：类型化 NavSection 枚举 + NavItem + permission 派生
- [ ] `router.ts`：route meta 扩展 `section/order/permission/hiddenInNav/featureFlag/icon`
- [ ] `packages/web/src/constants/permissions.ts`：PermissionKey 类型 + role→permission 矩阵
- [ ] 单元测试：permission resolver（7 角色 × 9 key（对齐 Spec §5.3））
- **复杂度**：中（类型设计 + 派生逻辑）
- **模型分工**：Sonnet（类型 + 派生）

### Slice 2：角色映射统一 + roleMap 修正（AC-9）
- [ ] `packages/web/src/constants/maps.ts`：roleMap/roleShortMap 改为后端 RoleEnum 全集（删 domain_expert/harness_engineer/system_ops，加 data_admin/admin/leader/employee）
- [ ] `auth store`：确认 userRole 来自后端（已 localStorage）
- [ ] DD 页面 roleLabel 验证（leader/admin/data_admin 正确显示）
- [ ] 测试：roleMap 覆盖后端 RoleEnum 全集
- **复杂度**：低（数据修正）
- **模型分工**：Sonnet

### Slice 3：新建目标路由 + Sidebar / HomeView / breadcrumb 迁移（AC-1/AC-2/AC-5）
- [ ] **新建路由**（P1-6）：`/capabilities/skills`（复用 SkillListView）、`/capabilities/mcp`（复用 McpServerListView）、`/data/templates`（复用 TemplateListView）、`/data/templates/:id`（复用 TemplateEditorView）、`/system`（占位页，D-6）
- [ ] `LayoutView.vue`：navItems/adminItems/aiAppItems 改为从 `nav.ts` 派生（按 permission 过滤）
- [ ] `HomeView.vue`：navItems/shortcuts 引用命名路由 + permission 过滤；移除"技能编排"占位
- [ ] 新建 `Breadcrumb.vue`：从 route meta section 派生
- [ ] `isActive` 改 route name 匹配（AC-6）
- [ ] 下线"技能编排"一级入口；MCP/Skill 迁能力中心 `/capabilities/*`；数据要素模板迁 `/data/templates`；`/admin` 占位页下线（重定向 `/system`）
- [ ] `/system/*` 5 子路由 V1 不创建（D-6 预留，hidden+featureFlag）
- [ ] 测试：7 角色导航矩阵（AC-7）
- **复杂度**：高（新建路由 + 3 视图迁移 + isActive 修复 + 矩阵测试）
- **模型分工**：Sonnet（视图）+ Opus review（RBAC 过滤正确性）

### Slice 4：深链守卫 + 403 页 + 旧链接重定向（AC-3/AC-10）
- [ ] `router.beforeEach` 增强：检查 `to.meta.permission`，无权限 -> `/403`
- [ ] 新建 `ForbiddenView.vue`（403 页）
- [ ] 旧路径重定向（D-3 完整）：`/skill-editor` -> `/capabilities/skills`；`/admin/mcp-servers` -> `/capabilities/mcp`；`/admin/skills` -> `/capabilities/skills`；`/admin/template` -> `/data/templates`；`/admin/template/:id` -> `/data/templates/:id`；`/admin` -> `/system`
- [ ] 测试：深链 403 + 重定向 + API 独立拒绝（AC-3 三层一致，**模板例外：TD-082 未关闭前仅前端两层**）
- **复杂度**：中（守卫 + 重定向）
- **模型分工**：Sonnet + Opus review（深链绕过）

### Slice 5：移动端 + a11y + 主题 + 回归收口（AC-8）
- [ ] 移动端折叠菜单验证（< 768px）
- [ ] 键盘导航 + aria 状态（aria-current/aria-expanded）
- [ ] 浅色/深色主题验收
- [ ] 全量前端 typecheck + lint + Vitest
- [ ] 全量后端 pytest（确认无回归）
- [ ] 工作台归档 + work-log
- **复杂度**：低（验收 + 收口）
- **模型分工**：Sonnet

## 迁移顺序（关键）

1. **建事实源**（Slice 1）：nav.ts + route meta + permission 矩阵 -- 不破坏现有
2. **统一角色**（Slice 2）：roleMap 修正 -- DD roleLabel 修复
3. **迁移菜单**（Slice 3）：Sidebar/HomeView 派生 + 下线占位 + 迁能力中心
4. **守卫加固**（Slice 4）：深链 403 + 重定向
5. **回归收口**（Slice 5）：a11y + 主题 + 全量门禁

每步独立 PR + 可回滚。Slice 3 是最大改动（3 视图 + isActive + 矩阵测试）。

## 关键文件

- `packages/web/src/app/nav.ts` - 新增（导航事实源）
- `packages/web/src/app/router.ts` - route meta 扩展
- `packages/web/src/constants/permissions.ts` - 新增（permission 矩阵）
- `packages/web/src/constants/maps.ts` - roleMap 统一
- `packages/web/src/views/LayoutView.vue` - Sidebar 派生
- `packages/web/src/views/HomeView.vue` - 首页快捷入口派生
- `packages/web/src/components/Breadcrumb.vue` - 新增
- `packages/web/src/views/ForbiddenView.vue` - 新增（403）
- `packages/web/tests/nav.spec.ts` - 导航矩阵测试

## Global Constraints

- 不实现 Agent Loop / Runtime / Agent Builder（只预留 hidden + featureFlag）
- 后端 RBAC 是最终裁决，前端隐藏不是安全控制
- 既有 API 不改（REQ-044/045/058 菜单归属迁移，不动 API）
- **模板 API 例外（TD-082）**：模板 API 当前无后端 RBAC，REQ-060 不修复（Non-goal），仅前端两层守（菜单隐藏 + 深链 403）。TD-082 关闭前 AC-3 对模板不强制三层一致。
- 旧链接重定向保留 1 版本周期

## Non-goals

- 后端 permission grants 下发（V1 角色映射）
- 业务页面视觉重做
- Agent Workspace UI（REQ-042）

## 风险与回滚

- **roleMap 修正破坏既有用户**：domain_expert/harness_engineer/system_ops 用户登录后 roleLabel 显示 raw role（后端已无这些角色，实际无影响）。回滚：保留旧映射 1 版本。
- **菜单迁移破坏书签**：旧链接重定向兼容。回滚：重定向移除。
- **permission 过滤误隐藏**：7 角色矩阵测试覆盖。回滚：nav.ts permission 派生回退到全可见。
- **isActive route name 匹配破坏**：详情路由高亮回归测试。回滚：startsWith。

## 验证摘要（shaping 阶段未实施，待 Slice 5 收口时填）

- 预期新增 ~15 前端测试（nav 矩阵 + permission resolver + 重定向 + 403）
- 预期全量前端 typecheck 0 / lint 0 / Vitest 0
- 预期全量后端 pytest 0 回归
- 安全闸：AC-3 深链 403 + API 独立；AC-9 roleMap 统一；AC-10 旧链接重定向
## Follow-up（REQ-060 范围外，登记技术债）

- **TD-082 模板 API 后端 RBAC**：`/api/v1/templates/*` 加 `require_high_privilege` 守卫。TD-082 关闭后模板纳入 AC-3 三层一致验收。REQ-060 实施时（Slice 5 收口）同步登记到 `docs/03-engineering-governance/technical-debt.md`。
- **`/system/*` 子路由创建**：V1 预留（D-6），后续系统管理各子页作为独立需求交付。
- **后端 permission grants 下发**：V1 用角色映射，后续切换不重写页面。
