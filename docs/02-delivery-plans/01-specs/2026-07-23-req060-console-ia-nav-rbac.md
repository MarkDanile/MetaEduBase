# Spec: REQ-060 企业 Agent 控制台信息架构与权限化导航

> Requirement: `docs/01-product-planning/05-requirements/REQ-060-enterprise-console-information-architecture.md`
> Status: 🔵 Ready（shaping 冻结）
> Priority: P1
> Area: Web / Information Architecture / Navigation / RBAC
> Shaped: 2026-07-23
> Revised: 2026-07-25（R1 复审修订）
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
| D-5 | path prefix 高亮语义混杂 | `startsWith` 会让 `/ai-apps/admin` 同时高亮应用广场和应用管理；但详情页又需要高亮父入口，不能简单改成 exact name |
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
| `/skill-editor` | `/capabilities/skills` | redirect，1 版本周期后移除；目标权限守卫重新裁决 |
| `/admin/mcp-servers` | `/capabilities/mcp` | redirect |
| `/admin/skills` | `/capabilities/skills` | redirect |
| `/admin/template` | `/data/templates`（知识与数据区域） | redirect |
| `/admin/template/:id` | `/data/templates/:id` | redirect（详情深链兼容） |
| `/admin` | `/system`（V1 占位重定向，见 D-6） | redirect |

### D-4 "AI 问答"保持名称，绑定 REQ-042 改名

REQ-060 保持"AI 问答" + route `/ai-chat`。REQ-042 Agent Workspace 验收通过后，单独 PR 改名"Agent 工作台" + route meta flag。避免菜单名称超前于真实能力（当前无 Agent Loop）。

### D-5 permission 派生：V1 本地角色只负责展示，API 是最终裁决

V1 前端 permission 由 `authStore.userRole` 映射。该值当前来自登录响应后写入 `localStorage`，刷新时直接恢复，不能称为持续验证的授权事实，也不能替代后端裁决。它只控制导航和展示体验：未知/缺失角色、未知 permission、未知 feature flag 一律 fail-closed；无 permission 的已认证基础路由才可放行。API 始终独立完成 RBAC/ABAC，后续切换后端下发 permission grants 时只替换 resolver，不改变 Route Record 和导航投影结构。

**前置依赖（已满足）**：TD-087（模板管理 API 后端 RBAC）已由 PR #495 完成，模板 API 已具备后端 HIGH_PRIVILEGE_ROLES 守卫。REQ-060 Slice 1 已实施，Slice 2 模板目标路由、深链守卫、旧链接迁移和 AC-3 验收可按原子迁移契约实施。（R1 形成时 TD-087 尚未完成，此段为历史状态记录。）

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
- `/apps/*` shell 可通过应用广场进入，但全部 `hiddenInNav=true`，不得由 Route 投影成侧边栏或首页一级入口
- `/apps/*` 默认 `activeNav=AiAppsMarketplace`，其详情页刷新时保持应用广场父入口高亮
- AC-3 "三层一致"对 `/apps/*` 不强制（shell 可见 + API 守卫，接受 shell 泄露）
- DD 详情 `/apps/enterprise-360-dd/tasks/:id` 等深链：前端不额外守卫，依赖后端 403

### D-8 Route Record 所有权与纯投影

- `router.ts` 的 Route Record 是 `path/name/meta` 唯一事实源；导航不得再维护第二份 path、permission 或 hidden 配置。
- `nav.ts` 只导出类型、section descriptor、permission/feature resolver 和接收 `router.getRoutes()` 结果的纯投影函数；不得导入 Router 实例，避免循环依赖。
- 首页展示文案可以按 route name 维护独立 presentation 配置，但不得复制 path、permission、feature flag 或 active 规则。
- Vue Router `RouteMeta` augmentation 允许 guest、redirect、layout parent 缺少导航字段；所有可认证访问的业务 leaf route 必须显式声明 title、section、permission/基础访问语义、hidden 和 active 映射。

### D-9 受保护路由原子迁移

新目标路由、permission meta、`/403`、深链守卫和旧链接重定向必须在同一 Slice/PR 交付。禁止先合并“菜单隐藏/路由迁移”、后补守卫的中间状态。TD-087 已关闭（PR #495），Slice 2 可按原子迁移契约实施 `/data/templates*`。

### D-10 移动端属于实施范围

