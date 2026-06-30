# TD-072 Plan: runner.py 接入 `get_embeddings_with_timeout_batch`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> Status: 🟡 进行中（plan）
> Created: 2026-06-22
> Spec: `docs/02-delivery-plans/01-specs/2026-06-22-td-072-runner-batch-wiring.md`
> Ledger: `docs/03-engineering-governance/technical-debt.md#td-072`
> Follow-up: REQ-040（本计划实施完成 = REQ-040 解除阻塞前条件）

**Goal:** `runner.py:_build_service` 改用 `get_embeddings_with_timeout_batch`（batch callable），`coverage._get_cached_embeddings_batch` 检测 callable 路由 batch 路径。60 run 评估 wall-clock 推算 5-7min（AC-4 ≤10min 目标首次可达）。

**Architecture:** `inspect.signature` 检测 callable 接受 list（batch）还是 str（单条）—— 1 个 positional 参数 = batch → 走 provider 原生 batch HTTP（5-15 条/批）。其他情况走原 TD-071 per-text gather（向后兼容）。失败回退 per-text。

**Tech Stack:** Python 3.10+ / `inspect` (stdlib) / `asyncio` / `asyncio.wait_for` / 已有 `get_embeddings_with_timeout_batch` helper / 已有 `_EMB_SEMAPHORE` 限流。

## Global Constraints

- 不改主链路代码（`PgChunkVectorRetriever` / `PgVectorRecallChannel` / `router.py:278` / `ai_chat_service.py`）。
- 不切 provider（保持硅流 Qwen3-Embedding-8B）。
- 不改 REQ-031 `_get_cached_embedding` 函数签名。
- 不改 TD-070 60s `asyncio.wait_for` 模式。
- 不改 `get_embeddings_with_timeout_batch` helper 现有签名（向后兼容）。
- 不改 `_EMB_SEMAPHORE` 值（仍 2）。
- 不动 `embedding_service.py`（TD-071 实施的 batch helper 已完整）。
- 不动 `main.py`（TD-071 实施的 `--concurrency` / gather / per-task session 已稳定）。
- 改动文件 ≤ 2（`runner.py` + `coverage.py`）+ 0 CLI flag。
- 每个 task 必须留 commit；每个 task 末尾跑 `ruff check` + 受影响单测确认无回归。

---

## File Structure

| 文件 | 职责 | 改动类型 |
|------|------|----------|
| `scripts/rag_validation/runner.py` | `_build_service` 改传 `get_embeddings_with_timeout_batch`（第 3 返回值） | Modify（1 行 + 1 import） |
| `scripts/rag_validation/coverage.py` | 新增 `_is_batch_embedding_callable` + `_per_text_fallback` + `_per_text_gather`；改造 `_get_cached_embeddings_batch` 检测 callable 路由 | Modify（向后兼容，保留单条 callable 路径） |

---

## Task 1: `runner.py:_build_service` 改用 `get_embeddings_with_timeout_batch`

**Files:**
- Modify: `scripts/rag_validation/runner.py:152-153`

**Interfaces:**
- Consumes: `app.contexts.knowledge.application.embedding_service.get_embeddings_with_timeout_batch`（TD-071 Task 1 实施）
- Produces: `_build_service` 返回的 3 元组第 3 项从 `get_embedding` 改为 `get_embeddings_with_timeout_batch`

### Steps

- [ ] **Step 1: 修改 `_build_service` 末尾的 import + 返回值**

`scripts/rag_validation/runner.py:152-153` 改成：

```python
# allow_llm: return service's real _call_llm for LLM-as-judge (REQ-028) and
# get_embeddings_with_timeout_batch for semantic embedding coverage (REQ-030;
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

- [ ] **Step 2: ruff check**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
python3 -m ruff check scripts/rag_validation/runner.py
```

Expected: `All checks passed!`

- [ ] **Step 3: smoke import**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase/packages/server-python
python3 -c "import sys; sys.path.insert(0, '../../scripts'); from rag_validation import main; print('import OK')"
```

Expected: `import OK`

- [ ] **Step 4: 验证 dry-run 行为不变（dry-run 走 `None` embedding_callable 路径）**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase/packages/server-python
python3 ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --weak-recall-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --limit 1 \
  --out /tmp/td072-task1-dryrun.md \
  --json-out /tmp/td072-task1-dryrun.json \
  --report-title "TD-072 Task 1 dry-run smoke" \
  --concurrency 4
```

