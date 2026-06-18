# REQ-024: P2 真实验收补强 — Query Understanding 与 graph_edge 补足样例

Status: 🔵 Ready
Priority: P0
Milestone: P2
Source: DOC-071 review follow-up
Related: REQ-016 / REQ-018 / REQ-017 / BUG-010

## 背景

2026-06-18 最近完成任务评审发现：REQ-016 的代码切片已完成，但真实 PG + LLM 验收报告仍是 placeholder；REQ-018 的 graph_edge 通道已接入并在真实 PG 中激活，但 AC-5“证明关系召回能补足 keyword/vector 不稳定问答”仍是条件通过。两个缺口都指向同一类问题：P2 检索增强需要用真实数据和真实问法证明效果，而不是只证明代码通道存在。

## 目标

- 跑通 REQ-016 的真实 PG + LLM Query Understanding 验收，填充真实报告。
- 构造或选择至少 2 个 graph_edge 能补足 keyword/vector 弱召回的真实样例。
- 对比开启 / 关闭 Query Understanding、开启 / 关闭 graph_edge 时的 retrieval_topn、fusion_topn、packed_blocks 和最终回答。
- 明确哪些问题是数据覆盖不足、权重配置不足、query understanding 不足，避免继续把所有问题混成“RAG 质量差”。

## 非目标

- 不重写 RRF、ContextPacker 或 AIChatService 主链路。
- 不引入 Neo4j、Elasticsearch、Milvus 或 reranker。
- 不把 graph_edge 强行调高到压过正文 chunk；只在弱召回样例中证明补足价值。

## 验收标准

1. REQ-016 验收报告中的 Q1/Q2/Q3/Q4 不再是空表，记录真实 method、confidence、expanded_terms、diagnostics 和召回变化。
2. 至少 2 个真实样例能展示 graph_edge 对 keyword/vector 弱召回的补足价值，或明确证明当前 KG 数据不足并形成后续数据任务。
3. 验收报告包含对比表：baseline、+Query Understanding、+graph_edge、+weighted RRF 的 topN 和最终回答差异。
4. 如发现数据不足，必须登记独立 `TD` / `REQ`，不得把 REQ-024 直接标记为完全成功。
5. Backlog、P2 milestone、current-work、work-log 和 review-score-log 状态同步。

## 建议执行顺序

1. 复用 REQ-015 / REQ-017 / REQ-018 已有 dev DB 样例和验收脚本。
2. 先补 REQ-016 报告中 4 个 query 的真实 diagnostics。
3. 再为 REQ-018 找 weak keyword/vector 样例；必要时先做小范围 KG 数据 backfill。
4. 最后用同一份报告输出“效果已闭环 / 数据不足 / 权重不足 / query understanding 不足”的明确结论。

## 事实源

- REQ-016: `docs/01-product-planning/05-requirements/REQ-016-p2-llm-hybrid-ner-query-understanding.md`
- REQ-018: `docs/01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md`
- REQ-016 validation report: `docs/02-delivery-plans/01-specs/2026-06-17-req-016-llm-hybrid-ner-validation-report.md`
- REQ-018 validation report: `docs/02-delivery-plans/01-specs/2026-06-18-req-018-four-channel-graph-edge-recall-validation-report.md`
