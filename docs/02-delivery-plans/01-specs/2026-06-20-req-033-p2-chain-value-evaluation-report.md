# REQ-033 P2 链路真 vector 价值评估报告

> Status: 🟢 完成
> Created: 2026-06-20
> Requirement: `docs/01-product-planning/05-requirements/REQ-033-p2-chain-real-vector-value-evaluation.md`
> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-033-p2-chain-value-evaluation.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-033-p2-chain-value-evaluation-plan.md`
> 数据源: `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md`（REQ-033 章节，真 LLM v3 10 样例）

## 1. 评估目标

REQ-032 证实 P2 链路在真 vector 下对 keypoint 覆盖无系统性正向贡献（AC-5 三口径各 1/10）。本评估回答：**P2 链路（graph_edge + weighted RRF）在真 vector 召回下到底有没有价值？价值体现在哪？是否需调整？**

不改主链路代码，基于真实数据评估 + 重新定义价值指标 + 给出建议。

## 2. 离线分析发现（基于 40 run 真实数据）

### 2.1 graph_edge 通道在 RRF 下几乎无效

8/10 样例 graph_edge 召回 7-8 个 chunks，但进 packed 的只有 5/10（Q1/Q2/Q3/Q6/Q10），且多数仅 1-2 个。Q7/Q8/Q9 召回 7-8 个但 RRF 融合时全被挤出 fusion_topN。

### 2.2 graph_edge 不扩展跨文档 grounding

10 样例中 **0 个** edge 带来新文档。edge chunks 全来自 vector/keyword 已召回的同文件。document_sources_count：9/10 样例 baseline=weighted，Q4 甚至 3→2 减少。

### 2.3 weighted RRF 主要重排，非引入新信息

packed_overlap（baseline ∩ weighted）：多数 5-6/8 重叠。weighted 用 edge chunks 替换部分 baseline chunks，但替换后跨 section 上下文反而收缩（Q1/Q2/Q4/Q6 section 增量 -1~-2），仅 Q3 +1。

## 3. 价值指标（贴合 graph_edge 设计意图）

keypoint 覆盖不是衡量 graph_edge 价值的正确指标。提出两个贴合「补足关联上下文」意图的指标：

| 指标 | 定义 | 结果 |
|------|------|------|
| A. graph_edge 关联补足率 | weighted scenario 中 packed 含 graph_edge 通道 chunk 的样例比例 | **5/10 (50%)** |
| B. 跨 section 上下文扩展 | weighted distinct section_path 数 > baseline 的样例比例 | **1/10 (10%)** |
| 补充. 跨文档 grounding 扩展 | edge 带来新文档的样例比例 | **0/10 (0%)** |

## 4. 价值判定

**判定：价值有限**

依据（按 spec §5.3 框架）：
- 指标 A = 50% > 0 但 < 理想（半数样例 edge 进 packed）
- 指标 B = 10%（多数样例上下文无扩展甚至收缩）
- 跨文档 grounding = 0%（edge 不扩展溯源广度）

**根因**：graph_edge 在 fake vector 时代（REQ-018/025 验收）有价值——keyword 兜底主导召回，edge 补足的关联 chunk 能进 packed 并改善答案。真 vector 召回下（TD-068+069 后）vector 通道已强，edge 通道在 RRF 融合时多被挤出 fusion_topN，且 edge chunks 多为同文档关联、不扩展跨文档 grounding。**价值转移是技术演进的自然结果，非 bug。**

## 5. 结论

1. **REQ-030 AC-5 不达标是指标错配，非链路缺陷**：keypoint 覆盖衡量「答案命中分散关键词」，graph_edge 补足「同文档关联上下文」，两者目标不一致。继续调阈值无法让 AC-5 达标（REQ-032 已证实）。
2. **P2 链路在真 vector 下价值有限但保留合理**：graph_edge 仍有 50% 样例进 packed，提供同文档关联上下文；只是不再像 fake vector 时代那样显著提升 keypoint 覆盖。
3. **评估口径已充分**：四口径（substring/semantic/semantic_emb/llm_judge）+ continuous + Spearman + retrieval 层指标（A/B/跨文档），足以如实反映 P2 链路表现。

## 6. 建议动作

| 动作 | 说明 | 归属 |
|------|------|------|
| REQ-030 翻完成 | 评估口径充分 + AC-5 根因归档为指标错配 | 本任务 |
| 登记 REQ-034 候选 | 评估是否下调 graph_edge RRF 权重 / 调整触发策略（如仅在 vector 召回弱时触发 edge），独立需求评估影响面 | 候选区 |
| 更新 REQ-025 验收基线说明 | graph_edge 进 prompt 验收在 fake vector 时代成立；真 vector 下价值转移，验收基线补充说明 | REQ-025 Delivery Record |

## 7. 非目标（确认未做）

- 未修改 RRF / ContextPacker / AIChatService / PgEdgeRetriever 主链路代码
- 未重跑 REQ-026/027/029 真 LLM 报告
- 未强行让 AC-5 达标

## 8. 数据可复现

```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out <report.md> --json-out <data.json> \
  --report-title "REQ-033 v3 re-run" --allow-llm --semantic-emb-threshold 0.35
```

REQ-033 章节在报告末尾，含完整 per-sample 三表 + 指标汇总 + 判定。
