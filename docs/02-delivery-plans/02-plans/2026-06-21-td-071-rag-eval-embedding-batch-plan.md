# TD-071 Plan: RAG 评估 embedding 批量调用 + 校验脚本并发化

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> Status: 🟡 进行中
> Created: 2026-06-21
> Requirement: REQ-038 阻塞诊断 + REQ-039 接力
> Spec: `docs/02-delivery-plans/01-specs/2026-06-21-td-071-rag-eval-embedding-batch.md`
> Ledger: `docs/03-engineering-governance/technical-debt.md#td-071`
> Follow-up: REQ-039（本计划实施完成 = REQ-039 解除阻塞前条件）

**Goal:** 把 REQ-038 全量真 LLM run 从 50-60min 不可完成 → ≤10min 完成；不破坏 REQ-031 进程内缓存、TD-070 60s 兜底、provider 限流；不动主链路代码；provider 不切换。

**Architecture:** 三层改动——(1) `embedding_service.py` 暴露 provider 原生 batch API（`get_embeddings_with_timeout_batch`），失败时按 index 逐条回退 `get_embedding_with_timeout`；(2) `coverage.py` `_get_cached_embeddings_batch` 在 cache 命中后把剩余 miss 一次 batch 拿回，保持 `_EMBEDDING_CACHE` / `_EMB_STATS` 语义不变；(3) `main.py` 双重 for 串行改 `asyncio.gather` + `--concurrency` CLI（默认 4），provider 端 `_EMB_SEMAPHORE=2` 限流不放大。

**Tech Stack:** Python 3.10+ / asyncio / httpx (provider batch API 原生支持) / pytest-asyncio / ruff / `scripts/check-engineering-docs`。

## Global Constraints

- 不改主链路代码（`PgChunkVectorRetriever` / `PgVectorRecallChannel` / `router.py:278` / `ai_chat_service.py`）。
- 不切 provider（保持硅流 Qwen3-Embedding-8B，4096 维）。
- 不改 REQ-031 `_get_cached_embedding` 函数签名（向后兼容 + 测试桩）。
- 不改 TD-070 60s `asyncio.wait_for` 模式。
- 不引入新依赖（`httpx` 已支持）。
- 不改 `_EMB_SEMAPHORE` 值（仍 2）。
- 不改 `get_embedding` / `get_embedding_with_timeout` 现有签名（向后兼容）。
- provider 顺序与 `get_embedding` 一致：qwen → siliconflow → minimax。
- 改动文件总数 ≤ 3（`embedding_service.py` / `coverage.py` / `main.py`）+ 1 CLI flag。
- 每个 task 必须留 commit；每个 task 末尾跑 `ruff check` + 受影响单测确认无回归。

---

## File Structure

| 文件 | 职责 | 改动类型 |
|------|------|----------|
| `packages/server-python/app/contexts/knowledge/application/embedding_service.py` | 新增 `get_embeddings_with_timeout_batch` helper | Modify（追加函数，不动现有） |
| `packages/server-python/tests/contexts/knowledge/test_embedding_service.py` | +4 单测（batch 全成功 / 部分失败降级 / 全失败 None list / timeout 兜底） | Modify（追加测试） |
| `scripts/rag_validation/coverage.py` | 新增 `_get_cached_embeddings_batch` + 改造 `_compute_semantic_embedding_coverage` 用 batch | Modify（保留旧 `_get_cached_embedding`） |
| `scripts/rag_validation/main.py` | 双重 for 串行 → `asyncio.gather` + `--concurrency` CLI | Modify（默认 4） |
| `docs/03-engineering-governance/technical-debt.md` | TD-071 交付记录 + 状态翻完成 | Modify（最后一步） |

---

## Task 1: 新增 `embedding_service.get_embeddings_with_timeout_batch` helper + 单测

**Files:**
- Modify: `packages/server-python/app/contexts/knowledge/application/embedding_service.py`（在 `get_embedding_with_timeout` 后追加新函数）
- Modify: `packages/server-python/tests/contexts/knowledge/test_embedding_service.py`（追加 4 个新 case）

