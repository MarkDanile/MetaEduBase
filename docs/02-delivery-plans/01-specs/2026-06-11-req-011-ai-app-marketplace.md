# REQ-011 AI 应用广场与应用注册中心 — Spec

> Spec 入口：REQ-011（需求塑形 2026-06-11）。本文件是验收口径与边界的事实源；实施拆分见 [`2026-06-11-req-011-ai-app-marketplace-plan.md`](../02-plans/2026-06-11-req-011-ai-app-marketplace-plan.md)。
> 需求正文：[`docs/01-product-planning/05-requirements/REQ-011-ai-application-marketplace-and-registry.md`](../../01-product-planning/05-requirements/REQ-011-ai-application-marketplace-and-registry.md)
> 2026-07-23 范围说明：APP-001“首个 Pilot”仅指教育应用子组合在广场中的首个接入样例；全项目应用开发当前以园区为优先，近期主线为 APP-005/009/012/030/016。顶级菜单决策由 REQ-060 重新治理，本 spec 继续约束应用注册与广场能力，不覆盖当前导航事实源。

## 目标

建立 AI 应用广场与应用注册中心，为 APP-001 到 APP-004 提供统一的注册、展示、治理和独立访问入口：

- 新增 `AI 应用` 顶级菜单（广场入口 + 管理子菜单）。
- `ai_applications` 表 + 强类型 `AppConfig` Pydantic 配置模型。
- 租户级 + 角色级两级可见性。
- 广场展示 + 应用详情 + 管理 CRUD + 独立路由。
- 预留 share_token / api_token 字段。

## 决策记录（2026-06-11 塑形澄清）

> 用户在 REQ-011 塑形阶段确认 5 项决策；后续 spec / plan 不得偏离。

- **Q1 — APP-001 作为教育应用广场首个 Pilot**：APP-001（课程能力图谱）以 Published/Pilot 状态进入广场；该决定不代表全项目应用交付优先级。
- **Q2 — 可见性粒度**：支持租户级隔离，`visibility` 字段由 `tenant_id` 协同控制。
- **Q3 — 应用管理入口（历史）**：原方案新增 `AI 应用` 顶级独立菜单；当前导航层级以 REQ-060 的统一 permission/nav 事实源为准。
- **Q4 — config_schema 方案**：强类型 Pydantic 配置模型，不只存原始 JSON。
- **Q5 — 对外发布预留**：同步预留 share_token（分享链接）和 api_token（API 暴露）字段。

## 数据模型

### ai_applications 表

```sql
CREATE TABLE ai_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) NOT NULL UNIQUE,        -- APP-001 / course-capability-map
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    icon VARCHAR(500),                        -- URL 或 emoji
    status VARCHAR(20) NOT NULL DEFAULT 'Draft' -- Draft | Published | Disabled | Archived
    visibility VARCHAR(20) NOT NULL DEFAULT 'internal', -- internal | role_limited | public
    entry_type VARCHAR(20) NOT NULL DEFAULT 'internal_route', -- internal_route | external_url | embedded | api
    route_path VARCHAR(200),                  -- 独立访问路由，如 /apps/course-capability-map
    external_url VARCHAR(500),
    config_schema JSONB,                      -- Pydantic AppConfig 序列化的 JSON
    required_capabilities JSONB,              -- 底座依赖列表
    owner VARCHAR(200),
    version VARCHAR(20) DEFAULT '1.0.0',
    sort_order INT DEFAULT 0,
    tenant_id UUID,                           -- 租户隔离（visibility=租户级时生效）
    share_token VARCHAR(100) UNIQUE,          -- 分享链接 token
    api_token VARCHAR(100) UNIQUE,           -- API 暴露 token
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_ai_applications_status ON ai_applications(status);
CREATE INDEX ix_ai_applications_tenant_id ON ai_applications(tenant_id);
```

### AppConfig 强类型配置模型

```python
class AppConfig(BaseModel):
    """应用配置基类，各应用可扩展"""
    theme: Optional[str] = None
    language: Optional[str] = "zh-CN"
    capabilities: list[str] = []


class CourseCapabilityMapConfig(AppConfig):
    """APP-001 课程能力图谱配置"""
    course_id: Optional[str] = None
    auto_refresh: bool = False
    max_nodes: int = 500


class PreviewGuideConfig(AppConfig):
    """APP-002 智能预习导学配置"""
    prerequisite_depth: int = 2
    generate_quiz: bool = True
```

