# REQ-052 Spec: 智能问数与国资信息化数据激活原子能力

> Status: 🔵 Ready
> Created: 2026-07-06
> Requirement: `docs/01-product-planning/05-requirements/REQ-052-intelligent-data-query-and-data-activation.md`
> App: APP-005 企业 360 背调工作台 / APP-020 / APP-022 / APP-023 / APP-028
> Related: REQ-046（企业 360 背调，§4.5 已为 REQ-052 预留 adapter）/ REQ-048（内部系统 adapter）/ REQ-051（指标语义层）
> Branch: `docs/req-052-shaping`

## 1. Problem Statement

国资国企过去多年投入了大量信息化系统，沉淀了招商、资管、合同、财务、工单、OA、报表和台账数据。AI 应用的关键价值不是只接外部工具，也不是只做文档 RAG，而是把这些结构化数据真正激活，让业务人员能用自然语言查询、解释和复用内部经营数据。

企业 360 背调（REQ-046）是首个高价值场景：外部企查查事实只能回答"这家公司在外部世界是什么样"，但国资园区真正关心的是"这家公司和本园区发生过什么、履约如何、欠费如何、工单投诉如何"。这些问题必须通过内部数据智能问数能力支撑。

当前后端有 `structured_data` context（`datasets` + `dataset_rows` 表 + 前端"数据库"视图），已支持用户上传结构化数据集。但缺少：
- 语义层（entity / metric / dimension / synonym / sensitive 字段映射）
- Query Planner（自然语言 → 结构化 query_plan）
- SQL Guard（只读 / limit / 租户隔离 / 敏感字段脱敏）
- Result Explainer（结果解释 + 口径 + 来源 + evidence_ref）

## 2. Goal

在现有 `structured_data` context 之上，建设可复用的智能问数原子能力：

```text
用户自然语言问题
  → LLM 生成 query_plan (entity/metrics/filters/time/limit)
  → 语义层校验 (entity → data_source, metric → 计算规则, filter → column)
  → Data Source Adapter (按 data_source_config.type 分派)
      ├── ImportedDatasetAdapter  (datasets + dataset_rows JSONB 查询)
      ├── DirectDBAdapter         (直连数据库只读视图 SQL 查询, V1)
      └── MCPAdapter              (企查查/自家 MCP tool call, V1)
  → SQL Guard (只读/limit/租户/敏感脱敏)
  → 执行查询 → 统一 result_rows
  → Result Explainer (表格 + 摘要 + 口径 + 来源)
  → evidence_ref (供 Skill / REQ-046 报告引用)
```

### 2.0 原子能力定位（与 Skill / 专业应用的关系）

REQ-052 是**数据激活原子能力**，不是业务应用。完成后，后续专业领域通过 **Skill（REQ-045 SOP 编排）** 在其上爆发：

```text
REQ-052（本 spec）= 数据激活原子能力
  - 统一语义层 + Query Planner + SQL Guard + Result Explainer
  - 暴露 API: POST /api/v1/data-query/ask
  - 被任何调用方复用（前端面板 / AI Chat / Skill / 其他应用）
      ↑ 被调用
REQ-045（Skill 注册与执行）= SOP 编排框架
  - Skill = 步骤序列，每步可调 API / MCP / LLM
      ↑ 使用
专业领域 Skill（后续按需构建）:
  - REQ-046 企业 360 背调 Skill（招商部门）
  - APP-020 续约风险 Skill
  - APP-023 经营分析 Skill
  - APP-028 空置去化 Skill
```

**架构对标 Palantir**：
- **Ontology（原子能力）** = REQ-052 统一语义层 + 数据激活
- **Workshop / AIP（编排 + 应用）** = REQ-045 Skill + 专业领域应用

**技术可行性确认**：
- ✅ REQ-052 API 可被 Skill 步骤调用（HTTP API）
- ✅ evidence_ref 链路完整（REQ-052 返回 → Skill 报告引用 → 前端展示）
- ✅ 企业主体确认可复用（Skill 步骤 1 企查查确认 → 步骤 2 传 confirmed_name 给 REQ-052）
- ⚠️ REQ-045 Skill 框架当前 Shaping，但不阻塞 REQ-052——API 先实现，Skill 框架后续调用

**爆发模式**：REQ-052 做完后，后续专业 Skill 只需"编排"不需"重写数据查询"——每个 Skill 定义自己的 SOP（步骤序列），步骤中调用 REQ-052 API 获取数据，LLM 生成报告。首期验证用 REQ-046 背调 Skill（1 个 Skill 验证模式），后续复制扩展到其他专业领域。

### 2.1 数据源统一架构（行业最佳实践）