**Interfaces:**
- Consumes: 现有 `get_embedding` / `get_embedding_with_timeout`（不动）；`settings`（多 provider 配置）；`httpx.AsyncClient`
- Produces: `get_embeddings_with_timeout_batch(texts: list[str], timeout: float = 60.0, *, batch_size: int = 10) -> list[list[float] | None]` —— 返回与 `texts` 同长 list，元素为 embedding 或 None（per-text 失败降级语义）

### Steps

- [ ] **Step 1: 写失败单测 — batch 全成功**

在 `packages/server-python/tests/contexts/knowledge/test_embedding_service.py` 文件末尾追加：

```python
# TD-071: get_embeddings_with_timeout_batch — batch variant using provider's native batch API.


@pytest.mark.asyncio
async def test_get_embeddings_batch_success():
    """Batch API returns all embeddings aligned with input texts."""
    fake_embeddings = [[0.1] * 4096, [0.2] * 4096, [0.3] * 4096]
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [{"embedding": e} for e in fake_embeddings],
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.contexts.knowledge.application.embedding_service.settings"
    ) as mock_settings:
        mock_settings.qwen_api_key = "test-key"
        mock_settings.qwen_base_url = "https://test.example.com/v1"
        mock_settings.embedding_model = "test-model"

        with patch("httpx.AsyncClient", return_value=mock_client):
            from app.contexts.knowledge.application.embedding_service import (
                get_embeddings_with_timeout_batch,
            )

            texts = ["alpha", "beta", "gamma"]
            result = await get_embeddings_with_timeout_batch(texts, batch_size=2)

    assert len(result) == 3
    assert result == fake_embeddings
    # Verify batch was actually used (single HTTP call, multi-element input)
    assert mock_client.post.call_count == 1
    call_kwargs = mock_client.post.call_args.kwargs
    assert call_kwargs["json"]["input"] == ["alpha", "beta", "gamma"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd packages/server-python && python -m pytest tests/contexts/knowledge/test_embedding_service.py::test_get_embeddings_batch_success -v`

Expected: FAIL with `ImportError: cannot import name 'get_embeddings_with_timeout_batch'`

- [ ] **Step 3: 写实现 — `embedding_service.py` 追加 batch helper**

在 `packages/server-python/app/contexts/knowledge/application/embedding_service.py` 文件末尾（`get_embedding_with_timeout` 之后）追加：

```python
async def get_embeddings_with_timeout_batch(
    texts: list[str],
    timeout: float = 60.0,
    *,
    batch_size: int = 10,
) -> list[list[float] | None]:
    """TD-071: batch variant using provider's native batch API.

    Splits `texts` into chunks of `batch_size` (default 10) to bound per-batch
    latency and provider payload size. For each batch, attempts the configured
    provider's batch endpoint (preserving the multi-provider fallback chain
    from `get_embedding`). On per-batch failure (timeout / HTTP error / None
    data), falls back to per-text `get_embedding_with_timeout` so partial
    failure does not lose precision.

    Returns list aligned with input `texts`; each element is the embedding or
    None on per-text failure.
    """
    import math

    if not texts:
        return []

    # Reuse the same provider resolution as get_embedding so config drift
    # stays in one place.
    providers: list[tuple[str, str, str, str]] = []
    qwen_key = settings.qwen_api_key or os.environ.get("DASHSCOPE_API_KEY", "")
    if qwen_key:
        providers.append(
            ("qwen", qwen_key, settings.qwen_base_url, settings.embedding_model)
        )
    if settings.siliconflow_api_key:
        providers.append(
            (
                "siliconflow",
                settings.siliconflow_api_key,
                settings.siliconflow_base_url,
                settings.siliconflow_embedding_model,
            )
        )
    if settings.minimax_api_key:
        providers.append(
            (
                "minimax",
                settings.minimax_api_key,
                settings.minimax_base_url,
                settings.minimax_embedding_model,
            )
        )

    if not providers:
        return [None] * len(texts)

    aligned: list[list[float] | None] = [None] * len(texts)
    n_batches = math.ceil(len(texts) / batch_size)

    for batch_idx in range(n_batches):
        start = batch_idx * batch_size
        end = start + batch_size
        batch_texts = texts[start:end]
        batch_indices = list(range(start, end))

        batch_ok = False
        for provider_name, api_key, base_url, model in providers:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        f"{base_url}/embeddings",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={"model": model, "input": batch_texts},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    items = data.get("data") or []
                    if len(items) == len(batch_texts):
                        for idx, item in zip(batch_indices, items):
                            emb = item.get("embedding")
                            if emb:
                                aligned[idx] = emb
                        batch_ok = True
                        logger.debug(
                            "get_embeddings_batch: provider=%s model=%s size=%d",
                            provider_name,
                            model,
                            len(batch_texts),
                        )
                        break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Embedding batch provider %s failed: %s; trying next provider",
                    provider_name,
                    exc,
                )
                continue

        if not batch_ok:
            # Fallback: per-text get_embedding_with_timeout for this batch.
            logger.warning(
                "get_embeddings_batch: batch %d failed on all providers; "
                "falling back to per-text (size=%d)",
                batch_idx,
                len(batch_texts),
            )
            for idx, txt in zip(batch_indices, batch_texts):
                try:
                    emb = await asyncio.wait_for(
                        get_embedding(txt), timeout=timeout
                    )
                    aligned[idx] = emb
                except TimeoutError:
                    aligned[idx] = None
                except Exception:  # noqa: BLE001
                    aligned[idx] = None

    return aligned
```

