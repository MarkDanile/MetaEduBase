# REQ-054 Spec: 平台级数据库（catalog）主题域分组与多源数据接入

> **Status**: 🟣 Shaping → Ready（待用户审）
> **Plan**: 待 writing-plans skill 产出
> **Related**: REQ-052（智能问数，已实施 PR #417）/ REQ-046（企业 360 背调）/ REQ-048（内部系统 adapter）

> **⚠️ 修正说明（2026-07-20，REQ-057）**：本文档为历史 spec，不重写历史。entity_type 策略已由 PR #422 从"白名单"改为**动态发现**——`validate_entity_type` 现为保留的 no-op，`get_discovered_entity_types` 按 datasets 表 DISTINCT 聚合，entity_type 由上传数据集自由产生，治理/演化归 REQ-055。本文中所有"entity_types 白名单"描述均已被取代（SUPERSEDED）。当前事实以 [REQ-057](../../01-product-planning/05-requirements/REQ-057-catalog-adapter-and-entity-contract-closure.md) 与 `app/contexts/structured_data/application/catalog_service.py` 为准。

---

## 1. 问题陈述

### 1.1 现状

REQ-052 智能问数原子能力已实施完成（PR #417 `60e60e70`），建立了 `datasets` / `semantic_models` / `query_audit_log` 等表，支持自然语言问数。但现有数据层是**扁平的**：

- 所有数据集平铺在 `metaedu.datasets` 表，`GET /api/v1/structured-data/datasets` 返回一个扁平列表
- 前端 `DatabaseView.vue` 平铺展示所有数据集，无分组
- `semantic_models` 按 `entity_type` 路由，无法区分同一 entity_type 在不同主题下的不同含义
- 知识图谱按 dataset 生成，无主题域聚合

用户当前数据是教育类（学生信息、课程表等），后续要持续入库产业园区资管数据（企业主数据、租赁合同、账单流水、工单）。如果继续用扁平结构：

1. 业务人员无法按主题筛选数据集（教育 + 园区混在一起）
2. 语义层冲突：`bill` entity_type 在园区是"租赁账单"，在教育是"学费账单"，column_mapping 完全不同
3. KG 跨主题混杂，无法按主题聚合查看
4. QueryPlanner 无法按主题路由到正确的 semantic_model

### 1.2 用户心智模型

用户的核心诉求（原话）：

> "我目前搭建的是基础平台。所以数据库层面，本身就要能够承载各个主题数据的入库和登记。如产业园区主题数据集和中高职教育数据集等。"
>
> "菜单-数据库-数据库列表卡片。可以新增数据集/库（自动导入数据集、连接数据库、第三方接口或者 MCP 服务映射的）"
>
> "如以前的上传的教育数据集，统一归类为'中高职教育数据集'。后续我会再创建一个数据库-产业园区数据库。会将资管类的数据不停的入库和填写。"

用户想要的是"像新建数据库一样新建主题域"——每个主题域是一个独立容器，下挂多个数据集，独立管理语义层 + KG + 问数。

### 1.3 为什么 catalog 不走 tenant_id 切分

**tenant_id 跨租户隔离是已有基础能力，必须保留**：REQ-052 已建立 tenant_id 机制——所有数据（datasets / semantic_models / knowledge_nodes / query_audit_log）都有 tenant_id 字段，跨租户严格隔离，这是安全边界，不能去掉。

**catalog 是 tenant 内部的主题域分组维度**，与 tenant_id 正交叠加：

- tenant_id：**跨组织隔离**（不同公司 / 不同学校），是安全边界，所有数据强制隔离
- catalog：**组织内主题域分组**（产业园区 / 中高职教育），是业务分组维度，在同一 tenant 内区分不同主题

用户之前说"理论上可以按照多租户进行数据切分。但是我目前搭建的是基础平台"——意思是**不用 tenant_id 做主题域分组**（因为主题域是组织内部的业务分类，不是组织隔离），而不是"不要 tenant_id 隔离"。tenant_id 隔离作为安全边界始终保留。

