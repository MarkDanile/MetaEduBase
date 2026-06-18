# REQ-025: P2 graph_edge 进入 prompt 与真实 LLM 效果验收收口

Status: 🟣 待验证（prompt-level 与真实 LLM run 已完成；最终质量改善证据不足）
Priority: P0
Milestone: P2
Source: REQ-024 validation follow-up
Related: REQ-016 / REQ-017 / REQ-018 / REQ-024 / TD-068

## 背景

REQ-024 干跑验收证明 graph_edge 通道在真实 dev DB 中可以补足 fusion 候选：2 个弱召回样例中 graph_edge 新 chunk 进入 fusion 阶段。但同一报告也确认 graph_edge 证据没有进入 packed context，`edge in packed = 0`，因此还不能证明第 4 通道最终影响 prompt 和回答质量。

同时，REQ-024 真实 LLM 验收没有执行：当前环境不允许把 dev DB 检索切片 / prompt context 发送给外部 LLM provider。Query Understanding 在 dry-run 下使用脚本内 fake provider，只能验证 diagnostics 结构和链路，不代表真实模型理解质量。

## 目标

- 让 graph_edge 召回的有效 chunk 或 section 能进入最终 packed context。
- 至少 2 个真实弱召回样例展示：baseline 缺失或排序靠后，开启 graph_edge + weighted RRF 后，相关证据进入 prompt 并改善最终回答。
- 用真实 LLM provider 跑一次授权验收，记录最终回答、引用、prompt 摘要和 diagnostics。
- 把结论回填到 REQ-018 AC-5、P2 milestone 和评审事实源，不再停留在“通道存在”。

## 非目标

- 不引入 Neo4j、Elasticsearch、Milvus 或 reranker。
- 不重写 AI Chat 主链路。
- 不把 graph_edge 权重调到无条件压过正文 chunk；只做可解释、可回滚的权重或 context packing 调整。

## 验收标准

1. 报告中至少 2 个真实问题满足：graph_edge topN > 0、edge in fusion > 0、edge in packed > 0。
2. 至少 2 个真实问题的最终回答比 baseline 更完整，且回答引用能指向相关文档来源。
3. 报告同时包含 baseline / +Query Understanding / +graph_edge / +weighted RRF 的 retrieval_topn、fusion_topn、packed_blocks 和最终回答摘要。
4. 如果真实 LLM 调用被安全策略或环境阻塞，必须记录阻塞原因，不能把任务标记为效果通过。
5. 报告必须记录 `vector fallback` 计数；当 fallback 大于 0 时，不能把 vector topN 解释为真实语义向量召回。

## 建议执行顺序

1. 基于 TD-068 的结论，先把 `vector fallback` 计数作为验收报告固定字段。
2. 复核 ContextPacker 对 `source_type="knowledge_edge"` / `channels=["graph_edge"]` 的处理，确保有效 edge 关联 chunk 可以进入 packed context。
3. 使用 REQ-024 脚本或其后续版本跑 dry-run，对比 packed context。
4. 获得用户明确授权后，再开启真实 LLM provider 验收。

## 验收记录（2026-06-18 dry-run）

- 已修复 `ContextPacker`：`knowledge_edge` 与 `knowledge_node` 共用 source chunk hydration 路径，`graph_edge` 的 `graph_source` block 可进入 packed context。
- 已修复 `AIChatService._hydrate_graph_chunks`：fusion 后的 `knowledge_edge` 会回填 `document_chunks` 的 `content`、`chunk_index`、`section_title`、`section_path`，避免 prompt 只拿 edge 描述。
- 已增加预算保底：当 fusion 已包含 `graph_edge` source block 时，packed context 至少保留 1 个 `graph_edge` source block，并遵守剩余字符预算。
- 已生成 dry-run 报告：[REQ-025 P2 graph_edge prompt impact validation report](../../02-delivery-plans/01-specs/2026-06-18-req-025-graph-edge-prompt-impact-validation-report.md)。
- dry-run 结果：`Q2_cross_section_relationship` / `Q3_keyword_only_baseline` 两个样例满足 `graph_edge topN > 0`、`edge in fusion > 0`、`edge in packed > 0`。
- `vector fallback trace count: 152`，因此本轮仍不能把 vector topN 解释为真实语义向量召回。
- 外部 LLM 未开启，本轮不能证明最终回答改善；下一步需用户明确授权后运行 `--allow-llm`。

## 验收记录（2026-06-18 real LLM）

- 用户已明确授权把本地 dev DB 检索出来的 prompt context 发送给当前 LLM provider 执行 `--allow-llm`。
- 已运行真实 LLM provider 验收并更新报告：[REQ-025 P2 graph_edge prompt impact validation report](../../02-delivery-plans/01-specs/2026-06-18-req-025-graph-edge-prompt-impact-validation-report.md)。
- 报告状态：`External LLM: enabled`，`Validation Status: real-llm-run`。
- 机械链路结论：2 个样例满足 `graph_edge topN > 0`、`edge in fusion > 0`、`edge in packed > 0`，说明 `knowledge_edge` 已能回源 chunk 并进入最终 prompt。
- 质量结论：最终回答改善证据不足。部分 baseline / query understanding 已能回答，部分 graph_edge-only 场景仍回答“未找到足够参考来源”，无法证明“至少 2 个真实问题最终回答比 baseline 更完整”。
- 报告中的 `vector fallback trace count` 大于 0，因此本轮仍不能把 vector topN 解释为真实语义向量召回；具体计数以报告为准。
- 后续由 [REQ-026](REQ-026-p2-rag-effect-comparison-and-weak-recall-samples.md) 承接：构建更稳定的弱召回样例集、自动质量比较口径和真实效果回归。

## 事实源

- REQ-024 report: `docs/02-delivery-plans/01-specs/2026-06-18-req-024-p2-real-validation-report.md`
- REQ-025 report: `docs/02-delivery-plans/01-specs/2026-06-18-req-025-graph-edge-prompt-impact-validation-report.md`
- REQ-024 script: `scripts/validate_req024_p2_real_validation.py`
