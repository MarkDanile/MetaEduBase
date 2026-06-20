# REQ-030: P2 RAG 自动质量评估新口径设计

Status: 🟡 部分收口（脚本改造 + 报告生成完成；真 LLM 报告 AC-4/AC-5 未达成，登记 REQ-031 接力）
Priority: P0
Milestone: P2
Source: REQ-028 v3 重跑发现（TD-068+069 schema 修复后 vector 真召回导致 AC-4/AC-5 退步）
Related: REQ-024 / REQ-025 / REQ-026 / REQ-027 / REQ-028 / REQ-029 / TD-068 / TD-069

## 背景

REQ-028 v3 真 LLM 报告在 TD-068+069 schema 修复后重跑，**关键发现**：

- `vector_fallback_count: 152 → 0`（vector 通道真正生效）
- `retrieval_topn.vector: 0 → 16`（真向量召回命中）
- 但 **AC-4 (semantic ≥ 0.50): 7/10 → 6/10** 退步
- **AC-5 residual: 5/10 → 1/10** 严重退步

Per-sample delta 揭示问题：vector 真召回让 baseline coverage 普遍上升（keyword 兜底不再占主导），但 weighted RRF coverage 反而下降，因为真召回的 chunks 不一定包含 expected keypoints 子串。

例如：

| Sample | PR #360 weighted | 本次 weighted | Δ |
|--------|----------------|--------------|---|
| Q2_generator_iterator_relationship | 1.00 | 0.40 | **-0.60** |
| Q6_python_closure | 1.00 | 0.40 | **-0.60** |
| Q4_prerequisite_knowledge_for_course | 0.40 | 0.80 | **+0.40** 改善 |
| Q8_training_program_occupation | 1.00 | 0.40 | **-0.60** |

REQ-028 三口径（substring / semantic / llm_judge）+ REQ-029 residual 阈值在 fake vector 数据上"易达成"，在真 vector 数据上反而要求更严。这暴露了 P2 长链当前评估口径的根本问题：**子串匹配不能识别 LLM 的同义改写**。

REQ-028 v3 重跑报告登记的 follow-up：本任务。

## 目标

设计并实施**新口径 P2 RAG 质量评估指标**，使 P2 链路能力评估在真实向量召回下仍能稳定区分 baseline / weighted 差异。

具体目标：

1. **语义匹配覆盖度**（semantic embedding coverage）：用 query embedding 与 answer embedding 的余弦相似度 + 答案中的语义片段命中 expected keypoints 的向量相似度评分。
2. **关键事实分项权重**（per-keypoint weight）：每个 keypoint 区分核心词 / 修饰词 / 同义词扩展，weight 分配合理。
3. **LLM-as-judge（secondary signal）**：用 LLM 单独评估 answer 与 expected_keypoints 的覆盖度，输出 `{covered, missing, score}` JSON。
4. **新 AC 阈值设计**：基于语义匹配覆盖度 + residual_ratio，给出在真 vector 召回下仍能稳定区分 baseline / weighted 的新 AC 阈值。
5. **验证**：在 REQ-028 v3 10 样例上重跑新口径，期望真召回场景下 baseline / weighted 区分度（delta）稳定 > 0.30。

## 非目标

- 不重写 RRF / ContextPacker / AIChatService 主链路。
- 不修复 TD-068（已 merge）。
- 不调整 graph_edge 权重（REQ-017 范围）。
- 不引入新依赖（如 sentence-transformers, BERT）—— 复用硅流 embedding service。
- 不重跑 REQ-026 / REQ-027 / REQ-029 真 LLM 报告（独立 PR 接力）。

