# REQ-046 Spec: 企业 360 背调工作台与 MCP / Skill 集成闭环

> Status: 🔵 Ready
> Created: 2026-07-03
> Requirement: `docs/01-product-planning/05-requirements/REQ-046-enterprise-360-due-diligence-workbench.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-07-03-req-046-enterprise-360-due-diligence-workbench-plan.md`
> App: APP-005 企业 360 背调工作台

## 1. Problem Statement

园区招商和投决前的企业背调需要同时汇聚外部公开事实、内部客户历史信息和标准化尽调 SOP。当前能力分散在三个层面：

- 企查查 MCP 已在 Codex 环境可用，但产品后端没有通用 MCP 运行时。
- 企查查 Skill 市场提供可借鉴的背调 SOP，但产品内还没有 Skill 注册和执行能力。
- 园区内部客户信息需要通过内部 MCP 获取，但接口契约尚未定义。
- 国资国企更核心的价值是激活多年信息化系统沉淀的数据，因此企业 360 背调还必须为 REQ-052 智能问数预留内部结构化数据查询能力。

如果直接把它做成普通 RAG 问答，会丢失工具 trace、报告归档、人工确认和业务系统集成能力。因此 REQ-046 应作为企业背调工作台，而不是普通聊天问答。

## 2. Goal

规划并实现企业 360 背调 V0 闭环：

```text
企业主体确认
  -> 企查查 MCP 外部事实
  -> 内部 MCP 客户历史信息
  -> 内部智能问数结果
  -> 背调 Skill / SOP 报告生成
  -> 证据链、人工确认和报告归档
```

## 3. Non-Goals

- 不在 V0 中覆盖所有企查查工具，只选背调报告必要维度。
- 不在 V0 中完成通用 MCP 市场和 Skill 市场全部能力。
- 不输出“准入 / 不准入”“投决通过 / 不通过”等最终业务决策。
- 不在没有用户确认的情况下用企业简称直接调用下游企查查工具。
- 不把内部客户 mock 数据伪装成真实系统返回。

## 4. Architecture

### 4.1 组件边界

| 组件 | 职责 |
|------|------|
| Enterprise Due Diligence App | APP-005 页面入口、任务创建、报告查看、人工确认 |
| Subject Resolver | 企业主体识别与确认；封装企查查实体锚定规则 |
| QCC MCP Adapter | 调用企查查 MCP；记录工具调用 trace；统一错误与缺失字段 |
| Internal Customer MCP Adapter | 调用内部资管 / 招商 / 财务 / 合同系统 MCP；V0 可用 mock |
| Intelligent Data Query Adapter | 对接 REQ-052；通过语义层和 SQL Guard 查询内部结构化数据，V0 可用 mock |
| Skill Runner | 执行背调 SOP，组织报告结构和输出 |
| Evidence Ledger | 保存来源、工具、时间、字段和报告引用关系 |
| Report Store | 保存报告草案、人工确认状态、版本和归档信息 |

### 4.2 企业主体锚定

企业名称输入必须进入以下状态机：

```text
raw input
  -> 完整登记名 / 统一社会信用代码
       -> subject confirmed
  -> 简称 / 品牌 / 股票简称 / 不完整名称
       -> get_company_by_query
       -> 用户选择候选主体
       -> subject confirmed
  -> 未匹配
       -> 提示用户检查关键词
```

主体未确认前，禁止调用风险扫描、股东、实控人、司法等下游工具。

### 4.3 企查查 MCP 背调维度

V0 优先维度：

| 维度 | 企查查能力 | 说明 |
|------|------------|------|
| 企业基础信息 | 工商登记 / 企业简介 | 法定代表人、注册资本、成立日期、登记状态、注册地址、业务简介 |
| 股权结构 | 股东 / 实控人 / UBO | 一层股东与穿透聚合结果分开展示，禁止自行计算穿透比例 |
| 风险概览 | 企业风险扫描 | 先扫 35 维计数，再按命中维度决定是否下钻 |
| 经营辅助 | 财务 / 招聘 / 公告等 | 仅在报告模板需要时调用，不做散弹枪 |
| 历史风险 | 历史类工具 | 只有用户或 Skill 明确要求历史维度时调用 |

V0 不要求一次接入全部原子工具，但必须保证工具调用可追踪、可复现、可解释。

### 4.4 内部 MCP 契约

