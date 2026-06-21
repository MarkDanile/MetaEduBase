# REQ-036 graph_edge 通道禁用实现报告

> Status: 🟢 完成（代码 + 单测 + dry-run 实证收口；真 LLM 全量验收因 embedding provider 慢阻，登记 follow-up）
> Created: 2026-06-20
> Requirement: `docs/01-product-planning/05-requirements/REQ-036-p2-graph-edge-channel-disable-impl.md`
> Spec: `docs/02-delivery-plans/01-specs/2026-06-20-req-036-graph-edge-channel-disable-impl.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-036-graph-edge-channel-disable-impl-plan.md`

## 1. 实现目标

实施 REQ-035 决策：生产环境禁用 graph_edge 通道，保留 `PgEdgeRecallChannel` 召回能力代码可经 config 重新启用。

## 2. 代码改动

### 2.1 config 门控（`ai_router.py`）

新增 `_graph_edge_recall_enabled()` helper（镜像 `_get_rrf_channel_weights` 模式），读 `GRAPH_EDGE_RECALL_ENABLED` env，真值（`1`/`true`/`yes`/`on`，大小写不敏感）→ 启用；否则禁用。**默认 false**（ enact REQ-035 禁用决策）。

`_build_evidence_service` 改：

```python
edge_retriever=PgEdgeRetriever() if graph_edge_on else None
```

附 `logger.info` 记录 gate 状态（disabled/enabled）便于运维观测。

### 2.2 代码保留

`PgEdgeRecallChannel`（`recall_service.py`）/ `PgEdgeRetriever`（`pg_graph_retriever.py`）代码**未删**，召回能力单元测试（`test_pg_edge_retriever.py`）继续通过。可随时经 `GRAPH_EDGE_RECALL_ENABLED=true` 重新启用（如 vector 召回退化或图谱扩充时）。

### 2.3 校验脚本不受影响

`scripts/rag_validation/runner._build_service` 独立构造 service（`edge_retriever=PgEdgeRetriever() if scenario.use_graph_edge else None`），不受生产 gate 影响——仍支持 edge scenario 评估。

## 3. 实证发现（dry-run 数据分析）

REQ-036 实证补充了 REQ-035 的判断：生产默认权重 0.5 下 `graph_edge_fusion_count=0`（10/10 样例，无纯 edge 项进 fusion），但 **4/10 样例 packed chunk-ids 与 edge-off baseline 不同**：

| 样例 | baseline packed | graph_edge@0.5 packed | overlap | ge_fusion | ge_packed |
|------|----------------|----------------------|---------|-----------|-----------|
| Q2_generator_iterator_relationship | 8 | 7 | 6 | 0 | 0 |
| Q3_default_param_pitfall | 7 | 7 | 6 | 0 | 0 |
| Q6_python_closure | 8 | 8 | 6 | 0 | 0 |
| Q10_python_advanced_synthesis | 8 | 8 | 6 | 0 | 0 |
| 其余 6 样例 | — | — | 全同 | 0 | 0 |

原因：edge 召回的共享节点（同时被 vector/keyword 召回）经 RRF 加权（`graph_edge: 0.5`）后分数提升，重排了 fusion_topN，导致 1-2 个 packed block 变化。即禁用 edge **非纯 no-op**，会改变 4/10 样例的 prompt——但变化幅度小（1-2 chunk，overlap 6/7-6/8）。

## 4. 验证

### 4.1 单元测试（通过）

```bash
cd packages/server-python
pytest tests/contexts/ai/test_ai_chat_router_req015.py tests/contexts/knowledge/test_ai_chat_service.py tests/contexts/knowledge/retrievers/test_pg_edge_retriever.py -q
```

→ **37 passed**，含新增 2 个 gate 测试：