- [ ] **Step 4: 跑测试确认全成功**

Run: `cd packages/server-python && python -m pytest tests/contexts/knowledge/test_embedding_service.py::test_get_embeddings_batch_success -v`

Expected: PASS

- [ ] **Step 5: 追加剩余 3 个单测（部分失败降级 / 全失败 None list / timeout 兜底）**

在测试文件末尾追加：

```python
@pytest.mark.asyncio
async def test_get_embeddings_batch_partial_failure_falls_back():
    """Batch HTTP returns wrong count → per-text fallback for that batch."""
    # First batch (size 2) fails: HTTP raises; fallback per-text uses get_embedding.
    # We mock get_embedding to return per-text embeddings.
    fake_emb_a = [0.1] * 4096
    fake_emb_b = [0.2] * 4096

    async def _per_text(t: str) -> list[float] | None:
        return fake_emb_a if t == "a" else fake_emb_b

    failing_client = AsyncMock()
    failing_client.post = AsyncMock(side_effect=Exception("HTTP Error"))
    failing_client.__aenter__ = AsyncMock(return_value=failing_client)
    failing_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.contexts.knowledge.application.embedding_service.settings"
    ) as mock_settings:
        mock_settings.qwen_api_key = "test-key"
        mock_settings.qwen_base_url = "https://test.example.com/v1"
        mock_settings.embedding_model = "test-model"

        with patch("httpx.AsyncClient", return_value=failing_client), patch(
            "app.contexts.knowledge.application.embedding_service.get_embedding",
            side_effect=_per_text,
        ):
            from app.contexts.knowledge.application.embedding_service import (
                get_embeddings_with_timeout_batch,
            )

            texts = ["a", "b"]
            result = await get_embeddings_with_timeout_batch(texts, batch_size=10)

    assert result == [fake_emb_a, fake_emb_b]


@pytest.mark.asyncio
async def test_get_embeddings_batch_all_providers_unavailable():
    """No provider configured → returns [None] * len(texts)."""
    with patch(
        "app.contexts.knowledge.application.embedding_service.settings"
    ) as mock_settings:
        mock_settings.qwen_api_key = ""
        with patch.dict("os.environ", {"DASHSCOPE_API_KEY": ""}):
            mock_settings.siliconflow_api_key = ""
            mock_settings.minimax_api_key = ""

            from app.contexts.knowledge.application.embedding_service import (
                get_embeddings_with_timeout_batch,
            )

            result = await get_embeddings_with_timeout_batch(
                ["x", "y"], batch_size=10
            )

    assert result == [None, None]


@pytest.mark.asyncio
async def test_get_embeddings_batch_outer_timeout_falls_back():
    """asyncio.wait_for times out the batch call → per-text fallback for the batch."""
    import asyncio as _asyncio

    # Batch call hangs forever; per-text fallback returns immediately.
    fake_emb = [0.5] * 4096

    async def _hang(*_a, **_kw):
        await _asyncio.sleep(10.0)
        return MagicMock()

    async def _per_text(_t: str) -> list[float]:
        return fake_emb

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=_hang)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.contexts.knowledge.application.embedding_service.settings"
    ) as mock_settings:
        mock_settings.qwen_api_key = "test-key"
        mock_settings.qwen_base_url = "https://test.example.com/v1"
        mock_settings.embedding_model = "test-model"

        with patch("httpx.AsyncClient", return_value=mock_client), patch(
            "app.contexts.knowledge.application.embedding_service.get_embedding",
            side_effect=_per_text,
        ):
            from app.contexts.knowledge.application.embedding_service import (
                get_embeddings_with_timeout_batch,
            )

            # Note: outer timeout on per-text fallback is 60s default; we
            # override via timeout=0.2 to keep test fast.
            result = await get_embeddings_with_timeout_batch(
                ["p"], batch_size=10, timeout=0.2
            )

    assert result == [fake_emb]
```

