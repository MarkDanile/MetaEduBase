# REQ-062: 动态数据采集、填报与报表发布平台

> Status: ⚫ Candidate
> Priority: P0
> Milestone: P3 / Enterprise Agent Platform
> Area: Industrial Park / Dynamic Forms / Data Collection / Reporting
> Created: 2026-07-23
> Source: 招商团队高频动态报表、上级机构数据申报和会展招商成果采集需求
> Parent: REQ-059
> Related: APP-012 / APP-030 / REQ-041 / REQ-047 / REQ-048 / REQ-049 / REQ-051 / REQ-052

## Problem

招商部门面向公司内部、集团和管委会存在高频但字段经常变化的数据统计需求。当前系统既不能判断本次统计项哪些已经由内部系统覆盖，也不能针对缺口生成可发布的采集表单、组织多人填报、汇总版本化数据并形成报告。会展招商还需要复用历史模板，让上百名招商人员通过表单或对话持续登记线索。

如果 APP-012 和 APP-030 分别实现一套表单、填报和汇总逻辑，后续每个报送场景都会形成新的数据孤岛。本需求建设共享的动态采集与报表能力，业务活动和报告语义仍归各 Agent App 所有。

## Users / Scenarios

| 角色 | 场景 |
|------|------|
| 报表发起人 | 发布一次性或常态化统计要求，确认字段、口径、填报对象、截止时间和报告模板 |
| 数据管理员 | 审核系统覆盖判断、字段定义、数据来源、权限和校验规则 |
| 填报人员 | 通过表单或受控对话提交、修订本人负责的数据并查看缺失项 |
| 招商领导 | 查看进度、覆盖率、异常、汇总结果和可追溯报告 |
| Agent App | APP-012/030 复用同一采集能力，但保留各自活动、线索和报告业务模型 |

## Core Model

| 实体 | 所有权与职责 |
|------|--------------|
| `CollectionTemplate` | 可复用采集模板；包含业务用途和当前发布版本，不直接覆盖历史版本 |
| `CollectionCampaign` | 一次性或周期性采集任务；定义租户、受众、时间、状态和模板版本 |
| `FormSchemaVersion` | 版本化字段、类型、枚举、校验、口径、敏感级别和来源要求；发布后不可原地修改 |
| `CoverageAssessment` | 将数据要求标记为 `system_available / derivable / manual_collection / unavailable`，并引用 Catalog、指标或人工判断依据 |
| `Submission` / `SubmissionRevision` | 填报主体、schema 版本、字段值、来源、校验状态和修订历史 |
| `ReportSnapshot` | 固定某次数据快照、统计口径和模板版本，并引用 REQ-047 AgentRun/Artifact/Evidence；不拥有第二套运行状态机 |

## Scope

- 支持输入自然语言、文件或历史模板作为统计要求，AI 只生成字段与映射草案，发布前必须由授权人员确认。
- 基于 REQ-054 Catalog、REQ-051 指标口径和 REQ-052 QueryService 生成覆盖分析；未覆盖字段不得伪装为系统已有数据。
- 支持动态表单草稿、预览、发布、版本、权限、截止时间、填写说明、字段校验和附件/证据引用。
- 发布后的 `FormSchemaVersion` 不可原地变更；字段变化创建新版本，已有 Submission 始终绑定原版本。
- 支持一次性采集、周期性采集和从已验收 Campaign 提升为常态化模板/应用配置。
- 支持填报进度、缺失项、重复项、修订、催办和汇总；提醒与周期触发复用 REQ-049。
- 支持对话式填报，但 Agent 只能提出字段候选并请求确认；写入 Submission 前执行字段校验和权限检查。
- 报表生成必须固定数据快照、统计口径和模板版本；缺失数据显式标注，不由模型静默补齐。
- APP-012 负责动态统计需求与综合报表；APP-030 负责展会、招商人员、线索和活动看板，两者共享本需求的通用能力。

## Acceptance

- AC-1：给定一份真实统计要求，系统输出字段级覆盖分析，并能追溯每个“系统已覆盖”判断到 Catalog/指标/Query。
- AC-2：授权人员可编辑并发布缺口采集表单；未审核的 AI 草案不可直接面向填报人员发布。
- AC-3：发布后修改字段会生成新 `FormSchemaVersion`，历史 Submission 和既有报告仍可按原版本重放。
- AC-4：填报入口按 tenant、Campaign、受众和字段权限隔离；越权用户无法读取或提交其他范围数据。
- AC-5：表单和对话两种入口写入同一 Submission contract；对话抽取结果必须经字段确认和校验。
- AC-6：汇总结果显示已填/缺失/异常/重复状态，报告中的每个关键统计可追溯到系统查询或 SubmissionRevision。
- AC-7：已验收的一次性 Campaign 可复制为周期模板；下一期复用字段和权限，但生成独立 Campaign 与数据快照。
- AC-8：APP-012 与 APP-030 不各自创建第二套通用表单、Submission 或报表运行事实源。

## Non-goals

- 不建设任意业务都能拖拽编排的通用低代码平台。
- 不允许模型未经审核直接发布表单、修改统计口径或代替人员填报未知数据。
- 不把 Artifact、Approval、AgentRun 或企业指标定义复制到本上下文。
- 不在首期实现复杂电子签章、法定统计直报或跨机构主数据同步。

## Open Questions

- 首个真实报表要求、字段数量、填报角色和上报格式由哪一个园区提供。
- 动态字段是否需要行列式明细表、重复分组、级联选择和文件证明等高级控件。
- 匿名/外部填报是否允许；推荐首期仅支持受邀身份或短期一次性 Token，并限制字段范围。
- 周期 Campaign 的调度、催办和冻结窗口如何与 REQ-049 对接。

## Delivery Links

- Backlog: [Product Backlog](../04-backlog.md)
- Applications: [Industrial Park AI Applications](../06-ai-applications/industrial-park-applications.md)
- Parent: [REQ-059](REQ-059-enterprise-agent-platform-kernel.md)