未来智能问数的核心数据源有 3 种，**本质上都统一建立语义层**：

| 数据源类型 | 说明 | Adapter | 首期 |
|-----------|------|---------|------|
| #1 直连数据库 | 本系统直接链接的内部系统数据库（资管/CRM/财务） | `DirectDBAdapter` | V1 |
| **#2 导入数据集** | **本系统直接导入的数据（当前 datasets + dataset_rows）** | **`ImportedDatasetAdapter`** | **✅ 首期** |
| #3 第三方 MCP | 自家 MCP（系统开发的 MCP）+ 企查查等外部 MCP | `MCPAdapter` | V1 |

**统一 Data Source Adapter 接口**（参考 Palantir Ontology 的 Object Set Source + Cube.dev 的 driverFactory）：

```python
class DataSourceAdapter(ABC):
    """统一数据源适配器接口。语义层不绑死数据源类型。"""

    @abstractmethod
    async def query(
        self,
        query_plan: QueryPlan,
        semantic_model: SemanticModel,
        tenant_id: UUID,
        user_role: str,
    ) -> list[dict]:
        """执行查询，返回统一格式的 result_rows。"""
        ...

    @abstractmethod
    def validate_query(self, query_plan: QueryPlan, semantic_model: SemanticModel) -> list[str]:
        """校验 query_plan 是否可执行（字段存在/类型匹配/权限）。"""
        ...
```

**语义层扩展**（`semantic_models` 表新增 `data_source_config` 字段）：

```json
{
  "data_source_config": {
    "type": "imported_dataset",  // imported_dataset / direct_db / mcp
    "dataset_id": "uuid-...",     // type=imported_dataset 时
    "db_connection": null,        // type=direct_db 时 (V1)
    "mcp_server": null,           // type=mcp 时 (V1)
    "mcp_tool": null              // type=mcp 时 (V1)
  }
}
```

**首期只实现 `ImportedDatasetAdapter`**（JSONB 查询路径），接口先行；`DirectDBAdapter` 和 `MCPAdapter` 留 V1，但接口已定义，后续扩展只需加 adapter 实现。

核心目标：

- 将自然语言问题映射到受治理的数据集、指标、维度、过滤条件和查询计划。
- 通过语义层屏蔽物理数据源差异（导入数据集 / 直连数据库 / MCP），避免大模型直接猜表、猜字段、猜口径。
- 在查询前做权限、敏感字段、查询安全和成本控制。
- 在查询后给出结果解释、数据来源、指标口径和异常提示。
- 支撑企业 360 背调、续约风险、报送材料、经营分析等上层应用。

### 2.1 技术路线选型（参考行业实践）

参考《智能问数技术路线与选型》（https://mp.weixin.qq.com/s/03bGPfs3Mc2zZMtI1-DyRw）三条主流路线：

| 路线 | 描述 | 适合场景 | 风险 |
|------|------|----------|------|
| 路线 1: Text2SQL | LLM 直接生成 SQL → 校验 → 执行 | 单表/小宽表、字段清晰、口径简单 | SQL 幻觉、join 错误、指标口径错误 |
| **路线 2: Text2DSL / 语义层** | LLM 生成 IR/DSL（query plan）→ 语义层生成 SQL | 复杂指标、多部门共用、企业级 | 需建语义层/指标层/对象层 |
| 路线 3: 语义层 + 本体 + 图谱 | 本体图谱建模对象关系 + 语义层算指标 + LLM 只理解意图 | 跨部门、跨系统、需归因/证据溯源 | 建模成本高 |

**本 spec 选路线 2（Text2DSL / 语义层）**——与企业级可信问数需求匹配，避免路线 1 的 SQL 幻觉风险。最终演进目标对标 **Palantir 本体论**（Ontology）——对象、关系、指标、规则、事件、证据一体化建模。

### 2.2 演进路径（分阶段，每阶段闭环可演示）

**核心原则：每个阶段都必须能闭环演示和使用，不允许"半成品堆叠到下阶段才可用"。**