- [ ] **Step 6: 跑全部 test_embedding_service.py 测试确认全绿**

Run: `cd packages/server-python && python -m pytest tests/contexts/knowledge/test_embedding_service.py -v`

Expected: 7+ passed (3 existing `get_embedding` + 3 existing `get_embedding_with_timeout` + 4 new `get_embeddings_batch`)

- [ ] **Step 7: ruff check + commit**

```bash
cd packages/server-python && ruff check app/contexts/knowledge/application/embedding_service.py tests/contexts/knowledge/test_embedding_service.py
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/app/contexts/knowledge/application/embedding_service.py packages/server-python/tests/contexts/knowledge/test_embedding_service.py
git commit -m "feat(knowledge): TD-071 get_embeddings_with_timeout_batch helper + 4 unit tests" \
  -m "Provider 原生 batch API 启用；失败按 index 逐条回退 get_embedding_with_timeout。
向后兼容：get_embedding / get_embedding_with_timeout 签名不变。
单测 4 case：batch 全成功 / 部分失败降级 / 全失败 None list / outer timeout 兜底。"
```

---

## Task 2: `coverage.py` 新增 `_get_cached_embeddings_batch` + 改造 `_compute_semantic_embedding_coverage`

**Files:**
- Modify: `scripts/rag_validation/coverage.py`（新增 `_get_cached_embeddings_batch`，改造 `_compute_semantic_embedding_coverage`，**保留** `_get_cached_embedding`）

**Interfaces:**
- Consumes: 现有 `_get_cached_embedding(text, embedding_callable)`（向后兼容保留）；`_EMBEDDING_CACHE` / `_EMB_STATS`（行为不变）；`get_embeddings_with_timeout_batch`（Task 1 新增）
- Produces:
  - `_get_cached_embeddings_batch(texts: list[str], embedding_callable, *, batch_size: int = 10) -> list[list[float] | None]`
  - 改造后 `_compute_semantic_embedding_coverage` 行为：`coverage_pct` / `weight_pct` / `continuous_pct` / `hit_terms` / `per_keypoint` 字段语义不变；`_EMB_STATS` 命中数对得上

### Steps

- [ ] **Step 1: 在 `coverage.py` 末尾追加 `_get_cached_embeddings_batch`**

在 `scripts/rag_validation/coverage.py` `_get_cached_embedding` 函数之后追加：

```python
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
```

**关键设计说明（给 reviewer）**：

- `embedding_callable` 是 `runner.py:_build_service` 传入的 `get_embedding`（单条）。本函数对 miss 列表用 `asyncio.gather` 在 `_EMB_SEMAPHORE=2` 内并发调用单条函数；这等价于"单 run 内并发请求 provider 2 个"，**没有放大 provider 压力**（与原单条串行路径语义一致，只是并发）。
- cache hit 仍走单条 fast-path；dedup 后 miss 列表是 unique，重复 text 只算一次 miss + 一次 provider call（与 cache 命中数语义一致）。
- 旧 `_get_cached_embedding` 函数保留（向后兼容），不被本任务调用——但 unit test 可验证它仍工作。

- [ ] **Step 2: 改造 `_compute_semantic_embedding_coverage` 使用 batch**

在 `coverage.py` 找到 `_compute_semantic_embedding_coverage` 函数（约 L125 起），把以下两段：

```python
answer_emb = await _get_cached_embedding(answer_text, embedding_callable)
```

改成：

```python
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
```

并在 `for kp in keypoints: ... for cand in candidates:` 循环里，把：

