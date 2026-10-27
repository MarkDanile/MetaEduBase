# REQ-064 S4 强制分页候选确认与前置规划

日期：2026-10-27。类型：product planning / pure-docs（含只读代码核查）。

**本文件只做代码事实核查与前置规划：不实现分页，不启动 S4 或 S6/S7，不启动 S1b、S2–S8、phase-D/E 或生产 backfill，不做分支/worktree/refs 清理。**

依据：[design spec §6](../01-specs/2026-10-22-req-064-ui-design-system.md)、[REQ-064 requirement](../../01-product-planning/05-requirements/REQ-064-global-ui-upgrade.md)、[后续 UI 切片路线与验收对齐](2026-10-26-req-064-ui-slice-roadmap.md)、[参考矩阵](../01-specs/2026-10-22-req-064-reference-matrix.md)（VE-01：筛选→数据→分页）。

## 0. 开工基线与核查范围

| 事实 | 当前值 |
|---|---|
| 分支 / base | `docs/req-064-s4-pagination-prereq`，从最新 `origin/main` 创建 |
| base SHA | `5ebff34c5364f5d775bbca8bc9cd62a86870e517` |
| worktree | 仅 1 个注册（主 checkout），工作区 clean |
| #670 路线规划 | MERGED，mergeCommit `b4dd5dfb`，mergedAt 2026-10-26T13:08:27Z，Original 92/100 |
| #671 合并后收口 | MERGED，mergeCommit `5ebff34c`，mergedAt 2026-10-27T08:58:09Z，Original 97/100，SCORE_BASE `58d1d68c` |
| design spec §6 的 S4 验收要求 | **保留，不调整口径**：「S4 列表、表单与详情样板｜**列表筛选/分页**，表单校验/保存，详情正文/来源/辅助面板，完整空/错/加载状态｜用户确认并合入后才批量迁移同类业务页面，**S6/S7 依赖此样板**」 |

**只读核查范围（实际读取/检索的路径）**

- 前端路由：`packages/web/src/app/router.ts`
- 前端视图：`packages/web/src/views/knowledge/**`、`packages/web/src/views/resource/**`、`packages/web/src/views/database/**`；S5 参考页 `views/skill-registry/SkillListView.vue`、`views/mcp-registry/McpServerListView.vue`
- 前端服务与查询：`packages/web/src/services/document.ts`、`services/knowledge.ts`、`services/skillRegistry.ts`、`services/mcpRegistry.ts`、`packages/web/src/views/database/queries.ts`
- 后端端点与仓储：`packages/server-python/app/contexts/document/interfaces/api/files.py`、`knowledge/infrastructure/knowledge_repository.py`、`structured_data/interfaces/api/router.py`
- 共享分页组件检索：`find packages/web/src -iname "*pagin*"`（**无结果**）；关键词 `usePagination` / `Pagination` / `pageSize` / `totalPages` / `hasNext` / `change-page` / `offset` / `limit` / `total`
- 未挂路由文件的引用检索：全仓 `grep ResourceView`（除 `ResourceLibraryView` 外**零命中**）

**核查方式限制**：本次为**只读静态核查**，未启动前端应用实际点击分页控件，未运行或修改 UI 来补齐缺口，未运行 Vitest / Playwright / 真实 PG / 真实 LLM。**不能绝对排除**经 store / composable / 第三方组件的间接分页实现，但已在视图、服务、查询与后端端点四层逐层核对，未发现此类实现；结论限定于下列已列路由及其实际组件。

## 1. S4 候选核查表

