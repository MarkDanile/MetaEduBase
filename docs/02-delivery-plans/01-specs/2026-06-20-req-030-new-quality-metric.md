# REQ-030 Spec: P2 RAG 自动质量评估新口径设计

> Status: 🟣 Shaping
> Created: 2026-06-20
> Source: REQ-028 v3 重跑发现（TD-068+069 schema 修复后 vector 真召回导致 AC 退步）
> Requirement: `docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-030-new-quality-metric-plan.md`

## 1. Problem Statement

REQ-028 v3 重跑揭示 P2 长链当前评估口径（substring + semantic + LLM-as-judge + residual 阈值）在真实向量召回下失效：

- AC-4 (semantic ≥ 0.50): 7/10 → 6/10 退步
- AC-5 residual: 5/10 → 1/10 严重退步

per-sample 显示 LLM 答案质量未退化，但 substring 匹配率下降。子串匹配不能识别 LLM 的同义改写（如"包装器" ≈ "wrapper"），不能识别上下文蕴含。

## 2. Goal

设计新口径 P2 RAG 质量评估指标：

1. **Semantic embedding coverage**：用硅流 embedding 算 answer 与每个 expected_keypoint 的余弦相似度，加权后归一化。
2. **LLM-as-judge coverage（已存在，启用）**：用 LLM 单独评估 answer 与 keypoints 覆盖度，输出 JSON。
3. **新 AC 阈值**：基于新口径，给出在真 vector 召回下仍能稳定区分 baseline / weighted 的 AC 阈值。

## 3. Non-Goals

- 不重写 RRF / ContextPacker / AIChatService 主链路
- 不修复 TD-068（已 merge）
- 不引入新依赖（sentence-transformers 等）
- 不重跑 REQ-026 / REQ-027 / REQ-029 真 LLM 报告（独立 PR）

## 4. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | 脚本支持 `keypoint_semantic_coverage`：answer embedding + keypoint embedding 余弦相似度加权平均 | ScenarioRun 字段 |
| AC-2 | 脚本支持 `keypoint_llm_judge_coverage`：LLM-as-judge 输出 `{covered, missing, score}` | ScenarioRun 字段（需 `--allow-llm`）|
| AC-3 | 报告新增"REQ-030 三口径对比"章节：semantic embedding / LLM-as-judge / substring (历史) per-sample 矩阵 | 报告章节 |
| AC-4 | REQ-028 v3 10 样例重跑：semantic embedding 口径下 P2 weighted 相对 baseline delta ≥ 0.30 的样例 ≥ 4/10 | 新报告验证 |
| AC-5 | LLM-as-judge 与 semantic embedding 口径的 Spearman 相关系数 ≥ 0.7（双口径一致性） | 统计计算 |
| AC-6 | 旧字段 `keypoint_coverage_pct` / `keypoint_coverage_pct_semantic` 保留（向后兼容） | 字段不变 |
| AC-7 | dry-run 与 `--allow-llm` 两种模式都可用 | CLI 行为 |
| AC-8 | 若 AC-4 未达成，登记独立 `REQ-031` / `TD-xxx` 接力 | 候选区登记 |

## 5. Architecture

### 5.1 Semantic Embedding Coverage

```python
def _compute_semantic_embedding_coverage(
    answer_preview: str,
    keypoints: list[Keypoint],  # each with term + synonyms + weight
    embedding_service: Callable,  # get_embedding
) -> dict:
    """Compute weighted semantic coverage using embedding cosine similarity.
    
    Algorithm:
    1. For each keypoint, compute its term's embedding + all synonyms' embeddings
    2. Compute answer embedding (whole text)
    3. For each keypoint, cosine similarity = max(cos(answer, term), cos(answer, each synonym))
    4. Coverage = sum(weight * similarity for keypoints with similarity > 0.5) / sum(weight for all keypoints)
    
    Threshold 0.5 = "semantically related enough to count as hit"
    """
```