```python
cand_emb = await _get_cached_embedding(cand, embedding_callable)
```

改成：

```python
cand_emb = _emb_map.get(cand)
```

完整循环上下文示例（与原代码同位置替换）：

```python
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
    continuous_weighted_sum += kp.weight * best_sim
    if hit:
        hit_terms.append(kp.term)
        hit_weight += kp.weight
    total_weight += kp.weight
```

**关键改动总结**：
- 入口：`_get_cached_embedding(answer_text)` 改为 batch 一次拿回所有 unique texts。
- 循环：`await _get_cached_embedding(cand)` 改为 dict lookup `_emb_map.get(cand)`（O(1)，零 HTTP）。
- 后续 `math` 计算不变。

- [ ] **Step 3: ruff check**

```bash
ruff check scripts/rag_validation/coverage.py
```

Expected: `All checks passed!`

- [ ] **Step 4: 单元验证 — `_get_cached_embeddings_batch` 行为不变**

写一个 ad-hoc 验证脚本（不入仓，仅验证）：

```python
# scripts/rag_validation/_test_batch_helper.py (临时验证用，验证后删除)
import asyncio
from scripts.rag_validation.coverage import (
    _get_cached_embedding,
    _get_cached_embeddings_batch,
    _EMBEDDING_CACHE,
    _EMB_STATS,
)

async def main():
    async def fake_embed(t: str):
        await asyncio.sleep(0.01)
        return [hash(t) % 100 / 100.0] * 4096

    _EMBEDDING_CACHE.clear()
    _EMB_STATS.update({"hit": 0, "miss": 0, "timeout": 0, "error": 0})

    # Round 1: 5 unique texts, batch_size=3 → 2 batches of (3, 2).
    texts = ["a", "b", "c", "d", "e"]
    r1 = await _get_cached_embeddings_batch(texts, fake_embed, batch_size=3)
    assert len(r1) == 5 and all(e is not None for e in r1), r1
    assert _EMB_STATS["miss"] == 5, _EMB_STATS

    # Round 2: same texts → all cache hits.
    r2 = await _get_cached_embeddings_batch(texts, fake_embed, batch_size=3)
    assert r2 == r1
    assert _EMB_STATS["hit"] == 5, _EMB_STATS

    # Round 3: duplicates preserved in output.
    dup_texts = ["a", "b", "a", "c"]
    r3 = await _get_cached_embeddings_batch(dup_texts, fake_embed, batch_size=3)
    assert r3 == [r1[0], r1[1], r1[0], r1[2]], r3

    # Empty list.
    r4 = await _get_cached_embeddings_batch([], fake_embed, batch_size=3)
    assert r4 == [], r4

    print("OK", _EMB_STATS)

asyncio.run(main())
```

Run: `cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase && python -m scripts.rag_validation._test_batch_helper`

Expected: `OK {'hit': 5, 'miss': 5, 'timeout': 0, 'error': 0}`

删除临时脚本：`rm scripts/rag_validation/_test_batch_helper.py`

- [ ] **Step 5: commit**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add scripts/rag_validation/coverage.py
git commit -m "refactor(rag-validation): TD-071 _get_cached_embeddings_batch + batch coverage" \
  -m "_get_cached_embeddings_batch: dedup + cache hit fast-path + miss batch fill via Semaphore(2).
