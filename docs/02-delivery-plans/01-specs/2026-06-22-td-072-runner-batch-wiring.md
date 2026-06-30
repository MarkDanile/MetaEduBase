# TD-072 Spec: runner.py 接入 `get_embeddings_with_timeout_batch`（TD-071 §5 偏差接力）

> Status: 🟡 进行中（spec）
> Created: 2026-06-22
> Source: TD-071 §5 偏差 + REQ-039 follow-up #4 + AC-4 子集验证报告 §4
> Ledger: `docs/03-engineering-governance/technical-debt.md#td-072`
> Follow-up: REQ-040（本 spec 实施完成 = REQ-040 解除阻塞前条件）

## 1. Problem Statement

TD-071 实施完成 + AC-4 子集验证共同确认：当前"per-text gather within `_EMB_SEMAPHORE=2`"路径虽加速 3-3.4×（50-60min 阻塞 → 17.8min 全 suite），但仍未到 AC-4 ≤10min 目标。

### 1.1 TD-071 §5 偏差（已诚实登记）

`runner.py:_build_service`（L152-153）：

```python
from app.contexts.knowledge.application.embedding_service import get_embedding
return service, service._call_llm, get_embedding  # 第 3 个返回值是单条
```

传给 `coverage._compute_semantic_embedding_coverage` 的 `embedding_callable` 是**单条 `get_embedding(text)`**。

`coverage._get_cached_embeddings_batch`（TD-071 Task 2 实施）接受 `embedding_callable(t)` 单条接口 → 内部走 `asyncio.gather` of per-text 调用 → **HTTP 总数不变**（典型 5-15 条/批都拆成单条 HTTP）。

TD-071 Task 1 实施的 `get_embeddings_with_timeout_batch(texts: list[str])` 是**预留接口，未被使用**。

### 1.2 加速效果

| 路径 | 60 run 推算 | HTTP 总数 | 加速 |
|------|-----------|---------|------|
| 历史阻塞（REQ-037） | 50-60min | ~140 | 1×（基线） |
| TD-071 后（per-text gather + Semaphore=2） | 15-20min（AC-4 子集验证实测 132 run 29.6min 按比例推算） | ~140 | **3-3.4×** |
| **TD-072 后（batch HTTP）** | **5-7min（target）** | **~10-15** | **6-10×** |

HTTP 数从 ~140 降到 ~10-15（5-15 条/批 vs 单条调用），叠加 batch 网络开销摊销，60 run 评估**首次具备 ≤10min 达标的可能**。

### 1.3 与 REQ-039 / AC-4 子集验证报告的关系

- REQ-039 验收报告 §6 follow-up #4：登记"离线批量 keypoint embedding 预计算"为后续候选。
- AC-4 子集验证报告 §4：建议 3 条候选路径（离线批量 keypoint 预计算 / runner.py 接 batch helper / 提 provider 限流）。
- 用户 2026-06-22 决策：**走 runner.py 接 batch helper**（价值最高，1 文件改动 + 1 函数分支判定，工程量最小）。

## 2. Goal

把 AC-4 ≤10min wall-clock 目标**首次变成可达**（之前 spirit 解释被实测推翻，根因是 HTTP 太多）。

| 指标 | 当前 | 目标 |
|------|------|------|
| 60 run 评估 wall-clock | 15-20min（推算） | **≤10min**（AC-4 target） |
| 132 run 全 suite wall-clock | 29.6min（实测） | ~5-7min |
| HTTP 总数（cache miss） | ~140 | ~10-15 |
| `_EMB_STATS` timeout/error | 0 / 0 | 0 / 0（不变） |
| provider 限流（`_EMB_SEMAPHORE=2`） | 维持 | 维持 |
| 现有单测无回归 | 10 passed | 10 passed（不变） |

## 3. Non-Goals

