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
  → 语义层校验 (entity → dataset_id, metric → 计算规则, filter → column)
  → JSONB 查询构造器 (在 dataset_rows.data 上构建 SQLAlchemy 查询)
  → SQL Guard (只读/limit/租户/敏感脱敏)
  → 执行查询 → 结果
  → Result Explainer (表格 + 摘要 + 口径 + 来源)
  → evidence_ref (供 REQ-046 报告引用)
```

核心目标：

- 将自然语言问题映射到受治理的数据集、指标、维度、过滤条件和 JSONB 查询计划。
- 通过语义层屏蔽物理表结构复杂度，避免大模型直接猜表、猜字段、猜口径。
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

### 2.2 演进路径（分阶段）

| 阶段 | 路线 | 范围 | 对应需求 |
|------|------|------|----------|
| **阶段 1（本 spec）** | 路线 2 | 语义层 + Query Planner + SQL Guard + Result Explainer | REQ-052 V0 |
| 阶段 2 | 路线 2 + 跨 dataset | 跨 dataset JOIN + 复杂指标计算 + 指标血缘 | REQ-052 V1 + REQ-051 |
| **阶段 3（最终目标）** | 路线 3 | 本体图谱（对象/关系/规则/事件/证据）+ 语义层 + 确定性引擎 | REQ-052 V2 + 对标 Palantir Ontology |
| 阶段 4 | Agentic | 问数后触发行动（异常→任务→通知→整改） | REQ-049（调度）+ REQ-050（规则引擎） |

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
  - entity → dataset_id (查 semantic_models 表)
  - metrics → column + aggregation (查 metric_definitions)
  - filters → column + op (查 column_mapping)
  - 校验失败 → 返回错误 + 建议问法
  ↓
SQL Guard
  1. 只读: JSONB 查询天然只读（无 INSERT/UPDATE/DELETE 风险）
  2. limit: 必须有 limit（默认 100, max 1000）
  3. 租户隔离: WHERE 必须含 tenant_id
  4. 敏感字段: 结果中 sensitive=true 的字段按角色脱敏
  5. 审计日志: 记录 user_id / question / query_plan / 执行时间 / result_count
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
| 语义层 | entity/metric/dimension/synonym/sensitive 映射 | `app/contexts/structured_data/domain/semantic_model.py` + `infrastructure/semantic_model_repository.py` |
| Query Planner | NL → query_plan (LLM) | `app/contexts/structured_data/application/query_planner.py` |
| 语义层校验 | query_plan → dataset_id + column + aggregation | `app/contexts/structured_data/application/semantic_validator.py` |
| SQL Guard | 只读/limit/租户/敏感脱敏/审计 | `app/contexts/structured_data/application/sql_guard.py` |
| JSONB 查询构造器 | query_plan → SQLAlchemy 查询 | `app/contexts/structured_data/infrastructure/jsonb_query_builder.py` |
| Result Explainer | 结果 → summary + 口径 + 来源 | `app/contexts/structured_data/application/result_explainer.py` |
| 问数 API | 端点编排 | `app/contexts/structured_data/interfaces/api/query_router.py` |
| 前端问数面板 | UI 输入 + 结果展示 | `packages/web/src/views/database/QueryPanel.vue`（或独立 tab） |

**复用现有模块**：
- `datasets` + `dataset_rows` 表（数据源）
- `DatasetRepository`（list_datasets / get_by_id / list_rows）
- 前端 `DatabaseView` + `DatasetTabsPanel`（UI 容器）
- `ai_chat_service._call_llm`（LLM 调用，复用 deepseek/minimax provider）

### 5.3 语义层模型（semantic_models 表）

```sql
CREATE TABLE metaedu.semantic_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    dataset_id UUID NOT NULL REFERENCES metaedu.datasets(id),
    entity_type VARCHAR(50) NOT NULL,  -- customer / contract / lease / bill / ticket
    entity_name VARCHAR(100) NOT NULL,  -- 客户 / 合同 / 租约 / 账单 / 工单
    column_mapping JSONB NOT NULL,  -- {column_name → {role, type, sensitive, synonym}}
    metric_definitions JSONB NOT NULL,  -- {metric_name → {column, aggregation, label}}
    version VARCHAR(20) NOT NULL DEFAULT 'v1',
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active / draft
    created_by UUID NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, dataset_id, entity_type)
);
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

## 6. Slice 拆分（实施路径）

### Slice 0: 数据问数盘点 + 语义层建表

- 新建 `metaedu.semantic_models` 表 + alembic migration
- 新建 `SemanticModelRepository`（CRUD）
- 用户上传 ≥3 个业务数据集（合同 / 账单 / 工单）到 `datasets`
- 为每个 dataset 配置 semantic_model（column_mapping + metric_definitions）
- **真实业务表字段在实施时与用户确认**

### Slice 1: Query Planner + 语义层校验

- 实现 `QueryPlanner`（LLM 生成 query_plan）
- 实现 `SemanticValidator`（query_plan → dataset_id + column + aggregation 校验）
- 单测：10 个真实问数样例 → query_plan 正确性

### Slice 2: SQL Guard + JSONB 查询构造器

- 实现 `JsonbQueryBuilder`（query_plan → SQLAlchemy 查询）
- 实现 `SqlGuard`（limit / 租户 / 字段白名单 / 敏感脱敏 / 审计）
- 单测：4 种拒绝场景 + 1 种脱敏场景

### Slice 3: Result Explainer + API 编排

- 实现 `ResultExplainer`（LLM 生成 summary + 口径 + caveats）
- 实现 `query_router.py`（POST /api/v1/data-query/ask）
- 集成测试：question → query_plan → 查询 → result → response

### Slice 4: 前端问数面板

- 在 `DatabaseView` 新增"智能问数"tab
- 输入框 + query_plan 展示 + result_rows 表格 + summary + 口径 + 来源
- 历史问数记录

### Slice 5: REQ-046 集成 + 回归样例

- REQ-046 背调 Skill 调用 REQ-052 问数 → evidence_ref 写入报告
- 10 个回归样例（成功 / 空结果 / 权限不足 / 字段缺失 / 脱敏 / 跨 entity / 时间范围 / 同义问法 / 高风险 / 边界）

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