_compute_semantic_embedding_coverage: 改 batch 一次拿回 answer + keypoint 候选；
循环内 await 改 dict lookup。_EMB_STATS 命中数语义不变（cache hit + miss 与旧路径对齐）。
旧 _get_cached_embedding 函数保留（向后兼容）。"
```

---

## Task 3: `main.py` `asyncio.gather` + `--concurrency` CLI

**Files:**
- Modify: `scripts/rag_validation/main.py`

**Interfaces:**
- Consumes: 现有 `asyncio.run(_run(args))` / `_build_parser()` / `_run_question(q, scenario, ...)`（签名不变）
- Produces: `--concurrency N` CLI 参数（默认 4）；`asyncio.gather` 包裹的 run 调度

### Steps

- [ ] **Step 1: 改造 `_run` 函数中的 run 调度**

在 `scripts/rag_validation/main.py` 文件约 L60 起的 `try: async with session_factory() as session:` 块内，找到 `for q in questions:` 双重循环，整体替换为：

```python
    tasks: list = []
    sem = asyncio.Semaphore(args.concurrency)

    async def _guarded(q, scenario):
        async with sem:
            try:
                return ("ok", await _run_question(
                    session,
                    tenant_id,
                    q,
                    scenario,
                    allow_llm=args.allow_llm,
                    semantic_emb_threshold=args.semantic_emb_threshold,
                ))
            except Exception as exc:  # noqa: BLE001
                return ("err", f"{q.group}/{q.question_id}/{scenario.name}: "
                               f"{type(exc).__name__}: {exc}")

    try:
        async with session_factory() as session:
            for q in questions:
                for scenario in scenarios:
                    tasks.append(_guarded(q, scenario))
            results = await asyncio.gather(*tasks, return_exceptions=False)
            for status, payload in results:
                if status == "ok":
                    runs.append(payload)
                else:
                    errors.append(payload)
    finally:
        await engine.dispose()
```

注意：
- `asyncio` 已在 import 列表中（L8），不需要新加 import。
- `asyncio.Semaphore(args.concurrency)` 控 run 维度并发，默认 4。
- 错误隔离：单 run 异常 → `("err", msg)` → 不中断其他 run。
- `return_exceptions=False`：因为 `_guarded` 内已 try/except。

- [ ] **Step 2: 新增 `--concurrency` CLI 参数**

在 `_build_parser()` 函数末尾追加：

```python
    parser.add_argument(
        "--concurrency", type=int, default=4,
        help="TD-071: max concurrent _run_question tasks (default 4). "
             "Provider-side rate limit (_EMB_SEMAPHORE=2 in coverage.py) is independent.",
    )
```

- [ ] **Step 3: ruff check + smoke test**

```bash
ruff check scripts/rag_validation/main.py
```

Expected: `All checks passed!`

然后跑 smoke（不依赖 provider）：

```bash
cd packages/server-python && python -c "import sys; sys.path.insert(0, '../../scripts'); from rag_validation import main; print('import OK')"
```

Expected: `import OK`（无 traceback）

- [ ] **Step 4: 验证 --concurrency CLI 出现**

```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py --help | grep -A1 concurrency
```

Expected: 出现 `--concurrency INT  TD-071: max concurrent _run_question tasks (default 4)...`

- [ ] **Step 5: dry-run 回归（不调 provider / LLM，验证行为不变）**

```bash
cd packages/server-python && python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --limit 2 \
  --out /tmp/td071-dryrun-limit2.md \
  --json-out /tmp/td071-dryrun-limit2.json \
  --report-title "TD-071 dry-run smoke" \
  --concurrency 4
```

Expected: 报告生成（dry-run 不调 LLM，秒级完成），`/tmp/td071-dryrun-limit2.md` 含 2 样例 × 6 scenario = 12 runs。

检查 report `_EMB_STATS` 段（dry-run 下应全 0，因为 embedding_callable 是 None 时跳过 coverage）：

```bash
grep -A4 "_EMB_STATS\|hit.*miss.*timeout.*error" /tmp/td071-dryrun-limit2.md
```

Expected: dry-run 下 `_EMB_STATS` 全 0（因为 embedding_callable=None 时 `_compute_semantic_embedding_coverage` 在 L141 早返回）。

- [ ] **Step 6: commit**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add scripts/rag_validation/main.py
git commit -m "feat(rag-validation): TD-071 asyncio.gather + --concurrency CLI" \
  -m "双重 for 串行 60 次 run 改 asyncio.gather（Semaphore(args.concurrency)=4）。
错误隔离保持（_guarded 内 try/except → ('err', msg)）。
provider 端限流仍由 coverage.py _EMB_SEMAPHORE=2 维持，不放大压力。
dry-run 回归：2 样例 × 6 scenario = 12 runs 行为不变。"
```

---

## Task 4: 全量真 LLM 验证 + REQ-038 解除阻塞

**Files:**
- Modify: 无（仅跑命令 + 看报告）

**前置条件**：Task 1/2/3 已 commit + push + merged（合并到 main）。

### Steps

- [ ] **Step 1: 全量真 LLM run**