| 阶段 | 路线 | 范围 | 闭环演示场景 | 对应需求 |
|------|------|------|-------------|----------|
| **阶段 1（本 spec）** | 路线 2 | 语义层 + Query Planner + SQL Guard + Result Explainer（单 dataset） | 用户上传"账单流水"数据集 → 配置语义模型 → 自然语言问"这家企业欠费多少" → 返回表格 + 欠费金额 + 口径 + 来源 | REQ-052 V0 |
| **阶段 2** | 路线 2 + 跨 dataset | 跨 dataset JOIN + 复杂指标计算 + 指标血缘 | 用户问"这家企业的合同到期 + 欠费 + 工单综合情况" → 跨合同/账单/工单 3 个 dataset JOIN → 返回综合背调数据表 | REQ-052 V1 + REQ-051 |
| **阶段 3（最终目标）** | 路线 3 | 本体图谱（对象/关系/规则/事件/证据）+ 语义层 + 确定性引擎 | 用户问"这家企业为什么风险高" → 本体图谱归因（欠费↑ + 工单↑ + 合同即将到期）→ 返回归因链 + 证据 + 建议动作 | REQ-052 V2 + 对标 Palantir Ontology |
| **阶段 4** | Agentic | 问数后触发行动（异常→任务→通知→整改） | 系统自动发现"某企业连续 3 月欠费" → 触发催缴任务 → 通知物业负责人 → 生成整改建议 | REQ-049（调度）+ REQ-050（规则引擎） |

**每阶段闭环验收标准**：

| 阶段 | 闭环验收（必须全部达成才进入下阶段） |
|------|-------------------------------------|
| 阶段 1 | ① 上传 1 个真实数据集 → ② 配置语义模型 → ③ 自然语言问数 → ④ 返回表格+摘要+口径+来源 → ⑤ 前端可演示 |
| 阶段 2 | ① 上传 3 个关联数据集（合同/账单/工单）→ ② 配置跨 dataset 关系 → ③ 自然语言综合问数 → ④ 返回 JOIN 结果 → ⑤ 前端可演示 |
| 阶段 3 | ① 建对象+关系本体 → ② 自然语言归因问数 → ③ 返回归因链+证据 → ④ 前端可演示 |
| 阶段 4 | ① 配置规则阈值 → ② 自动扫描发现异常 → ③ 触发任务+通知 → ④ 前端可演示 |

**阶段 3 目标（Palantir Ontology 对标）**：
- **对象层**：企业、合同、租约、账单、工单、楼宇、载体（谁是谁）
- **关系层**：企业→合同→租约→账单→工单（关系是什么）
- **指标层**：欠费率、出租率、NOI、续约率（怎么算）
- **规则层**：违约判定、风险阈值、到期提醒（规则是什么）
- **事件层**：签约、欠费、投诉、到期（发生了什么）
- **证据层**：数据来源、口径、时间戳、审计链（依据是什么）

LLM 在阶段 3 只负责理解意图，查询/计算/推理/溯源交给确定性引擎。

## 3. Non-Goals

- 不允许大模型直接对生产库裸写 SQL（首期走 JSONB 查询路径，不生成真实 SQL）。
- 不在首期替代 BI / 数据仓库 / 主数据平台。
- 不在权限不清楚时查询敏感经营数据。
- 不把问数结果当作不可质疑的最终经营结论；关键结论仍需展示口径和来源。
- 不要求首期支持所有数据库和所有业务系统。
- 不在首期做跨 dataset JOIN（单 dataset 内查询优先）。
- 不在 spec 中定义真实业务表字段——具体字段在实施阶段与用户确认真实表结构后填入。
- **不在首期做本体图谱（路线 3）**——对象关系建模、归因解释、证据溯源留阶段 3（对标 Palantir Ontology）。
- **不在首期做 Agentic 问数**——问数后触发行动（异常→任务→通知→整改）留阶段 4，承接 REQ-049（调度）+ REQ-050（规则引擎）。
- 不在首期做指标血缘追溯（首期只返回 metric_definitions 口径，不做血缘链路）。

### 3.1 语义层完整性说明

参考行业实践，完整的企业级语义层应包含：指标定义、维度定义、时间口径、聚合规则、常用过滤条件、join 路径。

**首期覆盖**（本 spec）：
- ✅ 指标定义（metric_definitions: column + aggregation + label）
- ✅ 维度定义（column_mapping: role=dimension）
- ✅ 时间口径（query_plan.time_range）
- ✅ 聚合规则（metric_definitions.aggregation: sum/count/avg）
- ✅ 常用过滤条件（query_plan.filters + column_mapping.synonym 同义词匹配）
- ✅ 敏感字段标记（column_mapping.sensitive + 角色脱敏）

**首期不覆盖**（留阶段 2）：
- ❌ join 路径（跨 dataset JOIN 留 V1）
- ❌ 指标血缘（留 V1 + REQ-051）
- ❌ 复杂计算指标（如 NOI = 收入 - 运营成本，需多列复合计算，留 V1）

