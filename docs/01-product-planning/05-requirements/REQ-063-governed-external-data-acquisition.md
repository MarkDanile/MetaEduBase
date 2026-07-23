# REQ-063: 受治理的外部数据采集与研究证据链

> Status: ⚫ Candidate
> Priority: P0
> Milestone: P3 / Enterprise Agent Platform
> Area: Industrial Park / External Data / Crawler / Evidence / Security
> Created: 2026-07-23
> Source: AI 载体选址的交通配套数据与产业研究的外部产业、政策和企业数据需求
> Parent: REQ-059
> Related: APP-009 / APP-016 / REQ-043 / REQ-044 / REQ-047 / REQ-054

## Problem

AI 载体选址需要交通、公共设施和周边配套数据，产业研究需要产业、政策、企业和区域数据。仅写一个通用“爬虫工具”会让 Agent 自由访问未知站点、绕过授权边界，并产生来源不可追溯、时效不明、许可不清和提示注入风险。

外部采集必须成为受治理的数据能力：优先使用授权 API/MCP 和采购数据源，只在允许范围内使用浏览器/爬虫 Connector，并将来源快照、提取过程、许可证和时效作为 Evidence 管理。

## Users / Scenarios

| 场景 | 外部数据 |
|------|----------|
| APP-009 AI 载体选址 | 地图、地理编码、通勤、交通枢纽、公共设施、周边产业和环境约束 |
| APP-016 产业研究辅助平台 | 政策、产业报告、企业名录、投融资、专利、人才、区域统计和公开新闻 |
| 平台管理员 | 审批来源、凭证、用途、许可、抓取频率、网络范围和保留策略 |
| 研究人员 | 查看来源、时间、覆盖范围、冲突和可引用证据，不把抓取结果当无条件事实 |

## Core Model

| 实体 | 所有权与职责 |
|------|--------------|
| `ExternalSourceDefinition` | 来源类型、域名/API、数据类别、许可、用途、凭证引用和负责人 |
| `AcquisitionPolicy` | tenant、purpose、allowlist、频率、并发、robots/条款、数据分类和保留策略 |
| `AcquisitionRecord` | 一次受控采集操作的 Connector、时间、预算、错误和审计记录，引用 AgentRun/ToolCall，不拥有独立运行状态机 |
| `SourceSnapshot` | 原始响应或对象存储引用、URL、获取时间、内容摘要、hash、解析器版本和许可元数据 |
| `ExtractedEvidence` | 从 Snapshot 提取的结构化事实、有效期、置信度和 Evidence 引用，不替代业务事实源 |

## Scope

- 数据接入优先级固定为授权业务 API/采购数据源 -> MCP/标准 Connector -> 经审批的浏览器/爬虫 Connector。
- 每个来源必须登记用途、许可或条款、负责人、数据分类、更新频率、保留周期和允许租户。
- 所有采集经 Tool Gateway、短期 ToolGrant 和网络 allowlist 执行；Runtime 不持有长期凭证，不接受模型任意扩域。
- 浏览器/爬虫遵守 robots、站点条款、频率和并发限制；禁止绕过登录、验证码、付费墙或访问控制。
- SourceSnapshot 保存可验证引用、获取时间、hash 和解析器版本；大正文进入对象存储，RunEvent 只保存摘要与 ref。
- 网页和文档内容按不可信输入处理，隔离其中的指令文本，防止外部内容改变 Agent 权限、工具或系统提示。
- 支持来源新鲜度、缓存、增量更新、失败重试、冲突事实并列和失效标记。
- APP-009 的地理/交通结果必须保留服务商、查询参数、坐标系、时间和距离/时长口径。
- APP-016 的产业研究结果必须区分原始来源、AI 摘要、分析假设和人工结论。

## Acceptance

- AC-1：未在 Source Registry 和 AcquisitionPolicy 中授权的域名、API 或用途无法被 Agent 调用。
- AC-2：每次采集可追溯到 tenant、purpose、ToolGrant、Connector、来源、获取时间、hash、费用和状态。
- AC-3：网络重定向、DNS rebinding、私网地址和跨域扩展继续受现有 SSRF 策略与新增 allowlist 双重限制。
- AC-4：网页中的提示词、工具指令或权限请求只作为数据，不改变系统提示和授权策略。
- AC-5：每条进入选址或产业报告的外部关键事实都有 SourceSnapshot/Evidence 引用、时间和新鲜度。
- AC-6：同一事实来源冲突时并列展示来源和时间，不由模型静默选择唯一真相。
- AC-7：Connector 失败、超限、许可过期或来源失效时明确降级，不能用模型猜测补齐。
- AC-8：通过至少一个地图/交通授权来源和一个产业研究授权来源完成真实数据 Spike 后，才能进入应用实现。

## Non-goals

- 不建设开放互联网的任意 URL 通用爬虫入口。
- 不绕过验证码、登录、付费墙、robots 或站点限制。
- 不采集与业务目的无关的个人信息，不将公开网页等同于可任意二次使用的数据。
- 不在本需求实现地图可视化、选址排序、产业研究方法或最终业务报告。
- 不把外部抓取结果直接写成内部主数据；进入业务系统前必须经过对应应用校验和人工确认。

## Open Questions

- 首期地图/交通、产业、企业和政策来源的采购或授权清单。
- SourceSnapshot 的对象存储保留周期、删除机制和法律审查责任人。
- 地图服务坐标系、路径规划、配额和费用上限。
- 产业研究是否允许新闻类来源，以及可信来源分级和引用门槛。

## Delivery Links

- Backlog: [Product Backlog](../04-backlog.md)
- Applications: [Industrial Park AI Applications](../06-ai-applications/industrial-park-applications.md)
- Parent: [REQ-059](REQ-059-enterprise-agent-platform-kernel.md)