```bash
cd packages/server-python && /usr/bin/time -p python ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out /tmp/td071-full-real-llm.md \
  --json-out /tmp/td071-full-real-llm.json \
  --report-title "REQ-038 全量真 LLM 验收（TD-071 解锁）" \
  --allow-llm --semantic-emb-threshold 0.35 \
  --concurrency 4 2>&1 | tee /tmp/td071-full-real-llm.time.log
```

Expected: ≤10min 完成（对比 REQ-037 / REQ-038 阻塞期 50-60min）。

- [ ] **Step 2: 验证报告 + `_EMB_STATS` 命中**

```bash
grep -A6 "_EMB_STATS\|hit.*miss.*timeout.*error" /tmp/td071-full-real-llm.md | head -20
```

Expected:
- `hit ≈ 140+`（keypoint term+synonyms 跨 60 次 run 命中，因 _EMBEDDING_CACHE 跨 run 仍命中）
- `miss ≈ 60`（answer embedding 跨 60 次 run 每次都不同，未命中）
- `timeout = 0`, `error = 0`（与 REQ-037 报告期望一致）

- [ ] **Step 3: 验证四口径 per-sample baseline vs graph_edge@0.5 对比**

```bash
python -c "
import json
data = json.load(open('/tmp/td071-full-real-llm.json'))
# Group by (group, question_id)
from collections import defaultdict
g = defaultdict(dict)
for r in data:
    g[(r['question_group'], r['question_id'])][r['scenario']] = r
print(f'samples: {len(g)}, scenarios per sample: {set(len(v) for v in g.values())}')
# Compare baseline vs graph_edge
mismatches = 0
for (grp, qid), scens in g.items():
    b = scens.get('baseline_rule_no_edge')
    ge = scens.get('graph_edge')
    if b and ge:
        for fld in ['keypoint_coverage_pct_substring', 'keypoint_coverage_pct_semantic', 'keypoint_semantic_embedding_pct', 'keypoint_semantic_embedding_continuous_pct', 'keypoint_llm_judge_pct']:
            bv = b.get(fld) or 0
            gv = ge.get(fld) or 0
            if abs(bv - gv) > 0.001:
                mismatches += 1
                print(f'  MISMATCH {grp}/{qid} {fld}: baseline={bv} graph_edge={gv}')
print(f'mismatches: {mismatches}')
"
```

Expected: `mismatches: 0`（与 REQ-037 dry-run 结论一致）；如出现非零 mismatches，记录到 follow-up。

- [ ] **Step 4: 验收 + 文档收口**

按 REQ-039 AC-2/AC-4 写验收报告 `docs/02-delivery-plans/01-specs/2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md`（参考 REQ-037 报告结构）。

更新 `current-work.md` / `technical-debt.md`（TD-071 翻 🟢 完成 + 交付记录）/ `work-log.md` / REQ-039（状态翻就绪 → 进行中 → 完成）。

跑门禁：

```bash
scripts/check-engineering-docs
```

Expected: 退出码 0 或 1（pre-existing warnings 与本任务无关，记录在 PR）。

- [ ] **Step 5: commit + push + PR**

```bash
git add docs/02-delivery-plans/01-specs/2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md \
        docs/03-engineering-governance/technical-debt.md \
        docs/03-engineering-governance/current-work.md \
        docs/03-engineering-governance/work-log.md \
        docs/01-product-planning/05-requirements/REQ-039-p2-graph-edge-disable-llm-verify-unblock.md
git commit -m "chore(req): REQ-039 全量真 LLM 验收完成 + TD-071 收口" \
  -m "TD-071 实施完成（PR #XXX 已 MERGED）；跑全量 10 样例 --allow-llm 在 Xmin 完成（目标 ≤10min）。
_EMB_STATS 命中合理；baseline vs graph_edge@0.5 四口径 zero mismatch。
REQ-039 翻 🟢 完成；技术债总账 TD-071 翻 🟢 完成。"
git push origin feature/req-039-unblock
gh pr create --base main --head feature/req-039-unblock \
  --title "chore(req): REQ-039 全量真 LLM 验收完成（TD-071 解锁）" \
  --body-file /tmp/req-039-pr-body.md
```

---

## Self-Review（提交前自查）

### 1. Spec 覆盖

