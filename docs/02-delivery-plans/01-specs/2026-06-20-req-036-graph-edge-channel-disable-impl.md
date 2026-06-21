# REQ-036 Spec: P2 graph_edge 通道禁用实现

> Status: 🟢 完成
> Created: 2026-06-20
> Source: REQ-035 follow-up（决策禁用 graph_edge 通道）
> Requirement: `docs/01-product-planning/05-requirements/REQ-036-p2-graph-edge-channel-disable-impl.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-036-graph-edge-channel-disable-impl-plan.md`

## 1. Problem Statement

REQ-035 决策禁用 graph_edge 通道。本任务实施该决策：生产 builder `ai_router._build_evidence_service` 经 env 门控 `edge_retriever` 注入，默认禁用。保留 `PgEdgeRecallChannel` 代码可重新启用。

REQ-036 实证补充：生产默认 0.5 下 4/10 样例 packed 因 edge-boosted 共享节点重排而变化（非纯 no-op），故需真 LLM 验收确认无答案回归。

当前架构事实（已 codegraph 确认）：

- `_build_evidence_service`（`ai_router.py:85`）是生产 builder，固定注入 `edge_retriever=PgEdgeRetriever()`。
- `_safe_retrieve_edge`（`ai_chat_service.py:469`）在 `edge_retriever is None` 时直接 `return []`——禁用机制已存在。
- 测试 `test_ai_chat_router_req015.py` 调 `_build_evidence_service` 但不断言 `edge_retriever`，默认禁用不破坏现有测试。
- 校验脚本 `runner._build_service` 独立构造 service（`edge_retriever=PgEdgeRetriever() if scenario.use_graph_edge else None`），不受生产 gate 影响——仍支持 edge scenario 评估。

## 2. Goal

生产禁用 graph_edge 通道（默认 off），保留代码可重新启用，真 LLM 验收无回归。

## 3. Non-Goals

- 不删 `PgEdgeRecallChannel` / `PgEdgeRetriever` 代码
- 不改 RRF 默认权重 / ContextPacker / recall_service / 校验脚本
- 不调整 graph_node 通道

## 4. Acceptance Criteria

见 requirement AC-1 ~ AC-6。

## 5. Architecture

### 5.1 config 门控（核心改动）

`ai_router.py` 新增 helper（镜像 `_get_rrf_channel_weights` 模式）：

```python
def _graph_edge_recall_enabled() -> bool:
    """REQ-036: graph_edge 通道生产门控。默认 false（REQ-035 决策禁用）。

    env GRAPH_EDGE_RECALL_ENABLED 真值（"1"/"true"/"yes"/"on"，大小写不敏感）
    → 启用 edge_retriever；否则 None（禁用，省召回成本）。
    PgEdgeRecallChannel 代码保留，可随时经 env 重新启用。
    """
    raw = os.environ.get("GRAPH_EDGE_RECALL_ENABLED", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}
```

`_build_evidence_service` 改：

```python
edge_retriever = PgEdgeRetriever() if _graph_edge_recall_enabled() else None
```

并附 logger.info 记录 gate 状态（disabled/enabled）便于运维观测。

### 5.2 测试

- 新增 `test_graph_edge_recall_gate`（`test_ai_chat_router_req015.py`）：env 未设 / "false" → `edge_retriever is None`；"1"/"true" → `isinstance(edge_retriever, PgEdgeRetriever)`。
- 现有 req015 测试（不断言 edge_retriever）继续通过。

### 5.3 真 LLM 验收

校验脚本 `baseline_rule_no_edge` scenario（`use_graph_edge=False` → `edge_retriever=None`）等价于生产 gate off。重跑 `--allow-llm`：

```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out <report.md> --json-out <data.json> \
  --report-title "REQ-036 graph_edge 禁用真 LLM 验收" --allow-llm --semantic-emb-threshold 0.35
```

判定：per-sample baseline（edge-off）覆盖度 ≥ graph_edge@0.5（edge-on）→ 禁用无回归。

### 5.4 REQ-018 基线降级

REQ-018 验收点「4 通道 graph_edge 召回能力」降级说明：生产环境 3 通道（vector/keyword/graph_node）+ edge 通道代码保留可经 `GRAPH_EDGE_RECALL_ENABLED` 重新启用。`PgEdgeRecallChannel` 召回能力单元测试（`test_pg_edge_retriever.py`）继续通过，证明能力本身未退化。

## 6. Risks

- **4/10 样例 packed 变化**：真 LLM 验收确认无答案回归。若发现回归，可经 env `GRAPH_EDGE_RECALL_ENABLED=true` 立即回滚（无需 redeploy 代码）。
- **默认 off 改变生产行为**：经真 LLM 验收 + env 回滚机制兜底。`PgEdgeRecallChannel` 代码保留，回滚零代码变更。
- **embedding API flaky**：真 LLM 验收依赖硅流 embedding（semantic_emb 口径）；若 batch 失败，按 REQ-031 cache+timeout 降级，substring/semantic/llm_judge 口径仍可用作判定。

## 7. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | `_graph_edge_recall_enabled` helper + `_build_evidence_service` gate + 单测 | — |
| Slice 2 | pytest 受影响测试无回归 | Slice 1 |
| Slice 3 | 真 LLM 验收 + 判定 | Slice 2 |
| Slice 4 | REQ-018 基线降级 + 文档收口 + commit + push + PR | Slice 3 |

## 8. References

- REQ-035 决策报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-035-graph-edge-channel-decision-report.md`
- REQ-018: `docs/01-product-planning/05-requirements/REQ-018-p2-four-channel-graph-edge-recall.md`
- 生产 builder: `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`
- 校验脚本: `scripts/validate_req024_p2_real_validation.py`
