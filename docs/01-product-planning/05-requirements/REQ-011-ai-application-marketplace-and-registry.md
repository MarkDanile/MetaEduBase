# REQ-011: AI 应用广场与应用注册中心

Status: 🔵 Ready
Priority: P1
Milestone: P2 / P3
Owner: TBD
Parent: APP-001 / APP-002 / APP-003 / APP-004

> 2026-07-23 优先级说明：本需求中的“APP-001 首个 Pilot”仅指教育应用子组合在 AI 应用广场中的首个接入样例，不代表全项目应用开发顺序。当前园区近期主线为 APP-005/009/012/030/016；菜单层级由 REQ-060 重新治理。

## 背景

`docs/01-product-planning/06-ai-applications/` 已记录学校真实场景下的 AI 应用组合：课程能力图谱、智能预习导学、个性化资源推荐、智能复习巩固。随着这些应用进入开发，系统需要一个统一的产品容器承载它们。

该容器不是应用本体，而是应用的注册、发现、治理和发布入口。每个 AI 应用仍应拥有自己的独立页面、交互、配置和验收标准；广场只负责展示、管理和跳转。

## 目标

- 新增“AI 应用广场”产品入口，用于展示和进入已注册 AI 应用。
- 支持应用注册、编辑、启用、禁用、归档等基础治理能力。
- 允许每个应用既能从广场进入，也能通过独立路由自主访问。
- 为未来外部发布、嵌入、API 暴露和多租户可见性预留字段与状态流。
- 先承载 APP-001 到 APP-004，不把广场做成开放插件市场。

## 非目标

- 不在第一版实现 Dify 式可视化 workflow 编排。
- 不在第一版实现第三方应用上传、审核、评分、收藏或付费市场。
- 不在第一版实现完整外部公开发布和匿名访问。
- 不强行统一四个应用的业务页面交互。

## 产品原则

```text
统一注册中心 + 统一广场展示 + 独立应用实现
```

### 广场层

负责应用元信息和入口治理：

- 应用展示、分类、搜索和详情。
- 注册、编辑、启用、禁用、归档。
- 发布状态、可见性和入口类型。
- 与具体应用路由、外部链接或嵌入入口建立映射。

### 应用层

负责具体业务体验：

- 独立路由。
- 独立页面交互。
- 独立业务数据。
- 独立配置。
- 独立验收标准。

## 初始应用

| ID | 应用 | 第一阶段状态建议 | 说明 |
|----|------|------------------|------|
| APP-001 | 课程能力图谱智能体工具 | Published / Pilot | 教育应用子组合中的首个广场接入样例，是 APP-002 到 APP-004 的能力基础；进入开发时间服从园区优先路线。 |
| APP-002 | 智能预习规划与导学智能体 | Draft / Planned | 等 APP-001 最小闭环明确后进入实现。 |
| APP-003 | 个性化学习资源推荐智能体 | Draft / Planned | 依赖能力图谱、资源标签、学生画像。 |
| APP-004 | 智能复习规划与巩固智能体 | Draft / Planned | 依赖学习记录、知识点掌握状态、微测验。 |

## 状态流

| 状态 | 含义 |
|------|------|
| Draft | 已登记但未对普通用户可见 |
| Published | 已发布，可从广场进入 |
| Disabled | 临时禁用，保留配置和历史数据 |
| Archived | 归档，不在默认广场展示 |

可见性独立于状态：

| 可见性 | 含义 |
|--------|------|
| internal | 仅内部用户可见 |
| role_limited | 指定角色或组织可见 |
| public | 可对外发布或分享 |

入口类型独立于状态：

| 入口类型 | 含义 |
|----------|------|
| internal_route | 进入本系统内部路由 |
| external_url | 跳转外部系统或独立部署地址 |
| embedded | 以 iframe / web component 等方式嵌入 |
| api | 作为 API 能力暴露 |

## 建议数据模型

```text
ai_applications
- id
- code                        # 稳定编号，如 APP-001 / course-capability-map
- name
- description
- category
- icon
- status                      # Draft | Published | Disabled | Archived
- visibility                  # internal | role_limited | public
- entry_type                  # internal_route | external_url | embedded | api
- route_path                  # 应用独立访问路由
- external_url                # 外部跳转地址
- config_schema               # Pydantic 强类型配置模型（JSON 列存）
- required_capabilities       # 底座依赖声明
- owner
- version
- sort_order
- tenant_id                   # 租户隔离（visibility=租户级时生效）
- share_token                 # 分享链接 token（public 应用生成）
- api_token                   # API 暴露 token（entry_type=api 时生成）
- created_at
- updated_at
```

字段说明：

- `code` 使用稳定编号或 slug，例如 `APP-001` / `course-capability-map`。
- `route_path` 支持应用独立访问。
- `entry_type` 预留内部路由、外部链接、嵌入和 API 能力。
- `visibility` 支持角色级和租户级两级可见性，由 `tenant_id` 协同控制。
- `config_schema` 强类型 Pydantic model，不只存原始 JSON。
- `required_capabilities` 声明底座依赖，例如 RAG、KG、学生画像、资源推荐、微测验。
- `share_token` / `api_token` 支持外部发布时的分享链接和 API token 暴露。

