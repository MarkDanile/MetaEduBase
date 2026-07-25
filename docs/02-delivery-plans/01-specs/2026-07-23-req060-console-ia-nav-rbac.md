# Spec: REQ-060 企业 Agent 控制台信息架构与权限化导航

> Requirement: `docs/01-product-planning/05-requirements/REQ-060-enterprise-console-information-architecture.md`
> Status: 🔵 Ready（shaping 冻结）
> Priority: P1
> Area: Web / Information Architecture / Navigation / RBAC
> Shaped: 2026-07-23
> Parent: REQ-059（🟢 Done）

## 1. 背景与问题

当前侧边栏、Router、首页卡片各自硬编码导航，三份事实源割裂；一级"技能编排"指向未实现占位页；MCP/Skill 作为 Agent 能力资产被放在系统配置层；系统管理和应用管理对所有登录用户显示，路由仅检查 Token，无菜单级 permission 事实源。继续增加 Agent、Runtime 和记忆页面会进一步放大漂移。

## 2. 当前菜单漂移盘点（事实）

### 2.1 三份割裂的导航事实源

| 事实源 | 文件 | 内容 |
|--------|------|------|
| 侧边栏 | `LayoutView.vue` | `navItems`（6 一级）+ `adminItems`（3 系统管理）+ `aiAppItems`（2 AI 应用） |
| 首页卡片 | `HomeView.vue` | 独立 `navItems`（功能模块卡片）+ `shortcuts` |
| 路由 | `router.ts` | routes 仅 `requiresAuth`，无 permission key |

### 2.2 菜单漂移问题

| # | 问题 | 证据 |
|---|------|------|
| D-1 | 两个 Skill 入口语义冲突 | 一级"技能编排" `/skill-editor`（占位 EmptyState "即将上线"）+ 系统管理"Skill 服务" `/admin/skills`（真实管理页） |
| D-2 | MCP/Skill 归属错误 | 在 `adminItems`（系统管理），应归"能力中心"（spec Target IA） |
| D-3 | 管理入口对普通用户可见 | `adminItems` + `aiAppItems` 对所有登录用户显示，无 role 过滤 |
| D-4 | 路由无 permission 守卫 | `router.beforeEach` 仅检查 token；深链直达管理页 -> API 401（非 403） |
| D-5 | isActive 误高亮 | `startsWith` 导致 `/resource/123` 误高亮 `/resource` 同前缀其他入口 |
| D-6 | 首页暴露占位入口 | HomeView `navItems` 含"技能编排"占位 |

### 2.3 角色映射漂移（P0 阻塞）

| 前端 `roleMap` | 后端 `RoleEnum`（BUG-017） | 状态 |
|----------------|---------------------------|------|
| super_admin | super_admin | ✅ 一致 |
| domain_expert | - | ❌ 前端独有（后端无） |
| teacher | teacher | ✅ |
| student | student | ✅ |
| harness_engineer | - | ❌ 前端独有 |
| system_ops | - | ❌ 前端独有 |
| - | data_admin | ❌ 后端独有（前端无） |
| - | admin | ❌ 后端独有（前端无） |
| - | leader | ❌ 后端独有（REQ-058 DD 用） |
| - | employee | ❌ 后端独有 |

**影响**：REQ-058 DD RBAC 用 `leader/admin/data_admin`，前端 roleMap 不认 -> DD 页面 roleLabel 显示 raw role；permission 过滤无法基于后端角色。

## 3. Decisions（2026-07-23 shaping 冻结）

### D-1 角色映射：统一到后端 RoleEnum

前端 `roleMap` / `roleShortMap` 改为后端 `RoleEnum` 全集（super_admin/data_admin/admin/leader/teacher/employee/student），删除 `domain_expert/harness_engineer/system_ops`。permission 派生自后端角色，不再维护前端独立角色集。

### D-2 能力中心对普通用户完全隐藏

能力中心（Skill 库 / MCP 工具）整个区域对 `teacher/student/employee/leader` 隐藏菜单 + 深链 403。普通用户通过 Agent 间接使用能力，不进 Registry 管理页。`admin/data_admin/super_admin` 可见。

### D-3 旧链接重定向兼容

