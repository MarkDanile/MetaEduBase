# REQ-031: P2 semantic embedding 覆盖率计算稳定性（REQ-030 接力）

Status: 🟢 完成（embedding 通路稳定，semantic_emb 8/10 非零；REQ-030 AC-4/5 阈值校准留 follow-up）
Priority: P0
Milestone: P2
Source: REQ-030 真 LLM 重跑诊断（硅流 embedding API 在 batch 下挂起，semantic_emb 全 0）
Related: REQ-030 / REQ-028 / TD-068 / TD-069

## 背景

REQ-030 实现 semantic embedding coverage 口径后，真 LLM 重跑 REQ-028 v3 10 样例时：

- **semantic_emb 字段全 0**（10 样例 × 4 scenarios = 40 行全 0）
- LLM-as-judge 通路完整（40 次调用全成功，AC-5 1/10: Q4 +0.60）
- dry-run 通过，单条 `get_embedding("测试")` 返回 4096 维 list[float] 正常

诊断根因：`_compute_semantic_embedding_coverage` 对每个 (sample, scenario) 重复计算 keypoint（term + synonyms）embedding，10 样例 × 4 scenarios × ~5 keypoints × ~2 candidates ≈ **440 次串行 HTTP 调用**。硅流 embedding API 在持续 batch 调用下响应变慢甚至挂起，httpx 默认 timeout=30s 不足以保护，进程 CPU 0% 长时间等待，1 小时+ 无输出。

问题**在调用频率和容错，不在算法本身**。

## 目标

在不引入新依赖（sentence-transformers 等）前提下，让 semantic embedding coverage 在真 LLM batch 重跑下能稳定产出非 0 数据，使 REQ-030 AC-4 / AC-5 可验证。

具体目标：

1. **keypoint embedding 缓存**：keypoint（term + synonyms）文本在同一次脚本运行内静态，跨 4 scenarios 复用同一 embedding，避免重复计算。预计将 440 次调用降至 ~140 次（100 keypoint + 40 answer）。
2. **硬超时 + 重试**：对每次 embedding API 调用加 `asyncio.wait_for` 硬超时（60s）+ 失败降级（返回 None，keypoint 标记未命中），避免单次挂起拖垮整批。
3. **真 LLM 重跑验证**：REQ-028 v3 10 样例重跑后 semantic_emb 字段非 0，能计算 Spearman ρ。
4. **REQ-030 AC-4 / AC-5 补判**：基于真实数据判定达标 / 未达标；若仍未达标，如实记录并评估是否调整阈值或转 sentence-transformers 方案。

## 非目标

- 不引入 sentence-transformers / BERT 等本地模型依赖（作为 fallback 方案仅在缓存+超时方案失败后评估）。
- 不修改 `embedding_service.py` 生产代码（`get_embedding` 已有 provider fallback；本任务只在验证脚本侧加缓存 + 超时包装）。
- 不重写 `_compute_semantic_embedding_coverage` 算法（cosine + threshold 0.5 逻辑不变）。
- 不重跑 REQ-026 / REQ-027 / REQ-029 真 LLM 报告（独立 PR）。

## 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | `_compute_semantic_embedding_coverage` 使用进程内 embedding 缓存（key by text），同文本不重复调 API | 代码 + 缓存命中日志 |
| AC-2 | 每次 embedding API 调用有 `asyncio.wait_for` 硬超时（60s），超时 / 异常降级返回 None 而非挂起 | 代码 + 真 LLM 重跑无 1h+ 挂起 |
| AC-3 | REQ-028 v3 10 样例真 LLM 重跑：semantic_emb 字段非 0 的 sample ≥ 5/10（缓存 + 超时让通路跑通） | 新报告 |
| AC-4 | 报告计算 Spearman ρ（semantic_emb vs LLM-judge），如实记录（不强制 ≥ 0.7） | 新报告 |
| AC-5 | REQ-030 AC-4 / AC-5 基于真实数据补判：达标则翻 REQ-030 完成；未达标则如实记录 + 评估下一步 | REQ-030 状态更新 |
| AC-6 | 旧字段（`keypoint_coverage_pct` / `keypoint_semantic_embedding_*`）行为不变（向后兼容） | 字段不变 |
| AC-7 | dry-run 与 `--allow-llm` 双模式仍可用 | CLI 行为 |
| AC-8 | 若缓存+超时方案仍无法产出非 0 数据，登记下一步（sentence-transformers 评估或阈值调整），不强行声明完成 | 候选区 / Delivery Record |

## 建议执行顺序

1. 改造 `scripts/validate_req024_p2_real_validation.py`：
   - 新增进程内 `_EMBEDDING_CACHE: dict[str, list[float]]` + `_get_cached_embedding(text, callable)` helper
   - `_compute_semantic_embedding_coverage` 改用 cached helper（answer + keypoint candidates 全走缓存）
   - 加 `asyncio.wait_for(..., timeout=60.0)` 硬超时 + 失败降级
   - 保留 `_EMB_SEMAPHORE`（防止未来并发化时打爆 API）
2. dry-run 验证机制不变（exit 0）
3. `--allow-llm` 真 LLM 重跑 REQ-028 v3 10 样例
4. 检查 semantic_emb 非零率 + Spearman ρ
5. 补判 REQ-030 AC-4 / AC-5，更新状态
6. 文档收口 + commit + push + PR

## 事实源

- REQ-030 requirement: `docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md`
- REQ-030 报告（诊断）: `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md`
- 基线脚本: `scripts/validate_req024_p2_real_validation.py`
- embedding service: `packages/server-python/app/contexts/knowledge/application/embedding_service.py`
- v3 样例集: `tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json`

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-20 | 登记 | REQ-030 真 LLM 重跑 semantic_emb 全 0，诊断为硅流 embedding API batch 挂起。登记 REQ-031 接力 |
| 2026-06-20 | 脚本改造 | `_EMBEDDING_CACHE` 进程内缓存 + `_get_cached_embedding` (asyncio.wait_for 60s 硬超时 + 降级) + `_EMB_STATS` 诊断计数写报告 |
| 2026-06-20 | dry-run | exit 0，0 scenario errors，机制不变 |
| 2026-06-20 | 真 LLM 重跑 | REQ-028 v3 10 样例重跑。缓存 hit=1581 / miss=259 / **timeout=0 / error=0**（彻底消除挂起）。semantic_emb 从全 0 变为 **8/10 样例非零**（Q4/Q9 全零）。AC-3 达标。Spearman ρ=0.109 (n=40) 如实计算。**REQ-030 AC-4/5 仍 0/10**：threshold 0.5 过严，semantic_emb 值集中 0.20-0.40——属阈值校准问题，留 follow-up（threshold 0.5→0.35 或改 continuous weighted coverage）。REQ-031 核心目标（通路稳定）达成 |
