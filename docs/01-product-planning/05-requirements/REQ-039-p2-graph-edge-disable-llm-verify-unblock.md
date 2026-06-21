# REQ-039: P2 graph_edge 禁用全量真 LLM 验收解除阻塞（TD-071 接力）

Status: 🔵 就绪（TD-071 实施完成后启动）
Priority: P3
Milestone: P2
Source: REQ-038 follow-up（TD-071 实施完成 = 本任务解除阻塞）
Related: REQ-036 / REQ-037 / REQ-038 / TD-070 / TD-071

## 背景

REQ-038 因 embedding provider 累积吞吐阻塞登记 🔴 Blocked。深度诊断（见 TD-071）显示阻塞由 2 个可改结构放大：

1. **`embedding_service` 串行单条调用**：`get_embedding` 只暴露单条接口（`input: [text]` 单元素列表），provider 原生 batch API（`SiliconFlowProvider.embed(texts: list[str])`）未启用 → 120 次 answer+recall embedding = 120 次 HTTP 串行。
2. **校验脚本串行 run**：`main.py` `for q: for scenario: await _run_question(...)` 双重 for 串行 60 次 run，无 `asyncio.gather`。

REQ-038 §"解除阻塞条件 #1 嵌入 provider 吞吐改善"被 TD-071 替代为"不改 provider、改调用方式"——方案 A+D（用户决策 2026-06-21）：
- 方案 A：`embedding_service` 暴露 batch API + coverage/retriever 改批量调用。
- 方案 D：`main.py` `asyncio.gather` + `--concurrency` CLI（默认 4，semaphore=2 维持 provider 限流不放大）。

预期 REQ-038 全量真 LLM run 50-60min → ≤10min 完成。

## 目标

TD-071 实施完成后，**重跑 REQ-038 全量 10 样例 `--allow-llm` 验收**，补 semantic_emb / continuous / llm_judge 口径的 baseline vs graph_edge@0.5 对比，进一步确认 REQ-036 禁用无回归。**不改代码**（TD-071 实施为前置条件）。

判定：per-sample baseline（edge-off）四口径覆盖度 ≥ graph_edge@0.5（edge-on）→ 禁用无回归；与 REQ-037 dry-run 结论一致（已证 baseline = graph_edge@0.5 零差异）。

## 非目标

- 不改主链路代码 / 校验脚本（TD-071 负责）
- 不重跑 REQ-026/027/028/029 真 LLM 报告
- 不强行让任何指标达标
- 不改 gate 默认值（已在 REQ-036 设为 off）
- 不切 provider（保持硅流）

## 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | TD-071 实施完成（merged），`get_embeddings_with_timeout_batch` 单测通过 + main.py `asyncio.gather` 改造可工作 | TD-071 PR 状态 MERGED + pytest 退出码 0 |
| AC-2 | 重跑 REQ-028 v3 10 样例 `--allow-llm --semantic-emb-threshold 0.35` 在 ≤10min 完成（TD-071 目标） | real-LLM 报告生成（`/usr/bin/time` 输出 + 报告时间戳） |
| AC-3 | 报告含 baseline（edge-off）vs graph_edge@0.5（edge-on）per-sample 四口径（substring / semantic / semantic_emb / continuous）覆盖度对比 + llm_judge 口径（来自 AC-2 `--allow-llm` 启用） | 报告章节 |
| AC-4 | 判定：baseline 覆盖度 ≥ graph_edge@0.5（per-sample 多数 + 汇总无系统性退步）→ 禁用无回归；与 REQ-037 dry-run 结论一致 | 报告结论 |
| AC-5 | 若发现回归，登记 follow-up（gate 回滚或重新评估），不强行声明无回归 | 报告结论 |
| AC-6 | dry-run 与 `--allow-llm` 都可复跑；报告可复现；`_EMB_STATS` 命中合理（keypoint 全 hit、answer 几乎全 miss 因无重复）、`timeout=0` `error=0` | CLI 行为 + 报告 `_EMB_STATS` 段 |

## 前置条件（与 TD-071 强耦合）

| 条件 | 阻塞期 | 解除 |
|------|--------|------|
| TD-071 PR merged | 阻塞 | TD-071 PR 翻 MERGED |
| `embedding_service.get_embeddings_with_timeout_batch` helper 可用 | 阻塞 | TD-071 单测通过 |
| `coverage._compute_semantic_embedding_coverage` 改用 batch | 阻塞 | TD-071 回归通过 |
| `main.py` 引入 `asyncio.gather` + `--concurrency` CLI | 阻塞 | TD-071 CLI 验证通过 |

## 事实源

- REQ-038 阻塞分析: `docs/01-product-planning/05-requirements/REQ-038-p2-graph-edge-disable-full-llm-verify-supplement.md`
- REQ-037 dry-run 结论: `docs/02-delivery-plans/01-specs/2026-06-21-req-037-graph-edge-disable-real-llm-verify-report.md`
- TD-071 任务卡 + spec: `docs/03-engineering-governance/technical-debt.md#td-071` / `docs/02-delivery-plans/01-specs/2026-06-21-td-071-rag-eval-embedding-batch.md`
- 校验脚本: `scripts/validate_req024_p2_real_validation.py`（`scripts/rag_validation/` 包）
- 样例集: `tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json`

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-21 | 登记 | REQ-038 阻塞诊断（TD-071 接力）→ 本任务登记。深度分析确认阻塞由 2 个可改结构放大：串行单条 embedding + 校验脚本串行 run。用户决策 2026-06-21 采纳方案 A+D（不改 provider、保持硅流），登记 TD-071。本任务接力 REQ-038 阻塞解除 |