## 4. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 至少登记 3 类内部业务数据源及其只读访问边界（通过 `datasets` 上传 + `semantic_models` 映射） | 数据源盘点文档 + semantic_models 表 ≥3 条 active 记录 |
| AC-2 | 至少建立企业、合同、租约、账单、工单 5 类核心语义实体（entity_type） | semantic_models 表 ≥5 条 entity_type 记录 |
| AC-3 | 自然语言问题必须先生成 query_plan，再生成 JSONB 查询；query_plan 可被记录和人工审查 | API 返回 query_plan JSON + 审计日志记录 |
| AC-4 | SQL Guard 能阻止写操作、无界查询（无 limit）、越权查询（跨租户）和敏感字段泄露（脱敏） | 单测覆盖 4 种拒绝场景 + 1 种脱敏场景 |
| AC-5 | 问数结果返回数据表、摘要、指标口径、过滤条件和数据来源 | API response schema 校验 + 集成测试 |
| AC-6 | 企业 360 背调能把内部问数结果作为 evidence_ref 写入报告 | REQ-046 集成测试：问数结果 → evidence_ref |
| AC-7 | 至少 10 个真实业务问数样例通过回归验收，覆盖成功、空结果、权限不足和字段缺失 | 回归测试集 10 case + 4 种边界覆盖 |

## 5. Architecture

### 5.1 数据流

```text
用户自然语言问题 + 已确认企业全称（从 REQ-046 主体确认传入）
  ↓
Query Planner (LLM)
  - 输入: question + semantic_model schema + 同义词 + 企业全称
  - 输出: query_plan JSON (entity/metrics/filters/time/limit/sort)
  ↓
语义层校验
  - entity → data_source_config (查 semantic_models 表)
  - metrics → column + aggregation (查 metric_definitions)
  - filters → column + op (查 column_mapping)
  - 校验失败 → 返回错误 + 建议问法
  ↓
Data Source Adapter 分派（按 data_source_config.type）
  - imported_dataset → ImportedDatasetAdapter (JSONB 查询, 首期)
  - direct_db → DirectDBAdapter (SQL 查询, V1)
  - mcp → MCPAdapter (tool call, V1)
  ↓
SQL Guard（adapter 执行后统一检查）
  1. 只读: adapter 返回只读结果（ImportedDatasetAdapter 天然只读；DirectDBAdapter 强制 SELECT；MCPAdapter 只调只读 tool）
  2. limit: 必须有 limit（默认 100, max 1000）
  3. 租户隔离: 查询必须含 tenant_id
  4. 敏感字段: 结果中 sensitive=true 的字段按角色脱敏
  5. 审计日志: 记录 user_id / question / query_plan / adapter_type / 执行时间 / result_count
  ↓
JSONB 查询构造器
  - SQLAlchemy select(dataset_rows).where(data['column'].astext.op(...)(value))
  - aggregation: sum/count/avg 在 Python 层或 SQL 层计算
  ↓
执行查询 → result_rows
  ↓
Result Explainer (LLM)
  - 输入: question + query_plan + result_rows + metric_definitions
  - 输出: summary + metric_values + filters_applied + source + caveats
  ↓
返回问数结果 (含 evidence_ref)
```

### 5.2 模块划分

| 模块 | 职责 | 文件位置 |
|------|------|----------|
| 语义层 | entity/metric/dimension/synonym/sensitive + data_source_config 映射 | `app/contexts/structured_data/domain/semantic_model.py` + `infrastructure/semantic_model_repository.py` |
| Query Planner | NL → query_plan (LLM) | `app/contexts/structured_data/application/query_planner.py` |
| 语义层校验 | query_plan → data_source + column + aggregation | `app/contexts/structured_data/application/semantic_validator.py` |
| **Data Source Adapter 接口** | 统一查询接口（抽象基类） | `app/contexts/structured_data/domain/data_source_adapter.py` |
| **ImportedDatasetAdapter** | query_plan → JSONB 查询（首期实现） | `app/contexts/structured_data/infrastructure/imported_dataset_adapter.py` |
| DirectDBAdapter (V1) | query_plan → SQL 查询（接口预留，V1 实现） | `app/contexts/structured_data/infrastructure/direct_db_adapter.py` |
| MCPAdapter (V1) | query_plan → MCP tool call（接口预留，V1 实现） | `app/contexts/structured_data/infrastructure/mcp_adapter.py` |
| SQL Guard | 只读/limit/租户/敏感脱敏/审计（adapter 执行后统一检查） | `app/contexts/structured_data/application/sql_guard.py` |
| Result Explainer | 结果 → summary + 口径 + 来源 | `app/contexts/structured_data/application/result_explainer.py` |
| 问数 API | 端点编排 | `app/contexts/structured_data/interfaces/api/query_router.py` |
| 前端问数面板 | UI 输入 + 结果展示 | `packages/web/src/views/database/QueryPanel.vue`（或独立 tab） |