| 路由 | 实际组件 | 切片归属 | 现有列表/筛选行为 | 分页证据（请求、返回消费、控件） | 分页对象 | 缺口与结论 |
|---|---|---|---|---|---|---|
| `/knowledge` | `KnowledgeBaseView.vue` | **S4** | 节点列表、`handleSearch`（`knowledgeApi.search`）、`clearSearch`、层级 `drillDown`、新建/删除节点 | `loadNodes(parentId?)` → `knowledgeApi.listNodes({ parent_id })`，**未传 offset/limit**；返回 `KnowledgeNodeDTO[]` 数组直接赋 `nodes`，**无 total**；无上一页/下一页控件 | 页面主列表 | **无分页实现**。后端 `list_nodes` 支持 `offset`/`limit`（默认 limit 50）且返回数组；可列为待选，但须补分页交互与总数来源。**另注意**：`handleSearch()` 会把同一 `nodes` 列表切换为 `/knowledge/search` 结果，该接口只有 `top_k`（默认 5、`le=50`），返回 `SearchResultDTO{node, score}`，**无 offset、无 total**——搜索态与列表态的数据契约不同，搜索态如何翻页须在 §4 明确 |
| `/resource` | `ResourceLibraryView.vue` | **S4** | 文件夹树 + 文件列表、`filterStatus` 状态筛选（**变更只更新 ref，组件无 watch，需手动刷新/选择目录/上传/删除等路径才重新请求**）、上传/删除 | `loadFiles()` → `documentApi.listFiles({ folder_id, status, limit: 100 })`，**固定 limit 100、无 offset**；返回 `FileDTO[]` 数组直接赋 `files`，**无 total**；无翻页控件 | 页面主列表 | **固定 limit ≠ 分页**。后端 `GET /document/files` 支持 `offset`/`limit`（`response_model=list[FileDTO]`，`limit` ≤ 100）；可列为待选，须补分页交互与总数来源 |
| `/resource/:id` | `FileDetailView.vue` + `FileTabsPanel.vue` | **S4** | 文件元信息、处理状态、Tabs（structured/chunks/kg）、重试/删除；**「切片列表」Tab 有 `v-for="chunk in chunks"` 的 chunks 次级列表** | `useFileChunksQuery` → `documentApi.listChunks(fileId)` 按 Tab 懒加载、一次性取回数组，**无 offset/limit、无 total、无翻页控件**；`useFileKgQuery` 同型 | **详情次级列表（chunks）** | 存在可分页对象，但**当前无分页实现**；是否作为 S4 对象由 **D-P1** 决定，不自动升为候选，也不以「无列表分页对象」排除 |
| `/database` | `DatabaseView.vue` + `CatalogCreateDialog.vue` | **S4** | catalog 卡片网格、新建数据库弹窗（**code/name 校验，description 可选**） | `catalogStore.fetch()` → `catalogs` 计算属性；`v-for catalog in catalogs`；无分页参数、无翻页控件 | 页面主列表（卡片网格） | **无分页实现** |
| `/database/:catalogCode`（**主数据集列表**） | `CatalogDetailPage.vue` + `DatasetListPanel.vue` | **S4** | 数据集列表、上传入口；**提供时间/名称/数据量排序控件，但 `@toggle-sort` / `@toggle-sort-dir` 均为 no-op（`() => {}`），父组件写死 `:sort-by="'created_at'"`、`:sort-dir="'desc'"`，实际固定 `created_at desc`，不是可工作的排序行为** | `loadCatalogDatasets()` → `structuredDataApi.listDatasets({ catalog_id })`，**未传 offset/limit**；后端 `list_datasets` 默认 `offset=0`、`limit=50`（`le=100`），返回 `list[DatasetDTO]`，**存在默认 50 条的隐式截断**；无 total、无翻页控件 | 页面主数据集列表 | **隐式截断 ≠ 分页**。注意：`DatasetDTO.row_count` 是**各数据集自身的行数元数据**，不是本列表的总条数，不能混用 |
| `/database/:catalogCode`（**数据预览**） | `CatalogDetailPage.vue` + `DatasetTabsPanel.vue` | **S4** | 数据预览 Tab、KG、问数 | 子组件按钮 `emit('change-page', ±1)`，`:disabled="offset === 0"` / `:disabled="offset + pageSize >= totalRows"`，且整块 `v-if="totalRows > pageSize"`；**父级 `:offset="0"`、`:page-size="20"` 为静态值**，`@change-page="() => {}"` 为 **no-op**；`rowsQuery = useDatasetRowsQuery(selectedDatasetId, ref({ offset: 0, limit: 20 }))` 为**静态参数**；**`:total-rows="datasetRows.length"` 绑定的是当前页行数（≤ 20），故 `totalRows > pageSize` 恒为 false，分页控件在当前绑定下永不渲染** | 数据集**数据预览**子视图 | **静态分页壳**：no-op handler + 静态参数 + totalRows 语义错误（以当前页行数冒充总数）→ 不可作为真实分页证据。后端 rows 端点支持 `offset`/`limit`（`limit` ≤ 200）且返回数组；**该对象已有 `selectedDataset.row_count` 可作为 total 候选来源**（见 D-P2 选项 D） |

