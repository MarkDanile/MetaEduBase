# REQ-046 Plan: 企业 360 背调工作台与 MCP / Skill 集成闭环

> Status: 🔵 Ready
> Created: 2026-07-03
> Requirement: `docs/01-product-planning/05-requirements/REQ-046-enterprise-360-due-diligence-workbench.md`
> Spec: `docs/02-delivery-plans/01-specs/2026-07-03-req-046-enterprise-360-due-diligence-workbench.md`

## 任务模式

新业务能力 + 平台能力验证。先做 V0 闭环，不一次性建设完整 MCP / Skill 市场。实现中必须保持 adapter 边界，避免把企查查 MCP 或某个内部系统写死进业务页面。

## 执行顺序

### Slice 0: 盘点工具与确认样例

- 盘点当前可用企查查 MCP 工具清单。
- 确认 V0 背调报告最小维度。
- 向用户确认首个样例企业是否可用于真实工具调用和验收报告。
- 明确内部 MCP 首期是 mock 还是接真实资管 / 招商 / 财务 / 合同系统。

交付物：

- 工具清单和 V0 背调维度说明
- 样例企业授权记录或 mock 说明

### Slice 1: 企业主体锚定与企查查 MCP Adapter

- 实现 Subject Resolver 状态机。
- 输入简称时先调用企业实体识别，要求用户确认候选主体。
- 封装 QCC MCP Adapter，记录工具名、参数摘要、返回摘要、错误和时间戳。
- 首期只接背调必需维度，不做 35 个原子工具散弹枪。

验证：

- 完整企业名 / 信用代码直达确认。
- 简称进入候选确认。
- 未确认主体时下游工具不可调用。

### Slice 2: 内部 MCP 契约与 mock

- 定义内部客户信息 MCP 契约：租赁、缴费、合同、工单、历史合作。
- 若真实系统暂未接入，建立 mock provider。
- mock 数据必须在响应和报告中标记 `source_type: "mock"`。
- 为 REQ-052 预留智能问数 adapter 边界，避免后续把内部数据查询写死在背调业务代码中。

验证：

- contract 测试覆盖字段结构。
- 报告不会把 mock 写成真实内部事实。

### Slice 3: 内部智能问数最小样例

- 建立 3 到 5 个背调相关问数样例：历史租赁、欠费缴费、合同义务、工单投诉、历史合作。
- 问数结果结构包含 question、query_plan、source_type、semantic_model_version、result_rows、evidence_refs。
- V0 可使用 mock，但必须显式标记 `source_type: "mock"`。
- 后续接入 REQ-052 时，替换为语义层 + SQL Guard + governed query。

验证：

- fixture 输入能生成稳定 query result。
- 报告能引用问数 evidence，不把 mock 当真实数据。

### Slice 4: 背调 Skill Runner 与结构化报告

- 把企查查 Skill 市场中的背调 SOP 转为平台可执行 Skill 输入。
- Skill 输出必须是结构化报告 schema。
- 报告区分 external_facts / internal_facts / risk_watch_items / human_review_items / evidence_refs。

验证：

- fixture 输入生成稳定结构化报告。
- 缺字段时输出“未返回 / 待人工补充”，不编造。

### Slice 5: 工作台页面与报告归档

- APP-005 页面入口：创建背调任务、查看进度、查看报告。
- 报告展示证据来源、工具调用和人工确认区。
- 支持保存草案、人工确认和归档。

验证：

- UI smoke：创建任务 -> 生成报告 -> 人工确认 -> 归档。
- 证据来源可追溯。

### Slice 6: 真实样例验收

- 使用用户授权企业样例跑 V0 全链路。
- 记录工具调用、报告结构、缺失字段、人工确认项。
- 如果真实企查查 MCP 或内部 MCP 不可用，必须写明阻塞，不用 mock 冒充通过。

验证：

- 生成验收报告。
- 同步 Requirement / Backlog / APP / current-work / work-log。

## 验证矩阵

| 层级 | 验证 |
|------|------|
| 文档门禁 | `scripts/check-engineering-docs` |
| 格式门禁 | `git diff --check` |
| 后端单元测试 | Subject Resolver / Adapter / Skill Runner |
| Contract 测试 | 内部 MCP 契约、智能问数 adapter 与 mock provider |
| 前端测试 | APP-005 页面入口和报告展示 smoke |
| 真实验收 | 用户授权样例企业端到端报告 |

## 依赖与并行建议

| 依赖 | 建议 |
|------|------|
| REQ-044 MCP 注册与管理 | 可以和 REQ-046 Slice 1 并行，但 REQ-046 adapter 必须预留通用 MCP registry 接口 |
| REQ-045 Skill 注册与管理 | 可以先用项目内 Skill Runner mock，后续接入通用 registry |
| REQ-041 / REQ-042 | 会话和三栏工作台未完成前，APP-005 可先做独立页面；完成后迁入统一 AI Workspace |
| REQ-052 智能问数与数据激活 | REQ-046 先预留 adapter 和 mock 问数结果；真实内部结构化数据查询由 REQ-052 承接 |

## 不做清单

- 不做企业准入自动决策。
- 不做所有企查查维度全量下钻。
- 不做非企业主体背调。
- 不做招投标、合同审核、租约预警等其他 P0 场景。
- 不在没有用户授权时跑真实企业样例验收。

## Git 收口

实现时按完整 Git 闭环：

1. 从 `main` 创建任务分支。
2. 更新 `current-work.md` 当前任务。
3. 分 slice 提交，保持每个 PR 小而可审。
4. 运行验证矩阵。
5. PR merge 后同步 Backlog / Requirement / APP / current-work / work-log。