## 验收标准

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 脚本支持 `keypoint_semantic_coverage`（硅流 embedding 计算每个 keypoint 与 answer 的余弦相似度，加权后归一化） | ScenarioRun 字段 |
| AC-2 | 脚本支持 `keypoint_llm_judge_coverage`（LLM-as-judge：输出 `{covered, missing, score}` JSON） | ScenarioRun 字段，可选 `--allow-llm` 触发 |
| AC-3 | 报告新增"REQ-030 三口径对比"章节：semantic embedding / LLM-as-judge / substring (历史) 三种口径 per-sample 矩阵 + delta 对比 | 报告章节 |
| AC-4 | REQ-028 v3 10 样例重跑：semantic embedding 口径下 AC-5 达标率 ≥ 4/10（即 P2 链路在真实 vector 召回下仍能展示 ≥ 40% 样例的正向贡献） | 新报告验证 |
| AC-5 | LLM-as-judge 与 semantic embedding 口径的 Spearman 相关系数 ≥ 0.7（双口径一致性） | 统计计算 |
| AC-6 | 旧 `keypoint_coverage_pct` / `keypoint_coverage_pct_semantic` 字段保留（向后兼容） | 字段不变 |
| AC-7 | 若 AC-4 未达成，必须登记独立 `REQ-031` / `TD-xxx` 接力（不能强行调阈值） | 候选区登记 |
| AC-8 | dry-run 与 `--allow-llm` 两种模式都可用；dry-run 不调 LLM（避免速率限制 / 成本） | CLI 行为 |

## 当前诊断的样例问题

REQ-028 v3 10 样例中：

- **Q1_decorator_concept**: expected_keypoints = `[装饰器, 函数, wrapper, 语法糖, @]`；真实 LLM 答案用"内部函数 / 包装器 / 被装饰的函数"等改写，substring 只能命中"函数"。LLM-as-judge 应能识别"包装器" = "wrapper"。
- **Q6_python_closure**: expected_keypoints = `[闭包, 装饰器, 函数, 内部, 引用]`；真实 LLM 答案用"嵌套函数 / 外层引用"等改写。substring 全 0。Semantic embedding 命中应能识别"嵌套函数" ≈ "内部" + "闭包"。
- **Q2_generator_iterator_relationship**: expected_keypoints = `[生成器, 迭代器, 列表生成式, yield, for]`；真实 LLM 答案可能用"生成器函数 / 可迭代对象"等改写。Semantic embedding 应能识别。

## 建议执行顺序

1. 改造 `validate_req024_p2_real_validation.py` 脚本：
   - 新增 `Keypoint` dataclass 扩展（支持 `synonyms` + `weight`，已存在但需确保向后兼容）
   - 新增 `_compute_semantic_embedding_coverage` 函数（硅流 embedding API）
   - 新增 `_compute_llm_judge_coverage_async` 函数（已存在，需启用）
   - 复用 v3 样例集（keypoint 已带 synonyms + weight）
2. 报告渲染新增"REQ-030 三口径对比"章节
3. 跑 REQ-028 v3 真 LLM 报告（新口径）
4. 验证 AC-4 / AC-5
5. 若不达标，登记 REQ-031 接力

## 事实源

- REQ-028 v3 重跑报告: `docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md`
- REQ-028 requirement: `docs/01-product-planning/05-requirements/REQ-028-p2-auto-quality-metric.md`
- REQ-029 requirement: `docs/01-product-planning/05-requirements/REQ-029-p2-ac5-threshold-redesign.md`
- REQ-028 v3 样例集: `tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json`
- TD-068 详情: `docs/03-engineering-governance/technical-debt.md#td-068`
- TD-069 详情: `docs/03-engineering-governance/technical-debt.md#td-069`

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-06-20 | 登记 | REQ-028 v3 重跑发现 AC-4/AC-5 退步，归根结底是子串匹配 + residual 阈值在真 vector 召回下失效。设计新口径需求登记 |
| 2026-06-20 | 脚本改造 | `_compute_semantic_embedding_coverage` 实现（硅流 embedding cosine）；`_render_req030_section` 报告章节；dry-run 时不跑 embedding（避免 fake LLM 错误）|
| 2026-06-20 | 真 LLM 重跑 | REQ-028 v3 10 样例重跑新口径。**AC-4 (semantic_emb ≥ 0.50): 0/10**，**AC-5 (semantic_emb lift ≥ 0.30): 0/10**，LLM-judge AC-5: 1/10 (Q4 +0.60 正向)，Spearman 相关性 0（scipy 不可用 + Pearson fallback）。**关键诊断**：硅流 embedding 大规模并发调用不稳定 (`failed: ; trying next provider`)，所有 semantic embedding coverage 全 0。**问题在调用频率，不在算法本身** |
| 2026-06-20 | 后续分流 | REQ-031 (⚫ Candidate)：REQ-030 接力 — 降低 AC 阈值（threshold 0.5 → 0.3）+ 加入 batch 限流 (5 req/sec) + 离线预计算 keypoint embeddings（避免每次 query 重新算）+ 评估用本地 sentence-transformers 替代硅流 API |