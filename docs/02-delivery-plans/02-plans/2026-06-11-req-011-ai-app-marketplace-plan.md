# REQ-011 AI 应用广场与应用注册中心 — Plan

> Plan 入口：REQ-011 实施计划。验收口径见 [`2026-06-11-req-011-ai-app-marketplace.md`](../01-specs/2026-06-11-req-011-ai-app-marketplace.md)。

## 切片划分

本需求按 **前后端并行 + 数据模型先行** 的原则分为 4 个 Slice：

| Slice | 内容 | 依赖 | 预计顺序 |
|-------|------|------|----------|
| Slice 1 | 数据模型 + 迁移 + 种子数据 + Service + API CRUD | 无 | 1 |
| Slice 2 | 前端路由 + 菜单 + 广场列表页 | Slice 1（API 可用） | 2 |
| Slice 3 | 前端应用管理 + 编辑页 | Slice 2 | 3 |
| Slice 4 | 独立应用框架页 + share_token / api_token 端点 | Slice 1 | 4 |

---

## Slice 1：数据模型 + 迁移 + Service + API CRUD

### Task 1.1 — Alembic 迁移

- 新建 `009_ai_applications` 迁移。
- 创建 `ai_applications` 表（字段详见 spec 数据模型节）。
- 添加索引 `ix_ai_applications_status`、`ix_ai_applications_tenant_id`。
- 可上可下（downgrade 删表）。

**文件：**
- `packages/server-python/alembic/versions/009_ai_applications.py`

**验证：**
```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
psql -c "\d ai_applications"
```

### Task 1.2 — Pydantic 配置模型

- `AppConfig` 基类。
- `CourseCapabilityMapConfig`、`PreviewGuideConfig` 子类。
- 存放路径：`app/domain/ai_app/configs.py`。

**文件：**
- `app/domain/ai_app/__init__.py`（新建）
- `app/domain/ai_app/configs.py`（新建）

**验证：**
- pytest 验证 config 序列化/反序列化。

### Task 1.3 — SQLAlchemy Model

- `AiApplication` model，对应 `ai_applications` 表。
- 枚举字段使用 `enum.Enum` 或 `sqlalchemy.Enum`。
- 路径：`app/domain/ai_app/models.py`。

**文件：**
- `app/domain/ai_app/models.py`（新建）

**验证：**
- `python -c "from app.domain.ai_app.models import AiApplication; print('OK')"`

### Task 1.4 — DTO / Schema

- `AiAppCreate` / `AiAppUpdate` / `AiAppResponse` Pydantic model。
- 配置 JSON 的 validation 在 service 层做。
- 路径：`app/domain/ai_app/schemas.py`。

**文件：**
- `app/domain/ai_app/schemas.py`（新建）

**验证：**
- pytest 验证 DTO 序列化。

### Task 1.5 — Service 层

- `AiAppService`：CRUD + 状态流转 + token 生成。
- 状态流转校验（Draft → Published → Disabled → Archived）。
- `secrets.token_urlsafe(32)` 生成 share_token / api_token。
- 配置 JSON 反序列化校验（根据 code 找到对应 AppConfig 子类）。
- 路径：`app/domain/ai_app/service.py`。

**文件：**
- `app/domain/ai_app/service.py`（新建）

**验证：**
- pytest 覆盖状态流转合法/非法路径。

### Task 1.6 — API 路由

- `/api/v1/ai-apps` CRUD 端点（FastAPI Router）。
- 11 个端点详见 spec API 端点节。
- 路由文件：`app/api/v1/ai_apps.py`。
- 注册到 `app/api/v1/__init__.py` 和 `app/main.py`。

**文件：**
- `app/api/v1/ai_apps.py`（新建）
- `app/api/v1/__init__.py`（修改）
- `app/main.py`（修改，添加 router）

**验证：**
```bash
pytest tests/ -k ai_app -v
curl GET /api/v1/ai-apps  # 需服务运行
```

### Task 1.7 — 种子数据

- APP-001 到 APP-004 插入 seed 逻辑。
- 可通过 `make seed-dev` 或 migration 后手动调用注入。
- APP-001 status=Published，APP-002/003/004 status=Draft。

**文件：**
- `app/shared/infrastructure/seed.py`（修改，添加 `seed_ai_applications`）

**验证：**
```bash
make seed-dev
psql -c "SELECT code, name, status FROM ai_applications ORDER BY sort_order;"
```

### Task 1.8 — 路由注册（后端）

- 确认 `/apps/*` 路由不与现有路由冲突。
- 如果冲突，在 `app/api/v1/ai_apps.py` 端点加说明。