因此 REQ-054 的设计是：
1. tenant_id 跨租户隔离**保留不变**（REQ-052 现有机制）
2. 在 tenant 内部新增 catalog 维度做主题域分组
3. `data_catalogs` 表自身也带 tenant_id（每个 tenant 有自己的 catalog 列表）
4. 唯一约束 `(tenant_id, code)`——同一 tenant 内 catalog code 唯一

---

## 2. 目标

### 2.0 核心定位

建设平台级 `catalog`（UI 称"数据库"）能力，让基础平台在**保留 tenant_id 跨租户隔离**的前提下，于 tenant 内部按主题域分组数据，每个主题域独立管理数据集、语义层、知识图谱和问数。这是 REQ-052 数据层的维度升级——不破坏现有 tenant_id 隔离和问数能力，只加 `catalog_id` 维度。

### 2.1 数据模型

新增 `metaedu.data_catalogs` 表：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `tenant_id` | UUID NOT NULL | 跨租户隔离（REQ-052 安全边界，保留不变） |
| `code` | varchar(50) | 英文标识，URL 友好，如 `park` / `education`。同 tenant 内唯一 |
| `name` | varchar(200) | 中文名，如"产业园区数据库" |
| `description` | text | 主题域说明 |
| `icon` | varchar(50) | lucide icon name（前端图标） |
| `color` | varchar(20) | hex 主题色，如 `#3b82f6` |
| `entity_types` | JSONB | 该库支持的 entity_type 白名单，如 `["customer", "contract", "lease", "bill", "ticket"]` |
| `default_business_purpose` | varchar(200) | 审计默认值，如"园区资管数据分析" |
| `is_active` | boolean | 软删标记 |
| `created_by` | UUID | 创建人 |
| `created_at` / `updated_at` | timestamp | |

唯一约束：`(tenant_id, code)`。

改动现有表（加 `catalog_id` FK）：

| 表 | 字段 | nullable | 说明 |
|----|------|----------|------|
| `datasets` | `catalog_id` | NOT NULL（迁移后） | 数据集所属数据库 |
| `semantic_models` | `catalog_id` | NOT NULL（迁移后） | 语义模型所属数据库 |
| `knowledge_nodes` | `catalog_id` | nullable（V1 标签） | KG 节点所属数据库（V1 不改生成流程，只加标签） |
| `query_audit_log` | `catalog_id` | nullable | 审计日志所属数据库（问数时填入） |

### 2.2 数据源 3 种类型

REQ-052 已设计 `data_source_config.type` 字段，3 种类型：

| 类型 | 说明 | V1 状态 |
|------|------|---------|
| `imported_dataset` | 上传 CSV/Excel 到 `dataset_rows` | ✅ REQ-052 已实现 |
| `direct_db` | 连接外部 PostgreSQL 只读查询 | V1 实现（REQ-054） |
| `mcp` | MCP 服务映射 | V1 实现（REQ-054） |

### 2.3 演进路径

- **V1（本次）**：catalog CRUD + 数据集归档 + 语义层路由 + QueryPlanner 路由 + KG 标签聚合 + UI 卡片列表 + 详情页 tab。3 种数据源类型至少 imported_dataset 完整可用，direct_db / mcp 实现 V1 占位（连接 + 只读查询）。
- **V2**：跨 catalog 实体对齐 / KG 实体合并 / catalog 级字段级 RBAC / DirectDB schema 自动探索 / MCP 接 QCC。
- **后续**：catalog 级配额 / 限流 / 监控告警。

---

## 3. 非目标

