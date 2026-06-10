# REQ-011: AI 应用广场与应用注册中心

Status: 🟣 Shaping
Priority: P1
Milestone: P2 / P3
Owner: TBD
Parent: APP-001 / APP-002 / APP-003 / APP-004

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
| APP-001 | 课程能力图谱智能体工具 | Published / Pilot | 优先真实接入，是 APP-002 到 APP-004 的能力基础。 |
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
- code
- name
- description
- category
- icon
- status
- visibility
- entry_type
- route_path
- external_url
- config_schema
- required_capabilities
- owner
- version
- sort_order
- created_at
- updated_at
```

字段说明：

- `code` 使用稳定编号或 slug，例如 `APP-001` / `course-capability-map`。
- `route_path` 支持应用独立访问。
- `entry_type` 预留内部路由、外部链接、嵌入和 API 能力。
- `visibility` 预留外部发布与角色可见性。
- `config_schema` 允许不同应用拥有不同配置。
- `required_capabilities` 声明底座依赖，例如 RAG、KG、学生画像、资源推荐、微测验。

## 页面规划

菜单新增：`AI 应用广场`

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
/ai-apps
/ai-apps/:code
/ai-apps/manage
/ai-apps/manage/:id

/apps/course-capability-map
/apps/preview-guide
/apps/resource-recommendation
/apps/review-planner
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
- APP-001 可作为首个真实接入应用；APP-002 到 APP-004 可先以规划中详情页承载。

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

## 开放问题

- APP-001 是否作为首个 Published / Pilot 应用进入广场。
- AI 应用是否需要租户级可见性，还是先只做角色级可见性。
- 应用管理是否放在系统管理子菜单，还是作为广场内的管理 Tab。
- `config_schema` 第一版是否只存 JSON，还是引入强类型配置模型。
- 对外发布是否需要独立域名、分享链接或 API token。

## 后续链接

- AI Applications: `docs/01-product-planning/06-ai-applications/README.md`
- Backlog: `docs/01-product-planning/04-backlog.md#backlog`
- Spec:
- Plan:
