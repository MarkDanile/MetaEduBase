# REQ-017 RRF / Weighted RRF 融合排序收口 — Spec

> Requirement: `docs/01-product-planning/05-requirements/REQ-017-p2-rrf-weighted-fusion.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-17-req-017-rrf-weighted-fusion-plan.md`
> Milestone: `docs/01-product-planning/02-milestones/02-growth-phase.md`

## Summary

当前 `RRFFusion` 已是 evidence AI Chat 生产链路默认融合器，`channel_weights` 参数已支持但未在生产配置中启用。本 spec 要求收口 weighted RRF 的生产配置、4 通道（vector / keyword / graph node / graph edge）排序验收、trace 完善和降级能力验证。

## Current Findings

| 发现 | 证据 | 影响 |
|------|------|------|
| `RRFFusion` 是生产默认 fusion | `ai_router._build_evidence_service()` L69 传入 `RRFFusion()` | 无需重写，只需配置化 |
| `channel_weights` 参数已存在 | `evidence_fusion.py` L96-98 | 只需在 router 注入配置，无需改融合器本身 |
| 权重已可影响排序 | `test_weighted_rrf_channel_weight_changes_rank` 覆盖 | 机制已验证，缺生产接入 |
| 4 通道中第 4 通道（graph_edge）待 REQ-018 | REQ-018 尚未完成 | 本任务先固化前 3 通道配置，预留第 4 通道接口 |
| `diagnostics` 已含 `retrieval_topn` / `fusion_topn` | `AIChatService` 已有 | 扩展 `fusion_weights` / `fusion_diagnostics` 字段即可 |

## Goals

- 确认并文档化 `RRFFusion` 作为 evidence AI Chat 默认 fusion 的事实（避免重复实现）。
- 生产配置入口支持 `channel_weights` 注入，默认 `{vector:1.0, keyword:1.0, graph_node:0.5}`。
- `diagnostics` 扩展，输出每个 fusion 输入通道的排名分值、最终 RRF 分值和排名。
- 单通道异常不影响整体回答（通道级 try/except 已部分存在，补齐 graph_edge 降级）。
- 真实样例证明正文 chunk 不被目录/简介系统性压过。

## Non-Goals

- 不引入 cross-encoder reranker。
- 不改前端引用 UI。
- 不新增外部搜索或向量引擎。
- 不重复实现已有 `RRFFusion`。
- 不在 REQ-018 完成前强行关闭 graph_edge 通道验收。
- 不修改 `SimpleFrequencyFusion`（保留为 fallback）。

## Proposed Design

### 1. Channel Weights 配置入口

在 `ai_router._build_evidence_service()` 增加可选权重参数，从环境变量或配置文件读取，默认：

```python
RRF_CHANNEL_WEIGHTS = {
    "vector": 1.0,
    "keyword": 1.0,
    "graph_node": 0.5,  # graph_node relevance calibrated lower than text chunks
    # graph_edge: 0.3   # REQ-018 后开启
}
```

Config 优先级：`环境变量 > .env > hardcoded defaults`。

### 2. Fusion Diagnostics 扩展

`PackedContext.diagnostics` 新增字段（向后兼容，现有调用方不报错）：

```python
class FusionDiagnostics(BaseModel):
    # 已有
    channel_top_k: dict[str, int] = {}
    fused_count: int = 0

    # 新增
    fusion_method: str = "RRF"  # or "Frequency"
    rrf_k: int | None = None
    rrf_weights_used: dict[str, float] = {}
    fusion_scores: dict[str, float] = {}  # evidence_id -> RRF score
    channel_ranks: dict[str, dict[str, int]] = {}  # channel -> evidence_id -> rank
```

### 3. Channel Degradation（通道降级）

每个通道在 `CompositeRetriever` 层已是独立调用，单通道抛异常被 `try/except` 捕获并返回空列表。本任务补充：

- 明确 `graph_node` 通道异常 → 返回空列表，继续其他通道。
- REQ-018 接入后 `graph_edge` 通道异常同样处理。
- 生产 service 的 `_retrieve()` 不因单通道失败整体中断。

### 4. Weighted RRF 测试覆盖

在 `test_evidence_fusion.py` 新增：

- 多通道不同权重场景下的排名验证（已有 `test_weighted_rrf_channel_weight_changes_rank`，确认保留）。
- 通道权重为 0 时该通道被完全忽略。
- `k` 值不同时 RRF 分值的量级差异验证。

### 5. Trace / 验收报告

在 REQ-014/REQ-015 真实 PG 样例基础上增加 RRF 排序分析：

- 各通道 topN + 排名。
- 融合前后排名对比表。
- 最终进入 prompt 的 evidence 及其 RRF 分值。

## Acceptance Criteria

- AC-1：`RRFFusion()` 保持为 evidence AI Chat 默认 fusion，生产链路无变化（向后兼容）。
- AC-2：`RRF_CHANNEL_WEIGHTS` 配置可注入，测试证明不同权重影响生产 service 的融合排序。
- AC-3：多通道重复命中同一 chunk 时合并 `channels`，并保留可解释排名依据。
- AC-4：单通道异常（模拟抛出）不影响整体回答，diagnostics 记录通道失败原因。
- AC-5：真实或 fixture 样例证明正文 chunk 不被目录/简介系统性压过（使用真实 PG 样例或 REQ-015 fixture）。
- AC-6：`diagnostics` 输出 RRF 分值、通道排名、权重配置，可复盘每个 evidence 的融合过程。
- AC-7：REQ-018 的 `graph_edge` 通道接入后，RRF 能正确处理第 4 通道，权重配置生效，并保留降级能力。

## Validation

- Backend:
  - `pytest tests/contexts/knowledge/test_evidence_fusion.py -q` — 全部通过
  - `pytest tests/contexts/knowledge/test_ai_chat_service.py -q` — 全部通过
  - 新增 weighted RRF 配置影响排序的集成测试
- Integration:
  - 有 PG 环境时跑 `/api/v1/ai/chat/evidence` 样例，验证 diagnostics 含 `fusion_scores` 和 `channel_ranks`
  - 记录各通道 topN、RRF 权重配置、融合后排名、最终 evidence
- Required:
  - `scripts/check-engineering-docs`
  - `ruff check app/contexts/knowledge/application/evidence_fusion.py`
  - `git diff --check`

## Risks

| 风险 | 缓解 |
|------|------|
| channel_weights 默认值不合理导致质量下降 | 先以实验性配置接入，通过 REQ-015 真实样例验证后固化为默认 |
| graph_edge 通道接入后权重需重新调优 | 4 通道权重默认值在 REQ-018 完成后再固化 |
| diagnostics 输出过多影响性能 | 只在 debug 模式或 diagnostics 请求头存在时输出完整分数 |