- 不改主链路代码（`PgChunkVectorRetriever` / `PgVectorRecallChannel` / `router.py:278` / `ai_chat_service.py`）
- 不切 provider（保持硅流 Qwen3-Embedding-8B）
- 不改 REQ-031 `_get_cached_embedding` 函数签名
- 不改 TD-070 60s `asyncio.wait_for` 模式
- 不改 `get_embeddings_with_timeout_batch` helper 现有签名（向后兼容 + 测试桩）
- 不改 `_EMB_SEMAPHORE` 值（仍 2）
- 不动 `embedding_service.py`（Task 1 已实施完整）
- 不做"离线批量 keypoint embedding 预计算"（REQ-039 follow-up #4 候选另一条，留独立任务）
- 不做"提 provider 限流"（AC-4 子集验证报告 §4 候选另一条，留独立任务）
- 不重跑 REQ-026/027/028/029 真 LLM 报告（专项任务）
- 不改 graph_edge 通道决策（维持 REQ-036 禁用）
- 不动 `main.py` 现有 `--concurrency` / `asyncio.gather` / per-task session 逻辑（已稳定）

## 4. Design

### 4.1 改动点 1：`runner.py:_build_service` 传 batch callable

**位置**：`scripts/rag_validation/runner.py:152-153`

**Before（TD-071 实施后）**：

```python
# allow_llm: return service's real _call_llm for LLM-as-judge (REQ-028) and
# get_embedding for semantic embedding coverage (REQ-030)
from app.contexts.knowledge.application.embedding_service import get_embedding
return service, service._call_llm, get_embedding  # type: ignore[method-assign]
```

**After（TD-072 实施）**：

```python
# allow_llm: return service's real _call_llm for LLM-as-judge (REQ-028) and
# get_embeddings_with_timeout_batch for semantic embedding coverage (REQ-030,
# TD-072: use the batch variant to cut HTTP count from ~140 to ~10-15).
from app.contexts.knowledge.application.embedding_service import (
    get_embeddings_with_timeout_batch,
)
return (
    service,
    service._call_llm,
    get_embeddings_with_timeout_batch,  # type: ignore[method-assign]
)
```

**关键设计**：
- `_build_service` 返回值元组第 3 项从 `get_embedding`（单条）改为 `get_embeddings_with_timeout_batch`（batch）。
- 旧 `get_embedding` import 删除（runner.py 内部不再直接引用）；coverage.py 内部也不直接 import 它（`embedding_callable` 走参数传递）。
- dry-run 路径（L140-149）仍返回 `None` 作为第 3 项（向后兼容 + `coverage._compute_semantic_embedding_coverage` 已处理 `embedding_callable is None` 的早返回）。

### 4.2 改动点 2：`coverage._get_cached_embeddings_batch` 接受 batch callable

**位置**：`scripts/rag_validation/coverage.py`（TD-071 Task 2 实施的函数）

**核心问题**：当前函数签名 `embedding_callable` 期望 `(text: str) -> list[float] | None` 单条接口；batch helper 签名是 `(texts: list[str]) -> list[list[float] | None]`。

**方案**：检测 callable 签名来路由。**Pythonic 方式**用 `inspect.signature` 检参数个数：

```python
import inspect

def _is_batch_embedding_callable(embedding_callable) -> bool:
    """TD-072: detect whether embedding_callable accepts a list (batch) or
    a single string (per-text). Used to route between batch HTTP and
    per-text gather paths in _get_cached_embeddings_batch.
    """
    if embedding_callable is None:
        return False
    try:
        sig = inspect.signature(embedding_callable)
        # POSITIONAL_OR_KEYWORD params: count those without defaults
        positional_params = [
            p for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)
        ]
        return len(positional_params) == 1
    except (ValueError, TypeError):
        return False
```

**改造 `_get_cached_embeddings_batch`**：