- 不用 tenant_id 做主题域分组（tenant_id 保留作跨租户安全边界；主题域分组用 catalog 维度，两者正交叠加）
- 不做跨 catalog 实体共享（V1 各库独立；跨库查询是 V2）
- 不做跨 catalog 实体对齐 / KG 合并（V2，需要实体对齐算法）
- 不做 catalog 级字段级 RBAC（V1 仅创建权限；字段级 RBAC 复用 REQ-052 现有 5 角色 + entity_type 机制）
- 不做 catalog 级配额 / 限流（V2）
- 不替换现有 dataset 上传流程（只加 catalog_id 参数，不破坏向后兼容）
- 不做 catalog 级 KG 生成流程改造（V1 只加 catalog_id 标签，KG 仍按 dataset 生成）
- 不改 REQ-052 已实施的 RBAC / PII / SqlGuard 逻辑（只加 catalog_id 维度）

---

## 4. 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | `metaedu.data_catalogs` 表创建，CRUD API 可用，entity_types 白名单校验生效（已被 PR #422 动态发现取代） | API 测试 + alembic migration 验证 |
| AC-2 | `datasets` / `semantic_models` / `knowledge_nodes` / `query_audit_log` 加 `catalog_id` FK，迁移后现有数据归入默认库 | migration 测试 + 数据验证 |
| AC-3 | 仅 admin / data_admin 可创建数据库；普通用户只能浏览使用 | RBAC 权限测试（5 角色 × CRUD 矩阵） |
| AC-4 | 数据集上传时必选 catalog_id；entity_type 必须在该库的白名单内（白名单部分已被 PR #422 动态发现取代） | 上传 API 测试（缺 catalog_id → 422；entity_type 不在白名单 → 400） |
| AC-5 | 语义层按 (catalog_id, entity_type) 路由；同 entity_type 在不同库下可独立配置 | repository 测试（同 entity_type 不同 catalog 返回不同 model） |
| AC-6 | QueryPlanner / QueryService.ask 按 catalog_id 路由到正确的 semantic_model | 集成测试（2 个库同 entity_type，问数返回各自结果） |
| AC-7 | 前端数据库列表卡片 + 详情页 tab（数据集 / 语义层 / KG / 问数） | 前端 vitest + 手动验证 |
| AC-8 | 知识图谱按数据库聚合展示（V1 标签聚合，跨 dataset 节点可见） | 前端 KG 页面按 catalog 筛选 |
| AC-9 | 现有教育数据集自动归入"中高职教育数据库"，用户无感迁移 | migration 后 GET /datasets 返回全部带 catalog_id |
| AC-10 | 3 种数据源类型（imported_dataset / direct_db / mcp）统一接入，至少 imported_dataset 完整可用 | adapter 测试（3 种类型各 1 case） |

---

## 5. 架构设计

### 5.1 数据模型 ER 图

```
metaedu.data_catalogs (NEW)
  id ─┬─< datasets.catalog_id
      ├─< semantic_models.catalog_id
      ├─< knowledge_nodes.catalog_id (V1 标签)
      └─< query_audit_log.catalog_id

metaedu.datasets (现有, +catalog_id)
  id, catalog_id (NEW FK), tenant_id, name, ...
  data_source_config: {type: imported_dataset|direct_db|mcp, ...}

metaedu.semantic_models (现有, +catalog_id)
  id, catalog_id (NEW FK), entity_type, column_mapping, ...
  UNIQUE (catalog_id, entity_type, data_source_config)  -- 改造唯一约束

metaedu.knowledge_nodes (现有, +catalog_id)
  id, catalog_id (NEW, nullable), source_dataset_id, ...

metaedu.query_audit_log (现有, +catalog_id)
  id, catalog_id (NEW, nullable), user_id, question, ...
```

### 5.2 API 端点

