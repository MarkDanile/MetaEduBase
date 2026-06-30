# REQ-040: P2 graph_edge 禁用评估 runner.py 接入 batch helper（TD-072 接力）

Status: 🔵 就绪（TD-072 实施完成后启动）
Priority: P3
Milestone: P2
Source: REQ-039 follow-up #4（TD-072 实施完成 = 本任务解除阻塞）
Related: REQ-037 / REQ-038 / REQ-039 / TD-070 / TD-071 / TD-072

## 背景

REQ-039 验证了 TD-071 实施（17.8min 全 suite / 推算 60 run ~6.6min）。**AC-4 子集验证（2026-06-22）实测推翻 spirit 解释**：仅传 `--req028-samples` 仍触发 132 run = 29.6min，按比例 60 run 推算 15-20min。AC-4 ≤10min 目标不可达，spirit 解释（6.6min）被实测推翻。

根因：TD-071 实施建了 `get_embeddings_with_timeout_batch` helper 但**未被 runner.py 真正调用**（TD-071 §5 诚实登记的偏差）。`runner.py:_build_service` 仍传单条 `get_embedding`，导致 `coverage._get_cached_embeddings_batch` 走 per-text gather 路径，HTTP 数不变。

**修复路径**（用户决策 2026-06-22 采纳 runner.py 接 batch helper）：
- `runner.py:_build_service` 改 `embedding_callable=get_embeddings_with_timeout_batch`
- `coverage._get_cached_embeddings_batch` 接受 batch callable 走真正 batch HTTP 路径
- 旧单条 callable 路径保留（向后兼容 + 测试桩）

预期 60 run 压到 5-7min（再加速 2-3×，叠加 TD-071 3-3.4× → 总 6-10× vs 历史 50-60min 阻塞）。

## 目标

TD-072 实施完成后，**重跑 REQ-028 v3 10 样例 `--allow-llm` 子集验证 AC-4 ≤10min 目标**（之前因 spirit 解释被推翻而失败）。同时复测 baseline vs graph_edge@0.5 mismatch（应保持 ~37 量级，70% LLM 噪声 + 30% 确定性抵消）。**不改主链路代码 / provider / 限流策略**。

判定：wall-clock ≤10min（AC-4 达标）+ `_EMB_STATS` 健康 + mismatch 量级不恶化 = runner.py 接 batch helper 成功。

## 非目标

- 不改主链路代码（`PgChunkVectorRetriever` / `PgVectorRecallChannel` / `router.py:278` / `ai_chat_service.py`）
- 不切 provider（保持硅流）
- 不改 REQ-031 `_get_cached_embedding` 行为（cache + stats 保持）
- 不改 TD-070 60s `asyncio.wait_for` 模式
- 不改 `_EMB_SEMAPHORE` 值（仍 2）
- 不改 `get_embeddings_with_timeout_batch` helper 现有签名（向后兼容）
- 不重跑 REQ-026/027/028/029 真 LLM 报告（专项任务）
- 不强行让任何指标达标

## 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | TD-072 实施完成（merged），`get_embeddings_with_timeout_batch` 真正被 `coverage._get_cached_embeddings_batch` 走 batch HTTP 路径；`runner.py` 传 batch callable | TD-072 PR 状态 MERGED + ad-hoc 验证 batch 路径生效 + 现有单测无回归 |
| AC-2 | 重跑 REQ-028 v3 10 样例 `--allow-llm --semantic-emb-threshold 0.35 --concurrency 4` 在 ≤10min 完成（AC-4 目标最终达成） | real-LLM 报告生成（`/usr/bin/time` 输出）+ wall-clock ≤600s |
| AC-3 | `_EMB_STATS` 健康：timeout=0 / error=0；hit/miss 比例合理（keypoint 全 hit、answer 全 miss 因无重复） | 报告 `_EMB_STATS` 段 |
| AC-4 | baseline vs graph_edge@0.5 mismatch 量级不恶化（~37 量级，70% LLM 噪声 + 30% 确定性抵消） | 报告 mismatch 分析段 |
| AC-5 | dry-run 与 `--allow-llm` 都可复跑；报告可复现 | CLI 行为 |
| AC-6 | 现有单测无回归（10 passed） | `pytest tests/contexts/knowledge/test_embedding_service.py -q` 退出码 0 |

## 前置条件（与 TD-072 强耦合）

| 条件 | 阻塞期 | 解除 |
|------|--------|------|
| TD-072 PR merged | 阻塞 | TD-072 PR 翻 MERGED |
| `runner.py:_build_service` 改用 `get_embeddings_with_timeout_batch` | 阻塞 | TD-072 实施完成 |
| `coverage._get_cached_embeddings_batch` 接受 batch callable | 阻塞 | TD-072 实施完成 |
| ad-hoc 验证 batch 路径生效 | 阻塞 | TD-072 验证通过 |

## 事实源

- REQ-039 验收报告：[2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md](../../02-delivery-plans/01-specs/2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md)
- AC-4 子集验证报告（spirit 解释被实测推翻）：[2026-06-22-td-071-ac4-subset-validation-report.md](../../02-delivery-plans/01-specs/2026-06-22-td-071-ac4-subset-validation-report.md)
- TD-071 spec（§5 偏差登记）：[2026-06-21-td-071-rag-eval-embedding-batch.md](../../02-delivery-plans/01-specs/2026-06-21-td-071-rag-eval-embedding-batch.md)
- TD-072 任务卡：[technical-debt.md#td-072](../../03-engineering-governance/technical-debt.md#td-072)
- 校验脚本：`scripts/validate_req024_p2_real_validation.py`（`scripts/rag_validation/` 包）
- 样例集：`tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json`

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-22 | 登记 | AC-4 子集验证完成后用户决策走"runner.py 接 batch helper"路径。本任务接力 REQ-039 follow-up #4（离线批量 keypoint embedding / runner.py 接 batch helper / 提 provider 限流 三选一最高价值）。登记 TD-072 实施完成后 = 本任务解除阻塞。 |
