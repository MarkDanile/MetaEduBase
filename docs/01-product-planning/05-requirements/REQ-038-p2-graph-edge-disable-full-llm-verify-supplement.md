# REQ-038: P2 graph_edge 禁用全量真 LLM 验收补强

Status: 🔴 Blocked（环境阻塞：embedding provider 累积吞吐不足；环境就绪后再做）
Priority: P3
Milestone: P2
Source: REQ-037 follow-up（全量真 LLM run 受 embedding provider 累积吞吐阻塞）
Related: REQ-036 / REQ-037 / TD-070

## 背景

REQ-037 以 dry-run 四口径覆盖度实证收口（10/10 样例 baseline = graph_edge@0.5 零覆盖度差异），判定 REQ-036 禁用 graph_edge 通道无答案覆盖度回归。全量真 LLM run（补 semantic_emb / continuous / llm_judge 口径）受 embedding provider 累积吞吐阻塞未完成，登记 REQ-038。

## 阻塞分析

全量 10 样例 × 6 scenario = 60 次 `_run_question`，每次触发：
- vector-recall query embedding（`recall_service.py` 经 TD-070 `get_embedding_with_timeout`，60s 超时）
- answer embedding（semantic_emb 口径）
- keypoint embedding（223 个 term+synonym 候选，REQ-031 进程内缓存跨 scenario 命中，单次 run 内仅算一次）

成本结构：
- keypoint embedding：223 次，但 REQ-031 进程内缓存使 keypoint 跨 6 scenario 命中，单次 run 内仅首次 scenario 计算 → **缓存已优化，非瓶颈**
- answer + vector-recall embedding：60 + 60 = 120 次，**每次 answer/query 不同，无法跨 scenario 缓存** → 真正瓶颈
- 单次 embedding ~25-30s（硅流 Qwen3-Embedding-8B），120 次 ≈ 50-60min，且 provider 慢时 CPU 0% 网络 I/O 等待

REQ-036 / REQ-037 多次后台 run（全量 + `--limit 18`）均 ~32-33min 未完成，单次探针 provider 可用（embedding dim 4096 + LLM OK）。**问题在累积吞吐，非单次可用性或代码缺陷。**

## 阻塞判定

- **外部依赖阻塞**：embedding provider（硅流）吞吐是环境因素，非本仓库代码可解。TD-070 已修单次无超时挂起，但累积吞吐仍超可接受时间。
- **离线 keypoint 预计算无效**：REQ-038 follow-up 原设想"离线批量预计算 keypoint embedding"消除全量 run 成本，但 keypoint 已被 REQ-031 进程内缓存优化（非瓶颈）；真正瓶颈是 120 次 answer+recall embedding（无法缓存），离线预计算不能解决。
- **决策阻塞**：用户决策（2026-06-21）跳过 REQ-038，环境就绪后再做。REQ-037 dry-run 实证已充分支撑 REQ-036 禁用决策，全量真 LLM 仅是补强，非阻塞 graph_edge 治理闭环。

## 解除阻塞条件（任一满足）

1. embedding provider 吞吐改善（单次 < 5s，或并发批次支持）
2. 校验脚本架构改为"预计算所有 answer+recall embedding 落盘 + 脚本读缓存离线 run"模式（需改 `scripts/rag_validation/` 架构，工程量大）
3. 切换到本地 sentence-transformers embedding（REQ-030 非目标已排除，但环境持续慢时可重评）

## 目标（解除阻塞后）

重跑 REQ-028 v3 10 样例 `--allow-llm`，补 semantic_emb / continuous / llm_judge 口径的 baseline vs graph_edge@0.5 对比，进一步确认禁用无回归。

## 非目标

- 不在本阻塞态改代码
- 不强行跑全量真 LLM（环境不支撑）
- 不改 graph_edge 通道决策（维持 REQ-036 禁用）

## 验收标准（解除阻塞后）

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 全量 10 样例 `--allow-llm --semantic-emb-threshold 0.35` 成功完成 | real-LLM 报告生成 |
| AC-2 | 报告含 baseline vs graph_edge@0.5 的 semantic_emb / continuous / llm_judge per-sample 对比 | 报告章节 |
| AC-3 | 判定与 REQ-037 dry-run 结论一致（禁用无回归），或发现新差异时登记 follow-up | 报告结论 |

## 事实源

- REQ-037 验收报告: `docs/02-delivery-plans/01-specs/2026-06-21-req-037-graph-edge-disable-real-llm-verify-report.md`
- REQ-036 实现报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-036-graph-edge-channel-disable-impl-report.md`
- TD-070: `docs/03-engineering-governance/technical-debt.md#td-070`
- 校验脚本: `scripts/validate_req024_p2_real_validation.py`（`scripts/rag_validation/` 包）

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-21 | 登记 | REQ-037 全量真 LLM run 受 embedding provider 累积吞吐阻塞，登记本补强需求。本任务接力 |
| 2026-06-21 | 阻塞判定 | 成本分析：120 次 answer+recall embedding（无法缓存）是真瓶颈，keypoint 已被 REQ-031 缓存优化非瓶颈。离线 keypoint 预计算不能解决。provider 吞吐是环境因素，非代码可解。用户决策跳过，环境就绪后再做。REQ-038 翻 🔴 Blocked（环境阻塞） |
