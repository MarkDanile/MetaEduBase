# REQ-054: 平台级数据库（catalog）主题域分组与多源数据接入

Status: 🟢 Done
Priority: P0
Milestone: P3
Domain: AI Workspace / Data Platform / Catalog / 产业园区
Source: 用户补充：基础平台需要按主题域（产业园区 / 中高职教育 / ...）分组数据集，单一 tenant 下承载多主题数据入库与登记
Related: REQ-052 / REQ-046 / REQ-048 / REQ-051
External:

## 背景

REQ-052 智能问数原子能力已实施完成（PR #417），但现有数据层是扁平的 `datasets` 表——所有数据集平铺在同一个列表里，没有主题域分组。用户当前数据是教育类，后续要持续入库产业园区资管数据（企业 / 合同 / 账单 / 工单），未来还会有更多主题。

如果所有主题数据混在一起：
- 业务人员无法按主题筛选数据集
- 语义层无法区分同一 entity_type 在不同主题下的不同含义（如 bill 在园区是租赁账单、在教育是学费账单）
- 知识图谱跨主题混杂，无法按主题聚合查看
- 问数时 QueryPlanner 无法按主题路由到正确的 semantic_model

用户的核心诉求：**基础平台保留 tenant_id 跨租户隔离，在 tenant 内部按主题域（"数据库"）分组数据集**，每个主题域独立管理数据集 + 语义层 + KG + 问数。用户心智模型是"像新建数据库一样新建主题域"。

## 目标

建设平台级 `catalog`（UI 称"数据库"）能力，让基础平台在保留 tenant_id 跨租户隔离的前提下，于 tenant 内部按主题域分组数据，每个主题域独立管理数据集、语义层、知识图谱和问数。

核心目标：

- 引入 `metaedu.data_catalogs` 表（UI 称"数据库"）作为主题域容器，`datasets` / `semantic_models` / `knowledge_nodes` / `query_audit_log` 加 `catalog_id` FK。
- 支持新建数据库（仅 admin / data_admin），填写名称 / code / 描述 / 图标 / 主题色；entity_type 采用动态发现策略（上传自由文本，非白名单，PR #422 起生效）。
- 数据集上传时必选所属数据库；3 种数据源类型（imported_dataset / direct_db / mcp）统一接入 adapter registry，能力分层（见 AC-10）。
- 语义层按 `(catalog_id, entity_type)` 路由，同一 entity_type 在不同数据库下可有不同 column_mapping。
- 知识图谱按数据库聚合展示（V1 标签聚合，V2 跨 dataset 实体合并）。
- 问数时 QueryPlanner 按 `(catalog_id, entity_type)` 路由到正确的 semantic_model。
- 现有教育数据集自动迁移到默认"中高职教育数据库"。

## 能力边界

| 层级 | 能力 | 说明 |
|------|------|------|
| 数据库管理 | CRUD + 列表卡片 | 仅 admin / data_admin 可建库；普通用户可浏览使用 |
| 数据集接入 | 3 种数据源类型统一接入（能力分层） | imported_dataset（上传 CSV/Excel，✅ 完整可用）/ direct_db（受控 V1：只读 SELECT + 表名正则白名单 + limit clamp 1000，经 adapter registry 可达）/ mcp（V1 明确占位，抛 CapabilityUnavailableError，不伪装成功空结果） |
| 语义层路由 | (catalog_id, entity_type) 双键 | 同一 entity_type 在不同数据库下独立 column_mapping / metric_definitions |
| 知识图谱 | 按 catalog_id 聚合 | V1 标签聚合（KG 仍按 dataset 生成，加 catalog_id 可按库筛选）；V2 跨 dataset 实体合并 |
| 问数路由 | QueryPlanner 按 catalog_id | API `/data-query/ask` 加 catalog_id 参数；QueryPanel 加数据库 select |
| 权限 | 数据库级 RBAC（V2） | V1 仅限创建权限（admin / data_admin）；V2 加数据库级字段级 RBAC |

## 与 REQ-052 的关系