### 范围外参考（**不自动算作 S4 候选**）

| 对象 | 归属 | 事实 | 结论 |
|---|---|---|---|
| `capabilities/skills` → `SkillListView.vue` | **S5** | 页面主列表 `loadSkills()` → `listSkills()` 无分页；**审计弹窗**内 `listExecutions(id, { limit, offset: auditPage * auditLimit })` → 消费 `res.items` / `res.total`，`auditPrev` / `auditNext` 带边界禁用，`auditPageInfo` 显示 `start-end / 共 total`；服务层返回 `ExecutionListResponse { items, total, limit, offset }` | **真实服务端分页**，但属 S5 且分页对象是审计弹窗而非页面主列表；**只作实现与契约参考** |
| `capabilities/mcp` → `McpServerListView.vue` | **S5** | 同构：`listInvocations(...)`，`auditPrev` / `auditNext`、边界禁用、`res.items` / `res.total`；主列表 `loadServers()` 无分页 | 同上，**只作参考** |
| `views/resource/ResourceView.vue` | 无路由、无组件引用 | 有 `offset/limit`、上一页/下一页、边界禁用与 `loadResources()`；但 `app/router.ts` 的 `/resource` 指向 `ResourceLibraryView.vue`，且全仓检索 `ResourceView` 无其他引用 | **存在分页代码 ≠ 存在可验收页面**，不计入候选 |

## 2. 核查结论：S4 当前**尚无合格分页候选**

在 design spec §6 所要求的 S4 候选范围（knowledge / resource / database 路由）内，**尚无**同时满足「现有路由 + 真实组件 + 可工作的分页行为」的候选页面。

- 固定 `limit`（`/resource` 的 100）、静态分页参数（`CatalogDetailPage` 的 `offset: 0` / `page-size: 20`）、no-op 事件处理器（`@change-page="() => {}"`）、无路由组件（`ResourceView.vue`）**均不算真实分页证据**。
- `CatalogDetailPage` 的分页控件在当前绑定下**永不渲染**（`totalRows` 为当前页行数，恒 `≤ pageSize`），因此连"按钮存在但不可用"都不能算作用户可见的分页行为。
- **S5 两页不自动迁入 S4**，也不得用其审计弹窗分页冒充 S4 已通过验收。
- **数据集已有 `row_count` 元数据与 `DatasetRepository.count_rows()`**，属于**现有 total 来源**（仅适用于数据预览对象），**不改变**「当前没有可工作的分页行为」的结论，但直接影响 D-P2 的选择，不能被「列表接口只返回数组」掩盖。
- 本结论为**限定于上述路由与组件的静态核查结论**，不是"全仓不存在分页代码"的绝对断言。

## 3. 待用户决定（本文件不代为决定）

以下三项均需用户确认后才能派发实施任务；**本文件不预选、不替用户拍板**。

### D-P1：分页对象与目标页面（必选）

