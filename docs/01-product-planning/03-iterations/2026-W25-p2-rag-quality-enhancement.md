# Iteration 2026-W25: P2 RAG 质量增强

Status: 🟡 Doing
Dates: 2026-W25
Goal: 在 REQ-012 多路 evidence 骨架之上，补齐召回后上下文组装、排序演进和真实问答 grounding，优先解决“资料库有正文但回答证据不足”的问题。

## Scope

| ID | 类型 | 状态 | 摘要 | 验收 |
|----|------|------|------|------|
| REQ-013 | REQ | 🟢 Done | RAG Context Packer 与回答 grounding 增强 | PR #305 已合并；命中 chunk 后按相邻 chunk / 同 section 组装 prompt。真实 PG 样例与最终 grounding 验收转入 REQ-014。 |
| BUG-007 | BUG | 🔵 Ready | pdf_parser sections path 错乱 | 修复 section path 计算，降低后续 section expansion 依赖坏 metadata 的风险。 |
| REQ-014 | REQ | 🟢 Done | RAG 真实 PG 样例、数据回填与回答 grounding 验收 | PR #308 squash merge：spec + plan + 一次性验收脚本 + 占位报告 + 跨事实源同步。follow-up：下个 PR 跑真 PG |
| REQ-015 | REQ | 🟢 Done | RAG 生产链路 grounding 与真实验收收口 | PR #314 merge `4d78667`：BUG-009 修复后真 dev DB prompt 前 context 已拿到 Python 正文；用户授权后完整 DeepSeek ask 已通过。 |
| BUG-009 | BUG | 🟢 Done | AI Chat 真实 PG 链路未把相关正文 chunk 送入 prompt | PR #314 merge `4d78667`：已修共享 `AsyncSession` 并发、RRF 阈值、lexical supplement 排序和邻居 TOC 识别；prompt 前和完整 ask 真实验收均通过。 |
| REQ-018 | REQ | 🟢 Done | P2 4 通道并行召回与图谱关系召回 | Slice 1+2+3 PR #333/#334/#335 已合并；Slice 4 真实 PG 验收已补，graph_edge 激活且 evidence_id bug 修复；AC-5 弱召回补足样例由 REQ-024 接力。 |
| REQ-017 | REQ | 🟢 Done | P2 RRF / Weighted RRF 融合排序收口 | PR #325 + 真实 PG 验收报告已收口；4 通道 RRF 融合正常，AC-1~7 通过。 |
| REQ-016 | REQ | 🟢 Done | P2 LLM 混合 NER / Query Understanding | PR #328/#329/#330 已合并；混合 Query Understanding、expanded_query 和 retriever 接入已收口，真实 PG + LLM 效果验收由 REQ-024 接力。 |
| REQ-024 | REQ | 🔴 Blocked | P2 真实验收补强：Query Understanding 与 graph_edge 补足样例 | 已产出 dry-run 报告：diagnostics 可复跑，graph_edge 进入 fusion；TD-068 已澄清 vector fallback；REQ-025 已补 graph_edge 进入 prompt，但真实质量改善仍需 REQ-026 接力。 |
| TD-068 | TD | 🟢 Done | AI Chat 真实验证中 query embedding 为空导致向量召回有效性不明 | PR #355 已合并；diagnostics 已透出 `embedding_fallback`，REQ-024 报告新增 `vector fallback` 计数；确认当前 vector topN 是 keyword fallback。 |
| REQ-025 | REQ | 🟣 待验证 | P2 graph_edge 进入 prompt 与真实 LLM 效果验收收口 | 2 个 graph_edge 样例已进入 packed context，真实 LLM provider 已跑；但最终回答相对 baseline 明显改善的证据不足。 |
| REQ-026 | REQ | 🟡 部分收口 | P2 RAG 效果比较与弱召回样例集收口 | PR #358 squash merge `930589b`：spec+plan+5 条弱召回样例集+扩展脚本+真 LLM 报告。机制 5/5 ✅；prompt 3/5 ✅；质量 1/5 ❌ (AC-1 未达成，Q4 退化 -0.60)；登记 REQ-027 接力 |

## Out of Scope

- 不在本迭代引入 Elasticsearch、Milvus、Neo4j 或完整 GraphRAG 框架。
- 不把 P2 所有 RAG 能力一次性做完；每次只推进有明确样例和验收的切片。
- 不把里程碑 open item 直接当开发任务；必须映射到 REQ / BUG / TD / DOC 后再进入工作台。

## Review

| 信号 | 结论 | 后续任务 |
|------|------|----------|
| REQ-012 后仍出现“只拿目录证据”的回答 | 当前缺口集中在 fusion 后的上下文包装，不是单纯增加召回通道 | REQ-013 |
| section metadata 近期仍有 path 错乱问题 | Context Packer 首版必须有 chunk_index fallback，不能强依赖 section_path | BUG-007 / REQ-013 |
| REQ-013 / BUG-007 合并后仍缺真实 PG 样例 backfill | 当前需要把机制测试推进到真实样例和最终回答验收 | REQ-014 |
| REQ-014 只完成 tooling，生产链路仍缺 ContextPacker 注入和 diagnostics | 当前需要把机制真正接入默认 AI Chat endpoint，并让脚本能读到 trace | REQ-015 |
| REQ-015 真实样例截停在 prompt 前仍缺正文 chunk | BUG-009 已把瓶颈收口：`fusion_topN[1]` 命中 `数据类型和变量` 正文，packed context 含基本类型证据，完整 DeepSeek ask 回答正确 | BUG-009 / REQ-015 已由 PR #314 收口 |
| P2 已有 PostgreSQL tsvector 基础 | 当前先用既有 PostgreSQL 能力提升质量，不急于换 ES / Milvus / Neo4j | P2-SEARCH / REQ-013；P2-RRF 仍留在里程碑 Open Items，待真实瓶颈明确后再映射稳定任务编号 |
| P2 正式进入增长期 | 重点不再是证明 P1 闭环存在，而是提升真实问答质量和可解释检索链路 | REQ-018 / REQ-017 / REQ-016 代码能力已接入；TD-068 已让 vector fallback 可见；REQ-025 已完成 graph_edge prompt-level 与真实 LLM run；REQ-026 继续收口真实效果比较 |