**复用现有模块**：
- `datasets` + `dataset_rows` 表（数据源 #2，ImportedDatasetAdapter 查询目标）
- `DatasetRepository`（list_datasets / get_by_id / list_rows）
- 前端 `DatabaseView` + `DatasetTabsPanel`（UI 容器）
- `ai_chat_service._call_llm`（LLM 调用，复用 deepseek/minimax provider）
- 后续 V1 复用 `app/shared/llm/mcp/`（MCP 运行时，MCPAdapter 调用）

### 5.3 语义层模型（semantic_models 表）

```sql
CREATE TABLE metaedu.semantic_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    dataset_id UUID REFERENCES metaedu.datasets(id),  -- type=imported_dataset 时必填; 其他类型可空
    entity_type VARCHAR(50) NOT NULL,  -- customer / contract / lease / bill / ticket
    entity_name VARCHAR(100) NOT NULL,  -- 客户 / 合同 / 租约 / 账单 / 工单
    data_source_config JSONB NOT NULL DEFAULT '{"type": "imported_dataset"}',  -- 数据源配置
    column_mapping JSONB NOT NULL,  -- {column_name → {role, type, sensitive, synonym}}
    metric_definitions JSONB NOT NULL,  -- {metric_name → {column, aggregation, label}}
    version VARCHAR(20) NOT NULL DEFAULT 'v1',
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active / draft
    created_by UUID NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, entity_type, data_source_config)
);
```

**data_source_config 示例**：

```json
// 数据源 #2: 导入数据集（首期）
{"type": "imported_dataset", "dataset_id": "uuid-..."}

// 数据源 #1: 直连数据库（V1）
{"type": "direct_db", "db_connection": "postgresql://readonly:...@host/db", "schema": "asset_mgmt", "table": "contracts"}

// 数据源 #3: MCP（V1）
{"type": "mcp", "mcp_server": "qcc", "mcp_tool": "search_company_history", "result_mapping": {...}}
```

**column_mapping 示例**：

```json
{
  "company_name": {"role": "entity_key", "type": "str", "sensitive": false, "synonym": ["企业名称", "公司名", "承租方"]},
  "unpaid_amount": {"role": "metric", "type": "float", "sensitive": true, "synonym": ["欠费", "欠租", "应收未收"]},
  "bill_date": {"role": "dimension", "type": "date", "sensitive": false, "synonym": ["账单日期", "费用期间"]},
  "contract_no": {"role": "filter", "type": "str", "sensitive": false, "synonym": ["合同编号"]}
}
```

**metric_definitions 示例**：

```json
{
  "unpaid_amount": {"column": "unpaid_amount", "aggregation": "sum", "label": "欠费金额"},
  "unpaid_count": {"column": "unpaid_amount", "aggregation": "count", "label": "欠费次数"}
}
```

**角色说明**：
- `entity_key`: 唯一标识实体的列（如 company_name / contract_no）
- `metric`: 可聚合计算的列（如 unpaid_amount）
- `dimension`: 可分组/过滤的列（如 bill_date）
- `filter`: 仅用于过滤、不参与聚合的列（如 contract_no）

### 5.4 Query Plan Schema

```json
{
  "entity": "bill",
  "metrics": ["unpaid_amount", "unpaid_count"],
  "filters": {
    "company_name": {"op": "eq", "value": "江苏神码信息技术有限公司"},
    "bill_date": {"op": "gte", "value": "2023-07-01"}
  },
  "time_range": {"field": "bill_date", "start": "2023-07-01", "end": "2026-07-01"},
  "limit": 100,
  "sort": {"field": "bill_date", "dir": "desc"}
}
```

**LLM prompt 注入**：
- semantic_model schema（entity_type + column_mapping + metric_definitions）
- 同义词（从 column_mapping.synonym 提取）
- 已确认企业全称（从 REQ-046 主体确认传入）
- 系统提示：只生成 query_plan JSON，不生成 SQL

### 5.5 SQL Guard 规则

| 规则 | 检查方式 | 失败行为 |
|------|----------|----------|
| 只读 | JSONB 查询构造器天然只读（无 INSERT/UPDATE/DELETE 能力） | N/A（架构保证） |
| limit 强制 | query_plan.limit 必须存在，默认 100，max 1000 | 缺失时填默认值；超 max 时截断 |
| 租户隔离 | 查询 WHERE 自动追加 `tenant_id = current_tenant` | N/A（构造器自动追加） |
| 字段白名单 | filter/sort/metric 的 column 必须在 column_mapping 中有定义 | 拒绝查询 + 返回 "字段未定义" |
| 敏感字段脱敏 | 结果中 sensitive=true 的字段按用户角色脱敏 | 普通用户 masked；管理层原文 |
| 审计日志 | 记录 user_id / question / query_plan / 执行时间 / result_count | 异步写入 audit_log 表 |

