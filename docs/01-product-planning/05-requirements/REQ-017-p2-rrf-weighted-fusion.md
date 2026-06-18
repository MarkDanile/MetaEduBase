# REQ-017: P2 RRF / Weighted RRF 融合排序

Status: 🔵 Ready
Priority: P0
Milestone: P2
Source: P2-RRF Open Item
Related: REQ-013 / REQ-015 / REQ-018

## Goal

收口现有 RRF 能力，而不是从零实现 RRF。当前 evidence AI Chat 生产链路已经默认注入 `RRFFusion()`，并且 `RRFFusion` 已支持 `channel_weights`。本需求的重点是把它推进到 P2 可验收状态：配置化 weighted RRF、覆盖 4 通道召回后的真实排序样例、补齐 trace / 验证报告，并为后续 reranker 留接口。

## Current Code Facts

| 能力 | 当前状态 | 证据 |
|------|----------|------|
| RRF 实现 | 已实现 | `packages/server-python/app/contexts/knowledge/application/evidence_fusion.py` 中 `RRFFusion` 按 `1 / (k + rank)` 聚合排名。 |
| Weighted RRF 基础 | 已实现但未生产配置化 | `RRFFusion(k=60, channel_weights={...})` 已支持权重；`test_weighted_rrf_channel_weight_changes_rank` 覆盖权重改变排序。 |
| 生产默认接入 | 已接入 | `ai_router._build_evidence_service()` 默认传入 `evidence_fusion=RRFFusion()`；`test_default_evidence_service_uses_rrf_and_context_packer` 已覆盖。 |
| RRF 阈值适配 | 已实现 | `AIChatService._uses_absolute_score_threshold()` 避免 RRF 小分值被 `min_evidence_score=0.3` 误过滤。 |
| Trace | 已部分实现 | `diagnostics.retrieval_topn` / `fusion_topn` / `packed_blocks` 已返回；仍需补齐 weighted 配置、4 通道场景和真实验收记录。 |

## Scope

- 明确并记录当前 `RRFFusion` 已接入生产 evidence AI Chat 链路的事实，避免重复实现。
- 增加 weighted RRF 的生产配置入口，至少支持 chunk vector、chunk keyword、graph node、graph edge 等通道权重。
- 保持 `EvidenceItem`、sources、document_sources 和 diagnostics 兼容。
- 保留单通道失败降级能力，新增图谱关系通道后也不能拖垮整体问答。
- 补真实样例回归：目录 / 简介 chunk、正文 chunk、graph node / graph edge evidence 混排时，正文 evidence 不应被系统性压低。
- 补 trace / 验收报告：各通道 topN、融合前排名、融合后 topN、融合分数、进入 prompt 的 evidence。

## Non-Goals

- 不引入 cross-encoder reranker。
- 不改前端引用 UI。
- 不新增外部搜索或向量引擎。
- 不重复实现已有 `RRFFusion` 类。
- 不在 REQ-018 完成前强行关闭 4 通道排序验收。

## Acceptance

- AC-1：确认并保留 `RRFFusion()` 作为 evidence AI Chat 默认 fusion；如新增可切换策略，默认仍可通过配置明确。
- AC-2：多通道重复命中同一 chunk 时能合并 channels，并保留可解释排名依据。
- AC-3：单通道异常不影响整体回答。
- AC-4：真实样例能证明正文 chunk 不被目录 / 简介 chunk 系统性压过。
- AC-5：trace 可复盘每个 evidence 的通道来源和融合分数。
- AC-6：weighted RRF 权重可配置，并有测试证明配置会影响生产 service 的融合排序。
- AC-7：REQ-018 的 graph edge 通道接入后，RRF / weighted RRF 能正确处理第 4 通道，并保留降级能力。

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-17 | Slice 1-3 完成 | PR #325 merge：RRFFusion 生产接入 + channel_weights 配置入口 + fusion diagnostics + 通道降级；测试覆盖 AC-1/2/3/6 |
| 2026-06-18 | Slice 4 占位 | 验收报告 placeholder 已产出 |
| 2026-06-18 | Slice 4 真实PG验收 | 4通道RRF融合正常，AC-4/5/7通过；验收报告已填充 |

## Delivery Links

- Backlog: `docs/01-product-planning/04-backlog.md`
- Milestone: `docs/01-product-planning/02-milestones/02-growth-phase.md`