```python
async def _get_cached_embeddings_batch(
    texts: list[str],
    embedding_callable,
    *,
    batch_size: int = 10,
) -> list[list[float] | None]:
    """... (docstring updated) ...

    TD-072: when embedding_callable is a batch variant (signature accepts
    a list[str]), use the native provider batch API (single HTTP call for
    multiple texts). Otherwise fall back to per-text gather within
    _EMB_SEMAPHORE (backward compatibility with single-text callables).
    """
    aligned: list[list[float] | None] = [None] * len(texts)
    if not texts:
        return aligned

    # 1. Dedup + cache hit fast-path (unchanged).
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

    if not miss_texts:
        # All cache hits, return aligned from cache.
        for i, t in enumerate(texts):
            aligned[i] = _EMBEDDING_CACHE.get(t)
        return aligned

    # 2. Detect batch vs per-text callable, route accordingly.
    use_batch_path = _is_batch_embedding_callable(embedding_callable)

    if use_batch_path:
        # TD-072: native batch HTTP path — one call per batch_size chunk.
        import math as _math
        n_batches = _math.ceil(len(miss_texts) / batch_size)
        for batch_idx in range(n_batches):
            start = batch_idx * batch_size
            end = start + batch_size
            batch = miss_texts[start:end]
            try:
                async with _EMB_SEMAPHORE:
                    embs = await asyncio.wait_for(
                        embedding_callable(batch),  # batch call
                        timeout=60.0,
                    )
            except asyncio.TimeoutError:
                _EMB_STATS["timeout"] += 1
                # Per-text fallback for this batch.
                await _per_text_fallback(batch, embedding_callable)
            except Exception:
                _EMB_STATS["error"] += 1
                await _per_text_fallback(batch, embedding_callable)
            else:
                if embs and len(embs) == len(batch):
                    for t, emb in zip(batch, embs):
                        if emb:
                            _EMBEDDING_CACHE[t] = emb
                else:
                    # Malformed response — fallback.
                    _EMB_STATS["error"] += 1
                    await _per_text_fallback(batch, embedding_callable)
    else:
        # TD-071 path: per-text gather within _EMB_SEMAPHORE.
        import math as _math
        n_batches = _math.ceil(len(miss_texts) / batch_size)
        for batch_idx in range(n_batches):
            start = batch_idx * batch_size
            end = start + batch_size
            batch = miss_texts[start:end]
            await _per_text_gather(batch, embedding_callable)

    # 3. Build aligned output (preserves input order + duplicates).
    for i, t in enumerate(texts):
        if not t:
            aligned[i] = None
            continue
        aligned[i] = _EMBEDDING_CACHE.get(t)

    return aligned
```

**辅助函数（同样在 coverage.py）**：

```python
async def _per_text_fallback(batch: list[str], embedding_callable) -> None:
    """TD-072: per-text fallback when batch call fails. Writes cache on
    success; bumps _EMB_STATS["miss"] is NOT bumped here (already counted
    once for the batch)."""
    for t in batch:
        try:
            async with _EMB_SEMAPHORE:
                emb = await asyncio.wait_for(
                    embedding_callable([t]),  # batch with single text
                    timeout=60.0,
                )
        except (asyncio.TimeoutError, Exception):
            continue
        if emb and emb[0]:
            _EMBEDDING_CACHE[t] = emb[0]


async def _per_text_gather(batch: list[str], embedding_callable) -> None:
    """TD-071: per-text gather (backward compat path for single-text
    callables). Mirrors the original TD-071 behavior."""

    async def _one(t: str) -> list[float] | None:
        async with _EMB_SEMAPHORE:
            try:
                emb = await asyncio.wait_for(
                    embedding_callable(t),  # single text
                    timeout=60.0,
                )
            except asyncio.TimeoutError:
                _EMB_STATS["timeout"] += 1
                return None
            except Exception:
                _EMB_STATS["error"] += 1
                return None
        if emb:
            _EMBEDDING_CACHE[t] = emb
        return emb

    await asyncio.gather(*(_one(t) for t in batch))
```

