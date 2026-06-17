# REQ-016: P2 LLM 混合 NER / Query Understanding

Status: 🟣 Shaping
Priority: P0
Milestone: P2
Source: P2-NER Open Item
Related: BUG-010 / REQ-017 / REQ-018

## Goal

在确定性 query normalizer 和规则 NER 之外，补一层可控的 LLM Query Understanding：把自然问法解析成结构化检索意图、实体、术语扩展和过滤条件，提升用户真实问法的召回稳定性。

## Current Code Facts

| 能力 | 当前状态 | 证据 |
|------|----------|------|
| 规则 NER | 已实现 | `RuleBasedNER` 位于 `packages/server-python/app/contexts/knowledge/application/ner_service.py`，由 AI Chat 和 graph retrieve 入口调用。 |
| 确定性 query normalizer | 已实现部分切片 | BUG-010 已增强 `keyword_query.tokenize_query()`，解决“函数参数”类自然问法术语拆分。 |
| LLM Query Understanding | 未实现 | 当前代码未发现稳定的 LLM query understanding schema、LLM NER adapter、低置信触发策略或 diagnostics 输出。 |
| Trace | 部分具备 | `AIChatService` 已输出 retrieval / fusion / packed trace，但还没有 query understanding 专属 trace。 |

因此 REQ-016 是 **新增 P2 能力**，不是收口已有 LLM NER。后续 CC 开发时应先做 schema、触发条件和降级策略，再接入生产链路。

## Scope

- 定义 LLM Query Understanding 输出 schema：原始 query、标准化 query、核心术语、同义词 / 扩展词、实体、过滤条件、置信度。
- 规则 NER / deterministic normalizer 优先；低置信或无命中时才调用 LLM。
- 输出结果必须可 trace，能进入 AI Chat diagnostics。
- 为真实样例建立回归：至少覆盖 Python 教程问法、课程能力问法和模板/资源库问法。

## Non-Goals

- 不训练专用 NER 模型。
- 不用 LLM NER 替代 chunk / graph / keyword 召回本身。
- 不在本任务内引入 Elasticsearch、Neo4j 或 reranker。

## Acceptance

- AC-1：LLM Query Understanding 有稳定 schema 和失败降级策略。
- AC-2：规则命中场景不额外调用 LLM，避免成本和延迟失控。
- AC-3：低置信 / 规则未命中场景可生成检索术语扩展，并被召回链路消费。
- AC-4：至少 3 类真实问法有回归测试或可复现实验记录。
- AC-5：trace 能显示原始 query、规范化结果、LLM 输出和最终用于召回的 terms。
- AC-6：保留 BUG-010 的 deterministic normalizer 行为，LLM Query Understanding 不能让已验证的确定性问法回归。

## Delivery Links

- Backlog: `docs/01-product-planning/04-backlog.md`
- Milestone: `docs/01-product-planning/02-milestones/02-growth-phase.md`

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-17 | Shaping 完成 | spec + plan 产出，PR #327 squash merge |
| 2026-06-17 | Shaping 收口 | spec（[Spec](../../02-delivery-plans/01-specs/2026-06-17-req-016-llm-hybrid-ner.md)）/ plan（[Plan](../../02-delivery-plans/02-plans/2026-06-17-req-016-llm-hybrid-ner-plan.md)）/ PR #327 已合并 |