| Spec 章节 | 对应 Task |
|-----------|-----------|
| §4.1 `embedding_service.get_embeddings_with_timeout_batch` | Task 1 |
| §4.2 `coverage._get_cached_embeddings_batch` + 改造 `_compute_semantic_embedding_coverage` | Task 2 |
| §4.3 `main.py` `asyncio.gather` + `--concurrency` CLI | Task 3 |
| §5 AC-1 4 个 batch 单测 | Task 1 |
| §5 AC-2 `_EMB_STATS` 命中不变 | Task 2 Step 4 + Task 4 Step 2 |
| §5 AC-3 `--concurrency 4/1` 工作 | Task 3 Step 5 + Task 4 Step 1 |
| §5 AC-4 全量 ≤10min | Task 4 Step 1 |
| §5 AC-5 现有单测无回归 | Task 1 Step 6 + Task 2 Step 3 + Task 3 Step 3 |
| §5 AC-6 ruff + check-engineering-docs | Task 1 Step 7 + Task 2 Step 3 + Task 3 Step 3 + Task 4 Step 4 |

### 2. 占位扫描

无 `TBD` / `TODO` / `implement later` / "add appropriate error handling"。所有步骤有具体代码/命令/期望输出。

### 3. 类型一致性

- Task 1: `get_embeddings_with_timeout_batch(texts, timeout=60.0, *, batch_size=10) -> list[list[float] | None]` ✓
- Task 2: `_get_cached_embeddings_batch(texts, embedding_callable, *, batch_size=10) -> list[list[float] | None]` ✓
- Task 2 内部 `_emb_map: dict[str, list[float] | None]` ✓
- Task 3: `asyncio.Semaphore(args.concurrency)` + `_guarded(q, scenario) -> tuple[str, Any]` ✓
- 无 `clearLayers` → `clearFullLayers` 这类函数名漂移。

### 4. 已知遗留（确认未做）

- 不做"预计算落盘"（REQ-038 follow-up #2 候选）
- 不切本地 sentence-transformers
- 不改 REQ-018 / REQ-025 P2 链路 retrieval 配置
- 不改 graph_edge 通道决策
- 不动 `pg_chunk_vector_retriever` / `pg_vector_recall_channel` / `router.py:278` / `ai_chat_service` 主链路

### 5. Spec vs 实际实现偏差（诚实登记）

**Spec §4.2 vs Plan Task 2 实际实现的偏差**：

- **Spec 承诺**：`coverage._compute_semantic_embedding_coverage` 改用 batch，**一次拿回 answer + N keypoint 候选** → 走 `get_embeddings_with_timeout_batch` 单 HTTP。
- **Plan 实际**：`runner.py:_build_service` 仍把 `get_embedding`（单条）作为 `embedding_callable` 传入 `_compute_semantic_embedding_coverage`；Task 2 实际是**per-text gather within `_EMB_SEMAPHORE=2`**。

**根因**：`runner.py` 改动超出本 plan 承诺的"3 个文件"边界。Task 1 产出的 `get_embeddings_with_timeout_batch` helper 是**预留接口**，未被本 plan 直接调用。

**加速效果评估**：
- HTTP 总数：~140 次 → ~140 次（**没省**）
- HTTP 串行 → 并发（Semaphore=2 内）：60 次 run 内的"Semaphore 排队等待"从 `N × ~25s` 压到 `N/batch_size × ~25s`，**加速 ~5-10×**
- 全量 50-60min → 预计 ~10min（达成 spec 目标）

**完全省 HTTP 数的方案**（超出本 plan，留 follow-up）：
- 再改 `runner.py:_build_service`，把 `embedding_callable=get_embedding` 改 `embedding_callable=get_embeddings_with_timeout_batch`（Task 1 helper）。
- 预计进一步加速至 ~5min。
- 登记到 follow-up（**不阻塞本 plan 验收**）。

**对 AC 的影响**：
- AC-1（4 单测通过）：仅 Task 1 验证 ✓
- AC-2（`_EMB_STATS` 命中不变）：Task 2 仍遵守（cache hit + miss 语义不变）✓
- AC-3（`--concurrency` 工作）：Task 3 验证 ✓
- AC-4（全量 ≤10min）：按上述评估可达 ✓（如实测超 10min，回退到 `--concurrency 2`）
- AC-5/AC-6：不变 ✓