**关键设计**：
- **检测逻辑**用 `inspect.signature` 检查 positional 参数数量：1 = batch callable（接受 list），其他 = 单条 callable（接受 str）。`get_embeddings_with_timeout_batch(texts: list[str])` 是 batch；`get_embedding(text: str)` 是单条。
- **batch 失败时仍走 per-text fallback**（per-text 内部也调 batch callable 传 `[t]` 1 元素 list，复用 batch helper 的 provider-fallback 链）—— 保证 batch 部分失败时不丢精度。
- **检测代码不引入新依赖**（`inspect` 是 stdlib）。
- **保留旧单条 callable 路径**：`_is_batch_embedding_callable` 返回 False 时走原 TD-071 行为，零回归。

### 4.3 `_EMB_STATS` 语义

按"实际发起 provider call 的次数"计：
- **batch 路径**：miss 列表走 N 个 batch（典型 1-3）→ 1 个 batch call 算 1 次 `timeout` / `error`。`_EMB_STATS["miss"]` 在 dedup 时按 unique miss 文本数计（与 TD-071 一致），但实际 provider call 是 batch 块数（比 unique miss 少 5-10×）。
- **单条路径**：per-text 路径保持 TD-031 / TD-071 行为不变。
- **per-keypoint term+synonyms 跨 run 命中**：cache hit 行为不变。

> 说明：本 spec 不要求 `_EMB_STATS` 严格分"miss by unique"和"miss by batch call"；保持 TD-071 既有语义"miss = unique miss 文本数"。这与之前报告（`hit=2177/miss=475` 等）一致。

### 4.4 数据流图

```
runner.py:_build_service
  ↓
  embedding_callable = get_embeddings_with_timeout_batch  (TD-072: 改这里)
_runner._question → coverage._compute_semantic_embedding_coverage
  ↓
  _get_cached_embeddings_batch(_unique_texts, embedding_callable)
    ↓
    1. dedup + cache hit fast-path
       cache hits → 直接返回（_EMB_STATS["hit"]++）
    2. miss 列表
       ↓ 检测 _is_batch_embedding_callable
       ├─ True (batch path): 1 HTTP 拿回 (典型 5-15 条/批)
       │   ↓ 失败
       │   per-text fallback (也走 batch callable 传 [t])
       └─ False (per-text path, TD-071 行为): asyncio.gather 内部
           _EMB_SEMAPHORE 限流
```

## 5. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | `runner.py:_build_service` 改用 `get_embeddings_with_timeout_batch`（1 行 + 1 import 改动） | `git diff` 显示 2 行变更；`ruff check` 通过 |
| AC-2 | `coverage._get_cached_embeddings_batch` 检测 callable 路由：batch callable 走 batch HTTP；单条 callable 走 per-text gather | ad-hoc 验证：mock batch callable，验证 batch HTTP 调用；mock 单条 callable，验证 per-text gather 路径 |
| AC-3 | 现有单测无回归（10 passed） | `pytest tests/contexts/knowledge/test_embedding_service.py -q` 退出码 0 |
| AC-4 | 60 run 真 LLM 评估 wall-clock ≤10min | 跑 REQ-028 v3 10 样例 `--allow-llm --semantic-emb-threshold 0.35 --concurrency 4`，`/usr/bin/time` 输出 ≤600s |
| AC-5 | `_EMB_STATS` timeout=0 / error=0；hit/miss 比例合理 | 报告 `_EMB_STATS` 段 |
| AC-6 | baseline vs graph_edge@0.5 mismatch 量级不恶化（~37 量级，70% LLM 噪声） | 报告 mismatch 分析段 |
| AC-7 | `ruff check` + `scripts/check-engineering-docs` 退出码 0（或仅 pre-existing 警告） | 命令输出 |

## 6. Risks