当前 `mobileMenuOpen` 没有打开入口，窄屏只会把固定侧栏压缩到 60px。REQ-060 必须实现移动端顶部菜单按钮和 off-canvas navigation，覆盖 backdrop/Escape/route-change 关闭、焦点返回、body scroll、`aria-controls`/`aria-expanded`，并建立可重复的 Playwright 桌面/移动验收，不得只写“人工验证”。

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

### 5.1 Route meta schema

每个 route record 的 `meta` 扩展为类型化：

```ts
interface RouteMeta {
  title?: string;             // 业务 leaf route 必填；guest/layout/redirect 可省略
  section?: NavSection;       // 业务 leaf route 必填
  order?: number;             // 区域内排序
  permission?: PermissionKey; // 所需 permission（缺省=已登录即可）
  hiddenInNav?: boolean;      // 详情/编辑/占位页不在菜单显示
  featureFlag?: FeatureFlagKey; // 未交付功能 flag；未知或未启用时 fail-closed
  activeNav?: RouteRecordName;  // 详情/编辑/shell 对应的父导航 route name
  icon?: Component;           // 菜单图标
}
```

`hiddenInNav` 对 guest、layout parent、redirect、详情、编辑、独立应用 shell 和占位页默认视为 `true`；只有显式可导航的业务 leaf route 才进入投影。`activeNav` 缺省为 route 自身 name，隐藏 route 必须显式指向可见父入口或声明不参与主导航高亮。

### 5.2 Route Record 单一源与 nav 纯投影

新建 `packages/web/src/app/nav.ts`，但它不是第二份配置表：只包含类型、section descriptor、fail-closed resolver 和 `projectNavigation(routes, accessContext)` 等纯函数。调用方把 `router.getRoutes()` 传入，Sidebar / breadcrumb / route guard / 首页快捷入口统一读取 Route Record meta，不再维护三份 path/permission 数组。`nav.ts` 不得导入 `router.ts` 或 Router 实例。

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

### 5.4 Route -> permission / visibility / active 显式映射表

| route | name | permission | hidden | activeNav | 备注 |
|-------|------|------------|:-:|-----------|------|
| `/` | home | `nav.overview` | - | `home` | 总览 |
| `/ai-chat` | ai-chat | `nav.ai_work` | - | `ai-chat` | AI 问答 |
| `/ai-apps` | AiAppsMarketplace | `nav.apps.marketplace` | - | `AiAppsMarketplace` | 应用广场 |
| `/ai-apps/admin` | AiAppsAdmin | `nav.apps.admin` | - | `AiAppsAdmin` | 应用管理 |
| `/ai-apps/admin/:id` | AiAppEdit | `nav.apps.admin` | ✅ | `AiAppsAdmin` | 编辑详情 |
| `/ai-apps/:code` | AiAppDetail | `nav.apps.marketplace` | ✅ | `AiAppsMarketplace` | 应用详情 |
| `/knowledge` | knowledge | `nav.knowledge` | - | `knowledge` | 知识库 |
| `/resource` | resource | `nav.knowledge` | - | `resource` | 资源库 |
| `/resource/:id` | file-detail | `nav.knowledge` | ✅ | `resource` | 文件详情 |
| `/database` | database | `nav.data` | - | `database` | 数据库 |
| `/database/:catalogCode` | catalog-detail | `nav.data` | ✅ | `database` | 目录详情 |
| `/data/templates` | templates-list | `nav.data.templates` | - | `templates-list` | TD-087 已完成，Slice 2 迁移 |
| `/data/templates/:id` | template-detail | `nav.data.templates` | ✅ | `templates-list` | 模板详情 |
| `/capabilities/skills` | capabilities-skills | `nav.capabilities` | - | `capabilities-skills` | Skill 库 |
| `/capabilities/mcp` | capabilities-mcp | `nav.capabilities` | - | `capabilities-mcp` | MCP 工具 |
| `/system` | system | `nav.system` | ✅ | - | V1 占位，不展示入口 |
| `/apps/*` | App* | `nav.apps.marketplace` | ✅ | `AiAppsMarketplace` | 独立应用 shell/详情，API 独立裁决 |
| `/skill-editor` | - | - | ✅ | - | redirect `/capabilities/skills` |
| `/admin` | - | - | ✅ | - | redirect `/system` |
| `/admin/*` 旧路径 | - | - | ✅ | - | redirect 新路径 |