#### Catalog CRUD

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/api/v1/catalogs` | admin / data_admin | 新建数据库 |
| GET | `/api/v1/catalogs` | 所有登录用户 | 列表（带统计：数据集数 / 实体数） |
| GET | `/api/v1/catalogs/{id}` | 所有登录用户 | 详情 + 数据集列表 + 实体统计 |
| PATCH | `/api/v1/catalogs/{id}` | admin / data_admin | 更新（name / description / icon / color / entity_types） |
| DELETE | `/api/v1/catalogs/{id}` | admin | 软删（is_active=false）或硬删（库下无数据集时） |

#### 数据集上传（改造现有）

| 方法 | 路径 | 改动 |
|------|------|------|
| POST | `/api/v1/structured-data/datasets/upload` | 加 `catalog_id` 必选参数 + `entity_type` 必选参数（必须在 catalog.entity_types 白名单内） |
| GET | `/api/v1/structured-data/datasets` | 加 `catalog_id` 可选过滤参数 |

#### 问数（改造现有）

| 方法 | 路径 | 改动 |
|------|------|------|
| POST | `/api/v1/data-query/ask` | 加 `catalog_id` 必选参数（替代原 entity_type 路由） |

### 5.3 语义层路由变化

**现状（REQ-052）**：
```python
SemanticModelRepository.get_active_by_entity_type(tenant_id, entity_type)
# 返回第一个匹配 entity_type 的 active model
```

**REQ-054 后**：
```python
SemanticModelRepository.get_active_by_catalog_and_entity_type(
    tenant_id, catalog_id, entity_type
)
# 返回 (catalog_id, entity_type) 双键匹配的 active model
```

唯一约束改造：`uq_semantic_models_tenant_entity_datasource` → `uq_semantic_models_tenant_catalog_entity_datasource`（加 catalog_id）。

### 5.4 QueryPlanner / QueryService 改造

```python
# QueryPlanner.plan 接受 catalog_id
async def plan(
    self,
    question: str,
    semantic_model: SemanticModel,  # 已包含 catalog_id
    confirmed_company_name: str | None = None,
) -> dict:
    # system prompt 里加入 catalog 上下文
    # "当前数据库: {semantic_model.catalog_name} ({semantic_model.catalog_code})"
    ...

# QueryService.ask 接受 catalog_id
async def ask(
    self,
    *,
    question: str,
    catalog_id: uuid.UUID,  # NEW
    entity_type: str,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    business_purpose: str,
    confirmed_company_name: str | None = None,
    ...
) -> dict:
    # 1. 按 (catalog_id, entity_type) 查 semantic_model
    semantic_model = await repo.get_active_by_catalog_and_entity_type(
        tenant_id, catalog_id, entity_type
    )
    # 2. 后续流程不变（Planner → Validator → Adapter → Guard → Explainer → Audit）
    # 3. audit log 写入 catalog_id
    ...
```

### 5.5 前端结构

```
菜单：数据库
  └─ DatabaseView.vue（改造为数据库列表卡片）
       │
       ├─ CatalogCard.vue（卡片组件）
       │    显示：icon / name / description / 数据集数 / 实体数 / 更新时间
       │    点击 → 路由到 CatalogDetailPage
       │
       └─ [+ 新建数据库] 按钮（仅 admin / data_admin 可见）
            → CatalogCreateDialog.vue

路由：
  /database                    → 数据库列表卡片
  /database/:catalogCode       → CatalogDetailPage
    tab: 数据集 / 语义层 / 知识图谱 / 问数