## 页面规划

菜单新增：`AI 应用`（顶级独立菜单，其下包含广场入口和管理入口）

> **决策：** Q3 确认采用独立菜单方案。应用广场（用户入口）和应用管理（管理员入口）作为 `AI 应用` 菜单的两个子菜单。

### 应用广场

面向普通使用者：

- 应用卡片列表。
- 分类筛选。
- 搜索。
- 应用详情。
- 进入使用。
- 未启用应用展示“规划中”或“暂未开放”。

### 应用管理

面向管理员：

- 注册应用。
- 编辑元信息。
- 设置状态和可见性。
- 配置入口类型和路由。
- 启用、禁用、归档。

## 路由建议

```text
/ai-apps                          # 广场（用户视角）
/ai-apps/:code                   # 应用详情
/ai-apps/admin                   # 应用管理列表（管理员）
/ai-apps/admin/:id               # 应用编辑

/apps/course-capability-map      # APP-001 独立路由
/apps/preview-guide              # APP-002 独立路由
/apps/resource-recommendation    # APP-003 独立路由
/apps/review-planner             # APP-004 独立路由
```

`/ai-apps/*` 是广场与管理入口；`/apps/*` 是独立应用入口。应用也可以从广场进入这些独立路由。

## 切片规划

### REQ-011-1: 应用注册中心数据模型与 API

目标：建立 `ai_applications` 模型、状态流、基础 CRUD 和内置应用种子数据。

验收：

- APP-001 到 APP-004 可作为内置应用登记。
- 支持列表、详情、创建、更新、启用、禁用、归档。
- 状态、可见性、入口类型有明确校验。

### REQ-011-2: AI 应用广场列表与详情页

目标：新增菜单入口，展示应用卡片、分类、搜索和应用详情。

验收：

- 普通用户可进入 `AI 应用广场`。
- Published 应用可点击进入独立路由。
- Draft / Disabled 应用不会误导用户为可用状态。

### REQ-011-3: 应用管理后台

目标：提供管理员视角的注册、编辑、启用、禁用和归档能力。

验收：

- 管理员可维护应用元信息。
- 状态变化有确认提示。
- 删除优先采用归档，不物理删除历史应用。

### REQ-011-4: 独立应用壳与入口契约

目标：明确每个应用如何独立访问、如何接收配置、如何从广场跳转。

验收：

- 每个应用拥有独立路由。
- 广场入口和独立访问使用同一注册信息。
- APP-001 可作为教育应用子组合的首个真实接入应用；APP-002 到 APP-004 可先以规划中详情页承载。全项目应用顺序仍以当前 Roadmap/P3 Milestone 为准。

### REQ-011-5: 外部发布预留

目标：为未来对外发布预留 public visibility、external_url、embedded、api 等能力。

验收：

- 第一版不必开放外部访问，但字段和状态不阻塞后续扩展。
- 文档明确内部使用与外部发布的边界。

## 设计参考

- Nuwax：智能体广场、分类导航、应用卡片、开箱即用的 Agent OS 体验。
- Dify：应用开发、workflow、RAG、agent、观测与 API 暴露的一体化平台。
- Coze：面向最终用户的 bot / agent 广场、发布与分享体验。

本项目第一阶段只吸收“应用注册、展示、入口和发布状态”这些稳定模式，不复制完整平台复杂度。

## 决策记录（2026-06-11）

| # | 问题 | 决策 | 说明 |
|---|------|------|------|
| Q1 | APP-001 是否作为教育应用广场首个 Pilot | **A）是，Published/Pilot** | APP-001 作为教育子组合首个广场接入样例；2026-07-23 后不再代表全项目应用优先级 |
| Q2 | 可见性粒度 | **B）支持租户级隔离** | visibility 字段支持 tenant_id + role 两级可见性控制 |
| Q3 | 应用管理入口 | **C）独立菜单（历史）** | 原决策为新增 `AI 应用` 顶级菜单；当前导航层级由 REQ-060 统一收口，避免与 MCP/Skill/管理入口重复 |
| Q4 | config_schema 方案 | **B）强类型配置模型** | 引入 `AppConfig` 等 Pydantic model，不只存原始 JSON |
| Q5 | 对外发布预留 | **B + C）分享链接 + API token** | 同时预留分享链接和 API token 暴露能力 |

## 开放问题

## 后续链接

- AI Applications: `docs/01-product-planning/06-ai-applications/README.md`
- Backlog: `docs/01-product-planning/04-backlog.md#backlog`
- Spec: `docs/02-delivery-plans/01-specs/2026-06-11-req-011-ai-app-marketplace.md`
- Plan: `docs/02-delivery-plans/02-plans/2026-06-11-req-011-ai-app-marketplace-plan.md`
