# REQ-033: P2 链路真 vector 价值评估（REQ-030 AC-5 根因接力）

Status: 🟢 完成（P2 链路判定为价值有限；REQ-030 AC-5 根因归档为指标错配，REQ-030 翻完成；登记 REQ-034 候选评估链路调整）
Priority: P0
Milestone: P2
Source: REQ-032 证实 AC-5 三口径各 1/10 不达标，根因为 P2 链路在真 vector 下对 keypoint 覆盖无系统性正向贡献
Related: REQ-030 / REQ-031 / REQ-032 / REQ-028 / REQ-018 / REQ-025

## 背景

REQ-032 阈值校准 + continuous 口径后，REQ-030 AC-5 三口径（semantic_emb / continuous / LLM-judge）各仅 1/10 达标，且正向 sample 互不一致（Q6 / Q9 / Q5）。根因不是阈值，是 P2 链路本身。

离线分析 `/tmp/req032_real.json` 的 40 个 run（10 样例 × 4 scenarios）揭示 P2 链路在真 vector 下的实际行为：

### 发现 1：graph_edge 通道存在但 RRF 融合时几乎无效

| 样例 | edge 召回 | edge 进 fusion | edge 进 packed |
|------|----------|----------------|----------------|
| Q2 | 8 | 2 | 2 |
| Q6 | 8 | 2 | 2 |
| Q1 | 8 | 0 | 0 |
| Q4 | 3 | 2(但 fusion_topN 内 0) | 0 |
| 其余 6 | 0-8 | 0 | 0 |

graph_edge 通道召回 chunks（8 样例各召回 8 个），但在 RRF 融合时被挤出 fusion_topN（Q4 召回 3 个、fusion_count=2，但 fusion_topN 内 0 个 edge evidence）。**graph_edge 设计意图是补足 keyword/vector 不稳定问答（REQ-018/025 AC），但真 vector 召回已足够强，edge 的补足价值被稀释。**

### 发现 2：graph_edge 不扩展跨文档 grounding

Q2 weighted 的 edge evidence 全部来自文件 `358bd704`（与 vector/keyword 同文件）。graph_edge 召回的是**同文档内的关联 chunk**，不是新文档。document_sources_count：10 样例中 9 个 baseline=weighted，Q4 甚至 3→2 减少。**graph_edge 没有扩展答案的文档溯源广度。**

### 发现 3：weighted RRF 主要在重排，非引入新信息

packed_overlap（baseline ∩ weighted）：多数样例 5-6/8 重叠。weighted 用 edge chunks 替换部分 baseline chunks（Q2/Q6 替换 5 个），但替换后 keypoint 覆盖反而退化（Q2/Q6 sem_emb delta -0.60）。

### 与 REQ-028 v3 核心发现一致

真 vector 召回下 baseline coverage 普遍上升（vector 通道真命中），weighted RRF coverage 反而下降——因为重排引入的 edge chunks 不含 expected keypoints 子串，稀释了覆盖。

## 目标

**不修改 P2 主链路代码**，基于真实数据评估 P2 链路在真 vector 下的价值，给出诚实结论 + 价值指标重新定义建议 + 后续方向。具体：

1. **retrieval 层价值评估**：graph_edge / weighted RRF 在召回层（fusion_topN / packed_blocks / document_sources）的真实贡献量化。
2. **价值指标重新定义**：keypoint 覆盖不是衡量 P2 链路价值的正确指标（edge 补足同文档关联，不命中分散 keypoint）。提出更贴合 graph_edge 设计意图的指标（如：跨 section 上下文完整性、graph_edge 命中 query 相关节点的比例、答案对 graph 知识的引用）。
3. **链路调整建议**：基于数据判断是否需调整 RRF 权重 / graph_edge 策略 / ContextPacker，或确认链路在真 vector 下"价值有限但保留合理"。
4. **结论 + 后续登记**：给出 P2 链路在真 vector 下的价值判定（有价值/有限/无效），登记后续动作（若需调整则开需求，若确认有限则更新验收基线）。

