# REQ-032: P2 semantic_emb 阈值校准与 continuous 口径（REQ-030 AC-4/5 接力）

Status: 🟢 完成（阈值校准 + continuous 双口径实现；AC-4 达标 4/10，AC-5 三口径各 1/10 不达标，根因定位为 P2 链路无正向贡献，登记 REQ-033）
Priority: P1
Milestone: P2
Source: REQ-031 接力后 semantic_emb 通路稳定（8/10 非零），但 threshold 0.5 过严致 AC-4/5 仍 0/10
Related: REQ-030 / REQ-031 / REQ-028 / REQ-029

## 背景

REQ-031 修复 embedding 通路后，真 LLM 重跑 v3 10 样例的 semantic_emb 数据揭示：

- **similarity 分布**：200 个 keypoint-similarity 对，median=0.329，p75=0.440，p90=0.537。threshold 0.5 命中率仅 14%。
- **threshold 0.5 过严**：Qwen3-Embedding-8B 对中文短 keypoint（"装饰器"/"闭包"）与长 answer 的余弦相似度天然偏低，多数落在 0.3-0.5 区间。
- **Spearman ρ=0.109**（threshold 0.5 vs LLM-judge）：semantic_emb 过于稀疏，丢失排序信息。

REQ-031 的 follow-up 建议两条路：(a) threshold 0.5→0.35 重判；(b) continuous weighted coverage（不二值化，用 similarity 直接加权）。

## 目标

对 semantic_emb 口径做阈值校准 + 引入 continuous 口径作为 secondary signal，基于真实数据判定 REQ-030 AC-4/5。**若两种口径都显示 AC-4/5 不达标，如实记录根因（P2 链路在真 vector 下无正向贡献，而非评估口径问题），不强行调阈值声明完成。**

具体目标：

1. **可配置 threshold**：`--semantic-emb-threshold` CLI 参数（默认 0.5，可降到 0.35），报告同时展示多 threshold 命中率。
2. **continuous weighted coverage 字段**：`keypoint_semantic_embedding_continuous_pct = sum(weight * best_sim) / sum(weight)`，不二值化，作为 secondary signal。
3. **真 LLM 重跑验证**：threshold 0.35 + continuous 两种口径重跑 v3，判定 AC-4/5。
4. **根因诊断**：若 AC-4/5 仍不达标，定位是阈值问题还是 P2 链路本身无正向贡献，登记后续任务。

## 非目标

- 不修改 P2 主链路（RRF / ContextPacker / AIChatService）——若诊断指向链路问题，登记独立需求评估，不在本任务修。
- 不引入新依赖。
- 不重跑 REQ-026 / REQ-027 / REQ-029 真 LLM 报告（独立 PR）。
- 不改 REQ-031 的缓存 + 超时机制（已稳定）。

## 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | `--semantic-emb-threshold` CLI 参数（默认 0.5），报告展示 threshold 0.50/0.45/0.40/0.35 多档命中率 | CLI + 报告 |
| AC-2 | ScenarioRun 新增 `keypoint_semantic_embedding_continuous_pct` 字段（continuous weighted coverage） | 字段 + JSON dump |
| AC-3 | 报告 REQ-030 章节增加 continuous 口径列 + per-sample delta | 报告章节 |
| AC-4 | 真 LLM 重跑 v3：threshold 0.35 + continuous 两种口径的 AC-5 (delta ≥ 0.30) 达标数如实记录 | 新报告 |
| AC-5 | Spearman ρ（continuous vs LLM-judge）如实计算 | 新报告 |
| AC-6 | 旧字段（threshold-based semantic_emb）行为不变（向后兼容） | 字段不变 |
| AC-7 | 若 AC-4/5 仍不达标，定位根因（阈值 vs P2 链路）并登记后续任务，不强行声明完成 | Delivery Record + 候选区 |
| AC-8 | dry-run 与 `--allow-llm` 双模式可用 | CLI 行为 |

## 事实源

- REQ-030 报告（REQ-031 后）: `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md`
- REQ-031 requirement: `docs/01-product-planning/05-requirements/REQ-031-p2-semantic-embedding-coverage-stabilization.md`
- 基线脚本: `scripts/validate_req024_p2_real_validation.py`
- v3 样例集: `tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json`

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-20 | 登记 | REQ-031 接力后 semantic_emb 通路稳定（8/10 非零），但 threshold 0.5 过严致 AC-4/5 仍 0/10。登记 REQ-032 阈值校准 |
| 2026-06-20 | 预诊断 | 离线分析 200 个 keypoint-similarity 对：median=0.329 / p75=0.440 / p90=0.537；threshold 0.5 命中率 14%，0.35 命中率 44%。continuous weighted coverage baseline vs weighted delta 全在 -0.15~+0.24，**AC-5 仍 0/10**；continuous vs LLM-judge Pearson=-0.266（负相关）。**预判根因不是阈值，而是 P2 链路在真 vector 下对 keypoint 覆盖无系统性正向贡献** |
| 2026-06-20 | 脚本改造 | `--semantic-emb-threshold` CLI（默认 0.5）+ `keypoint_semantic_embedding_continuous_pct` 字段（continuous weighted coverage，不二值化）+ 报告 cont cov 列 / continuous delta / continuous vs LLM-judge Spearman |
| 2026-06-20 | dry-run | exit 0，0 scenario errors |
| 2026-06-20 | 真 LLM 重跑 | threshold 0.35 + continuous 双口径。**AC-4 (semantic_emb ≥ 0.50): 4/10 达标**（Q1/Q6/Q7/Q10，比 0.5 时 0/10 改善）。**AC-5 三口径各 1/10**：sem_emb Q6 +0.40 / continuous Q9 +0.31 / LLM-judge Q5 +0.40——正向 sample 互不一致。continuous delta 全在 -0.16~+0.31，9/10 中性。continuous vs LLM-judge Pearson=0.072 (n=39)。**最终结论**：评估口径已充分，无法通过调阈值让 AC-5 达 4/10；根因是 P2 链路本身在真 vector 下对 keypoint 覆盖无系统性正向贡献（与 REQ-028 v3 核心发现一致）。登记 REQ-033 评估 P2 链路 |
