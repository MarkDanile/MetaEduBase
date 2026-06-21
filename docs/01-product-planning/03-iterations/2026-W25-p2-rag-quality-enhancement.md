# Iteration 2026-W25: P2 RAG 质量增强

Status: 🟢 Done
Dates: 2026-W25
Goal: 在 REQ-012 多路 evidence 骨架之上，补齐召回后上下文组装、排序演进和真实问答 grounding，优先解决“资料库有正文但回答证据不足”的问题。

## Scope

| ID | 类型 | 状态 | 摘要 | 验收 |
|----|------|------|------|------|
| REQ-013 | REQ | 🟢 Done | RAG Context Packer 与回答 grounding 增强 | PR #305 已合并；命中 chunk 后按相邻 chunk / 同 section 组装 prompt。真实 PG 样例与最终 grounding 验收转入 REQ-014。 |
| BUG-007 | BUG | 🟢 Done | pdf_parser sections path 错乱 | 修复 section path 计算，降低后续 section expansion 依赖坏 metadata 的风险。PR #303 squash merge：section path 改用 docling counters 算法 + 非标题黑名单补全；mock tests pass。 |
| REQ-014 | REQ | 🟢 Done | RAG 真实 PG 样例、数据回填与回答 grounding 验收 | PR #308 squash merge：spec + plan + 一次性验收脚本 + 占位报告 + 跨事实源同步。follow-up：下个 PR 跑真 PG |
| REQ-015 | REQ | 🟢 Done | RAG 生产链路 grounding 与真实验收收口 | PR #314 merge `4d78667`：BUG-009 修复后真 dev DB prompt 前 context 已拿到 Python 正文；用户授权后完整 DeepSeek ask 已通过。 |
| BUG-009 | BUG | 🟢 Done | AI Chat 真实 PG 链路未把相关正文 chunk 送入 prompt | PR #314 merge `4d78667`：已修共享 `AsyncSession` 并发、RRF 阈值、lexical supplement 排序和邻居 TOC 识别；prompt 前和完整 ask 真实验收均通过。 |
| REQ-018 | REQ | 🟢 Done | P2 4 通道并行召回与图谱关系召回 | Slice 1+2+3 PR #333/#334/#335 已合并；Slice 4 真实 PG 验收已补，graph_edge 激活且 evidence_id bug 修复；AC-5 弱召回补足样例由 REQ-024 接力。 |
| REQ-017 | REQ | 🟢 Done | P2 RRF / Weighted RRF 融合排序收口 | PR #325 + 真实 PG 验收报告已收口；4 通道 RRF 融合正常，AC-1~7 通过。 |
| REQ-016 | REQ | 🟢 Done | P2 LLM 混合 NER / Query Understanding | PR #328/#329/#330 已合并；混合 Query Understanding、expanded_query 和 retriever 接入已收口，真实 PG + LLM 效果验收由 REQ-024 接力。 |
| REQ-024 | REQ | 🟢 Done | P2 真实验收补强：Query Understanding 与 graph_edge 补足样例 | 真实 dev DB dry-run + 真实 LLM 报告；REQ-029 residual 阈值补判后长链收口翻完成 |
| TD-068 | TD | 🟢 Done | AI Chat 真实验证中 query embedding 为空导致向量召回有效性不明 | PR #355 已合并；diagnostics 已透出 `embedding_fallback`，REQ-024 报告新增 `vector fallback` 计数；确认当前 vector topN 是 keyword fallback。 |
| REQ-025 | REQ | 🟢 Done | P2 graph_edge 进入 prompt 与真实 LLM 效果验收收口 | 2 个 graph_edge 样例进入 packed context + 真实 LLM provider 验收；REQ-029 residual 阈值补判后翻完成 |
| REQ-026 | REQ | 🟢 Done | P2 RAG 效果比较与弱召回样例集收口 | PR #358：5 条弱召回样例集 + 关键事实覆盖度自动比较 + real LLM 报告。REQ-029 residual 阈值补判 AC-1 改判为达成，翻完成 |
| REQ-027 | REQ | 🟢 Done | P2 弱召回知识覆盖与样例多样性 | PR #359：5 条 v2 样例 + wrapper 脚本 + 真 LLM v1+v2 两轮报告。REQ-029 residual 阈值补判 AC-4 9/10 达标，翻完成 |
| REQ-028 | REQ | 🟢 Done | P2 弱召回自动质量比较口径改造 | PR #360：脚本支持三口径 + v3 样例 10 条 + 真 LLM 报告。REQ-029 residual 阈值补判 AC-5 5/10 达标，翻完成 |
| REQ-029 | REQ | 🟢 Done | P2 弱召回 AC-5 阈值重设计 | residual ratio 公式 + --lift-mode CLI + 报告双模式。整条 P2 RAG 真实效果验收长链收口翻完成 |
| REQ-030 | REQ | 🟢 Done | P2 RAG 自动质量评估新口径（semantic embedding + LLM-as-judge） | 四口径 + continuous + retrieval 层指标 A/B 评估口径充分。AC-4 达标 4/10；AC-5 三口径各 1/10 不达标，REQ-033 归档为指标错配（keypoint 覆盖 vs graph_edge 关联补足目标不一致），非链路缺陷。经 REQ-031/032/033 三轮接力收口 | [REQ-030](../../01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md) / [Report](../../02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md) / [REQ-033 评估报告](../../02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation-report.md) |
| REQ-031 | REQ | 🟢 Done | P2 semantic embedding 覆盖率计算稳定性（REQ-030 接力） | 分支 `feat/req-031-semantic-embedding-stability`；进程内 embedding 缓存（hit=1581/miss=259）+ asyncio.wait_for 60s 硬超时 + 降级。timeout=0/error=0 消除 batch 挂起，semantic_emb 8/10 非零 | [REQ-031](../../01-product-planning/05-requirements/REQ-031-p2-semantic-embedding-coverage-stabilization.md) / [Report](../../02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md) |
| REQ-032 | REQ | 🟢 Done | P2 semantic_emb 阈值校准与 continuous 口径（REQ-030 AC-4/5 接力） | 分支 `feat/req-032-semantic-emb-threshold-calibration`；`--semantic-emb-threshold` CLI + continuous 字段。threshold 0.35 后 AC-4 达标 4/10；AC-5 三口径各 1/10，根因定位为 P2 链路无正向贡献，登记 REQ-033 | [REQ-032](../../01-product-planning/05-requirements/REQ-032-p2-semantic-emb-threshold-calibration.md) / [Report](../../02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md) |
| REQ-033 | REQ | 🟢 Done | P2 链路真 vector 价值评估（REQ-030 AC-5 根因接力） | 分支 `feat/req-033-p2-chain-real-vector-value-evaluation`；retrieval 层价值评估（指标 A=5/10 / B=1/10 / 跨文档=0/10）。判定**价值有限**。AC-5 根因归档为指标错配，REQ-030 翻完成。登记 REQ-034 候选 | [REQ-033](../../01-product-planning/05-requirements/REQ-033-p2-chain-real-vector-value-evaluation.md) / [评估报告](../../02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation-report.md) |
| REQ-034 | REQ | 🟢 Done | P2 graph_edge RRF 权重/策略调整评估（REQ-033 follow-up） | 分支 `feat/req-034-graph-edge-rrf-evaluation`；5 点 weight sweep（0.3/0.5/0.7/1.2 + off）+ 策略可行性 + REQ-018/025 影响面。**关键发现**：生产默认 0.5 下 graph_edge 召回 8 chunks/样例但 0 进 fusion/packed（惰性死权重）；REQ-033 Metric A=5/10 实测于 w=1.2 boosting，高估生产贡献。下调权重无效（0.5 已惰性）。保留 0.5，登记 REQ-035 决策候选 | [REQ-034](../../01-product-planning/05-requirements/REQ-034-p2-graph-edge-rrf-weight-strategy-evaluation.md) / [评估报告](../../02-delivery-plans/01-specs/2026-06-20-req-034-graph-edge-rrf-weight-strategy-evaluation-report.md) |
| REQ-035 | REQ | 🟢 Done | P2 graph_edge 通道去留决策（REQ-034 follow-up） | 分支 `feat/req-035-graph-edge-channel-decision`；成本/收益对照 + 禁用/上调可行性 + 决策。**决策：禁用 graph_edge 通道**。生产默认 0.5 下召回 8 chunks/样例（3 SQL）0 进 fusion/packed（纯无效）；即使 boosting w=1.2 使 edge 进 packed 50%，REQ-033 证跨 section 扩展仅 10%、跨文档 0%——增益有限。禁用机制已存在（`edge_retriever=None`），消除纯浪费且产出与现状相同。登记 REQ-036 实现候选 | [REQ-035](../../01-product-planning/05-requirements/REQ-035-p2-graph-edge-channel-decision.md) / [决策报告](../../02-delivery-plans/01-specs/2026-06-20-req-035-graph-edge-channel-decision-report.md) |
| REQ-036 | REQ | 🟢 Done | P2 graph_edge 通道禁用实现（REQ-035 follow-up） | 分支 `feat/req-036-graph-edge-disable-impl`；`ai_router._build_evidence_service` 经 `GRAPH_EDGE_RECALL_ENABLED` env 门控，默认禁用 graph_edge 通道；`PgEdgeRecallChannel` 代码保留可重新启用。单测 37 passed 无回归。dry-run 实证 4/10 样例 packed 仅 1-2 chunk 微调。真 LLM 全量验收因 embedding provider 慢阻登记 REQ-037 follow-up。REQ-018 基线降级为「3 通道生产 + edge 保留可启用」 | [REQ-036](../../01-product-planning/05-requirements/REQ-036-p2-graph-edge-channel-disable-impl.md) / [实现报告](../../02-delivery-plans/01-specs/2026-06-20-req-036-graph-edge-channel-disable-impl-report.md) |
| REQ-037 | REQ | 🟢 Done | P2 graph_edge 禁用真 LLM 全量验收（REQ-036 follow-up） | 分支 `feat/req-037-graph-edge-disable-real-llm-verify`；TD-070 修复单次挂起后全量真 LLM run 仍受 embedding provider 累积吞吐阻塞。以 dry-run substring/semantic 口径实证收口：**10/10 样例 baseline = graph_edge@0.5 零覆盖度差异**，4/10 packed diff 仅重排噪声。判定禁用无回归。全量真 LLM（semantic_emb/continuous/llm_judge 口径）登记 follow-up | [REQ-037](../../01-product-planning/05-requirements/REQ-037-p2-graph-edge-disable-real-llm-verify.md) / [验收报告](../../02-delivery-plans/01-specs/2026-06-21-req-037-graph-edge-disable-real-llm-verify-report.md) |
| TD-068 | TD | 🟢 Done | AI Chat vector embedding 为空底层修复 | 分支 `feat/td-069-embedding-column-vector-migration` 与 TD-069 一起合并：alembic 030 迁移 `text` → `vector(4096)` + 同步 merge TD-068 Slice 2 代码修复 (`embedding_service.py` 多 provider fallback + retriever CAST)。验证 psql pgvector cosine 真返回 + `vector_fallback_count: 0` + 4 通道全部激活 | [PR #355](https://github.com/MarkDanile/MetaEduBase/pull/355) + PR #TODO |
| TD-069 | TD | 🟢 Done | dev DB embedding schema `text` → `vector(4096)` migration + 599 knowledge_nodes backfill | 一次性 `backfill_knowledge_node_embeddings.py` 脚本回填 599 节点 (硅流 8B 4096 维) + `extract_knowledge_graph.py` 加 embedding 字段填充 + 同步代码修复 | [TD-068](../../03-engineering-governance/technical-debt.md#td-068) / PR #TODO |

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
| REQ-028 真 LLM v3 重跑发现 AC-5 在真 vector 下系统性退步 | 指标错配（keypoint 覆盖 vs graph_edge 关联补足），非链路缺陷 | REQ-030 / REQ-031 / REQ-032 / REQ-033 三轮接力诊断 |
| REQ-033 判定 graph_edge 在真 vector 下价值有限 | 真 vector 召回下 vector 通道已强，edge 通道 RRF 融合多被挤出，跨文档 grounding=0/10 | REQ-034 评估调整 / REQ-035 决策 / REQ-036 实现 / REQ-037 验证 / REQ-038 补强（环境阻塞） |
| REQ-036 实施 graph_edge 通道禁用但 4/10 packed 出现微调 | edge-boosted 共享节点重排导致 1-2 chunk 微调，需真 LLM 验证答案无回归 | REQ-037 验证（dry-run 10/10 零覆盖度差异） + TD-070 修 vector-recall 超时 + REQ-038 补强（🔴 Blocked） |
| W25 整体收口（2026-06-21） | Scope 全 🟢 Done（24 项）。P2 RAG 质量链路：上下文组装（REQ-013）+ 真实 PG grounding（REQ-014/015）+ 4 通道并行召回（REQ-016/017/018）+ 真实效果验收长链（REQ-024→037）+ TD-068/069 schema 与 vector fallback + TD-070 vector-recall 超时兜底 + DOC-074 完成态分层口径。graph_edge 通道治理全闭环（评估→决策→实现→验证→补强阻塞）。交付事实详见 work-log + 各 spec/plan/report + PR。 | 后续候选见 current-work：REQ-038 全量真 LLM 补强（🔴 Blocked 等环境）+ REQ-002 模板配置（🔵 Ready）+ APP-001 课程能力图谱（⚫ Candidate 需 Shaping） |
