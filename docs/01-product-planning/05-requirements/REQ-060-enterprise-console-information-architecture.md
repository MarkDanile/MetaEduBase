# REQ-060: 企业 Agent 控制台信息架构与权限化导航

> Status: ⚫ Candidate
> Priority: P1
> Milestone: P3 / Enterprise Agent Platform
> Area: Web / Information Architecture / Navigation / RBAC
> Created: 2026-07-23
> Source: 用户指出 MCP / Skill 管理入口与一级“技能编排”菜单发生语义和层级漂移
> Parent: REQ-059
> Related: REQ-011 / REQ-042 / REQ-044 / REQ-045

## Problem

当前侧边栏、Router 和首页卡片分别硬编码导航。一级“技能编排”指向未实现占位页，系统管理又包含真实的“Skill 服务”；MCP/Skill 作为 Agent 能力资产被放在系统配置层；系统管理和应用管理对所有登录用户显示，路由仅检查 Token，没有菜单级 permission 事实源。继续增加 Agent、Runtime 和记忆页面会进一步放大漂移。

## Current Evidence

- `LayoutView.vue` 独立维护 `navItems/adminItems/aiAppItems`。
- `HomeView.vue` 再维护一套入口卡片，并暴露未实现的“技能编排”。
- `router.ts` 的 MCP/Skill/Application route 只有 `requiresAuth`，全局 guard 只判断 Token。
- MCP/Skill 页面内部再按本地角色隐藏按钮，导航可见性、路由可达性和 API 授权语义不一致。

## Target Information Architecture

| 一级区域 | 二级入口 | 主要受众 |
|----------|----------|----------|
| 总览 | 平台概览 | 已登录用户 |
| AI 工作 | AI 问答；REQ-041/042 完成后升级为 Agent 工作台；我的任务（后续） | 业务用户 |
| 智能体应用 | 应用中心；应用管理 | 用户；管理员/构建者 |
| 知识与数据 | 知识库、资源库、数据库、数据要素模板 | 按数据权限 |
| 能力中心 | Skill 库、MCP 工具；后续 Agent 定义、Workflow、Runtime 接入 | Agent Builder / tenant admin |
| 系统管理 | 用户与角色、租户、模型与凭证、安全策略、审计 | super_admin / 授权管理员 |

“技能编排”占位一级入口下线。未来可视化编排作为 Skill 详情中的创建/编辑能力，不再制造第二个 Skill 产品概念。MCP/Skill 从系统管理迁入能力中心；普通用户通过 Agent 使用授权能力，不需要进入 Registry 管理页。

## Navigation Source

- 建立类型化导航/路由元数据事实源，至少包含 route name、label、section、order、permission、feature flag 和 hidden 状态。
- Sidebar、路由守卫和面包屑从同一事实源派生；首页快捷入口只引用 route name，不复制 path 和权限。
- V1 可由已验证身份角色映射 permission；API 始终是授权事实源。后续切换后端下发 permission grants 时不重写页面结构。
- 详情页、编辑页和占位页使用 `hiddenInNav`，不因为存在 Route 自动出现在菜单。

## Acceptance

- AC-1：侧边栏不存在两个含义不清的 Skill 入口；未交付功能默认不显示。
- AC-2：MCP、Skill 位于能力中心，数据要素模板位于知识与数据，系统管理只承载平台治理。
- AC-3：普通用户看不到应用管理、能力中心和系统管理入口；直接导航时路由守卫给出 403/无权限页，API 仍独立拒绝越权。
- AC-4：Sidebar、breadcrumb 和 route guard 使用同一 permission/nav 元数据；新增菜单不再要求修改三份数组。
- AC-5：首页快捷入口引用命名路由并按同一权限过滤，不再出现失效或占位入口。
- AC-6：刷新任一可访问深链时展开正确菜单分组并高亮父级；详情路由不误高亮同前缀其他入口。
- AC-7：覆盖 employee/teacher/student/leader/admin/data_admin/super_admin 的最小导航矩阵测试。
- AC-8：移动端折叠菜单、键盘导航、aria 状态和浅色/深色主题通过浏览器验收。

## Non-goals

- 不在本需求实现 Agent Builder、Workflow 或 Runtime 管理功能，只为已交付页面和明确后续入口预留位置。
- 不把前端隐藏当安全控制；后端 RBAC/ABAC 仍是最终裁决。
- 不同时重做所有业务页面视觉。

## Dependencies / Next Step

- 可在 REQ-059 架构冻结后独立补 spec/plan 并实施，不依赖 Pi/ACP。
- “AI 问答”改名“Agent 工作台”的时点与 REQ-041/042 验收绑定，避免菜单名称超前于真实能力。
