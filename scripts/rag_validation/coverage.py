"""Keypoint coverage computation for REQ-024 P2 real validation.

Split out of the original monolithic script (TD-032 slice 8). Holds:
- substring / semantic coverage (REQ-026/028)
- semantic embedding coverage with in-process cache + hard timeout (REQ-030/031)
- LLM-as-judge coverage (REQ-028)

Module-level globals `_EMB_SEMAPHORE` / `_EMBEDDING_CACHE` / `_EMB_STATS` are
process-singletons defined here; `report_quality` reads `_EMB_STATS` only.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .models import Keypoint


def _compute_keypoint_coverage(
    answer_preview: str,
    sources_titles: list[str],
    keypoints: list[Keypoint],
) -> tuple[int, list[str], int, float]:
    """Backward-compatible substring coverage (REQ-026/027 baseline)."""
    if not keypoints:
        return 0, [], 0, 0.0
    haystack = (answer_preview or "") + "\n" + "\n".join(sources_titles or [])
    haystack_lower = haystack.lower()
    hit_list: list[str] = []
    for kp in keypoints:
        if not kp.term:
            continue
        if kp.term.lower() in haystack_lower:
            hit_list.append(kp.term)
    total = len([k for k in keypoints if k.term])
    pct = (len(hit_list) / total) if total else 0.0
    return len(hit_list), hit_list, total, pct


def _compute_semantic_coverage(
    answer_preview: str,
    sources_titles: list[str],
    keypoints: list[Keypoint],
) -> dict[str, Any]:
    """REQ-028 semantic coverage: matches term + synonyms, supports per-keypoint weight.

    Returns dict with: hit_count, total, coverage_pct, weight_pct, hit_terms.
    """
    if not keypoints:
        return {
            "hit_count": 0,
            "total": 0,
            "coverage_pct": 0.0,
            "weight_pct": 0.0,
            "hit_terms": [],
        }
    haystack = ((answer_preview or "") + "\n" + "\n".join(sources_titles or [])).lower()
    hit_terms: list[str] = []
    total_weight = 0.0
    hit_weight = 0.0
    for kp in keypoints:
        if not kp.term:
            continue
        candidates = [kp.term] + list(kp.synonyms or [])
        if any((c or "").lower() in haystack for c in candidates if c):
            hit_terms.append(kp.term)
            hit_weight += kp.weight
        total_weight += kp.weight
    total = len([k for k in keypoints if k.term])
    coverage_pct = (len(hit_terms) / total) if total else 0.0
    weight_pct = (hit_weight / total_weight) if total_weight else 0.0
    return {
        "hit_count": len(hit_terms),
        "total": total,
        "coverage_pct": round(coverage_pct, 4),
        "weight_pct": round(weight_pct, 4),
        "hit_terms": hit_terms,
    }


# REQ-030 / REQ-031: rate limit embedding API calls (硅流 / Qwen 默认 30 req/min，
# 串行排队避免 429 卡死。Semaphore 控制并发数 = 2 即可保证 ≤ 30 req/min 在 batch 内)。
_EMB_SEMAPHORE = asyncio.Semaphore(2)

# REQ-031: 进程内 embedding 缓存。keypoint (term + synonyms) 文本在同一脚本运行内
# 静态，跨 4 scenarios 完全相同，缓存命中避免重复 HTTP 调用。
# 将 10 样例 × 4 scenarios × ~5 keypoints × ~2 candidates ≈ 440 次调用降至 ~140 次。
_EMBEDDING_CACHE: dict[str, list[float]] = {}

# REQ-031: 缓存命中 / miss / 超时降级计数（写报告诊断段）
_EMB_STATS = {"hit": 0, "miss": 0, "timeout": 0, "error": 0}


async def _get_cached_embedding(text: str, embedding_callable) -> list[float] | None:
    """REQ-031: cached embedding with hard timeout + graceful degradation.

    - cache hit: return immediately (no HTTP)
    - cache miss: asyncio.wait_for(embedding_callable(text), timeout=60s)
    - timeout / exception: return None (keypoint marked not hit, no hang)
    - success: write cache + return
    """
    if not text:
        return None
    cached = _EMBEDDING_CACHE.get(text)
    if cached is not None:
        _EMB_STATS["hit"] += 1
        return cached
    _EMB_STATS["miss"] += 1
    try:
        async with _EMB_SEMAPHORE:
            emb = await asyncio.wait_for(embedding_callable(text), timeout=60.0)
    except asyncio.TimeoutError:
        _EMB_STATS["timeout"] += 1
        return None
    except Exception:  # noqa: BLE001
        _EMB_STATS["error"] += 1
        return None
    if emb:
        _EMBEDDING_CACHE[text] = emb
    return emb


async def _get_cached_embeddings_batch(
    texts: list[str],
    embedding_callable,
    *,
    batch_size: int = 10,
) -> list[list[float] | None]:
    """TD-071: batched cache lookup + provider batch fill.

    - Dedup by `text` (dict preserves order).
    - Cache hits return immediately (no HTTP); bump `_EMB_STATS["hit"]`.
    - Cache misses accumulate; pass unique misses to provider via
      `embedding_callable` (per-text). Within a batch chunk (size
      `batch_size`), per-text calls run concurrently via `asyncio.gather`,
      with each call entering `async with _EMB_SEMAPHORE` to keep provider
      pressure at ≤ 2 (same as the pre-existing single-call path).
    - Per-text timeout: `asyncio.wait_for(embedding_callable(t), 60.0)`;
      on `asyncio.TimeoutError` → `_EMB_STATS["timeout"]++` + return None;
      on other exception → `_EMB_STATS["error"]++` + return None.
    - On success: write `_EMBEDDING_CACHE[t] = emb` and return.
    - Returns list aligned with input `texts` (preserves duplicates and
      original order).
    """
    aligned: list[list[float] | None] = [None] * len(texts)
    if not texts:
        return aligned

    # 1. Dedup while preserving order; collect miss list.
    seen: dict[str, None] = {}
    miss_texts: list[str] = []
    for t in texts:
        if not t:
            continue
        if t in _EMBEDDING_CACHE:
            _EMB_STATS["hit"] += 1
        elif t not in seen:
            seen[t] = None
            miss_texts.append(t)
            _EMB_STATS["miss"] += 1

    # 2. Fill cache misses via per-text embedding_callable in semaphore-bound
    #    concurrent batches. We do NOT call get_embeddings_with_timeout_batch
    #    directly here because `embedding_callable` (passed in by runner.py) is
    #    `get_embedding` from server-python — a single-text function. The batch
    #    optimization at the embedding_service layer (Task 1) is exercised when
    #    callers invoke it directly. Here we batch the *callable invocations*
    #    with the existing Semaphore(2) to keep provider pressure identical.
    if miss_texts:
        # Process misses in chunks of `batch_size`; within a batch, run calls
        # concurrently limited by _EMB_SEMAPHORE.
        import math as _math

        n_batches = _math.ceil(len(miss_texts) / batch_size)
        for batch_idx in range(n_batches):
            start = batch_idx * batch_size
            end = start + batch_size
            batch = miss_texts[start:end]

            async def _one(t: str) -> list[float] | None:
                async with _EMB_SEMAPHORE:
                    try:
                        emb = await asyncio.wait_for(
                            embedding_callable(t), timeout=60.0
                        )
                    except asyncio.TimeoutError:
                        _EMB_STATS["timeout"] += 1
                        return None
                    except Exception:  # noqa: BLE001
                        _EMB_STATS["error"] += 1
                        return None
                if emb:
                    _EMBEDDING_CACHE[t] = emb
                return emb

            results = await asyncio.gather(*(_one(t) for t in batch))
            for t, emb in zip(batch, results):
                if emb is not None:
                    _EMBEDDING_CACHE[t] = emb

    # 3. Build aligned output (preserves input order + duplicates).
    for i, t in enumerate(texts):
        if not t:
            aligned[i] = None
            continue
        aligned[i] = _EMBEDDING_CACHE.get(t)

    return aligned


async def _compute_semantic_embedding_coverage(
    answer_preview: str,
    sources_titles: list[str],
    keypoints: list[Keypoint],
    embedding_callable,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """REQ-030 semantic embedding coverage: cosine similarity between answer
    embedding and each keypoint's term + synonyms embeddings.

    REQ-031: uses _get_cached_embedding (in-process cache + 60s hard timeout)
    so keypoint embeddings are computed once per script run and reused across
    the 4 scenarios per sample.

    Returns dict with: coverage_pct, weight_pct, hit_terms, per_keypoint.
    """
    if not keypoints or embedding_callable is None:
        return {
            "coverage_pct": 0.0,
            "weight_pct": 0.0,
            "hit_terms": [],
            "per_keypoint": [],
            "error": "no embedding_callable or empty keypoints",
        }
    answer_text = (answer_preview or "") + "\n" + "\n".join(sources_titles or [])
    if not answer_text.strip():
        return {
            "coverage_pct": 0.0,
            "weight_pct": 0.0,
            "hit_terms": [],
            "per_keypoint": [],
        }
    # TD-071: batched — collect answer + all keypoint candidates, single batch call.
    _unique_texts: list[str] = [answer_text]
    for _kp in keypoints:
        if not _kp.term:
            continue
        _unique_texts.append(_kp.term)
        _unique_texts.extend(s for s in (_kp.synonyms or []) if s)
    _unique_texts = list(dict.fromkeys(_unique_texts))  # dedup, preserve order
    _embs = await _get_cached_embeddings_batch(
        _unique_texts, embedding_callable, batch_size=10
    )
    _emb_map = dict(zip(_unique_texts, _embs))
    answer_emb = _emb_map.get(answer_text)
    if not answer_emb:
        return {
            "coverage_pct": 0.0,
            "weight_pct": 0.0,
            "hit_terms": [],
            "per_keypoint": [],
            "error": "answer embedding failed (timeout/error/None)",
        }

    import math
    hit_terms: list[str] = []
    per_keypoint: list[dict[str, Any]] = []
    total_weight = 0.0
    hit_weight = 0.0
    continuous_weighted_sum = 0.0  # REQ-032

    for kp in keypoints:
        if not kp.term:
            continue
        candidates = [kp.term] + [s for s in (kp.synonyms or []) if s]
        best_sim = 0.0
        best_text = kp.term
        for cand in candidates:
            cand_emb = _emb_map.get(cand)
            if not cand_emb or len(cand_emb) != len(answer_emb):
                continue
            # cosine similarity
            dot = sum(a * b for a, b in zip(answer_emb, cand_emb))
            norm_a = math.sqrt(sum(a * a for a in answer_emb))
            norm_c = math.sqrt(sum(b * b for b in cand_emb))
            if norm_a == 0 or norm_c == 0:
                continue
            sim = dot / (norm_a * norm_c)
            if sim > best_sim:
                best_sim = sim
                best_text = cand
        hit = best_sim >= threshold
        per_keypoint.append({
            "term": kp.term,
            "best_match": best_text,
            "similarity": round(best_sim, 4),
            "hit": hit,
            "weight": kp.weight,
        })
        # REQ-032: continuous weighted coverage accumulator (no binarization)
        continuous_weighted_sum += kp.weight * best_sim
        if hit:
            hit_terms.append(kp.term)
            hit_weight += kp.weight
        total_weight += kp.weight

    total = len([k for k in keypoints if k.term])
    coverage_pct = (len(hit_terms) / total) if total else 0.0
    weight_pct = (hit_weight / total_weight) if total_weight else 0.0
    # REQ-032: continuous = sum(weight * best_sim) / sum(weight), range [0, 1]
    continuous_pct = (continuous_weighted_sum / total_weight) if total_weight else 0.0
    return {
        "coverage_pct": round(coverage_pct, 4),
        "weight_pct": round(weight_pct, 4),
        "continuous_pct": round(continuous_pct, 4),
        "hit_terms": hit_terms,
        "per_keypoint": per_keypoint,
    }


def _compute_llm_judge_coverage(
    answer_preview: str,
    keypoints: list[Keypoint],
    llm_callable,
) -> dict[str, Any] | None:
    """Sync placeholder. Real implementation is the async variant below; this
    exists only so legacy callers that import the sync name still resolve.
    Use ``await _compute_llm_judge_coverage_async(...)`` instead.
    """
    return None


async def _compute_llm_judge_coverage_async(
    answer_preview: str,
    keypoints: list[Keypoint],
    llm_callable,
) -> dict[str, Any] | None:
    """Async LLM-as-judge coverage (REQ-028).

    Returns None when llm_callable is None (dry-run mode).
    """
    if llm_callable is None or not keypoints:
        return None
    keypoint_terms = [kp.term for kp in keypoints if kp.term]
    if not keypoint_terms:
        return None
    system_prompt = (
        "你是一名严谨的答案评估员。给定一段 AI 回答和一组关键事实，"
        "判断关键事实在回答中是否被覆盖。忽略同义改写和上下文蕴含，"
        "只判断显式或明确等价表述是否出现。"
        "严格输出 JSON: {\"covered\": [\"事实1\", ...], \"missing\": [\"事实2\", ...], \"score\": 0.0~1.0}。"
        "score = len(covered) / len(全部事实)，范围 [0, 1]。不要输出 JSON 以外内容。"
    )
    user_prompt = (
        f"## 关键事实列表（共 {len(keypoint_terms)} 条）\n"
        + "\n".join(f"{i+1}. {t}" for i, t in enumerate(keypoint_terms))
        + "\n\n## AI 回答\n"
        + (answer_preview or "(空)")
    )
    try:
        raw = await llm_callable(system_prompt, user_prompt)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "coverage_pct": None}
    if not raw:
        return {"error": "empty llm output", "coverage_pct": None}
    # Parse JSON robustly: find first { ... } block.
    text = str(raw).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {"error": "llm output not JSON", "raw": text[:200], "coverage_pct": None}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        return {"error": f"json parse: {exc}", "raw": text[:200], "coverage_pct": None}
    score = data.get("score")
    if not isinstance(score, (int, float)):
        score = None
    return {
        "covered": list(data.get("covered", []) or []),
        "missing": list(data.get("missing", []) or []),
        "score": score,
        "coverage_pct": round(float(score), 4) if isinstance(score, (int, float)) else None,
    }
    # Parse JSON robustly: find first { ... } block.
    text = raw.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {"error": "llm output not JSON", "raw": text[:200], "coverage_pct": None}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        return {"error": f"json parse: {exc}", "raw": text[:200], "coverage_pct": None}
    score = data.get("score")
    if not isinstance(score, (int, float)):
        score = None
    return {
        "covered": list(data.get("covered", []) or []),
        "missing": list(data.get("missing", []) or []),
        "score": score,
        "coverage_pct": round(float(score), 4) if isinstance(score, (int, float)) else None,
    }