内部 MCP V0 建议先定义统一输入输出，不强绑定具体系统：

```json
{
  "subject": {
    "company_name": "string",
    "credit_code": "string | null"
  },
  "lease_history": [],
  "payment_history": [],
  "contract_history": [],
  "service_tickets": [],
  "cooperation_notes": []
}
```

真实系统未接入前，mock 返回必须显式标记 `source_type: "mock"`，报告中不得写成真实事实。

### 4.5 智能问数边界

REQ-046 不直接实现完整智能问数平台，但必须为 REQ-052 预留 adapter 边界。企业背调 V0 至少要能接入以下结构化问数结果：

```json
{
  "question": "该企业过去三年是否有欠费记录？",
  "query_plan": {
    "entity": "customer",
    "metrics": ["unpaid_amount", "unpaid_count"],
    "filters": {"company_name": "string", "period": "last_3_years"}
  },
  "result_rows": [],
  "source_type": "mock | governed_sql | mcp",
  "semantic_model_version": "string",
  "evidence_refs": []
}
```

约束：

- 不允许大模型直接裸写生产 SQL。
- 查询必须经过语义层、权限检查和 SQL Guard。
- mock 问数结果必须显式标记，不能伪装成真实内部事实。
- 问数结果进入报告时，必须展示问题、口径、过滤条件和来源。

### 4.6 Skill 报告生成

背调 Skill 输入包括：

- 主体确认结果
- 企查查 MCP facts
- 内部 MCP facts
- 报告用途：招商准入 / 投决会 / 存量客户复核
- 输出要求：事实摘要、风险关注点、待人工确认项、证据来源

背调 Skill 输出必须是结构化结果，不只是自然语言长文：

```json
{
  "summary": [],
  "external_facts": [],
  "internal_facts": [],
  "risk_watch_items": [],
  "human_review_items": [],
  "evidence_refs": [],
  "report_sections": []
}
```

### 4.7 报告与证据链

报告中每个关键结论必须至少绑定一种来源：

- 企查查 MCP tool call id
- 内部 MCP tool call id
- 智能问数 query id / query plan id
- 用户上传 / 系统已有资料 id
- 人工填写项

来源缺失时，只能写“未返回 / 未接入 / 待人工补充”，不能推断。

## 5. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 输入简称时必须进入候选主体确认，未确认不得调用下游企查查工具 | 单元测试 / UI smoke |
| AC-2 | 企查查 MCP adapter 记录工具名、参数摘要、返回摘要、错误、耗时和时间戳 | 后端测试 / trace 检查 |
| AC-3 | 内部 MCP adapter 有稳定契约，mock 数据显式标记 source_type | contract 测试 |
| AC-4 | 内部智能问数 adapter 能接收至少 3 类背调问题并返回结构化 query result；mock 必须显式标记 | contract 测试 / fixture |
| AC-5 | Skill Runner 生成结构化背调报告，不混淆事实、分析和人工结论 | 单元测试 / fixture |
| AC-6 | 报告关键事实均可回溯 evidence_refs，包括智能问数 query refs | 端到端测试 |
| AC-7 | 工具失败或字段缺失时，报告明确标注缺失原因，不编造 | 错误分支测试 |
| AC-8 | 至少完成一个用户授权样例企业的 V0 演示验收 | 手工验收报告 |
| AC-9 | 完成后同步 APP / Backlog / Requirement / Plan / current-work / work-log | 文档门禁 |

## 6. Risk Controls

- 企查查工具调用成本：先按背调 Skill 需要的最小维度调用，不全量散弹枪。
- 主体误判：使用候选确认，强制记录用户选择。
- 决策越界：报告只列关注点和复核项，最终结论由人工填写。
- 内部数据不完整：V0 可 mock，但必须显式标注，不得混入真实事实。
- Skill 漂移：报告 schema 固定，Skill 输出必须结构化校验。

## 7. References

- Requirement: `docs/01-product-planning/05-requirements/REQ-046-enterprise-360-due-diligence-workbench.md`
- Intelligent Data Query: `docs/01-product-planning/05-requirements/REQ-052-intelligent-data-query-and-data-activation.md`
- AI Applications: `docs/01-product-planning/06-ai-applications/README.md#app-005-企业-360-背调工作台`
- QCC MCP Guide: https://agent.qcc.com/guide
- QCC Skill Market: https://agent.qcc.com/skills
