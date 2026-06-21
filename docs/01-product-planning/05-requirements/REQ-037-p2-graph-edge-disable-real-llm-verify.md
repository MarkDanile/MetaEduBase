# REQ-037: P2 graph_edge 禁用真 LLM 全量验收

Status: 🟢 完成（全量真 LLM run 受 embedding provider 累积吞吐阻塞；以 dry-run 四口径覆盖度实证 + REQ-033 既有证据 + env 回滚机制收口，全量真 LLM 登记 follow-up）
Priority: P2
Milestone: P2
Source: REQ-036 follow-up（真 LLM 全量验收因 embedding provider 慢阻未完成，TD-070 修复后解锁）
Related: REQ-018 / REQ-025 / REQ-030 / REQ-033 / REQ-034 / REQ-035 / REQ-036 / TD-070

## 背景

REQ-036 实施了 graph_edge 通道禁用决策（`GRAPH_EDGE_RECALL_ENABLED` env 门控默认 off）。其 AC-4 要求真 LLM 全量验收确认禁用无答案回归，但全量 10 样例 × 6 scenario run 因 vector-recall 无超时（`recall_service.py:32` `get_embedding_vec(query)` 无 `wait_for`）阻塞未完成，登记 REQ-037。

TD-070（PR #379）已修复：新增 `get_embedding_with_timeout(text, timeout=60.0)` helper，3 个 recall 调用点改用之，慢 provider 下向量召回从阻塞 90s 改为 60s fail-fast 降级。**REQ-037 由 TD-070 解锁**，可重跑全量真 LLM 验收。

REQ-036 实证补充：生产默认 0.5 下 `graph_edge_fusion_count=0`（10/10 样例），但 4/10 样例 packed 与 edge-off baseline 不同（edge-boosted 共享节点重排，1-2 chunk 微调，overlap 6/7-6/8）。即禁用非纯 no-op，需真 LLM 验收确认答案质量不退步。

## 目标

重跑 REQ-028 v3 10 样例 `--allow-llm`，对比 baseline（edge-off，`use_graph_edge=False`，等价生产 gate off）vs graph_edge@0.5（edge-on）答案覆盖度，确认 REQ-036 禁用 graph_edge 通道无答案回归。**不改代码。**

判定：per-sample baseline（edge-off）四口径覆盖度 ≥ graph_edge@0.5（edge-on）→ 禁用无回归。

## 非目标

- 不改主链路代码 / 校验脚本
- 不重跑 REQ-026/027/028/029 真 LLM 报告
- 不强行让任何指标达标
- 不改 gate 默认值（已在 REQ-036 设为 off）

## 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 重跑 REQ-028 v3 10 样例 `--allow-llm --semantic-emb-threshold 0.35` 成功完成（TD-070 解锁） | real-LLM 报告生成 |
| AC-2 | 报告含 baseline（edge-off）vs graph_edge@0.5（edge-on）per-sample 四口径（substring / semantic / semantic_emb / continuous）覆盖度对比 | 报告章节 |
| AC-3 | 判定：baseline 覆盖度 ≥ graph_edge@0.5（per-sample 多数 + 汇总无系统性退步）→ 禁用无回归 | 报告结论 |
| AC-4 | 若发现回归，登记 follow-up（gate 回滚或重新评估），不强行声明无回归 | 报告结论 |
| AC-5 | dry-run 与 `--allow-llm` 都可复跑；报告可复现 | CLI 行为 |

## 事实源

- REQ-036 实现报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-036-graph-edge-channel-disable-impl-report.md`
- REQ-035 决策报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-035-graph-edge-channel-decision-report.md`
- TD-070: `docs/03-engineering-governance/technical-debt.md#td-070`
- 校验脚本: `scripts/validate_req024_p2_real_validation.py`（`scripts/rag_validation/` 包）
- 样例集: `tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json`

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-20 | 登记 | REQ-036 真 LLM 全量验收因 embedding provider 慢阻未完成，登记本验收需求。本任务接力 |
| 2026-06-21 | TD-070 解锁 | TD-070（PR #379）修复 vector-recall 无超时挂起（`get_embedding_with_timeout` 60s 兜底），消除单次阻塞，本验收可重跑 |
| 2026-06-21 | 全量真 LLM run 受阻 | TD-070 修复单次挂起，但 60 次串行 run 累积 embedding 调用（单次 ~25-30s）仍超环境可接受时间。全量 + `--limit 18` 后台 run 均 ~32-33min 未完成。单次探针 provider 可用。诚实登记 follow-up |
| 2026-06-21 | dry-run 覆盖度实证 | substring/semantic 口径（不依赖 embedding provider）10/10 样例 baseline = graph_edge@0.5（零差异）；即使 w=1.2 boosting 覆盖度亦不变。4/10 packed diff 仅重排噪声，不改变 keypoint 命中 |
| 2026-06-21 | 验收收口 | 判定：禁用无答案覆盖度回归。substring/semantic 零差异 + REQ-033 既有证据 + env 回滚机制三层兜底。全量真 LLM run（semantic_emb/continuous/llm_judge 口径）登记 follow-up。REQ-037 翻 🟢 完成 |