### 5.5 深链守卫与 fail-closed

- 前端 `router.beforeEach` 增强：检查 `to.meta.permission` 和 feature flag；未知角色、未知 permission、未知/关闭 flag 均进入 `/403`，不得默认放行。
- 后端 API 独立拒绝越权（**既有 RBAC**，不依赖前端隐藏）。
- AC-3：隐藏菜单 + 深链 403 + API 401/403 三层一致。

**模板迁移门禁（TD-087 已关闭）**：模板 API（`/api/v1/templates/*`）后端 RBAC 已由 TD-087（PR #495）补齐。模板目标路由、HIGH_PRIVILEGE 导航/深链守卫和旧链接迁移在 Slice 2 同批交付，并纳入 AC-3 三层一致验收。

### 5.6 activeNav 精确匹配

`isActive` 比较当前 route 的 `activeNav ?? name` 与可见 NavItem 的 route name，不使用 path prefix。这样 `/ai-apps/admin` 不会同时高亮应用广场，而 `file-detail`、`catalog-detail`、`AiAppEdit` 和独立应用详情仍能高亮显式父入口。面包屑和分组展开使用同一 section/activeNav 投影。

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
- AC-3：普通用户看不到应用管理、能力中心、系统管理入口；深链 -> 前端 403 页 + API 独立 401/403。模板路由在 Slice 2 迁移，并必须同批满足三层一致。
- AC-4：Route Record 是 path/name/meta 唯一事实源；Sidebar / breadcrumb / route guard 通过 `nav.ts` 纯投影消费，不再维护三份数组或产生 Router 循环依赖。
- AC-5：首页快捷入口引用命名路由 + 按同一 permission 过滤；不再出现失效/占位入口。
- AC-6：刷新任一深链按 `activeNav` 展开正确菜单分组并高亮唯一父级；独立应用 shell 不投影成一级菜单。
- AC-7：覆盖 7 角色及 unknown/null role 的导航、深链与 fail-closed 矩阵测试。
- AC-8：实现移动端 off-canvas 菜单、键盘/焦点/aria 状态，并通过 Playwright 桌面/移动、浅色/深色主题验收。
- AC-9（新增）：前端 roleMap 统一到后端 RoleEnum；DD 页面 roleLabel 正确显示 leader/admin/data_admin。
- AC-10（新增）：旧链接 `/skill-editor` `/admin/mcp-servers` `/admin/skills` `/admin/template` 重定向到新路径。

## 8. Non-goals

- 不实现 Agent Builder / Workflow / Runtime 管理功能（只预留 hidden 入口）。
- 不把前端隐藏当安全控制；后端 RBAC/ABAC 仍是最终裁决。
- 不同时重做所有业务页面视觉。
- 不实现后端 permission grants 下发（V1 用角色映射，后续切换不重写页面）。
- 不在 REQ-060 内统一 MCP/Skill/Database 页面按钮的业务 action permission；这些按钮仍由各业务 API 最终裁决，后续 action grant 需独立契约，不能复用 `nav.*` 冒充业务授权。

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
- TD-087（🟢 完成，PR #495）模板管理 API 后端 RBAC；`/data/templates*` 迁移和 REQ-060 AC-3 收口前置已解除。
- REQ-042/043/047（未实施）—— REQ-060 只预留位置，不阻塞。

## 11. R1 Review Corrections（2026-07-25）

源码复审发现原 shaping 的“P0/P1 清零”声明不成立，修订前结果为 `P0/P1/P2 = 0/4/2`：

- 原 `isActive` 诊断把 `/resource/:id` 高亮父入口误判成问题，改成 exact name 又会使详情页无高亮；现以 `activeNav` 明确父映射。
- `/apps/*` 原表未隐藏，会被 Route 投影为一级菜单；现统一 `hiddenInNav=true`。
- TD-087 已由 PR #495 完成（🟢），模板路由迁移前置已解除。（R1 形成时 TD-087 尚未进入技术债总账，此段为历史状态记录。）
- 原 Slice 3/4 分开造成菜单迁移后、守卫落地前的中间态；现要求原子交付。
- 当前移动端状态没有 opener，不能把 AC-8 写成纯验证；现纳入真实实现和 Playwright 回归。
- AI Applications、Iteration、Milestone 状态滞后；本次同步修正并把评审落入 score log。
