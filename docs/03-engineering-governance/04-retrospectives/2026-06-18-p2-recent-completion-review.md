# 2026-06-18: 最近完成任务与 P2 里程碑评审

Trigger:
- 用户要求“按流程评审最近的完成任务，特别是 `02-growth-phase.md` 中的任务”。

Scope:
- 以 `current-work.md` 最近完成区和 `work-log.md` 中 DOC-069 后的任务为入口。
- 重点评审 P2 里程碑相关项：P2-SEARCH、BUG-009、BUG-010、REQ-016、REQ-017、REQ-018。
- 同步轻量评审近期视觉收敛链：REQ-019、REQ-020、REQ-021、REQ-022、REQ-023，以及 BUG-011。

## 总体结论

P2 的“代码能力接入”推进明显：tsvector、RRF、ContextPacker、Hybrid Query Understanding、graph_edge 第 4 通道都已经进入主链路或具备主链路入口。但“真实效果验收”仍不均衡：REQ-017 的 RRF 验收最完整；REQ-018 通道存在和 trace 已成立，但弱召回补足样例不足；REQ-016 代码切片完成，但真实 PG + LLM 报告仍是 placeholder。

因此本轮不是继续加规则，而是修正事实源口径，并将真实验收缺口统一分流到 REQ-024。

## Findings

| 任务 | 结论 | 主要证据 | 问题 / 风险 | 处理 |
|------|------|----------|-------------|------|
| P2-SEARCH | 可关闭 | TD-047 PR #192 + REQ-012 PR #216 + REQ-014 PR #308 + REQ-015 PR #314；里程碑已收口。 | 当前不再是搜索基础设施缺口，后续重点转向真实样例。 | 不新增 follow-up。 |
| BUG-009 | 可关闭 | PR #314；真实 DeepSeek ask 通过，回答包含基本数据类型和引用。 | 后续类似问题应纳入 REQ-024 的真实验收集。 | 不新增 follow-up。 |
| BUG-010 | 可关闭 | PR #316；确定性 normalizer 解决函数参数 A/B 自然问法差异。 | 不等于 LLM NER 全面闭环。 | 由 REQ-016 / REQ-024 继续覆盖。 |
| REQ-016 | 代码切片可关闭，效果待验收 | PR #328/#329/#330；CodeGraph 显示 HybridQueryUnderstandingService、diagnostics、expanded_query 已接入。 | `2026-06-17-req-016-llm-hybrid-ner-validation-report.md` 仍为空表 placeholder。 | 新增 REQ-024。 |
| REQ-017 | 可关闭 | PR #325 + `2026-06-18-req-017-rrf-weighted-fusion-validation-report.md`；AC-1~7 通过。 | Backlog / requirement 仍停在 Doing / Ready，已修正。 | 无 follow-up。 |
| REQ-018 | 条件关闭 | PR #333/#334/#335；真实 PG 报告显示 graph_edge 通道激活、evidence_id bug 已修。 | AC-5 只有 1 个强样例；报告承认 keyword/vector 已强时 edge 未进入 top10。 | 新增 REQ-024。 |
| BUG-011 | 可关闭但需服务重启复测 | PR #342；fast ValueError 降级到 fallback；6 fallback tests + 91 template tests。 | `.env` key 变更需后端重启后复测接口 200。 | 不新增规则；运行时复测可在下次模板任务中确认。 |
| REQ-019~023 | 可关闭 | PR #336/#338/#340/#343/#345；主题从多主题收敛到 light/dark，并完成登录页品牌面调整。 | 视觉任务连续 5 个小 PR，方向变化频繁但最终事实源清晰。 | 不新增规则。 |

## 评分

| 任务 | 分数 | 结论 | 必修 follow-up |
|------|------|------|----------------|
| P2-SEARCH | 88 | 良好；PostgreSQL tsvector + chinese_zh 已从基础设施走到运行时和真实问答链路。 | 无 |
| BUG-009 | 90 | 优秀；真实 PG + DeepSeek ask 证明问题修复，不只是 mock。 | 无 |
| BUG-010 | 87 | 良好；确定性 query normalizer 小而有效，直接改善真实问法。 | 无 |
| REQ-016 | 82 | 良好但有条件；代码切片完整，真实 PG + LLM 效果验收缺口必须分流。 | REQ-024 |
| REQ-017 | 91 | 优秀；RRF 默认接入、配置、trace 和 4 通道真实验收都比较完整。 | 无 |
| REQ-018 | 84 | 良好；4 通道接入成立，但 AC-5 真实补足价值仍需更强样例。 | REQ-024 |
| BUG-011 | 84 | 良好；异常处理修正清晰，服务重启后接口复测仍需在后续任务确认。 | 无 |
| REQ-019~023 | 86 | 良好；视觉系统最终收敛到 light/dark + 登录页品牌面，验证和收口完整。 | 无 |

## 规则判断

本轮不新增规则。现有 `review-scorecard.md`、`workbench.md`、`task-modes.md#任务入口解析门禁` 已能发现主要问题。真正的问题是执行层把“代码接入完成”和“真实效果验收完成”混写在多个事实源中；通过 REQ-024 分流即可，不需要继续扩写规则。

## 后续优先级

| 顺序 | 任务 | 理由 |
|------|------|------|
| 1 | REQ-024 | 直接补齐 P2 最关键的真实效果验收：Query Understanding + graph_edge 弱召回补足样例。 |
| 2 | P2-EXTRACT | 等 REQ-024 证明 RAG 主链路质量后，再推进抽取 schema 稳定化。 |
| 3 | P2-INFRA | 只有当真实验收暴露成本、稳定性或吞吐瓶颈时，再进入缓存 / RabbitMQ / LiteLLM / MinIO。 |