### 5.6 Result Explainer Schema

```json
{
  "question": "这家企业过去三年是否有欠费记录？",
  "query_plan": {...},
  "result_rows": [...],
  "result_count": 3,
  "summary": "该企业过去三年共有 3 条欠费记录，累计欠费金额 12.5 万元，最近一次欠费发生在 2026-05-10。",
  "metric_values": {
    "unpaid_amount": {"label": "欠费金额", "aggregation": "sum", "value": 125000.00},
    "unpaid_count": {"label": "欠费次数", "aggregation": "count", "value": 3}
  },
  "filters_applied": {"company_name": "江苏神码信息技术有限公司", "period": "2023-07-01 ~ 2026-07-01"},
  "source": {"dataset_id": "...", "dataset_name": "账单流水 2023-2026", "source_type": "governed_query"},
  "evidence_refs": [{"type": "data_query", "ref": "query_log_id"}],
  "confidence": "high",
  "caveats": []
}
```

**caveats 触发条件**：
- 空结果：`caveats: ["查询结果为空，可能该企业无相关记录或数据未录入"]`
- 权限不足：`caveats: ["部分敏感字段已脱敏，如需查看原文请联系管理员"]`
- 口径不明确：`caveats: ["欠费金额按账单应付金额计算，不含滞纳金"]`

### 5.7 企业主体匹配（与 REQ-046 衔接）

REQ-052 **不自行做企业主体识别**——承接 REQ-046 的企查查主体确认结果：

```text
REQ-046: 用户输入 "江苏神码信息"
  → 企查查 MCP 实体识别 → 多候选
  → 用户确认 → "江苏神码信息技术有限公司"
  → 传入 REQ-052 (confirmed_company_name)

REQ-052: 收到 confirmed_company_name
  → query_plan.filters.company_name = confirmed_company_name
  → 内部 dataset 查询（按 column_mapping.synonym 匹配 company_name 列）
```

如果内部 dataset 中企业名称与企查查确认名称不完全一致（如简称 vs 全称），通过 column_mapping.synonym 做模糊匹配（首期用 `ilike` 或 `contains`）。

### 5.8 AI Chat 接入（Tool Calling 框架）

用户除前端问数面板外，也可在 AI Chat 中直接问数。需要给 AI Chat 加 tool calling 能力。

**当前 AI Chat 架构**（`ai_chat_service.py` + `ai_router._call_llm`）：
- 只发 `messages`（system + user），LLM 生成答案
- 无 tools / function calling 支持
- RAG 检索结果注入 prompt → LLM 生成

**扩展设计**（OpenAI 兼容 tools 参数，deepseek/minimax/qwen 均支持）：

```text
AI Chat 流程扩展:
  用户问题 "这家企业欠费多少"
  ↓
  LLM 第一步调用 (带 tools 参数)
    - messages: [system + user]
    - tools: [
        {
          "name": "query_internal_data",
          "description": "查询内部结构化业务数据（合同/账单/工单/租约）。当用户问金额、数量、统计、列表等结构化数据问题时调用。",
          "parameters": {
            "question": "str (用户的自然语言问题)",
            "entity_hint": "str? (可选: customer/contract/lease/bill/ticket)"
          }
        }
      ]
    - tool_choice: "auto"
  ↓
  LLM 返回 tool_call: query_internal_data(question="这家企业欠费多少")
  ↓
  执行问数工具: 调用 REQ-052 API (POST /api/v1/data-query/ask)
    → 返回 result_rows + summary + metric_values + source
  ↓
  LLM 第二步调用 (带 tool 结果)
    - messages: [system + user + assistant(tool_call) + tool(result)]
    → LLM 基于问数结果生成自然语言答案
  ↓
  返回 AI Chat 答案 (含问数结果引用)
```

**关键设计点**：

| 设计点 | 说明 |
|--------|------|
| Tool 注册 | `query_internal_data` 工具注册到 AI Chat tool registry（首期硬编码 1 个工具，后续可扩展为通用 registry） |
| 意图判断 | LLM 自动判断（`tool_choice: "auto"`）——文档 RAG 问题不触发工具，结构化数据问题触发 |
| 混合场景 | RAG 检索 + 问数工具可共存（LLM 先调工具拿数据，再结合 RAG 文档生成答案） |
| `_call_llm` 扩展 | 新增 `tools` 参数 + 处理 `tool_calls` 响应；保持向后兼容（不传 tools 时行为不变） |
| 结果展示 | AI Chat 答案中展示问数结果表格 + 来源（evidence_ref 复用 REQ-052 的） |
| 企业主体 | AI Chat 需先确认企业全称（复用 REQ-046 主体确认逻辑，或首期要求用户输入全称） |