### 5.2 LLM-as-judge Coverage (已存在, 启用)

`_compute_llm_judge_coverage_async` 已在 REQ-028 实现（在 `validate_req024_p2_real_validation.py`），需确保：
- 输出 `{covered: [keypoint terms], missing: [keypoint terms], score: 0.0~1.0}` JSON
- 仅在 `--allow-llm` 模式下启用
- dry-run 返回 None

### 5.3 新 AC 阈值

| 口径 | AC-5 阈值 | 理由 |
|------|----------|------|
| substring (历史) | delta ≥ 0.30 | REQ-029 之前；fake vector 时代可达成 |
| residual (REQ-029) | residual_ratio ≥ 0.30 | baseline 高时也公平；fake vector 可达成 |
| **semantic embedding (REQ-030)** | **weighted_semantic - baseline_semantic ≥ 0.30** | 真 vector 召回下能区分能力 |
| LLM-as-judge | weighted_judge - baseline_judge ≥ 0.30 | secondary signal |

### 5.4 双口径一致性 (Spearman)

```
semantic_embedding_score (per sample, per scenario)
vs
llm_judge_score (per sample, per scenario)

rho = spearmanr(semantic, judge).correlation
```

期望 ρ ≥ 0.7（两种语义理解方法对覆盖度的排序一致）。

## 6. File Layout

```
scripts/
├── validate_req024_p2_real_validation.py    # 改造：新增 _compute_semantic_embedding_coverage

docs/02-delivery-plans/01-specs/
└── 2026-06-20-req-030-new-quality-metric-report.md   # 新增：v3 10 样例重跑报告

docs/02-delivery-plans/02-plans/
└── 2026-06-20-req-030-new-quality-metric-plan.md      # 本文件

docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md   # 已产出
```

## 7. Diagnostics Trace

ScenarioRun 新增字段：

```json
{
  "keypoint_semantic_embedding_pct": 0.65,    // 新
  "keypoint_llm_judge_pct": 0.60,            // 已有，需确保启用
  "keypoint_semantic_embedding_hit_terms": ["装饰器", "包装器"],  // 新
  "keypoint_llm_judge_covered": ["装饰器"],   // 已有
  "keypoint_llm_judge_missing": ["@"]         // 已有
}
```

## 8. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | `_compute_semantic_embedding_coverage` 实现 + ScenarioRun 字段 + 报告章节 | — |
| Slice 2 | 真 PG dry-run v3 + 新口径报告（含 LLM-as-judge secondary signal） | Slice 1 |
| Slice 3 | `--allow-llm` 真 LLM 重跑 v3 + Spearman 相关性计算 | Slice 2 |
| Slice 4 | 文档收口 + commit + push + PR | Slice 3 |

## 9. Risks

- **硅流 embedding API 调用成本**：每 sample × 4 scenario × 2 调用（query + keypoint）= 80 次嵌入调用 + LLM-as-judge 80 次 = 160 次 LLM 成本。需 limit 控制
- **semantic embedding 阈值 0.5 偏严**：不同领域 keypoint 可能需调，可能出现 0 coverage 假阴性
- **LLM-as-judge prompt 不稳定**：不同温度下结果可能不一致
- **Spearman 0.7 阈值**：双口径若都用硅流 embedding 可能同质化，无法验证一致性

## 10. References

- REQ-028 v3 重跑报告: `docs/02-delivery-plans/01-specs/2026-06-18-req-028-rag-effect-comparison-v3-report.md`
- REQ-028 requirement: `docs/01-product-planning/05-requirements/REQ-028-p2-auto-quality-metric.md`
- REQ-029 requirement: `docs/01-product-planning/05-requirements/REQ-029-p2-ac5-threshold-redesign.md`
- REQ-028 v3 样例集: `tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json`
- `scripts/validate_req024_p2_real_validation.py` (基线脚本)