- `test_graph_edge_recall_gate_defaults_off`：env 未设 / `false`/`0`/`no`/`off`/`FALSE` → `edge_retriever is None`
- `test_graph_edge_recall_gate_enabled_truthy`：`1`/`true`/`yes`/`on`/大小写变体 → `isinstance(edge_retriever, PgEdgeRetriever)`

现有 req015 测试（不断言 edge_retriever）无回归。

### 4.2 真 LLM 验收（部分受阻，登记 follow-up）

单次探针确认 embedding + chat LLM provider 均可用：

- `get_embedding('测试')` → OK，dim=4096（~25s）
- `_call_llm(...)` → OK，返回正常

但全量 10 样例 × 6 scenario run（60 次 `_run_question`）阻塞：每次 `_run_question` 触发 vector-recall 的 query embedding（`recall_service.py:32` `get_embedding_vec(query)`，**无超时**，单次 ~25s）+ keypoint coverage embedding + LLM 答案调用，串行累计耗时极长且 embedding provider 慢。多次后台运行均在 CPU 0% 网络 I/O 等待，未在可接受时间内完成。

**这是环境问题（embedding provider 慢 + `recall_service` vector-recall 无超时），非本任务代码缺陷。** 已登记 follow-up（见 §6）。

### 4.3 决策依据（不依赖全量真 LLM）

gate 默认 off 的决策有充分兜底：

1. **dry-run 实证**：4/10 样例 packed 仅 1-2 chunk 微调（overlap 6/7-6/8），变化幅度小。
2. **REQ-033 已证**：edge 即使进 packed（w=1.2 boosting），Metric B（跨 section 扩展）=1/10、跨文档 grounding=0/10——对答案质量增益有限。
3. **env 回滚机制**：若部署后发现回归，设 `GRAPH_EDGE_RECALL_ENABLED=true` 立即恢复 edge（无需 redeploy 代码）。
4. **代码保留**：`PgEdgeRecallChannel` 未删，回滚零代码变更。

## 5. REQ-018 验收基线降级

REQ-018 验收点「4 通道 graph_edge 召回能力」降级说明（已写入 REQ-018 Delivery Record）：

- **生产环境 3 通道**（vector/keyword/graph_node）+ **edge 通道代码保留可经 `GRAPH_EDGE_RECALL_ENABLED` 重新启用**。
- `PgEdgeRecallChannel` 召回能力本身（`test_pg_edge_retriever.py` 单测）未退化，仅生产未注入。
- 降级依据：REQ-033/034/035 三轮评估证 graph_edge 在真 vector 召回下价值有限。

## 6. 非目标与 follow-up

### 非目标（确认未做）

- 未删 `PgEdgeRecallChannel` / `PgEdgeRetriever` 代码
- 未改 RRF 默认权重 / ContextPacker / recall_service / 校验脚本
- 未调整 graph_node 通道

### follow-up

| 项 | 说明 | 归属 |
|----|------|------|
| 真 LLM 全量验收 | embedding provider 恢复稳定后重跑 REQ-028 v3 10 样例 `--allow-llm`，对比 baseline（edge-off）vs graph_edge@0.5 答案覆盖度，确认禁用无回归 | 候选区 |
| vector-recall 超时 | `recall_service.py:32` `get_embedding_vec(query)` 无超时，慢 provider 下会阻塞；可加 `asyncio.wait_for` 兜底（与 REQ-031 `_get_cached_embedding` 一致） | 候选区（TD） |

## 7. 数据可复现

```bash
# 单测
cd packages/server-python
pytest tests/contexts/ai/test_ai_chat_router_req015.py -q

# dry-run 实证（不调 LLM，复现 4/10 packed diff）
python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out <report.md> --json-out <data.json> \
  --report-title "REQ-036 dry-run"

# 真 LLM 全量验收（embedding provider 稳定时；当前环境慢阻）
python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out <report.md> --json-out <data.json> \
  --report-title "REQ-036 真 LLM 验收" --allow-llm --semantic-emb-threshold 0.35
```
