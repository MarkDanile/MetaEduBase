# REQ-037 Spec: P2 graph_edge 禁用真 LLM 全量验收

> Status: 🟢 完成
> Created: 2026-06-21
> Source: REQ-036 follow-up（TD-070 解锁）
> Requirement: `docs/01-product-planning/05-requirements/REQ-037-p2-graph-edge-disable-real-llm-verify.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-21-req-037-graph-edge-disable-real-llm-verify-plan.md`

## 1. Problem Statement

REQ-036 AC-4 要求真 LLM 全量验收确认 graph_edge 通道禁用无答案回归，但全量 10 样例 × 6 scenario run 因 vector-recall 无超时阻塞未完成。TD-070（PR #379）已修复（`get_embedding_with_timeout` 60s 兜底），解锁本验收。

REQ-036 实证：生产默认 0.5 下 4/10 样例 packed 与 edge-off baseline 不同（1-2 chunk 微调），禁用非纯 no-op，需真 LLM 验收。

## 2. Goal

重跑 REQ-028 v3 10 样例 `--allow-llm`，对比 baseline（edge-off）vs graph_edge@0.5（edge-on）答案覆盖度，确认禁用无回归。**不改代码。**

## 3. Non-Goals

- 不改主链路代码 / 校验脚本 / gate 默认值
- 不重跑 REQ-026/027/028/029 真 LLM 报告
- 不强行让任何指标达标

## 4. Acceptance Criteria

见 requirement AC-1 ~ AC-5。

## 5. Architecture

### 5.1 真 LLM 全量验收

校验脚本 `baseline_rule_no_edge` scenario（`use_graph_edge=False` → `edge_retriever=None`）等价生产 gate off；`graph_edge` scenario（`use_graph_edge=True`, weight 0.5）等价生产 gate on（旧默认）。重跑 `--allow-llm --semantic-emb-threshold 0.35`：

```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out <report.md> --json-out <data.json> \
  --report-title "REQ-037 graph_edge 禁用真 LLM 全量验收" --allow-llm --semantic-emb-threshold 0.35
```

TD-070 后向量召回有 60s 超时兜底，全量 run 可完成（慢 provider 下 fail-fast 降级 keyword，不阻塞）。

### 5.2 对比口径

per-sample 四口径覆盖度 baseline vs graph_edge@0.5：

- **substring**（历史基线）：子串匹配
- **semantic**（REQ-028）：term + synonyms 集合匹配
- **semantic_emb**（REQ-030，threshold 0.35）：硅流 embedding cosine
- **continuous**（REQ-032）：weighted continuous coverage

### 5.3 判定框架

| 条件 | 判定 |
|------|------|
| baseline 四口径汇总 ≥ graph_edge@0.5，且 per-sample 多数 baseline ≥ edge | 禁用无回归，REQ-037 收口 |
| 部分样例 edge > baseline（edge 有改善） | 仍可禁用（REQ-033 已证 edge 整体价值有限），但记录样例；若无系统性退步则收口 |
| baseline 系统性退步（多数样例 edge > baseline 且汇总下降） | 禁用有回归，登记 follow-up 评估 gate 回滚或重新启用 |

## 6. Risks

- **embedding provider 仍慢**：TD-070 已加 60s 超时，慢 provider 下 fail-fast 降级 keyword，全量 run 可完成（不再阻塞）。若 provider 完全不可用，semantic_emb 全 0，但 substring/semantic/llm_judge 口径仍可用作判定。
- **判定主观性**：以 per-sample 多数 + 汇总无系统性退步为准，结合 REQ-033 已证的 edge 整体价值有限，避免单样例噪声影响判定。

## 7. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | 真 LLM 全量 run + 数据 | TD-070 |
| Slice 2 | per-sample 四口径对比 + 判定 + 报告 | Slice 1 |
| Slice 3 | 文档收口 + commit + push + PR | Slice 2 |

## 8. References

- REQ-036 实现报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-036-graph-edge-channel-disable-impl-report.md`
- TD-070: `docs/03-engineering-governance/technical-debt.md#td-070`
- 校验脚本: `scripts/validate_req024_p2_real_validation.py`