```

---

## 6. Slice 拆分

### Slice 0: Schema + 迁移（2-3 Task）

- Task 1: `metaedu.data_catalogs` 表 alembic migration + ORM
- Task 2: `datasets` / `semantic_models` / `knowledge_nodes` / `query_audit_log` 加 `catalog_id` FK migration
- Task 3: 迁移脚本 — 自动建默认库 "中高职教育数据库"（code=education），现有 datasets / semantic_models 回填 catalog_id

### Slice 1: Catalog CRUD + 权限（2 Task）

- Task 4: CatalogRepository + CatalogService + CRUD API（含 entity_types 白名单校验）
- Task 5: RBAC 权限门禁（仅 admin / data_admin 可创建/修改/删除）

### Slice 2: 数据集上传改造 + DirectDB/MCP adapter（2 Task）

- Task 6: 数据集上传加 catalog_id + entity_type 参数；entity_type 白名单校验
- Task 7: DirectDB adapter V1（连接外部 PG 只读查询）+ MCP adapter V1（MCP 服务映射占位）

### Slice 3: 语义层 + 问数按 catalog 路由（2 Task）

- Task 8: SemanticModelRepository 改造为 (catalog_id, entity_type) 双键；QueryPlanner / QueryService.ask 接受 catalog_id
- Task 9: `/data-query/ask` API 加 catalog_id 参数；audit log 写入 catalog_id

### Slice 4: 前端数据库列表 + 详情页（2-3 Task）

- Task 10: DatabaseView 改造为数据库列表卡片 + CatalogCreateDialog
- Task 11: CatalogDetailPage（数据集 tab + 语义层 tab + KG tab + 问数 tab）
- Task 12: QueryPanel 加数据库 select + 上传 dialog 加数据库选择

### Slice 5: 端到端 + closeout（1 Task）

- Task 13: 端到端测试（2 个库 × 同 entity_type 不同配置 → 问数返回各自结果）+ 文档更新

**总计 13 Task**（视 plan 细化可能合并为 9-11 Task）。

---

## 7. 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 现有数据迁移破坏 REQ-052 已有能力 | 高 | 迁移后跑 REQ-052 全套测试（110 tests）确保无回归 |
| `semantic_models` 唯一约束改造冲突 | 中 | migration 时先 DROP 旧约束再加新约束；现有数据先回填 catalog_id 再加 NOT NULL |
| DirectDB adapter V1 安全风险（SQL 注入） | 高 | 复用 REQ-052 SqlGuard（只读 / limit / 字段白名单 / tenant 隔离）；DirectDB 只允许 SELECT |
| MCP adapter V1 对接不确定 | 中 | V1 先实现接口骨架 + 占位，不接真实 MCP server；V2 接 QCC |
| 前端 DatabaseView 改造破坏现有数据集管理 UX | 中 | 渐进式改造：先加 catalog 分组，再改路由；保留现有数据集列表作为 CatalogDetailPage 的数据集 tab |
| entity_types 白名单过严导致上传失败 | 低 | 白名单在 catalog 级配置，admin 可随时调整；上传时校验 + 友好错误提示 |

---

## 8. 超出范围

- 跨 catalog 实体对齐 / KG 实体合并（V2）
- catalog 级字段级 RBAC（V2）
- catalog 级配额 / 限流（V2）
- DirectDB schema 自动探索（V2）
- MCP 接 QCC 真实 server（V2）
- catalog 级 KG 生成流程改造（V2，V1 只加标签）
- catalog 导出 / 导入（V2）
- catalog 级监控告警（V2）

---

## 9. 参考

- REQ-052 spec: `docs/02-delivery-plans/01-specs/2026-07-06-req-052-intelligent-data-query.md`
- REQ-052 plan: `docs/02-delivery-plans/02-plans/2026-07-01-req-052-intelligent-data-query.md`
- REQ-052 PR: #417 (`60e60e70`)
- REQ-046 spec: `docs/02-delivery-plans/01-specs/2026-07-03-req-046-enterprise-360-due-diligence-workbench.md`
- BUG-014（DB 不可用 503 处理，alias: 历史 BUG-013）: `docs/01-product-planning/05-requirements/BUG-014-resource-database-500-endpoints.md`

---

## 10. 决策记录（本次塑形确认）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 命名 | UI「数据库」/ 代码 `catalog` | UI 贴合用户心智；代码避免与 PG database 概念混淆 |
| 现有数据迁移 | 自动建默认库"中高职教育数据库" | 用户无感迁移，立即可用 |
| 新建权限 | 仅 admin / data_admin | 多人协作需要治理；普通员工只能浏览使用 |
| V1 范围 | 一次性全做 | 用户选择；改动面与 REQ-052 相似，subagent-driven 可控 |
| KG 耦合 | V1 标签聚合（方案 A） | 改动小，现有 KG 流程不动；V2 实体合并 |
| 跨 catalog 共享 | V1 完全独立 | 简单清晰；跨库查询是 V2 能力 |
| entity_types | 白名单（非建议） | 防止脏数据（园区库下不会突然冒出学生成绩） |
| tenant_id 隔离 | 保留不变（REQ-052 安全边界） | 所有数据跨租户严格隔离；catalog 是 tenant 内部分组维度，与 tenant_id 正交叠加 |
| catalog 分组维度 | 不用 tenant_id 切分主题域 | 主题域是组织内部业务分类，不是组织隔离；用 catalog 在 tenant 内部分组 |

---

## 11. 首期能力边界

### 11.1 完整可用

- catalog CRUD（admin / data_admin 创建，所有用户浏览）
- 数据集上传 + catalog_id 归档 + entity_type 白名单校验
- 语义层按 (catalog_id, entity_type) 路由
- QueryPlanner / QueryService.ask 按 catalog_id 路由
- 审计日志写入 catalog_id
- 前端数据库列表卡片 + 详情页 tab（数据集 / 语义层 / KG / 问数）
- 现有教育数据自动迁移到默认库
- imported_dataset 数据源类型完整可用

### 11.2 V1 占位（接口骨架，不接真实数据源）

- DirectDB adapter：连接外部 PG 只读查询（V1 支持手动配置 schema，V2 自动探索）
- MCP adapter：接口骨架 + 占位（V1 不接真实 MCP server，V2 接 QCC）

### 11.3 V2 留口

- 跨 catalog 实体对齐 / KG 合并
- catalog 级字段级 RBAC
- DirectDB schema 自动探索
- MCP 真实 server 对接
- catalog 级配额 / 限流 / 监控

---

## 12. 安全与合规

### 12.1 RBAC

- catalog 创建 / 修改 / 删除：仅 admin / data_admin（REQ-052 现有 5 角色机制）
- catalog 浏览 + 数据集上传 + 问数：所有登录用户
- V1 不加 catalog 级字段级 RBAC（复用 REQ-052 现有 entity_type + role 机制）
- V2 加 catalog 级字段级 RBAC（如"员工只能看 education 库的 bill，不能看 park 库的 bill"）

### 12.2 数据隔离

- **tenant_id 是跨租户安全边界**（REQ-052 现有机制，保留不变）——所有数据（含 data_catalogs 自身）强制 tenant_id 隔离，跨租户访问被 SqlGuard + RBAC + SQL WHERE 三重拦截
- **catalog_id 是 tenant 内部路由键**，不是安全边界——用于主题域分组和语义层路由，不替代 tenant_id 隔离
- 两层正交叠加：同一 tenant 内多个 catalog 共享用户体系 / RBAC / 审计；跨 tenant 仍严格隔离
- 跨 catalog 查询 V1 不支持（各库独立）；V2 跨库查询仍受 tenant_id 约束（不会因为跨 catalog 而突破 tenant 边界）

### 12.3 审计

- `query_audit_log.catalog_id` 记录每次问数所属数据库
- catalog 创建 / 修改 / 删除操作记入现有审计日志（admin 操作审计）
- V2 加 catalog 级统计报表（每库问数次数 / 数据集数 / KG 节点数）

### 12.4 DirectDB adapter 安全

- 只允许 SELECT（SqlGuard 复用 REQ-052 现有只读检查）
- 连接配置加密存储（V1 明文，V2 加密）
- 连接池隔离（每个 DirectDB 数据源独立连接池，避免跨数据源污染）
- V1 不支持跨租户 DirectDB 查询（连接配置 tenant 级隔离）

### 12.5 MCP adapter 安全

- V1 占位，不接真实 MCP server
- V2 接 QCC 时，复用 REQ-052 SqlGuard + RBAC 审计
- MCP 调用结果仍过 PII 检测 + 字段白名单（last defense 不变）