---

## Slice 2：前端路由 + 菜单 + 广场列表页

### Task 2.1 — 前端路由

- 路由：`/ai-apps`、`/ai-apps/:code`、`/ai-apps/admin`、`/ai-apps/admin/:id`。
- 路由：`/apps/course-capability-map`、`/apps/preview-guide`、`/apps/resource-recommendation`、`/apps/review-planner`。
- 路径：`apps/web/src/router/`（或现有 router 配置）。

**验证：**
- `pnpm typecheck` 通过。

### Task 2.2 — 菜单配置

- 新增 `AI 应用` 顶级菜单。
- 子菜单：`应用广场` → `/ai-apps`，`应用管理` → `/ai-apps/admin`。
- 在现有侧边栏/导航配置中添加。

**文件：**
- 菜单配置文件（根据现有项目结构查找）

**验证：**
- 手动验证菜单渲染。

### Task 2.3 — 应用广场列表页

- `AiAppsMarketplaceView`（或现有命名规范）。
- 应用卡片列表（只展示 Published）。
- 分类筛选（按 category）。
- 搜索（按 name / description）。
- Draft / Disabled / Archived 不在广场显示。

**文件：**
- `apps/web/src/views/ai-apps/MarketplaceView.vue`（新建）

**验证：**
- 手动验证：登录后进入 `/ai-apps`，看到 APP-001 卡片。

### Task 2.4 — 应用详情页

- `AiAppDetailView`。
- 展示应用元信息。
- "立即使用"跳转独立路由。
- 未发布应用显示"规划中"提示。

**文件：**
- `apps/web/src/views/ai-apps/DetailView.vue`（新建）

**验证：**
- 手动验证：点击 APP-001 卡片，进入详情页。

---

## Slice 3：前端应用管理 + 编辑页

### Task 3.1 — 应用管理列表页

- `AiAppsAdminView`（管理员）。
- 列表展示所有应用（含所有状态）。
- 状态筛选。
- 新建应用按钮。
- 快速操作：发布 / 禁用 / 编辑 / 归档。

**文件：**
- `apps/web/src/views/ai-apps/AdminView.vue`（新建）

**验证：**
- 手动验证：进入 `/ai-apps/admin`，看到所有应用。

### Task 3.2 — 应用编辑页

- `AiAppEditView`。
- 完整表单（字段见 spec）。
- config_schema 使用 JSON 编辑器（textarea 或 Monaco）。
- 状态变更确认提示。
- share_token / api_token 显示 + 重新生成按钮。

**文件：**
- `apps/web/src/views/ai-apps/EditView.vue`（新建）

**验证：**
- 手动验证：编辑 APP-002，将 status 从 Draft 改为 Published。

### Task 3.3 — API Service 对接

- `aiAppsApi` service（axios 或现有 HTTP client）。
- 与后端 `/api/v1/ai-apps` 端点对接。

**文件：**
- `apps/web/src/services/aiAppsApi.ts`（新建）

**验证：**
- `pnpm typecheck` 通过。

---

## Slice 4：独立应用框架页 + Token 端点

### Task 4.1 — 独立应用框架页

- 4 个框架页：`/apps/course-capability-map`、`/apps/preview-guide`、`/apps/resource-recommendation`、`/apps/review-planner`。
- 统一展示：应用名称、描述、"功能开发中"状态。
- 路由守卫：未登录跳转登录页。

**文件：**
- `apps/web/src/views/apps/CourseCapabilityMapView.vue`（新建）
- `apps/web/src/views/apps/PreviewGuideView.vue`（新建）
- `apps/web/src/views/apps/ResourceRecommendationView.vue`（新建）
- `apps/web/src/views/apps/ReviewPlannerView.vue`（新建）

**验证：**
- 手动验证：进入 `/apps/course-capability-map`，看到框架页。

### Task 4.2 — share_token / api_token 端点验证

- 后端 `POST /api/v1/ai-apps/:id/regenerate-share-token` 端点。
- 后端 `POST /api/v1/ai-apps/:id/regenerate-api-token` 端点。
- 生成后在前端编辑页展示。

**验证：**
- pytest 验证 token 变化。

---

## 交付记录

| 日期 | Slice | 交付内容 | PR |
|------|-------|----------|-----|
| TBD | Slice 1 | 数据模型 + 迁移 + Service + API CRUD | TBD |
| TBD | Slice 2 | 前端路由 + 菜单 + 广场列表 + 详情页 | TBD |
| TBD | Slice 3 | 前端管理 + 编辑页 | TBD |
| TBD | Slice 4 | 独立应用框架页 + Token 端点 | TBD |