| 能力 | REQ-052（已实施） | REQ-054（本次） |
|------|------|------|
| 语义层 | `semantic_models` 按 entity_type | 加 `catalog_id`，按 (catalog_id, entity_type) |
| 数据集 | 扁平 `datasets` 表 | 加 `catalog_id` FK，按数据库分组 |
| QueryPlanner | 按 entity_type 路由 | 加 `catalog_id` 参数，双键路由 |
| QueryService.ask | 接受 entity_type 查 semantic_model | 加 `catalog_id`，按 (catalog_id, entity_type) 查 |
| 知识图谱 | 按 dataset 生成 | 加 `catalog_id`，按数据库聚合展示 |
| 审计 | query_audit_log | 加 `catalog_id`，按数据库统计 |

REQ-054 是 REQ-052 的数据层升级，不破坏 REQ-052 已有能力，只加 `catalog_id` 维度。

## 推荐实现路径

### Slice 0: 数据库 schema + 迁移

- `metaedu.data_catalogs` 表（id / code / name / description / icon / color / entity_types / default_business_purpose / is_active / created_by / timestamps）
- `datasets.catalog_id` FK（nullable，迁移时回填默认库）
- `semantic_models.catalog_id` FK
- `knowledge_nodes.catalog_id`（标签，V1 不改 KG 生成流程）
- `query_audit_log.catalog_id`
- 自动建默认库 "中高职教育数据库"（code=education），现有 datasets 全部归入

### Slice 1: 数据库 CRUD API + 权限

- `POST /api/v1/catalogs`（仅 admin / data_admin）
- `GET /api/v1/catalogs`（所有登录用户）
- `GET /api/v1/catalogs/{id}`（详情 + 数据集列表 + 实体统计）
- `PATCH /api/v1/catalogs/{id}`（仅 admin）
- `DELETE /api/v1/catalogs/{id}`（软删 is_active=false；硬删需库下无数据集）

### Slice 2: 数据集上传 + 3 种数据源

- `POST /api/v1/datasets/upload` 加 `catalog_id` 必选参数
- 数据集列表 `GET /datasets?catalog_id=...` 按库过滤
- DirectDB adapter V1 实现（连接外部 PG 只读查询）
- MCP adapter V1 实现（MCP 服务映射）

### Slice 3: 语义层 + 问数按 catalog 路由

- `semantic_models` 查询按 (catalog_id, entity_type)
- `QueryPlanner.plan` 接受 catalog_id
- `QueryService.ask` 接受 catalog_id
- `POST /data-query/ask` 加 catalog_id 参数
- `QueryPanel.vue` 加数据库 select

### Slice 4: 前端数据库列表卡片 + 详情页

- `DatabaseView.vue` 改为数据库列表卡片
- 新增 `CatalogDetailPage.vue`（数据集 / 语义层 / KG / 问数 tab）
- 上传 dialog 加数据库选择
- KG 页面按数据库聚合

## 验收标准

> 2026-07-20 修正：以下 AC 由 REQ-057 按真实最高验证层级重写。entity_type 策略为动态发现（PR #422 起生效：上传自由文本，`get_discovered_entity_types` 按 datasets 表 DISTINCT 聚合，`validate_entity_type` 保留为 no-op），原“白名单”声明已作废，治理/演化归 REQ-055。手动端到端验证受环境限制未跑，已如实标注。

| ID | 内容 |
|----|------|
| AC-1 | `metaedu.data_catalogs` 表创建，CRUD API 可用（API 测试 + alembic migration 验证）；`entity_types` 字段保留存储但不再作白名单校验（PR #422 起 entity_type 动态发现） |
| AC-2 | `datasets` / `semantic_models` / `knowledge_nodes` / `query_audit_log` 加 `catalog_id` FK，迁移后现有数据归入默认库（migration 测试覆盖） |
| AC-3 | 仅 admin / data_admin 可创建数据库；普通用户只能浏览使用（5 角色 RBAC 权限测试覆盖） |
| AC-4 | 数据集上传时必选 catalog_id（缺省 422 测试覆盖）；entity_type 为自由文本动态发现，不做白名单拦截（PR #422；原“必须在该库的白名单内”声明作废，治理归 REQ-055） |
| AC-5 | 语义层按 (catalog_id, entity_type) 路由；同 entity_type 在不同库下可独立配置（repository 测试 + REQ-057 补两 Catalog 同 entity_type 隔离集成测试，commit `736cf2e1`） |
| AC-6 | QueryPlanner / QueryService.ask 按 catalog_id 路由到正确的 semantic_model（集成测试覆盖；REQ-056 真实业务样例 10/10 绿，含多 catalog 双键隔离） |
| AC-7 | 前端数据库列表卡片 + 详情页 tab（数据集 / 语义层 / KG / 问数）（vitest 覆盖；手动 e2e 受环境限制未跑） |
| AC-8 | 知识图谱按数据库聚合展示（V1 标签聚合，跨 dataset 节点可见）（实现完成；手动 KG 页面验证未跑） |
| AC-9 | 现有教育数据集自动归入"中高职教育数据库"，用户无感迁移（018 migration + 回填验证测试覆盖） |
| AC-10 | 3 种数据源类型统一接入 adapter registry（REQ-057 收口，commits `62aad607`/`5cf4b649`），按能力分层验收：imported_dataset 完整可用；direct_db 受控 V1 经 QueryService factory 可达（只读 SELECT + 表名正则白名单 + limit clamp 1000）；mcp 明确占位抛 CapabilityUnavailableError（QueryService 捕获后写审计 ok=False，不伪装成功空结果） |

