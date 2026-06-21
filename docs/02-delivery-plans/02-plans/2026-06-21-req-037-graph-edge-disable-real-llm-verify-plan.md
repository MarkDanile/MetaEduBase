# REQ-037 Plan: P2 graph_edge 禁用真 LLM 全量验收

> Status: 🟢 完成
> Created: 2026-06-21
> Requirement: `docs/01-product-planning/05-requirements/REQ-037-p2-graph-edge-disable-real-llm-verify.md`
> Spec: `docs/02-delivery-plans/01-specs/2026-06-21-req-037-graph-edge-disable-real-llm-verify.md`

## 任务模式

验证任务（Verification），同 REQ-033/034/035。不改代码，基于真 LLM 全量 run 给出禁用无回归判定。TD-070 解锁。

## 执行步骤

### Slice 1: 真 LLM 全量 run

```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out <report.md> --json-out <data.json> \
  --report-title "REQ-037 graph_edge 禁用真 LLM 全量验收" --allow-llm --semantic-emb-threshold 0.35
```

TD-070 后 60s 超时兜底，全量 run 可完成。

### Slice 2: 对比 + 判定 + 报告

从 `--json-out` 提取 per-sample baseline vs graph_edge@0.5 四口径覆盖度，按 spec §5.3 判定框架给结论。写独立验收报告 `2026-06-21-req-037-graph-edge-disable-real-llm-verify-report.md`。

### Slice 3: 文档收口 + Git

- 同步 backlog / iteration / milestone / current-work / work-log
- `scripts/check-engineering-docs` 门禁
- commit + push + PR + squash merge + 删分支 + 同步 main

## 验证矩阵

| 项 | 命令 |
|----|------|
| 真 LLM run | Slice 1 命令 |
| 门禁 | `scripts/check-engineering-docs` |

## 风险与回退

- 全部改动限定在新增文档，不碰代码；回退即 revert。
- 若判定为有回归，登记 follow-up 评估 gate 回滚（`GRAPH_EDGE_RECALL_ENABLED=true`），不在本任务改代码。