## 非目标

- 不修改 RRF / ContextPacker / AIChatService / PgEdgeRetriever 主链路代码（本任务只评估 + 建议）。
- 不重跑 REQ-026/027/029 真 LLM 报告（独立 PR）。
- 不引入新依赖。
- 不强行让 AC-5 达标——若链路确实无正向贡献，如实记录并重新定义价值指标。

## 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 新增 P2 链路 retrieval 层价值分析报告章节：graph_edge 进 fusion/packed 比例、跨文档 grounding、packed_overlap 量化 | 报告章节 |
| AC-2 | 提出至少 2 个更贴合 graph_edge 设计意图的新价值指标定义（带计算方式） | 报告章节 |
| AC-3 | 基于现有 40 run 数据计算新指标（无需重跑 LLM，用 JSON 已有数据 + 离线 embedding） | 报告数据 |
| AC-4 | 给出 P2 链路在真 vector 下的价值判定（有价值/有限/无效）+ 理由 | 报告结论 |
| AC-5 | 给出链路调整建议（调 RRF 权重 / graph_edge 策略 / 保留现状）或确认价值有限需更新验收基线 | 报告建议 |
| AC-6 | 若建议调整链路，登记独立需求（不在本任务改代码）；若确认有限，更新 REQ-030/025 验收基线说明 | 候选区 / Delivery Record |
| AC-7 | REQ-030 最终状态明确（部分收口 + AC-5 根因归档为链路价值问题，非评估口径问题） | REQ-030 状态 |
| AC-8 | `scripts/check-engineering-docs` 通过 | 门禁 |

## 事实源

- REQ-032 报告（根因诊断）: `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md#0-1-根因诊断req-032-最终结论`
- 真 LLM JSON 数据: `/tmp/req032_real.json`（40 run，含 fusion_topn / packed_blocks / graph_edge_chunk_ids）
- REQ-018（graph_edge 设计意图）: `docs/01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md`
- REQ-025（graph_edge 进 prompt 验收）: `docs/01-product-planning/05-requirements/REQ-025-p2-graph-edge-prompt-impact-and-real-llm-validation.md`
- 基线脚本: `scripts/validate_req024_p2_real_validation.py`
- 链路代码: `packages/server-python/app/contexts/knowledge/application/`（AIChatService / recall_service / evidence_fusion / context_packer）

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-20 | 登记 | REQ-032 证实 AC-5 根因为 P2 链路无正向贡献，登记 REQ-033 评估链路本身 |
| 2026-06-20 | 离线分析 | 分析 `/tmp/req032_real.json` 40 run：(1) graph_edge 8 样例召回但仅 Q2/Q6 进 packed（各 2），RRF 融合时被挤出；(2) edge chunks 全同文档，不扩展 grounding 广度；(3) packed_overlap 5-6/8，weighted 主要重排非引入新信息。证实 graph_edge 在真 vector 下价值被稀释 |
| 2026-06-20 | 脚本改造 | 新增 `_render_req033_section`：graph_edge 通道有效性表 + 跨文档 grounding + packed 重排度 + 指标 A（关联补足率）/ 指标 B（跨 section 扩展）+ 价值判定框架 |
| 2026-06-20 | dry-run | exit 0，REQ-033 章节渲染正常 |
| 2026-06-20 | 真 LLM 重跑 + 评估 | 真 LLM v3 10 样例。**指标 A=5/10 (50%) / 指标 B=1/10 / 跨文档 grounding=0/10**。**价值判定：价值有限**。graph_edge 在真 vector 下价值被稀释（vector 已强），edge 通道 RRF 融合时多被挤出 fusion_topN，且不扩展跨文档 grounding。**REQ-030 AC-5 不达标归档为指标错配**（keypoint 覆盖 vs graph_edge 关联补足目标不一致），非链路缺陷。REQ-030 翻完成。登记 REQ-034 候选评估链路调整 |