| 选项 | 目标 | 现状与代价 |
|---|---|---|
| 1 | `/knowledge` 节点**主列表** | 当前完全无分页；后端 `list_nodes` 已支持 `offset`/`limit`（默认 50）；需新增翻页交互、状态与总数来源 |
| 2 | `/resource` 文件**主列表** | 当前固定 `limit: 100`；后端 `GET /document/files` 已支持 `offset`/`limit`（`limit` ≤ 100）；需把固定 limit 改为真实翻页，并说明对现有"一次取 100 条"行为的影响 |
| 3a | `/database/:catalogCode` 的**数据预览**子视图 | 当前为静态分页壳（no-op + 静态参数 + totalRows 语义错误），后端 rows 端点已支持 `offset`/`limit`（`limit` ≤ 200），需同时修正 `totalRows` 语义与事件接线；**已有 `selectedDataset.row_count` 可作 total 来源（D-P2 选项 D 仅适用于本项）** |
| 3b | 同页**主数据集列表** | 需处理后端默认 `limit=50` 的隐式截断；该列表**无现成 total 来源**——`DatasetDTO.row_count` 与 `DatasetRepository.count_rows()` 统计的是**单个数据集的数据行**，**不是目录中数据集的总条数，不得用于本项**；还须处理语义层聚合、选中详情与标题计数的跨页消费者（见 §4） |
| 4 | 用户另行指定的 S4 页面/子视图 | 需先按 §1 的核查口径补证据，再决定是否纳入 |

**明确不采纳**：把 S5 审计弹窗分页"算作"S4 候选（切片归属不同、分页对象为弹窗）。

### D-P2：总数（total）来源（必选）

当前 S4 三个相关后端列表接口（`/document/files`、`/knowledge/nodes`、数据集 rows）**均只返回数组，响应体不含 total 字段**。**这不等于「数据集没有 total 来源」**：数据集本身已带有行数元数据，且仓储已有精确计数方法（见下表选项 D）。

| 选项 | 内容 | 影响 |
|---|---|---|
| D（**现有来源，仅 D-P1=3a 数据预览可用；3b 主数据集列表不得使用**） | **复用 `DatasetDTO.row_count`**：数据集列表/详情 DTO 已返回该字段（`packages/web/src/services/structured-data.ts`、`packages/server-python/app/contexts/structured_data/application/dto.py`），现有 UI 已展示（`DatasetDetailMetaBar.vue`、`DatasetListPanel.vue`）；父组件 `selectedDataset` 已持有，可作为 `totalRows` 的真实来源 | **不需新增后端契约**。**必须评估** `row_count` 与物理行数在处理中、重新初始化、删除/重传等时序下的一致性，以及翻页/刷新时的更新时机；若评估发现不一致，须先修正元数据或改选 A/B。**适用对象限定**：`row_count` 是**单个数据集的数据行数**，不是目录中数据集的总条数，**不得用于 3b 主数据集列表** |
| A | **后端契约扩展**：为选定接口增加 `total`，或统一为 `{ items, total, limit, offset }` 信封（参照 S5 `ExecutionListResponse`）。**若对象为 3a 数据预览**，已有 `DatasetRepository.count_rows()`（精确 `COUNT(*)`，见 `dataset_repository.py:206-214`）可作为实现基础，不是从零增加计数查询；**若对象为 3b 主数据集列表**，须改为**带相同 catalog/status/tag 过滤条件的数据集计数查询**——`count_rows()` 统计的是单个数据集的数据行，**不是目录中数据集的总条数，不得用于 3b** | 属**后端契约变更**，须走契约所有权与同步验证流程，并单列后端验收（真实 PG 用例）；**不在本规划任务内实施** |
| B | **前端 `limit + 1` 探测**：请求 `limit + 1` 条判断是否有下一页，只提供「上一页/下一页 + 边界禁用」，**不显示总条数/总页数**。**页大小必须小于端点最大 limit**（`/document/files` ≤ 100、数据集 rows ≤ 200），否则 `limit + 1` 会触发 422，**首页也加载不了**；若需要更大页大小，改用「页大小请求 + 独立单条探测」（例如在下一页 offset 处请求 1 条） | 不改后端契约；须明确向用户说明「不显示总数」是有意取舍；须补**最大允许页大小边界测试**（含首页不 422） |
| C | **客户端分页**（对已取回的全量数组切片） | **仅在数据量有明确上界且用户接受时才可选**，否则与"真实分页"目标不符；本文件不默认推荐 |

### D-P3：验收证据形态（必选确认）