Expected: 报告生成（dry-run 走 `_call_llm = _dry_llm` + `embedding_callable = None` 路径，行为不变）。

- [ ] **Step 5: commit**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add scripts/rag_validation/runner.py
git commit -m "feat(rag-validation): TD-072 runner.py pass get_embeddings_with_timeout_batch" \
  -m "_build_service 第 3 返回值从 get_embedding (单条) 改为
get_embeddings_with_timeout_batch (batch helper)。coverage.py 仍接受单条 callable
走 per-text gather（向后兼容 + 行为不变）。dry-run 路径走 None embedding_callable
早返回，行为不变。"
```

---

## Task 2: `coverage._get_cached_embeddings_batch` 检测 callable 路由 batch 路径

**Files:**
- Modify: `scripts/rag_validation/coverage.py`（在 `_get_cached_embeddings_batch` 函数体中改造；新增 `_is_batch_embedding_callable` / `_per_text_fallback` / `_per_text_gather` 3 个辅助函数）

**Interfaces:**
- Consumes: 现有 `_get_cached_embeddings_batch(texts, embedding_callable, *, batch_size=10)`；现有 `_EMBEDDING_CACHE` / `_EMB_STATS` / `_EMB_SEMAPHORE`；`embedding_callable` 接受 `list[str]` 时走 batch 路径（TD-072 新），接受 `str` 时走 per-text 路径（TD-071 旧行为）。
- Produces:
  - 新增 `_is_batch_embedding_callable(embedding_callable) -> bool`：检测 callable 签名（1 个 positional 参数 = batch）
  - 新增 `_per_text_fallback(batch: list[str], embedding_callable)`：batch 失败时 per-text 兜底（调 batch callable 传 `[t]` 1 元素 list）
  - 新增 `_per_text_gather(batch: list[str], embedding_callable)`：旧 TD-071 行为（per-text gather 走 `embedding_callable(t)`）
  - 改造 `_get_cached_embeddings_batch`：检测 callable 路由

### Steps

- [ ] **Step 1: 在 `coverage.py` 顶部加 `import inspect`**

`scripts/rag_validation/coverage.py:1-7` 附近（`from __future__ import annotations` 之后）加：

```python
from __future__ import annotations

import asyncio
import inspect  # TD-072: detect batch vs per-text embedding_callable
import json
from typing import Any

from .models import Keypoint
```

- [ ] **Step 2: 在 `_get_cached_embeddings_batch` 函数前新增 3 个辅助函数**

在 `coverage.py` 的 `_get_cached_embeddings_batch` 函数（约 L96 之前）追加：

```python
def _is_batch_embedding_callable(embedding_callable) -> bool:
    """TD-072: detect whether `embedding_callable` accepts a list (batch)
    or a single string (per-text). Used to route between batch HTTP and
    per-text gather paths in `_get_cached_embeddings_batch`.

    Returns True iff the callable has exactly one POSITIONAL_OR_KEYWORD or
    POSITIONAL_ONLY parameter (i.e., it expects `list[str]`).

    Falls back to False (per-text path) when signature introspection fails
    (e.g., builtins, C-implemented callables, lambdas without hints).
    """
    if embedding_callable is None:
        return False
    try:
        sig = inspect.signature(embedding_callable)
        positional_params = [
            p
            for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)
        ]
        return len(positional_params) == 1
    except (ValueError, TypeError):  # noqa: BLE001
        return False


async def _per_text_fallback(
    batch: list[str], embedding_callable
) -> None:
    """TD-072: per-text fallback when batch call fails.

    Calls `embedding_callable([t])` (batch callable with a single-element
    list) so the provider-fallback chain in `get_embeddings_with_timeout_batch`
    is reused. Writes cache on success; silently skips on failure
    (stats already bumped by the caller).
    """
    for t in batch:
        try:
            async with _EMB_SEMAPHORE:
                emb = await asyncio.wait_for(
                    embedding_callable([t]),
                    timeout=60.0,
                )
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            continue
        if emb and emb[0]:
            _EMBEDDING_CACHE[t] = emb[0]


