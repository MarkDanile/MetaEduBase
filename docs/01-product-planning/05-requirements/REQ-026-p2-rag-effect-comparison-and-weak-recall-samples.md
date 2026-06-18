# REQ-026: P2 RAG 效果比较与弱召回样例集收口

Status: 🔵 Ready
Priority: P0
Milestone: P2
Source: REQ-025 real LLM validation follow-up
Related: REQ-016 / REQ-017 / REQ-018 / REQ-024 / REQ-025 / TD-068

## 背景

REQ-025 已证明 `graph_edge` 可以回源 chunk 并进入 packed context，也已在用户授权下跑过真实 LLM provider。但真实报告显示，“通道进入 prompt”不等于“最终回答稳定变好”：部分 baseline 已能回答，部分 graph_edge-only 场景仍回答“未找到足够参考来源”，因此不能把 REQ-025 直接视为 P2 RAG 效果验收完成。

当前缺少一组更适合评估 P2 能力增益的真实弱召回样例，以及可复跑的自动比较口径。后续需要把“机制存在”推进到“质量可证”。

## 目标

- 建立 P2 RAG 弱召回样例集，覆盖 Query Understanding、graph_edge、weighted RRF 和 context packing 的真实增益场景。
- 为每个样例记录 baseline / +Query Understanding / +graph_edge / +weighted RRF 的 retrieval topN、fusion topN、packed context、引用和最终回答。
- 增加自动质量比较口径，不只看 response shape，也不只看通道 topN。
- 明确 `vector fallback` 出现时的解释边界，避免把 keyword fallback 误判为真实语义向量召回。

## 非目标

- 不引入 Neo4j、Elasticsearch、Milvus 或 reranker。
- 不重写现有 AI Chat 主链路。
- 不把 LLM-as-judge 作为唯一验收依据；必须保留可人工复核的 evidence / prompt / answer 摘要。

## 验收标准

1. 至少 3 个真实样例满足：baseline 回答不足，P2 完整链路回答明显更完整或引用更准确。
2. 每个样例必须记录 retrieval topN、fusion topN、packed blocks、document sources、final answer preview 和 `vector fallback` 计数。
3. 至少 2 个样例证明 graph_edge 的 evidence 进入 packed context，并对最终回答有正向贡献；若无正向贡献，必须记录原因。
4. 至少 1 个样例证明 Query Understanding 对自然问法有正向贡献。
5. 验收报告必须区分：
   - 代码能力已接入
   - prompt-level evidence 已进入
   - 真实 LLM 回答质量已改善
6. 如果当前数据集无法构造足够弱召回样例，必须记录数据缺口，并登记数据回填 / 重建索引任务。

## 建议执行顺序

1. 复用并扩展 `scripts/validate_req024_p2_real_validation.py`，不要另起一套不可复用脚本。
2. 从真实问答问题中筛选弱召回样例，优先包含用户已反馈的问题和课程 / Python 文档问题。
3. 为样例增加人工期望要点，用于判断最终回答是否覆盖关键事实。
4. 增加 dry-run 模式和授权 `--allow-llm` 模式，dry-run 能看 prompt，授权模式才调用外部 provider。
5. 更新 P2 milestone、Backlog、Iteration 和 REQ-024 / REQ-025 事实源。

## 事实源

- REQ-025 report: `docs/02-delivery-plans/01-specs/2026-06-18-req-025-graph-edge-prompt-impact-validation-report.md`
- REQ-025 requirement: `docs/01-product-planning/05-requirements/REQ-025-p2-graph-edge-prompt-impact-and-real-llm-validation.md`