**`_call_llm` 扩展签名**（向后兼容）：

```python
# 现有
async def _call_llm(system_prompt: str, user_content: str) -> str: ...

# 扩展后
async def _call_llm(
    system_prompt: str,
    user_content: str,
    *,
    tools: list[dict] | None = None,       # OpenAI tools schema
    tool_choice: str = "auto",              # "auto" / "none" / {"type": "function", ...}
) -> str | dict:                            # 返回 content 或 tool_calls
```

**AI Chat tool calling 编排**（`ai_chat_service.chat` 扩展）：

```python
# 伪代码
async def chat(self, request, ...):
    # 1. RAG 检索（现有）
    rag_context = await self._retrieve_and_pack(...)

    # 2. LLM 第一步（带 tools）
    result = await self._call_llm(
        system_prompt, user_content + rag_context,
        tools=[query_internal_data_tool],
    )

    # 3. 如果 LLM 返回 tool_call
    if isinstance(result, dict) and result.get("tool_calls"):
        tool_result = await self._execute_tool(result["tool_calls"][0])
        # 4. LLM 第二步（带 tool 结果）
        final_answer = await self._call_llm(
            system_prompt, user_content + rag_context,
            # 追加 assistant(tool_call) + tool(result) 到 messages
        )
        return final_answer

    # 5. 如果 LLM 直接返回 content（无需工具）
    return result
```

**首期范围**：
- ✅ 只注册 1 个工具：`query_internal_data`
- ✅ 只支持单轮 tool call（LLM 调一次工具 → 生成答案）
- ❌ 不做多轮 tool call（LLM 多次调工具，留 V1）
- ❌ 不做通用 tool registry（首期硬编码，留 V1）

## 6. Slice 拆分（每 Slice 闭环可演示）

**核心原则：每个 Slice 完成后都能独立演示一个端到端场景，不允许"等下个 Slice 才能用"。**

### Slice 0: 语义层建表 + 数据上传 + 手动配置

**闭环演示**：用户上传 1 个"账单流水"数据集 → 在前端配置语义模型（entity_type=bill + column_mapping + metric_definitions）→ 保存成功 → 可查看语义模型。

- 新建 `metaedu.semantic_models` 表 + alembic migration
- 新建 `SemanticModelRepository`（CRUD）
- 前端 `DatabaseView` 新增"语义模型"tab：为 dataset 配置 column_mapping / metric_definitions
- 用户上传 ≥1 个业务数据集到 `datasets` + 配置语义模型
- **真实业务表字段在实施时与用户确认**
- 演示验收：上传数据集 → 配置语义模型 → 查看 column_mapping + metric_definitions 已保存

### Slice 1: Query Planner + JSONB 查询 + API（最小闭环）

**闭环演示**：用户 POST `/api/v1/data-query/ask` 问"这家企业欠费多少" → 返回 query_plan + result_rows + metric_values。

- 实现 `QueryPlanner`（LLM 生成 query_plan）
- 实现 `SemanticValidator`（query_plan → dataset_id + column + aggregation 校验）
- 实现 `JsonbQueryBuilder`（query_plan → SQLAlchemy JSONB 查询）
- 实现 `SqlGuard`（limit / 租户 / 字段白名单 / 敏感脱敏 / 审计）
- 实现 `query_router.py`（POST /api/v1/data-query/ask）返回 query_plan + result_rows + metric_values（**不含 LLM summary**）
- 单测：10 个真实问数样例 → query_plan + result 正确性 + 4 种 Guard 拒绝场景
- 演示验收：curl / API 调用 → 返回 query_plan JSON + result_rows 表格 + metric_values

### Slice 2: Result Explainer + 前端问数面板（完整闭环）

**闭环演示**：用户在前端"智能问数"面板输入自然语言 → 看到 query_plan + result_rows 表格 + LLM summary + 口径 + 来源 + caveats。

- 实现 `ResultExplainer`（LLM 生成 summary + 口径 + caveats）
- 前端 `DatabaseView` 新增"智能问数"tab：输入框 + query_plan 展示 + result_rows 表格 + summary + 口径 + 来源
- 历史问数记录（前端展示最近 N 条）
- 集成测试：question → query_plan → 查询 → result → summary → 前端展示
- 演示验收：前端输入"这家企业欠费多少" → 看到表格 + 摘要 + 口径 + 来源

### Slice 3: AI Chat Tool Calling 接入（聊天问数闭环）

**闭环演示**：用户在 AI Chat 页面问"这家企业欠费多少" → AI 自动判断调问数工具 → 返回自然语言答案 + 问数结果表格。

