# REQ-031 Spec: P2 semantic embedding 覆盖率计算稳定性

> Status: 🟣 Shaping
> Created: 2026-06-20
> Source: REQ-030 真 LLM 重跑诊断（semantic_emb 全 0）
> Requirement: `docs/01-product-planning/05-requirements/REQ-031-p2-semantic-embedding-coverage-stabilization.md`
> Plan: `docs/02-delivery-plans/02-plans/2026-06-20-req-031-semantic-embedding-stability-plan.md`

## 1. Problem Statement

REQ-030 实现的 `_compute_semantic_embedding_coverage` 在真 LLM batch 重跑（10 样例 × 4 scenarios）下产出 semantic_emb 全 0。诊断：

- 每个 (sample, scenario) 重新计算所有 keypoint（term + synonyms）的 embedding
- 10 × 4 × ~5 keypoints × ~2 candidates ≈ 440 次串行 HTTP 调用
- 硅流 embedding API 在持续 batch 下响应变慢 / 挂起
- httpx 默认 timeout=30s 不足以保护，进程长时间 CPU 0% 等待

问题在调用频率 + 容错，不在算法。

## 2. Goal

让 semantic embedding coverage 在真 LLM batch 重跑下稳定产出非 0 数据，使 REQ-030 AC-4 / AC-5 可验证。

## 3. Non-Goals

- 不引入 sentence-transformers / BERT（fallback 仅在缓存+超时失败后评估）
- 不修改生产 `embedding_service.py`
- 不改 cosine + threshold 0.5 算法

## 4. Acceptance Criteria

见 requirement 文件 AC-1 ~ AC-8。

## 5. Architecture

### 5.1 进程内 embedding 缓存

keypoint 文本（term + synonyms）在同一脚本运行内静态，跨 4 scenarios 完全相同。用模块级 dict 缓存：

```python
_EMBEDDING_CACHE: dict[str, list[float]] = {}


async def _get_cached_embedding(text: str, embedding_callable) -> list[float] | None:
    """Cache embedding by text. Hard timeout 60s + graceful degradation."""
    if not text:
        return None
    if text in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[text]
    try:
        emb = await asyncio.wait_for(embedding_callable(text), timeout=60.0)
    except (asyncio.TimeoutError, Exception):
        return None  # degrade: keypoint marked not hit
    if emb:
        _EMBEDDING_CACHE[text] = emb
    return emb
```

调用次数对比：

| 项 | 改造前 | 改造后 |
|----|--------|--------|
| keypoint embedding | 10×4×~5×~2 ≈ 400 | 10×~5×~2 ≈ 100（缓存命中 300） |
| answer embedding | 40 | 40（不缓存，每 scenario 答案不同） |
| 合计 | ~440 | ~140 |

### 5.2 硬超时 + 降级

`asyncio.wait_for(..., timeout=60.0)` 保证单次调用最多 60s，超时返回 None。`_compute_semantic_embedding_coverage` 已有 None 检查（`if not cand_emb: continue`），降级为 keypoint 未命中，不会挂起整批。

### 5.3 真 LLM 重跑预期

- 140 次调用 × 平均 ~1-2s = ~3-5 分钟（vs 改造前 440 次挂起 1h+）
- semantic_emb 非零率 ≥ 5/10（AC-3）
- Spearman ρ 如实计算（AC-4，不强制 ≥ 0.7）

## 6. File Layout

```
scripts/
└── validate_req024_p2_real_validation.py    # 改造：_EMBEDDING_CACHE + _get_cached_embedding

docs/02-delivery-plans/01-specs/
└── 2026-06-20-req-030-new-quality-metric-report.md   # 覆盖式重跑（semantic_emb 非零后补判 AC-4/5）
```

## 7. Risks

- **缓存命中率不足**：若 keypoint synonyms 文本在不同 sample 间无重叠，缓存只省同 sample 内 4 scenarios 复用。但 4× 已经够（400→100）。
- **60s 超时仍不够**：若硅流 API 整体不可用，140 次都超时 = 140×60s = 2.3h。需监控；若发生则转 sentence-transformers fallback。
- **semantic_emb 数据语义不可解释**：即使非 0，threshold 0.5 可能过严 / 过松，AC-4 delta ≥ 0.30 可能仍不达。如实记录。

## 8. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | `_EMBEDDING_CACHE` + `_get_cached_embedding` + `wait_for` 超时 | — |
| Slice 2 | dry-run 验证机制不变 | Slice 1 |
| Slice 3 | `--allow-llm` 真 LLM 重跑 v3 + AC 补判 | Slice 2 |
| Slice 4 | 文档收口 + commit + push + PR | Slice 3 |

## 9. References

- REQ-030 requirement: `docs/01-product-planning/05-requirements/REQ-030-p2-rag-new-quality-metric.md`
- REQ-030 报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-030-new-quality-metric-report.md`
- 基线脚本: `scripts/validate_req024_p2_real_validation.py`