| 风险 | 缓解 |
|------|------|
| `inspect.signature` 检参数不准确（如 callable 是 `functools.partial` 或 lambda） | 用 `try/except (ValueError, TypeError)` 兜底；如检测失败回退 per-text 路径 |
| batch helper provider 限流不严导致 429 | `_EMB_SEMAPHORE=2` 仍罩 batch 调用（`async with _EMB_SEMAPHORE`），不放大 provider 压力 |
| batch 部分失败回退 per-text 增加 latency | 失败率 < 5% 时净加速仍显著；极端情况有超时兜底 |
| `_EMB_STATS` 语义变更影响现有报告可比性 | miss 计数保持"unique miss 文本"语义，与 TD-071 一致；timeout/error 在 batch 粒度上算 |
| dry-run 路径 `embedding_callable=None` 行为破坏 | 已处理：`if not keypoints or embedding_callable is None: return ...`（L229-236 早返回） |
| `get_embedding` 旧 import 在 runner.py 残留 | 删除旧 import（替换为 `get_embeddings_with_timeout_batch`） |

## 7. Rollback

- 改动只动 2 文件（runner.py + coverage.py）+ 0 主链路代码。
- runner.py 改 1 行 + 1 import → 单 commit revert 即可。
- `coverage._get_cached_embeddings_batch` 的 batch path 失败回退到 per-text 路径（`else` 分支保持原 TD-071 行为），内部版本无破坏。
- AC-1/AC-2/AC-3 不达标时回退到 main HEAD。

## 8. Out of Scope（确认不做）

- 不做"离线批量 keypoint embedding 预计算"（REQ-039 follow-up #4 候选另一条，留独立任务）
- 不提 `_EMB_SEMAPHORE=2`（AC-4 子集验证报告 §4 候选另一条，留独立任务）
- 不切本地 sentence-transformers
- 不改 REQ-018 / REQ-025 P2 链路 retrieval 配置
- 不改 graph_edge 通道决策（维持 REQ-036 禁用）
- 不动 `pg_chunk_vector_retriever` / `pg_vector_recall_channel` / `router.py:278` / `ai_chat_service` 主链路
- 不动 `embedding_service.py`（TD-071 实施的 batch helper 已完整）
- 不动 `main.py`（TD-071 实施的 `--concurrency` / gather 已稳定）
- 不改 `get_embeddings_with_timeout_batch` helper 签名（向后兼容）

## 9. 事实源

- TD-071 spec §5 偏差登记：[2026-06-21-td-071-rag-eval-embedding-batch.md](../01-specs/2026-06-21-td-071-rag-eval-embedding-batch.md#5-4-改动点-1-embedding_service-py-新增-batch-helper)
- TD-071 plan §5 已知遗留：[2026-06-21-td-071-rag-eval-embedding-batch-plan.md](../02-plans/2026-06-21-td-071-rag-eval-embedding-batch-plan.md#5-spec-vs-实际实现偏差诚实登记)
- TD-071 实施 commit `bb375d3`：`get_embeddings_with_timeout_batch` helper 实施完整（4 单测覆盖）
- REQ-039 验收报告 §6 follow-up #4：[2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md#6-follow-up](../01-specs/2026-06-21-req-039-p2-graph-edge-disable-llm-verify-unblock-report.md#6-follow-up)
- AC-4 子集验证报告 §4：[2026-06-22-td-071-ac4-subset-validation-report.md](../01-specs/2026-06-22-td-071-ac4-subset-validation-report.md#4-ac-4-不可达根因建议后续优化方向)
- TD-072 任务卡：[technical-debt.md#td-072](../../03-engineering-governance/technical-debt.md#td-072)
- REQ-040 接力：[REQ-040-p2-runner-batch-helper-wiring.md](../../01-product-planning/05-requirements/REQ-040-p2-runner-batch-helper-wiring.md)
- 当前 wiring：
  - `runner.py:152-153` 传单条 `get_embedding`
  - `coverage._get_cached_embeddings_batch` 接受 `embedding_callable(t)` 单条接口
  - `coverage._compute_semantic_embedding_coverage` 用 `_emb_map` dict 接收 batch 块内多 embedding
- 校验脚本：`scripts/validate_req024_p2_real_validation.py`（`scripts/rag_validation/` 包）
- 样例集：`tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json`（10 样例）