| 旧路径 | 新路径 | 策略 |
|--------|--------|------|
| `/skill-editor` | `/capabilities/skills`（或首页 + "已下线"提示） | redirect，1 版本周期后移除 |
| `/admin/mcp-servers` | `/capabilities/mcp` | redirect |
| `/admin/skills` | `/capabilities/skills` | redirect |
| `/admin/template` | `/data/templates`（知识与数据区域） | redirect |
| `/admin/template/:id` | `/data/templates/:id` | redirect（详情深链兼容） |
| `/admin` | `/system`（V1 占位重定向，见 D-6） | redirect |

### D-4 "AI 问答"保持名称，绑定 REQ-042 改名

REQ-060 保持"AI 问答" + route `/ai-chat`。REQ-042 Agent Workspace 验收通过后，单独 PR 改名"Agent 工作台" + route meta flag。避免菜单名称超前于真实能力（当前无 Agent Loop）。

### D-5 permission 派生：V1 用已验证角色，API 是最终裁决

V1 前端 permission 由已验证身份角色（`authStore.userRole`）映射；API 始终是授权事实源（后端 RBAC 独立拒绝）。后续切换后端下发 permission grants 时不重写页面结构（只改 permission resolver）。

**例外（前置依赖）**：模板 API（`/api/v1/templates/*`）当前后端**无 RBAC**（仅 `get_current_user` 认证，无 role 守卫），不满足"API 独立拒绝"。REQ-060 不在范围内修复后端（Non-goal"既有 API 不改"），改为：
- Spec §5.4 显式撤回对模板的"既有 RBAC"承诺
- AC-3 注明模板暂不纳入"三层一致"验收
- 登记 TD-082「模板 API 缺后端 RBAC」作为前置依赖（REQ-060 实施前不阻塞，但模板权限化验收依赖 TD-082 关闭）

### D-6 `/system/*` 路由 V1 预留，不创建

§4 Target IA 列出的 `/system/users` `/system/tenants` `/system/models` `/system/security` `/system/audit` 5 个子路由在 V1 **不创建**（既有 `/admin` AdminView 是占位页）。V1 只：
- 下线 `/admin` 占位页，重定向到 `/system`（占位页 + "系统管理即将上线"）
- 菜单不显示系统管理子项（hidden + featureFlag=`system_management`）
- 后续系统管理各子页作为独立需求交付时再创建路由

避免 REQ-060 提前实现未交付的系统管理页面。

### D-7 `/apps/*` 独立应用 permission 策略

`/apps/enterprise-360-dd/*`（REQ-046/058）有后端角色限制（`dd_permissions.py` CREATE/RUN 限 leader/admin/data_admin，READ 限 leader/admin/data_admin/super_admin）。`/apps/course-capability-map` 等 4 个占位应用无后端守卫。

V1 策略：
- `/apps/*` 路由 permission = `nav.apps.marketplace`（已登录即可见 route），但**具体应用的后端 RBAC 独立裁决**（DD 后端已守，占位应用无敏感数据）
- 前端不隐藏 `/apps/*` shell（普通用户可见入口），API 越权由后端 403
- AC-3 "三层一致"对 `/apps/*` 不强制（shell 可见 + API 守卫，接受 shell 泄露）
- DD 详情 `/apps/enterprise-360-dd/tasks/:id` 等深链：前端不额外守卫，依赖后端 403

## 4. 目标信息架构（Target IA）

| 一级区域 | route prefix | 二级入口 | permission | 受众 |
|----------|--------------|----------|------------|------|
| 总览 | `/` | 平台概览 | 已登录 | 全部 |
| AI 工作 | `/ai-chat` | AI 问答（REQ-042 后改 Agent 工作台） | 已登录 | 业务用户 |
| 智能体应用 | `/ai-apps` | 应用广场（公开）；应用管理（admin+） | 广场：已登录；管理：HIGH_PRIVILEGE | 用户 / 管理员 |
| 知识与数据 | `/knowledge` `/resource` `/database` `/data/templates` | 知识库、资源库、数据库、数据要素模板 | 按数据权限 | 全部（模板 admin+） |
| 能力中心 | `/capabilities/skills` `/capabilities/mcp` | Skill 库、MCP 工具（后续 Agent 定义/Workflow/Runtime 预留） | HIGH_PRIVILEGE | Agent Builder / tenant admin |
| 系统管理 | `/system` | 用户与角色、租户、模型与凭证、安全策略、审计（**V1 预留，不创建子路由**，见 D-6） | super_admin | 平台运维 |

"技能编排"占位一级入口下线。未来可视化编排作为 Skill 详情中的创建/编辑能力，不再制造第二个 Skill 产品概念。

## 5. 导航事实源设计（Single Source of Truth）

### 5.1 route meta schema