## 非目标

- 不用 tenant_id 做主题域分组（tenant_id 保留作跨租户安全边界；主题域分组用 catalog 维度，两者正交叠加）
- 不做跨 catalog 实体共享（V1 各库独立；跨库查询是 V2 能力）
- 不做跨 catalog 实体对齐 / KG 合并（V2 能力，需要实体对齐算法）
- 不做 catalog 级字段级 RBAC（V1 仅创建权限；字段级 RBAC 复用 REQ-052 现有 5 角色 + entity_type 机制）
- 不做 catalog 级配额 / 限流（V2）
- 不替换现有 dataset 上传流程（只加 catalog_id 参数，不破坏向后兼容）

## Open Questions

- 数据库删除策略：软删（is_active=false，数据集保留）还是硬删（级联删除数据集 + 语义层 + KG）？建议软删 + 级联硬删两种模式都支持，由 admin 选择。
- DirectDB adapter V1 是否需要支持 schema 探索（自动发现表 / 字段）？还是只支持手动配置？建议 V1 手动配置，V2 自动探索。
- MCP adapter V1 对接哪个 MCP server？企查查 QCC MCP？还是通用 MCP registry？建议 V1 通用接口，V2 接 QCC。
- 数据库图标 / 主题色是否需要预设库？还是用户自定义？建议预设 lucide icon 子集 + 自定义色值。

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-07-07 | 登记 | 用户补充基础平台需要按主题域分组数据集；登记 REQ-054 为 P0 原子能力，承接 REQ-052 数据层升级。 |
| 2026-07-08 | 实施完成 | 9 Task 全部实施完成（分支 `feat/req-054-catalog`）。Task 1：schema（alembic 016-018 + ORM + 默认库迁移）；Task 2：catalog CRUD API + RBAC；Task 3：上传改造（catalog_id 必选 + entity_type 白名单）；Task 4：DirectDB + MCP adapter V1；Task 5：语义层双键路由 (catalog_id, entity_type)；Task 6：QueryPlanner + /data-query/ask 加 catalog_id；Task 7：前端数据库列表卡片 + 新建对话框；Task 8：前端详情页 + QueryPanel + 上传改造；Task 9：端到端 + closeout。backend 207 passed / frontend 128 passed / ruff 0 / pnpm lint 0 errors / pnpm typecheck 0 / check-engineering-docs exit 0。AC-1~10 全覆盖。手动 e2e 受环境限制未跑。PR 未开，merge 后翻 🟢 Done。 |
| 2026-07-15 | Code Review | PR #421 / #422 / #424 已合并；Catalog 主体能力有条件关闭。复评确认 `default_adapter_factory` 尚未路由 direct_db / mcp，且 PR #422 的动态 entity_type 策略未同步 Requirement / Spec / Plan，原“AC-1~10 全覆盖”声明过满。必修 follow-up：[REQ-057](REQ-057-catalog-adapter-and-entity-contract-closure.md)。 |
| 2026-07-20 | AC 修正 | REQ-057 完成并修正过满声明：验收标准按真实最高验证层级重写（entity_type 动态发现取代白名单；AC-10 改为能力分层 imported 完整可用 / direct_db 受控 V1 可达 / mcp 明确占位抛 CapabilityUnavailableError）；adapter registry 3 类型路由收口（commits `62aad607` / `5cf4b649` / `736cf2e1`）；PR #421 / #422 / #424 已在事实链中。 |