### AppStatus 枚举

| 值 | 含义 |
|----|------|
| Draft | 已登记但未对普通用户可见 |
| Published | 已发布，可从广场进入 |
| Disabled | 临时禁用，保留配置和历史数据 |
| Archived | 归档，不在默认广场展示 |

### AppVisibility 枚举

| 值 | 含义 |
|----|------|
| internal | 仅内部用户可见 |
| role_limited | 指定角色可见 |
| public | 公开（生成 share_token） |

### AppEntryType 枚举

| 值 | 含义 |
|----|------|
| internal_route | 进入本系统内部路由 |
| external_url | 跳转外部系统 |
| embedded | iframe / web component 嵌入 |
| api | 作为 API 能力暴露（生成 api_token） |

## API 端点

### 应用注册中心

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/ai-apps | 列表（支持 category/status/visibility 过滤） |
| GET | /api/v1/ai-apps/:id | 详情 |
| POST | /api/v1/ai-apps | 创建应用 |
| PUT | /api/v1/ai-apps/:id | 更新应用元信息 |
| DELETE | /api/v1/ai-apps/:id | 归档（软删除） |
| POST | /api/v1/ai-apps/:id/publish | 发布（Draft → Published） |
| POST | /api/v1/ai-apps/:id/disable | 禁用（Published → Disabled） |
| POST | /api/v1/ai-apps/:id/enable | 启用（Disabled → Published） |
| POST | /api/v1/ai-apps/:id/archive | 归档（任意状态 → Archived） |
| POST | /api/v1/ai-apps/:id/regenerate-share-token | 重新生成 share_token |
| POST | /api/v1/ai-apps/:id/regenerate-api-token | 重新生成 api_token |

### 种子数据

APP-001 到 APP-004 作为内置应用插入：

| code | name | status | entry_type | route_path |
|------|------|--------|------------|------------|
| APP-001 | 课程能力图谱智能体工具 | Published | internal_route | /apps/course-capability-map |
| APP-002 | 智能预习规划与导学智能体 | Draft | internal_route | /apps/preview-guide |
| APP-003 | 个性化学习资源推荐智能体 | Draft | internal_route | /apps/resource-recommendation |
| APP-004 | 智能复习规划与巩固智能体 | Draft | internal_route | /apps/review-planner |

## 范围

### 包含 — Backend

- **模型层**：
  - `AiApplication` SQLAlchemy model，对应 `ai_applications` 表。
  - `AppConfig` / `CourseCapabilityMapConfig` / `PreviewGuideConfig` 等 Pydantic model，config_schema JSONB 存取时做序列化/反序列化校验。
  - `AiAppStatus` / `AiAppVisibility` / `AiAppEntryType` 枚举。
- **Service 层**：
  - `AiAppService` 提供 CRUD + 状态流转 + token 生成逻辑。
  - 状态流转校验：Draft → Published → Disabled → Archived 的合法路径。
  - share_token / api_token 生成：使用 `secrets.token_urlsafe(32)`。
  - 配置校验：创建/更新时 config_schema JSON 反序列化为对应 AppConfig 子类，失败返回 422。
- **API 层**：
  - `/api/v1/ai-apps` REST 端点（FastAPI）。
  - 请求/响应 DTO 使用 Pydantic model。
  - 租户隔离：列表查询自动按 `tenant_id` 过滤（从 current user context 获取）。
- **迁移**：
  - 新建 Alembic 迁移 `009_ai_applications` 创建表。
- **种子数据**：
  - APP-001 到 APP-004 写入 seed 逻辑（init-dev-db 时注入，或 migration 后手动调用）。

### 包含 — Frontend

- **路由**：
  - `/ai-apps` — 应用广场列表页。
  - `/ai-apps/:code` — 应用详情页（只看已 Published）。
  - `/ai-apps/admin` — 应用管理列表（管理员）。
  - `/ai-apps/admin/:id` — 应用编辑页。
  - `/apps/course-capability-map` — APP-001 独立路由（框架页，暂无具体业务功能）。
  - `/apps/preview-guide` — APP-002 独立路由（框架页）。
  - `/apps/resource-recommendation` — APP-003 独立路由（框架页）。
  - `/apps/review-planner` — APP-004 独立路由（框架页）。