每个 route record 的 `meta` 扩展为类型化：

```ts
interface RouteMeta {
  title: string;              // 显示名
  section: NavSection;        // 一级区域枚举
  order?: number;             // 区域内排序
  permission?: PermissionKey; // 所需 permission（缺省=已登录即可）
  hiddenInNav?: boolean;      // 详情/编辑/占位页不在菜单显示
  featureFlag?: string;       // 未交付功能 flag（hidden until flag on）
  icon?: Component;           // 菜单图标
}
```

### 5.2 nav config 单一源

新建 `packages/web/src/app/nav.ts`：类型化导航配置（从 route meta 派生 section/order/permission）。Sidebar / breadcrumb / route guard / 首页快捷入口都从 `nav.ts` 派生，不再维护三份数组。

### 5.3 permission key 矩阵

| permission key | super_admin | data_admin | admin | leader | teacher | employee | student |
|----------------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `nav.overview` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `nav.ai_work` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `nav.apps.marketplace` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `nav.apps.admin` | ✅ | ✅ | ✅ | - | - | - | - |
| `nav.knowledge` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `nav.data` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `nav.data.templates` | ✅ | ✅ | ✅ | - | - | - | - |
| `nav.capabilities` | ✅ | ✅ | ✅ | - | - | - | - |
| `nav.system` | ✅ | - | - | - | - | - | - |

（`HIGH_PRIVILEGE_ROLES` = super_admin/data_admin/admin；system 仅 super_admin）

**层级语义**：permission key 独立校验，**子 key 不蕴含父 key**（如持有 `nav.data.templates` 不自动获 `nav.data`）。resolver 对每个 key 独立判断。`nav.apps.marketplace` 与 `nav.apps.admin` 同理独立。

### 5.4 route -> permission 显式映射表

| route | name | permission | hiddenInNav | 备注 |
|-------|------|------------|:-:|------|
| `/` | home | - | - | 总览 |
| `/ai-chat` | ai-chat | `nav.ai_work` | - | AI 问答 |
| `/ai-apps` | AiAppsMarketplace | `nav.apps.marketplace` | - | 应用广场 |
| `/ai-apps/admin` | AiAppsAdmin | `nav.apps.admin` | - | 应用管理 |
| `/ai-apps/admin/:id` | AiAppEdit | `nav.apps.admin` | ✅ | 编辑详情 |
| `/ai-apps/:code` | AiAppDetail | `nav.apps.marketplace` | ✅ | 应用详情 |
| `/knowledge` | knowledge | `nav.knowledge` | - | 知识库 |
| `/resource` | resource | `nav.knowledge` | - | 资源库 |
| `/resource/:id` | file-detail | `nav.knowledge` | ✅ | 文件详情 |
| `/database` | database | `nav.data` | - | 数据库 |
| `/database/:catalogCode` | catalog-detail | `nav.data` | ✅ | 目录详情 |
| `/data/templates` | templates-list | `nav.data.templates` | - | 数据要素模板（迁自 `/admin/template`） |
| `/data/templates/:id` | template-detail | `nav.data.templates` | ✅ | 模板详情 |
| `/capabilities/skills` | capabilities-skills | `nav.capabilities` | - | Skill 库（迁自 `/admin/skills`） |
| `/capabilities/mcp` | capabilities-mcp | `nav.capabilities` | - | MCP 工具（迁自 `/admin/mcp-servers`） |
| `/system` | system | `nav.system` | ✅ | 系统管理占位（V1 预留，D-6） |
| `/apps/*` | App* | `nav.apps.marketplace` | - | 独立应用（D-7，后端独立裁决） |
| `/skill-editor` | - | - | - | **下线**，重定向 `/capabilities/skills`（D-3） |
| `/admin` | - | - | - | **下线**，重定向 `/system`（D-3/D-6） |
| `/admin/*` 旧路径 | - | - | - | 重定向新路径（D-3） |

### 5.4 深链守卫

- 前端 `router.beforeEach` 增强：检查 `to.meta.permission`，无权限 -> 重定向 `/403`（新建无权限页）或首页 + toast。
- 后端 API 独立拒绝越权（**既有 RBAC**，不依赖前端隐藏）。
- AC-3：隐藏菜单 + 深链 403 + API 401/403 三层一致。

**例外（前置依赖 TD-082）**：模板 API（`/api/v1/templates/*`）当前后端无 RBAC（仅认证无授权），不满足"API 独立拒绝"。REQ-060 范围内：
- 前端按 `nav.data.templates`（HIGH_PRIVILEGE）隐藏菜单 + 深链 403
- 后端 API 暂不对模板做角色守卫（TD-082 未关闭前）
- **AC-3 对模板不强制"三层一致"**（前端两层守 + API 暂敞口，登记 TD-082 后续加固）
- TD-082 关闭后模板纳入三层一致验收

### 5.5 isActive 精确匹配

`isActive` 改为 route name 匹配（非 path startsWith），避免详情路由误高亮同前缀。面包屑用 route meta section 展开正确分组。

## 6. 所有权边界

| 需求 | 所有权 | REQ-060 关系 |
|------|--------|--------------|
| REQ-042 Agent Workspace 三栏 | UI/UX 实现 | REQ-060 只预留 nav 位置（hidden + featureFlag）；不实现 Workspace |
| REQ-043 Runtime/Agentic RAG | Runtime 实现 | REQ-060 不实现；能力中心预留 Runtime 入口（hidden） |
| REQ-047 Agent Run 中心 | Run/Approval 实现 | REQ-060 不实现；AI 工作区预留"我的任务"入口（hidden） |
| REQ-059 Agent 平台内核 | 已 Done | REQ-060 复用其 RBAC 边界，不重复 |
| REQ-044 MCP Registry | 已 Done | REQ-060 迁移菜单归属，不改 API |
| REQ-045 Skill Registry | 已 Done | REQ-060 迁移菜单归属，不改 API |

**禁止**：REQ-060 不实现 Agent Loop、Runtime、Agent Builder、Workflow 管理功能，只为已交付页面和明确后续入口预留位置（hidden + featureFlag）。

## 7. Acceptance（细化 spec 8 条）

- AC-1：侧边栏不存在两个 Skill 入口；"技能编排"占位下线；未交付功能默认 `hiddenInNav`。
- AC-2：MCP/Skill 位于能力中心 `/capabilities/*`；数据要素模板位于知识与数据 `/data/templates`；系统管理只承载平台治理。
- AC-3：普通用户看不到应用管理、能力中心、系统管理入口；深链 -> 前端 403 页 + API 独立 401/403。**例外：模板 API 暂无后端 RBAC（TD-082），AC-3 对模板不强制三层一致，前端两层守 + API 暂敞口**。
- AC-4：Sidebar / breadcrumb / route guard 使用同一 `nav.ts` + route meta；新增菜单不再修改三份数组。
- AC-5：首页快捷入口引用命名路由 + 按同一 permission 过滤；不再出现失效/占位入口。
- AC-6：刷新任一深链展开正确菜单分组 + 高亮父级；详情路由不误高亮同前缀（route name 匹配）。
- AC-7：覆盖 7 角色（employee/teacher/student/leader/admin/data_admin/super_admin）最小导航矩阵测试。
- AC-8：移动端折叠菜单 + 键盘导航 + aria 状态 + 浅色/深色主题浏览器验收。
- AC-9（新增）：前端 roleMap 统一到后端 RoleEnum；DD 页面 roleLabel 正确显示 leader/admin/data_admin。
- AC-10（新增）：旧链接 `/skill-editor` `/admin/mcp-servers` `/admin/skills` `/admin/template` 重定向到新路径。

## 8. Non-goals

- 不实现 Agent Builder / Workflow / Runtime 管理功能（只预留 hidden 入口）。
- 不把前端隐藏当安全控制；后端 RBAC/ABAC 仍是最终裁决。
- 不同时重做所有业务页面视觉。
- 不实现后端 permission grants 下发（V1 用角色映射，后续切换不重写页面）。

## 9. Open Questions（已冻结）

> 2026-07-23 shaping 决策见 §3 Decisions；保留原问题供追溯。

- 前端 roleMap 与后端 RoleEnum 不一致如何统一？-> D-1 统一到后端 RoleEnum
- 能力中心对普通用户可见性？-> D-2 完全隐藏
- 旧链接兼容策略？-> D-3 重定向
- "AI 问答"何时改名？-> D-4 绑定 REQ-042

## 10. Dependencies

- REQ-059（🟢 Done）平台内核 + RBAC 边界。
- BUG-017（🟢 Done）RoleEnum + HIGH_PRIVILEGE_ROLES。
- REQ-044/045（🟢 Done）MCP/Skill Registry API（菜单归属迁移，不改 API）。
- REQ-042/043/047（未实施）—— REQ-060 只预留位置，不阻塞。
