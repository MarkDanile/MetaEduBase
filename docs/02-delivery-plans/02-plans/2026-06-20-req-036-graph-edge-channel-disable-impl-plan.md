# REQ-036 Plan: P2 graph_edge 通道禁用实现

> Status: 🟢 完成
> Created: 2026-06-20
> Requirement: `docs/01-product-planning/05-requirements/REQ-036-p2-graph-edge-channel-disable-impl.md`
> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-036-graph-edge-channel-disable-impl.md`

## 任务模式

实现任务（Implementation）。改生产 builder `ai_router._build_evidence_service`（config 门控），保留 edge 代码，真 LLM 验收。

## 执行步骤

### Slice 1: config 门控 + 单测

1. `ai_router.py` 新增 `_graph_edge_recall_enabled()` helper（读 `GRAPH_EDGE_RECALL_ENABLED` env，默认 false）。
2. `_build_evidence_service` 改 `edge_retriever = PgEdgeRetriever() if _graph_edge_recall_enabled() else None`；附 logger.info。
3. `test_ai_chat_router_req015.py` 新增 `test_graph_edge_recall_gate_*`：env 未设/"false" → None；"1"/"true" → PgEdgeRetriever。

### Slice 2: pytest 无回归

```bash
cd packages/server-python
pytest tests/contexts/ai/test_ai_chat_router_req015.py tests/contexts/knowledge/test_ai_chat_service.py tests/contexts/knowledge/retrievers/test_pg_edge_retriever.py -q
```

### Slice 3: 真 LLM 验收

```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out <report.md> --json-out <data.json> \
  --report-title "REQ-036 graph_edge 禁用真 LLM 验收" --allow-llm --semantic-emb-threshold 0.35
```

判定：baseline（edge-off）覆盖度 ≥ graph_edge@0.5（edge-on）→ 禁用无回归。

### Slice 4: 文档收口 + Git

- REQ-018 Delivery Record 降级说明
- 同步 backlog / iteration / milestone / current-work / work-log
- `ruff` + `check-engineering-docs` 门禁
- commit + push + PR + squash merge + 删分支 + 同步 main

## 验证矩阵

| 项 | 命令 |
|----|------|
| 代码风格 | `ruff check packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py` |
| 单测 | `pytest tests/contexts/ai/test_ai_chat_router_req015.py -q` |
| 无回归 | `pytest tests/contexts/ai/test_ai_chat_router_req015.py tests/contexts/knowledge/test_ai_chat_service.py tests/contexts/knowledge/retrievers/test_pg_edge_retriever.py -q` |
| 真 LLM | Slice 3 命令 |
| 门禁 | `scripts/check-engineering-docs` |

## 风险与回退

- 改动限定在 `ai_router._build_evidence_service` + 1 单测文件；`PgEdgeRecallChannel` 代码保留。
- 回滚：env `GRAPH_EDGE_RECALL_ENABLED=true` 立即恢复 edge（无需 redeploy）。
- 真 LLM 验收若发现回归，gate 默认改 true 或设 env 回滚，登记 follow-up。