S4 强制分页项的验收证据必须来自**真实候选页面**：可运行预览 + 同条件改前/改后截图 + 结构化度量 + **绑定 commit 的 PR 结构化评论**。本文件**不预写"已通过"**，也不以其他列表样板替代。

## 4. 推荐的最小前置任务边界（供用户批准后实施）

**目标**：在**用户选定的唯一 S4 页面/子视图**上交付**可验收的真实分页**，作为 design spec §6 的 S4「列表筛选/分页」证据对象。**不扩展到其他页面**（其余页面仍属后续 S4 切片）。

**包含**

1. **分页交互**：上一页/下一页（或页码）控件；边界禁用（首页禁上一页、末页禁下一页）；加载中禁用；翻页重新请求数据并更新列表。
2. **数据契约**：按 D-P2 的选择实现——D 复用 `DatasetDTO.row_count` 并验证其与物理行数的一致性；A 需后端 `total`（契约变更单列任务、单独验收，可复用已有 `DatasetRepository.count_rows()`）；B 采用前端 `limit + 1` 探测；**C 客户端分页须先证明「全量可取得」**：受后端单请求 limit 上限约束（`/document/files` ≤ 100、`/knowledge/nodes` 默认 50、数据集 rows ≤ 200、主数据集列表默认 50），须分批拉取直至取尽或由用户确认上界，`total` 由全量数组长度得到，筛选与翻页在客户端对全量数组切片，测试须覆盖「实际超过单请求上限时不会被静默截断」。**禁止**把 `totalRows` 绑定为当前页行数（`CatalogDetailPage` 现有错误不得复制）。**所有 offset 分页须有稳定且确定的全排序**：主排序键可重复（`created_at`、名称、数据量等）时**必须追加唯一键（如 `id`）作 tie-breaker**，并覆盖相同排序键跨页的重复与漏读测试；B 的 `limit + 1` 须满足**页大小 < 端点最大 limit**，否则首页即 422。
3. **状态与边界**：空态、加载、错误、无权限；翻页后空页（如删除末页最后一条后回退）；筛选/搜索条件变化时重置到第一页；文件夹/目录切换时重置分页状态。并补充以下硬边界：
   - **搜索态（仅 `/knowledge`）**：`handleSearch()` 会把同一 `nodes` 列表切换为 `/knowledge/search` 结果，该接口只有 `top_k`（默认 5、`le=50`），**无 offset、无 total**。须在 D-P1 一并确认搜索态口径：①搜索态**不分页**（搜索替换列表，分页控件隐藏/禁用并说明原因，验收时明确「搜索原行为不变」的口径）；②搜索态**也需分页**（须先扩展 search 契约支持 offset/total，属后端变更，单列验收）。**不得**在搜索态直接调用 `listNodes` 翻页而丢失搜索谓词。
   - **主数据集列表的其他消费者（仅 3b）**：`allDatasetsForCatalog` 还驱动 `discoveredEntityTypes`、`semanticModels`、`hasDatasetsWithoutEntityType` 与 `selectedDataset`，`DatasetListPanel` 标题直接显示 `datasets.length`。服务端分页后，**语义聚合须基于全 catalog 数据集（或独立全量查询）**，**选中详情须保留跨页引用**，**标题须区分「当前页条数」与「目录总条数」**；不得把该数组直接替换为当前页数据。补跨页语义层、详情与标题计数回归测试。
   - **筛选语义（仅 `/resource`）**：当前 `filterStatus` 变更只更新 ref，组件**无 watch**，需手动刷新/选择目录/上传/删除等路径才重新请求。实施时须明确筛选变化是否自动重新请求，**不得只重置分页状态而不发起筛选请求**，并补对应测试。
   - **排序与分页联动（仅 3b）**：主数据集列表现有排序**控件**为 no-op（`@toggle-sort` / `@toggle-sort-dir` 均为 `() => {}`，父组件写死 `created_at desc`）。若实施排序接线，须同时规定排序参数与分页的联动（排序变化重置到第一页、全排序稳定）；否则保持「固定 `created_at desc`」的现状说明，**不得把排序写成已可用行为**。
   - **并发请求防护**：搜索、目录切换、筛选、刷新与翻页产生的并发请求须有**请求序号或取消策略**，**旧响应不得覆盖新条件**；补「旧响应不得覆盖新页面/新筛选条件」的测试边界。