- **菜单**：
  - 新增 `AI 应用` 顶级菜单。
  - 子菜单：`应用广场` → `/ai-apps`，`应用管理` → `/ai-apps/admin`。
- **应用广场页（/ai-apps）**：
  - 应用卡片列表（展示 Published 应用）。
  - 分类筛选（按 category）。
  - 搜索（按 name / description）。
  - Draft / Disabled 应用不在广场展示（管理员可在管理页看到）。
  - 应用卡片：图标 + 名称 + 描述 + 状态标签 + 进入按钮。
- **应用详情页（/ai-apps/:code）**：
  - 应用元信息展示。
  - 状态指示。
  - "立即使用"按钮跳转独立路由。
  - "规划中" / "暂未开放"状态提示。
- **应用管理页（/ai-apps/admin）**：
  - 管理员列表所有应用（含 Draft / Disabled / Archived）。
  - 状态筛选。
  - 新建应用按钮。
  - 快速操作：发布 / 禁用 / 编辑 / 归档。
- **应用编辑页（/ai-apps/admin/:id）**：
  - 表单：code / name / description / category / icon / status / visibility / entry_type / route_path / external_url / config_schema（JSON 编辑器）/ required_capabilities。
  - 状态变更时弹出确认提示。
  - share_token / api_token 显示 + 重新生成按钮。
- **独立应用框架页（/apps/*）**：
  - 简单框架页，展示应用名称、描述和"功能开发中"状态。
  - 不在本 spec 实现具体业务功能。

### 包含 — 配置模型扩展

- 各应用可在 `app/domain/ai_app/configs/` 下扩展自己的 `AppConfig` 子类。
- `AiAppService` 根据 `code` 查找对应配置类做校验。
- 第一版只实现 `AppConfig` 基类 + `CourseCapabilityMapConfig` + `PreviewGuideConfig`，其他应用留空配置。

## 非目标

- 第一版不做 Dify 式可视化 workflow 编排。
- 第一版不做第三方应用上传、审核、评分、收藏或付费市场。
- 第一版不实现外部公开发布的完整流程（只预留 share_token / api_token 字段）。
- 四个应用的独立业务功能（APP-001 图谱构建、APP-002 预习规划等）不在本 spec 实现。
- 不实现多语言国际化。

## 验收标准（AC）

| ID | 描述 | 验证方式 |
|----|------|----------|
| AC-1 | `ai_applications` 表存在，11 个核心字段 + tenant_id + share_token + api_token | `alembic upgrade head` 成功；`psql` 查询表结构 |
| AC-2 | APP-001 到 APP-004 种子数据存在，APP-001 status=Published | seed 后 `psql` 查询 |
| AC-3 | `GET /api/v1/ai-apps` 返回 Published 应用列表；`GET /api/v1/ai-apps?status=Draft` 只返回 Draft | pytest 验证 |
| AC-4 | `POST /api/v1/ai-apps` 创建应用，config_schema JSON 合法时成功，不合法时返回 422 | pytest 验证 |
| AC-5 | 状态流转：Draft→Published→Disabled→Archived 合法；Draft→Archived 不允许 | pytest 验证流转校验 |
| AC-6 | `POST /api/v1/ai-apps/:id/regenerate-share-token` 生成新 token | pytest 验证 |
| AC-7 | `POST /api/v1/ai-apps/:id/regenerate-api-token` 生成新 token | pytest 验证 |
| AC-8 | 前端 `/ai-apps` 展示应用卡片，Draft 不在广场显示 | 手动验证 |
| AC-9 | 前端 `/ai-apps/admin` 展示所有状态应用，可进行新建/编辑/状态变更 | 手动验证 |
| AC-10 | 前端 `/apps/course-capability-map` 等独立路由可访问（框架页） | 手动验证 |
| AC-11 | 菜单显示 `AI 应用 → 应用广场 / 应用管理` | 手动验证 |

## 行为变化声明

- 无现有功能被修改；本 spec 为纯新增。
- 既有 `/apps/*` 路由如果已被占用，需要协调路由冲突（当前为预留路由）。
