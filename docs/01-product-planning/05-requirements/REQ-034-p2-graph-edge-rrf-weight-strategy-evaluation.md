# REQ-034: P2 graph_edge RRF 权重/策略调整评估

Status: 🟢 完成
Priority: P1
Milestone: P2
Source: REQ-033 follow-up（graph_edge 在真 vector 下价值有限，建议评估是否调整 RRF 权重/策略）
Related: REQ-018 / REQ-025 / REQ-030 / REQ-033 / TD-068 / TD-069

## 背景

REQ-033 基于 40 run 真实数据评估 P2 链路（graph_edge + weighted RRF）在真 vector 召回下的价值，判定**价值有限**：

- 指标 A（graph_edge 关联补足率）= 5/10（50% 样例 edge 进 packed）
- 指标 B（跨 section 上下文扩展）= 1/10
- 跨文档 grounding 扩展 = 0/10

根因：真 vector 召回下（TD-068+069 后）vector 通道已强，graph_edge 通道在 RRF 融合时多被挤出 fusion_topN，且 edge chunks 多为同文档关联、不扩展跨文档 grounding。**价值转移是技术演进的自然结果，非 bug。**

REQ-033 建议动作之一：登记需求评估是否下调 graph_edge RRF 权重 / 调整触发策略（如仅在 vector 召回弱时触发 edge），独立需求评估影响面。本任务即该 follow-up。

当前 graph_edge 配置事实：
- `RRFFusion` 默认权重 `{vector: 1.0, keyword: 1.0, graph_node: 0.5, graph_edge: 0.5}`（`ai_router.py:_RRF_DEFAULT_WEIGHTS`）
- graph_edge 通道**无条件触发**（`PgEdgeRecallChannel.recall` 每次 query 都跑，ILIKE 种子 → knowledge_edges → 关联节点）
- 可经 `RRF_CHANNEL_WEIGHTS` env var 覆盖

## 目标

基于真实数据评估三个候选调整策略的效果与可行性，给出明确建议。**不改主链路代码。**

三个候选策略：

1. **下调 graph_edge RRF 权重**（0.5 → 更低）：通过 weight sweep 评估 Metric A/B/跨文档 grounding/packed overlap 随权重的变化，判断是否存在更优权重或权重不敏感。
2. **仅在 vector 召回弱时触发 edge**（conditional trigger）：分析可行性与预期效果——当前 edge 无条件触发，若改为「vector 召回数 < 阈值 才触发 edge」，能否减少无效召回而不损失有价值样例。
3. **调整 ContextPacker 优先级**：分析可行性——当前 packer 按 score 排序 + `_ensure_graph_edge_source_block` 保证 edge source block 进 packed，若调整优先级能否提升 Metric A/B。

## 非目标

- 不修改主链路代码（RRFFusion / ContextPacker / AIChatService / recall_service / PgEdgeRecallChannel）
- 不重跑 REQ-026/027/028/029 真 LLM 报告
- 不强行让任何指标达标
- 不在本任务实施代码调整——若评估建议改代码，登记独立实现需求

## 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 脚本支持 graph_edge weight sweep：≥3 个 `use_graph_edge=True` 的 weight level（含已有 0.5/1.2，新增 0.3/0.7） | Scenario 定义 |
| AC-2 | 报告新增 "REQ-034" 章节：weight sensitivity 表（per weight：Metric A / Metric B / 跨文档 grounding / packed overlap vs off-baseline / fusion edge 计数） | 报告章节 |
| AC-3 | 章节含三个候选策略可行性分析（权重下调 / conditional trigger / packer 优先级），基于代码 + 数据 | 报告章节 |
| AC-4 | 章节含 REQ-018/025 历史验收影响面评估（graph_edge 通道验收 / 进 prompt 验收在权重调整下的成立性） | 报告章节 |
| AC-5 | 给出明确建议（保留 0.5 / 下调到 X / conditional trigger / packer 调整 / 关闭通道）；若建议改代码则登记独立实现需求 | 报告结论 |
| AC-6 | dry-run 与 `--allow-llm` 两种模式都可用；weight sweep 在 dry-run 下可复跑（retrieval 层指标不需要 LLM） | CLI 行为 |
| AC-7 | 不修改主链路代码；仅新增 scenario + 报告章节 | 代码 diff |

## 事实源

- REQ-033 评估报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation-report.md`
- REQ-033 requirement: `docs/01-product-planning/05-requirements/REQ-033-p2-chain-real-vector-value-evaluation.md`
- REQ-018: `docs/01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md`
- REQ-025: `docs/01-product-planning/05-requirements/REQ-025-p2-graph-edge-prompt-impact-and-real-llm-validation.md`
- RRF 实现: `packages/server-python/app/contexts/knowledge/application/evidence_fusion.py`
- RRF 权重配置: `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`（`_RRF_DEFAULT_WEIGHTS` / `_get_rrf_channel_weights`）
- graph_edge 召回: `packages/server-python/app/contexts/knowledge/application/recall_service.py`（`PgEdgeRecallChannel`）
- ContextPacker: `packages/server-python/app/contexts/knowledge/application/context_packer.py`
- 基线脚本: `scripts/validate_req024_p2_real_validation.py`

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-20 | 登记 | REQ-033 判定 graph_edge 价值有限，建议登记需求评估是否调整 RRF 权重/策略。本任务接力 |
| 2026-06-20 | 脚本改造 | `_default_scenarios` 新增 `graph_edge_w03`(0.3)/`graph_edge_w07`(0.7) 与已有 0.5/1.2 组成 5 点 weight sweep；`_render_req034_section` weight sensitivity 表 + 策略可行性 + REQ-018/025 影响面 + 建议判定 + 惰性检测 |
| 2026-06-20 | dry-run weight sweep | 5 weight level × 10 样例。**关键发现**：生产默认 0.5（及 0.3/0.7）下 graph_edge 召回 8 chunks/样例但 **0 进 fusion/packed**（惰性死权重）；仅 w=1.2（校验 boosting，非生产）下 edge 进 packed 50%。REQ-033 Metric A=5/10 实测于 w=1.2，高估了生产贡献 |
| 2026-06-20 | 评估收口 | 策略 1（下调权重）无效——0.5 已惰性，0.3 无差别。策略 2/3 主链路改动且收益存疑（REQ-033 证 edge 进 packed 亦不改善 Metric B/跨文档）。建议保留 0.5；登记 REQ-035 决策候选（禁用省成本 vs 上调使贡献）；REQ-025 验收基线补「默认惰性」说明。REQ-034 翻 🟢 完成 |