4. **可访问性**：按钮可聚焦、有可读名称（如 `aria-label="上一页"`）、禁用态不仅靠颜色区分、键盘可达；翻页后焦点合理保持；若分页位于弹窗内，遵循 spec §6 的 role/aria-modal 约束。
5. **回归**：既有列表/筛选/上传/删除/详情行为不变；不得引入新的默认截断（如 `/resource` 现有"一次取 100 条"的行为若改变须显式说明）。

**交付物（验收证据）**

- 页面 diff + 针对分页的 Vitest（边界禁用、翻页请求参数、total 或探测逻辑、筛选重置）
- 对应 e2e（独占 `METAEDU_E2E_PORT`，文件名匹配 `*-desktop.spec.ts` / `*-mobile.spec.ts` / `*-shared.spec.ts` 发现规则）
- lint / typecheck / build / 相关 Vitest / 对应 e2e 的**实际命令与退出码**
- 固定环境可运行预览 + 同条件改前/改后截图 + 结构化度量（行数、页码、边界禁用、加载/空/错状态），以及绑定 commit 的 **PR 结构化评论**
- 若选 D-P2 = A，另需后端契约验收（真实 PG 用例）

**明确排除**

- 不实现 S4 其余页面的分页（属后续 S4 切片）
- 不把 S5 页面迁入 S4；不删除 `ResourceView.vue`；不改 design spec §6
- 不改共享组件/CSS、不改 DTO/权限/路由导航语义（D-P2 = A 所需的契约扩展除外，且须单列任务）
- 不启动 S1b、S2–S8、phase-D/E 或生产 backfill；不做分支/worktree/refs 清理

## 5. 停止边界与验收门

- **本前置任务完成且验收通过前，S4 强制分页门仍未闭合，S6/S7 继续受阻**；不得宣称 S4 全部验收完成。
- 本文件中的候选方案**均未实现、未批准、未通过**；D-P1 / D-P2 / D-P3 需用户确认后才可派发实施任务。
- 即使前置任务完成，S4 仍需完成其自身样板用户视觉确认与合入，S6/S7 才可按路线文档放行。
- REQ-064 仍为 **🟡 Doing**；S1 未收口；S3 负责人未指定、S3 继续阻塞；S1b 与 S2–S8 未启动；三类用户视觉确认未完成。

## 6. 证据边界

- 本次为**只读静态核查**：未启动前端应用实际点击分页控件，未运行 UI / Vitest / Playwright / 真实 PostgreSQL / 真实 LLM，未执行视觉确认。
- "无分页实现"结论**限定于已列路由与其实际组件**，并已在视图、服务、查询、后端端点四层核对；**不能绝对排除**经 store / composable / 第三方组件的间接实现。
- **`row_count` 与物理行数的一致性未做动态验证**：本文件把它列为**必须评估的现有候选来源**，而非未经验证的最终权威；处理中、重新初始化、删除/重传等时序下是否一致，须在实施前评估。
- 本 PR 的 CI 为 docs-only scope：Engineering docs 与 Whitespace gate 实跑，Frontend / Backend 为 no-op，full hermetic 为 skipped，**不构成任何前后端、Playwright、full hermetic 或业务测试通过证据**。

## 7. 索引

- [后续 UI 切片路线与验收对齐](2026-10-26-req-064-ui-slice-roadmap.md)（§4.5 S4 强制分页验收映射、§6 D9、§13）
- [design spec §6](../01-specs/2026-10-22-req-064-ui-design-system.md)
- [参考矩阵 VE-01](../01-specs/2026-10-22-req-064-reference-matrix.md)（筛选→数据→分页）
- 本文件的实施派发须由用户在 D-P1 / D-P2 / D-P3 明确后另行下达。