- 扩展 `ai_router._call_llm` 支持 `tools` 参数 + `tool_calls` 响应处理（向后兼容）
- 扩展 `ai_chat_service.chat` 支持 tool calling 编排（第一步 LLM 判断 → 执行工具 → 第二步 LLM 生成答案）
- 注册 `query_internal_data` 工具（调用 REQ-052 API）
- 前端 AI Chat 展示问数结果表格 + 来源引用
- 单测：tool calling 编排 + 工具执行 + 意图判断（文档问题不触发工具）
- 演示验收：AI Chat 问"这家企业欠费多少" → AI 返回答案含数据表格 + 来源

### Slice 4: REQ-046 集成 + 回归样例（背调闭环）

**闭环演示**：REQ-046 企业 360 背调流程中 → 企查查主体确认 → 内部问数 → evidence_ref 写入背调报告。

- REQ-046 背调 Skill 调用 REQ-052 问数 → evidence_ref 写入报告
- 10 个回归样例（成功 / 空结果 / 权限不足 / 字段缺失 / 脱敏 / 跨 entity / 时间范围 / 同义问法 / 高风险 / 边界）
- 演示验收：REQ-046 背调报告含内部问数 evidence_ref + 10 回归样例全通过

## 7. Risks & Mitigations

| 风险 | 缓解 |
|------|------|
| LLM 生成错误 query_plan（幻觉字段/错误 entity） | 语义层校验严格拒绝未定义字段；LLM prompt 注入完整 schema + 同义词 |
| JSONB 查询性能（大数据集慢） | limit 强制 + 索引（dataset_id + tenant_id）；首期数据量小（样例库） |
| 敏感字段脱敏遗漏 | column_mapping.sensitive 标记 + SqlGuard 结果层过滤；单测覆盖 |
| 企业主体匹配不准（简称 vs 全称） | column_mapping.synonym 配置 + ilike/contains 模糊匹配；首期人工确认 |
| 真实业务表字段未定义（实施时才确认） | spec 中 column_mapping 是通用 schema；实施时填入真实字段 |
| LLM provider 不可用（deepseek 402） | 复用 ai_chat_service 的 provider fallback chain（minimax/deepseek/qwen） |

## 8. 与现有模块的复用关系

| 现有模块 | 复用方式 |
|----------|----------|
| `datasets` + `dataset_rows` 表 | 数据源（用户上传结构化数据集） |
| `DatasetRepository` | list_datasets / get_by_id / list_rows |
| 前端 `DatabaseView` + `DatasetTabsPanel` | UI 容器（新增"智能问数"tab） |
| `ai_chat_service._call_llm` | LLM 调用（Query Planner + Result Explainer） |
| `app/shared/llm/` provider chain | LLM provider fallback（minimax/deepseek/qwen） |
| `metaedu.tenants` + `tenant_id` | 租户隔离 |
| `metaedu.users` + 角色 | 敏感字段脱敏角色判断 |

## 9. Out-of-Scope (Explicit)

- 不生成真实 SQL（首期走 JSONB 查询路径）
- 不做跨 dataset JOIN（单 dataset 内查询优先）
- 不做实时数据同步（首期用上传的静态数据集）
- 不做指标血缘追溯（首期只返回 metric_definitions 口径）
- 不做自然语言结果朗读（TTS）
- 不做多轮对话（首期单次问答）
- 不在 spec 中定义真实业务表字段（实施时与用户确认）
- 不做本体图谱 / 对象关系建模（阶段 3，对标 Palantir Ontology）
- 不做 Agentic 问数 / 行动触发（阶段 4，承接 REQ-049 + REQ-050）

## 10. 参考

- REQ-052 requirement：[REQ-052-intelligent-data-query-and-data-activation.md](../../01-product-planning/05-requirements/REQ-052-intelligent-data-query-and-data-activation.md)
- REQ-046 spec §4.5 智能问数边界：[2026-07-03-req-046-enterprise-360-due-diligence-workbench.md](2026-07-03-req-046-enterprise-360-due-diligence-workbench.md)
- 产业园区 AI 应用组合：[industrial-park-applications.md](../../01-product-planning/06-ai-applications/industrial-park-applications.md)
- **智能问数技术路线与选型**（路线 1/2/3 + Agentic 趋势）：https://mp.weixin.qq.com/s/03bGPfs3Mc2zZMtI1-DyRw
- 企查查 MCP 主体识别规则：https://agent.qcc.com/guide
- Palantir Ontology（本体论，阶段 3 对标）：https://www.palantir.com/docs/foundr/ontology/overview
- 智能问数技术栈参考：https://mp.weixin.qq.com/s/03bGPfs3Mc2zZMtI1-DyRw
- 企查查 MCP 主体识别规则：https://agent.qcc.com/guide