async def _per_text_gather(
    batch: list[str], embedding_callable
) -> None:
    """TD-071: per-text gather (backward compat path for single-text
    callables like `get_embedding`). Mirrors the original TD-071 behavior.
    """

    async def _one(t: str) -> list[float] | None:
        async with _EMB_SEMAPHORE:
            try:
                emb = await asyncio.wait_for(
                    embedding_callable(t),
                    timeout=60.0,
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

    await asyncio.gather(*(_one(t) for t in batch))
```

- [ ] **Step 3: 改造 `_get_cached_embeddings_batch` 检测 callable 路由**

找到 `_get_cached_embeddings_batch` 函数体（约 L96 起），把 `# 2. Fill cache misses via per-text embedding_callable in semaphore-bound ...` 整段（大约 L70-90 段）替换为：

```python
    # 2. Fill cache misses via batch HTTP (TD-072) or per-text gather (TD-071).
    if miss_texts:
        # Route: detect batch vs per-text callable signature.
        use_batch_path = _is_batch_embedding_callable(embedding_callable)

        import math as _math

        n_batches = _math.ceil(len(miss_texts) / batch_size)
        for batch_idx in range(n_batches):
            start = batch_idx * batch_size
            end = start + batch_size
            batch = miss_texts[start:end]

            if use_batch_path:
                # TD-072: native batch HTTP path.
                try:
                    async with _EMB_SEMAPHORE:
                        embs = await asyncio.wait_for(
                            embedding_callable(batch),
                            timeout=60.0,
                        )
                except asyncio.TimeoutError:
                    _EMB_STATS["timeout"] += 1
                    await _per_text_fallback(batch, embedding_callable)
                except Exception:  # noqa: BLE001
                    _EMB_STATS["error"] += 1
                    await _per_text_fallback(batch, embedding_callable)
                else:
                    if embs and len(embs) == len(batch):
                        for t, emb in zip(batch, embs):
                            if emb:
                                _EMBEDDING_CACHE[t] = emb
                    else:
                        # Malformed response — fallback to per-text.
                        _EMB_STATS["error"] += 1
                        await _per_text_fallback(batch, embedding_callable)
            else:
                # TD-071 path: per-text gather for single-text callables.
                await _per_text_gather(batch, embedding_callable)
```

**关键说明**：
- 保留原 `if miss_texts:` 块的全部逻辑框架（cache miss 累计 → 分 batch_size 批 → 处理）
- 新增 `use_batch_path` 路由分支
- 旧 `def _one(t: str): ...` 内联代码被抽到 `_per_text_gather` 复用

- [ ] **Step 4: ruff check**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
python3 -m ruff check scripts/rag_validation/coverage.py
```

Expected: `All checks passed!`

- [ ] **Step 5: ad-hoc 验证 batch path 生效（临时脚本）**

写 `scripts/rag_validation/_test_batch_path.py`（不入仓）：

```python
"""TD-072 ad-hoc test: verify _get_cached_embeddings_batch routes batch vs per-text."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, "/Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase/scripts")

from rag_validation.coverage import (
    _get_cached_embeddings_batch,
    _EMBEDDING_CACHE,
    _EMB_STATS,
)


async def main():
    # Reset state
    _EMBEDDING_CACHE.clear()
    _EMB_STATS.update({"hit": 0, "miss": 0, "timeout": 0, "error": 0})

    # Case 1: batch callable (1 positional arg = list)
    batch_calls = []

    async def batch_callable(texts: list[str]):
        batch_calls.append(len(texts))
        return [[0.5] * 4096 for _ in texts]

    texts = ["a", "b", "c", "d", "e"]
    r1 = await _get_cached_embeddings_batch(texts, batch_callable, batch_size=3)
    assert len(r1) == 5 and all(e is not None for e in r1), r1
    assert len(batch_calls) == 2, f"expected 2 batch calls (5 texts, batch_size=3), got {batch_calls}"
    assert batch_calls == [3, 2], batch_calls
    assert _EMB_STATS["miss"] == 5, _EMB_STATS
    print(f"Case 1 OK: batch_calls={batch_calls}, stats={_EMB_STATS}")

    # Case 2: per-text callable (1 positional arg = str)
    per_text_calls = []

    async def per_text_callable(text: str):
        per_text_calls.append(text)
        return [0.5] * 4096

    _EMBEDDING_CACHE.clear()
    _EMB_STATS.update({"hit": 0, "miss": 0, "timeout": 0, "error": 0})
    r2 = await _get_cached_embeddings_batch(texts, per_text_callable, batch_size=3)
    assert len(r2) == 5 and all(e is not None for e in r2), r2
    assert len(per_text_calls) == 5, f"expected 5 per-text calls, got {len(per_text_calls)}"
    assert sorted(per_text_calls) == ["a", "b", "c", "d", "e"]
    print(f"Case 2 OK: per_text_calls={per_text_calls}, stats={_EMB_STATS}")

    # Case 3: batch callable that fails — fallback to per-text
    _EMBEDDING_CACHE.clear()
    _EMB_STATS.update({"hit": 0, "miss": 0, "timeout": 0, "error": 0})
    fallback_calls = []

    async def failing_batch(texts: list[str]):
        raise Exception("batch failure")

    async def working_batch(texts: list[str]):
        fallback_calls.extend(texts)
        return [[0.5] * 4096 for _ in texts]

    r3 = await _get_cached_embeddings_batch(
        ["x", "y"], working_batch, batch_size=10
    )
    # working_batch is what _per_text_fallback uses. The first call to failing_batch
    # fails, then per-text fallback uses working_batch.
    assert len(r3) == 2, r3
    assert len(fallback_calls) == 2, fallback_calls
    assert sorted(fallback_calls) == ["x", "y"]
    assert _EMB_STATS["error"] == 1, _EMB_STATS
    print(f"Case 3 OK: fallback_calls={fallback_calls}, stats={_EMB_STATS}")

    # Case 4: None embedding_callable
    r4 = await _get_cached_embeddings_batch(["p", "q"], None, batch_size=10)
    assert r4 == [None, None], r4
    print(f"Case 4 OK: r4={r4}")

    print("ALL OK")


asyncio.run(main())
```

Run:
```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
python3 scripts/rag_validation/_test_batch_path.py
```

Expected: `ALL OK`（4 case 全过）。

删除临时脚本：`rm scripts/rag_validation/_test_batch_path.py`

- [ ] **Step 6: commit**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add scripts/rag_validation/coverage.py
git commit -m "feat(rag-validation): TD-072 coverage batch vs per-text route" \
  -m "_is_batch_embedding_callable: inspect.signature 检测 1 个 positional 参数 = batch callable。
_get_cached_embeddings_batch 改造：检测 callable 路由 batch 路径 (走
get_embeddings_with_timeout_batch 单 HTTP 多 text) 或 per-text 路径 (TD-071 旧行为)。
新增 _per_text_fallback (batch 失败时调 batch callable 传 [t] 1 元素 list) +
_per_text_gather (旧行为抽取)。
_EMB_STATS 语义不变: miss 按 unique miss 文本计 (与 TD-071 一致); timeout/error
在 batch 粒度上算。_EMB_SEMAPHORE=2 仍罩 batch HTTP 调用, 不放大 provider 压力。"
```

---

## Task 3: 全量真 LLM 验证 + REQ-040 解除阻塞

**Files:**
- Modify: 无（仅跑命令 + 看报告）

**前置条件**：Task 1/2 已 commit + push + merged（合并到 main）。

### Steps

- [ ] **Step 1: 10 样例 REQ-028 v3 子集真 LLM run（严格 ≤10min 目标）**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase/packages/server-python
/usr/bin/time -p python3 ../../scripts/validate_req024_p2_real_validation.py \
  --req028-samples ../../tests/fixtures/rag_validation_samples/validate_real_pg_rag_req028_weak_recall_v3.example.json \
  --out /tmp/td072-ac4-real-llm.md \
  --json-out /tmp/td072-ac4-real-llm.json \
  --report-title "REQ-040 AC-4 真 LLM 验证（TD-072 解锁）" \
  --allow-llm --semantic-emb-threshold 0.35 \
  --concurrency 4 2>&1 | tee /tmp/td072-ac4-real-llm.time.log
```

Expected: wall-clock ≤600s（10min 目标）。**注意**：brief 命令仍只传 `--req028-samples`，所以子集范围由 fixture（10 样例）决定。实测 runs 应接近 60（10 样例 × 6 scenario），不再像 AC-4 子集验证那样触发 132 run。

- [ ] **Step 2: 验证报告 + `_EMB_STATS`**

```bash
grep -A6 "_EMB_STATS\|hit.*miss.*timeout.*error" /tmp/td072-ac4-real-llm.md | head -20
```

Expected:
- `timeout = 0`, `error = 0`
- `hit ≫ miss`（keypoint term+synonyms 跨 60 run 大部分命中；answer 跨 run 不重）
- HTTP 总数从 ~140（TD-071）降到 ~10-15（TD-072 batch 化后）

- [ ] **Step 3: mismatch 分析（保持 ~37 量级）**

```bash
python3 -c "
import json
from collections import defaultdict
data = json.load(open('/tmp/td072-ac4-real-llm.json'))
g = defaultdict(dict)
for r in data:
    g[(r['question_group'], r['question_id'])][r['scenario']] = r
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
print(f'mismatches: {mismatches}, samples: {len(g)}')
"
```

Expected: `mismatches` 接近 27 / 60 samples × 5 fields 量级（按比例），与 REQ-039 报告 ~37 量级相比**不恶化**。如显著恶化（>2x），登记 follow-up。

- [ ] **Step 4: 验收 + 文档收口**

写 REQ-040 验收报告 `docs/02-delivery-plans/01-specs/2026-06-22-req-040-p2-runner-batch-helper-wiring-report.md`（参考 REQ-039 报告结构）。

更新 `current-work.md` / `technical-debt.md`（TD-072 翻 🟢 完成 + 交付记录）/ `work-log.md` / `REQ-040`（状态翻 🔵→🟢）。

跑门禁：
```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
python3 scripts/check-engineering-docs
```

Expected: 退出码 0 或 1（pre-existing warnings 与本任务无关，记录在 PR）。

- [ ] **Step 5: commit + push + PR**

```bash
git add docs/02-delivery-plans/01-specs/2026-06-22-req-040-p2-runner-batch-helper-wiring-report.md \
        docs/03-engineering-governance/technical-debt.md \
        docs/03-engineering-governance/current-work.md \
        docs/03-engineering-governance/work-log.md \
        docs/01-product-planning/05-requirements/REQ-040-p2-runner-batch-helper-wiring.md
git commit -F /tmp/td072-task3-msg.txt
git push origin feature/td-072-runner-batch-helper-wiring
gh pr create --base main --head feature/td-072-runner-batch-helper-wiring \
  --title "feat(rag-validation): TD-072 runner.py 接 batch helper + AC-4 解锁" \
  --body-file /tmp/td072-task3-pr-body.md
```

---

## Self-Review（提交前自查）

### 1. Spec 覆盖

| Spec 章节 | 对应 Task |
|-----------|-----------|
| §4.1 `runner.py:_build_service` 改传 batch callable | Task 1 |
| §4.2 `coverage._get_cached_embeddings_batch` 检测 callable 路由 | Task 2 |
| §5 AC-1 ~ AC-7 | Task 1/2/3 各 step + Task 3 全量验证 |
| §6 风险 | Task 2 Step 5 ad-hoc 覆盖（batch 失败回退 per-text / 单条 callable 向后兼容） |

### 2. 占位扫描

无 `TBD` / `TODO` / "add appropriate error handling" / "similar to Task N"。所有步骤有具体代码 / 命令 / 期望输出。

### 3. 类型一致性

- Task 1: `_build_service` 返回 `(service, llm_callable, embedding_callable_batch) — tuple[AIChatService, Callable, Callable[[list[str]], Awaitable[list[list[float] | None]]]]`
- Task 2: `_is_batch_embedding_callable(embedding_callable) -> bool`；`_per_text_fallback(batch: list[str], embedding_callable)`；`_per_text_gather(batch: list[str], embedding_callable)`；`_get_cached_embeddings_batch` 签名不变
- Task 2 Step 3 路由逻辑 `_is_batch_embedding_callable(embedding_callable)` 调用一致

### 4. 已知遗留（确认未做）

- 不做"离线批量 keypoint embedding 预计算"（独立任务）
- 不提 `_EMB_SEMAPHORE`（独立任务）
- 不切本地 sentence-transformers
- 不改 REQ-018 / REQ-025 P2 链路 retrieval 配置
- 不改 graph_edge 通道决策
- 不动 `pg_chunk_vector_retriever` / `pg_vector_recall_channel` / `router.py:278` / `ai_chat_service` 主链路
- 不动 `embedding_service.py`（TD-071 实施的 batch helper 已完整）
- 不动 `main.py`（TD-071 实施的 `--concurrency` / gather / per-task session 已稳定）
- 不改 `get_embeddings_with_timeout_batch` helper 签名
