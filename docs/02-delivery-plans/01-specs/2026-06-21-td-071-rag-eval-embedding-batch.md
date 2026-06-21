# TD-071 Spec: RAG 评估 embedding 批量调用 + 校验脚本并发化

> Status: 🟡 进行中（spec）
> Created: 2026-06-21
> Source: REQ-038 阻塞诊断（用户决策 2026-06-21 采纳方案 A+D）
> Ledger: `docs/03-engineering-governance/technical-debt.md#td-071`
> Follow-up: REQ-039（本 spec 实施完成 = REQ-039 解除阻塞前条件）

## 1. Problem Statement

REQ-038 全量真 LLM 验收（10 样例 × 6 scenario = 60 次 `_run_question`）因 embedding provider 累积吞吐阻塞。深度诊断显示阻塞由 **2 个可改代码结构** 放大，与 provider 自身吞吐改善无强耦合。

### 1.1 累积成本结构

| 路径 | 调用点 | 次数 | 可缓存？ |
|------|--------|------|----------|
| vector-recall query embedding | `PgChunkVectorRetriever` → `get_embedding_with_timeout` | 60 | ❌ |
| answer embedding | `_compute_semantic_embedding_coverage` → `_get_cached_embedding` | 60 | ❌ |
| keypoint embedding | 同上 | ~140 | ✅ REQ-031 进程内缓存 |
| **合计单条 HTTP** | — | **120 次** | — |
| 单次耗时（硅流） | — | ~25-30s | — |
| **总耗时** | — | **50-60min** | — |

单次探针 provider 可用（`get_embedding_with_timeout('测试')` → OK dim=4096 ~30s），CPU 0% 网络 I/O 等待。**问题在累积吞吐，非单次可用性或代码缺陷。** TD-070 把"无限阻塞"改为"60s fail-fast 降级"，但 60 次串行 run 的总成本仍超可接受时间。

### 1.2 三个被忽视的非吞吐问题

1. **Provider 原生支持 batch，未启用**：`SiliconFlowProvider.embed(self, texts: list[str], timeout=60.0)`（`packages/server-python/app/shared/llm/providers/siliconflow.py:37-55`）接受 `input: texts` 列表（多元素）。**当前 `embedding_service.get_embedding` 只暴露单条接口**（`input: [text]` 单元素列表），把 120 次单条调用串行排队——而 1 次 batch=10 调用大约等于 1 次单条调用的网络等待时间。

2. **校验脚本 run 串行**：`scripts/rag_validation/main.py:60-77` 是双重 for 串行：
   ```python
   for q in questions:
       for scenario in scenarios:
           await _run_question(...)  # 60 次串行
   ```
   即使单次加速到 5s，60 次串行仍 5min；batch 化只解决"单 run 内"问题，跨 run 仍串行。

3. **Semaphore=2 是限流，不解决累积**：`scripts/rag_validation/coverage.py:85` `_EMB_SEMAPHORE = asyncio.Semaphore(2)` 是为了"避免 429 卡死"。**Batch 化后 Semaphore 仍控总并发 2，不放大 provider 压力**——本 spec 复用这个限流而非放大。

### 1.3 与 REQ-038 §"解除阻塞条件"的关系

REQ-038 列了 3 个解除条件：
1. embedding provider 吞吐改善（单次 < 5s，或并发批次支持） → **本 spec 不靠这个**
2. 校验脚本架构改为"预计算所有 answer+recall embedding 落盘 + 脚本读缓存离线 run"模式（需改 `scripts/rag_validation/` 架构，工程量大） → **本 spec 不走这条**
3. 切换到本地 sentence-transformers embedding → **本 spec 不切 provider**

本 spec 走"不改 provider、不改架构、改调用方式 + 改 run 模型"的最小代码改造路径。

## 2. Goal

把 REQ-038 全量真 LLM run 从 50-60min 不可完成 → **≤10min 完成**；保持 REQ-031 进程内缓存命中统计不变；不破坏 TD-070 60s 兜底；不动主链路代码；provider 不切换。

| 指标 | 当前 | 目标 |
|------|------|------|
| REQ-038 全量 10 样例 `--allow-llm` 耗时 | 50-60min 阻塞 | ≤ 10min |
| REQ-031 `_EMB_STATS` keypoint 命中率（cache hit） | ~140/140 = 100% | 100%（不变） |
| TD-070 60s 兜底 | ✓ | ✓（不变） |
| provider 限流（_EMB_SEMAPHORE=2） | ✓ | ✓（不变） |
| 现有单测无回归 | — | 全绿 |

## 3. Non-Goals

- 不改主链路代码（`PgChunkVectorRetriever` / `PgVectorRecallChannel` / `router.py:278` / `ai_chat_service.py`）
- 不切 provider（保持硅流 Qwen3-Embedding-8B）
- 不改 REQ-031 `_get_cached_embedding` 行为（cache + stats 保持）
- 不改 TD-070 60s `asyncio.wait_for` 模式
- 不引入新依赖（`httpx` 已支持）
- 不做"预计算落盘"（架构改造，REQ-038 follow-up #2 候选，本 spec 不走）
- 不改 `_EMB_SEMAPHORE` 值（仍 2）
- 不改 `get_embedding` / `get_embedding_with_timeout` 现有签名（向后兼容 + 测试桩）
- 不动 REQ-037 dry-run 已实证的结论（仅接力 REQ-038 补强真 LLM 口径）

## 4. Design

### 4.1 改动点 1：`embedding_service.py` 新增 batch helper

**位置**：`packages/server-python/app/contexts/knowledge/application/embedding_service.py`（在 `get_embedding_with_timeout` 后追加）

**新增**：

```python
async def get_embeddings_with_timeout_batch(
    texts: list[str],
    timeout: float = 60.0,
    *,
    batch_size: int = 10,
) -> list[list[float] | None]:
    """TD-071: batch variant using provider's native batch API.

    - Splits `texts` into chunks of `batch_size` (default 10) to bound
      per-batch latency and provider payload size.
    - For each batch: call provider's batch API via the first configured
      provider (Qwen > SiliconFlow > MiniMax), preserving the multi-provider
      fallback chain from `get_embedding`.
    - On per-batch failure (timeout / HTTP error / None data): fall back to
      per-text `get_embedding_with_timeout` for that batch's texts, so partial
      failure does not lose precision.
    - Returns list aligned with input `texts`; each element is the embedding
      or None on per-text failure.
    """
```

**关键设计**：
- **Provider 顺序与 `get_embedding` 一致**：qwen → siliconflow → minimax；复用现有多 provider fallback 链。
- **复用 `_EMB_SEMAPHORE` 行为**：本 helper 在 `coverage.py` 层受 `_EMB_SEMAPHORE` 限流（详见 4.2）；helper 自身**不**再加锁，避免双重 Semaphore。
- **Batch 失败 → 逐条回退**：单 batch 失败（timeout / HTTP / None）时该批内 text 逐条 `get_embedding_with_timeout`，与现状 per-text `None` 降级语义一致。
- **60s 超时罩整个 batch 调用**：`asyncio.wait_for(batch_call, timeout=60.0)`，与 TD-070 模式一致。
- **`get_embedding` / `get_embedding_with_timeout` 不动**：向后兼容（`test_pg_chunk_vector_retriever_embedding_fallback.py` 现有 patch 不破）。

### 4.2 改动点 2：`coverage.py` `_compute_semantic_embedding_coverage` 改 batch

**位置**：`scripts/rag_validation/coverage.py`

**新增函数**：

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
    - Cache misses accumulate; split into batches of `batch_size` (default 10).
    - Per batch: `async with _EMB_SEMAPHORE` (rate limit) + `asyncio.wait_for(
      get_embeddings_with_timeout_batch(...), timeout=60.0)`.
    - On timeout/error per batch: increment `_EMB_STATS["timeout"|"error"]`,
      mark all texts in that batch as miss with None.
    - On success: write `_EMBEDDING_CACHE` for each text + return.
    - Returns list aligned with input `texts` (preserves duplicates).
    """
```

**改造 `_compute_semantic_embedding_coverage`**：

```python
# Before (current):
answer_emb = await _get_cached_embedding(answer_text, embedding_callable)
# ... loop:
for cand in candidates:
    cand_emb = await _get_cached_embedding(cand, embedding_callable)
    # ...

# After (TD-071):
texts = [answer_text] + [cand for kp in keypoints for cand in [kp.term] + list(kp.synonyms or []) if cand]
texts = list(dict.fromkeys(texts))  # dedup, preserve order
embeddings = await _get_cached_embeddings_batch(texts, embedding_callable, batch_size=10)
emb_map = dict(zip(texts, embeddings))
answer_emb = emb_map.get(answer_text)
# ... loop:
for cand in candidates:
    cand_emb = emb_map.get(cand)
    # ...
```

**关键设计**：
- **`_EMBEDDING_CACHE` / `_EMB_STATS` 行为不变**：先吃 cache hit（hit++），再 batch 拿 miss（miss++）；与 REQ-031 报告里"hit=1581/miss=259"等统计可对照验证。
- **批内顺序与输入对齐**：`dict.fromkeys` + `zip` 保证返回 list 与 `texts` 索引一致。
- **批大小 10 默认**：覆盖典型 "1 answer + 5-9 keypoint candidates" 场景；通过 `batch_size` 参数允许测试桩传入更小值（如 1）以触发单条回退路径。
- **保持 60s 单批总超时**：与 TD-070 模式一致。

### 4.3 改动点 3：`main.py` 改 `asyncio.gather` + `--concurrency` CLI

**位置**：`scripts/rag_validation/main.py`

**改造**：

```python
# Before (current):
for q in questions:
    for scenario in scenarios:
        try:
            runs.append(await _run_question(...))
        except Exception as exc:
            errors.append(...)

# After (TD-071):
import asyncio
sem = asyncio.Semaphore(args.concurrency)
async def _guarded(q, scenario):
    async with sem:
        try:
            return ("ok", await _run_question(...))
        except Exception as exc:
            return ("err", f"{q.group}/{q.question_id}/{scenario.name}: {type(exc).__name__}: {exc}")

tasks = [_guarded(q, s) for q in questions for s in scenarios]
results = await asyncio.gather(*tasks, return_exceptions=False)
for status, payload in results:
    if status == "ok":
        runs.append(payload)
    else:
        errors.append(payload)
```

**新增 CLI 参数**：

```python
parser.add_argument(
    "--concurrency", type=int, default=4,
    help="TD-071: max concurrent _run_question tasks (default 4). "
         "Note: provider-side rate limit (_EMB_SEMAPHORE=2 in coverage.py) is independent.",
)
```

**关键设计**：
- **`Semaphore(args.concurrency)` 控 run 维度并发**：默认 4，可下调到 2（与 provider 限流对齐）或上调到 8（实验性）。
- **provider 限流仍由 `_EMB_SEMAPHORE=2` 维持**：run 间并发提升，但每个 run 内调 provider 仍受 Semaphore=2 约束，**不放大 provider 压力**。
- **错误隔离**：单 run 异常不中断其他 run（与现状 try/except 行为一致）。
- **`return_exceptions=False`**：因为我们在 `_guarded` 内已捕获 + 编码为 `("err", msg)`，gather 不需要再包一层。

### 4.4 数据流图

```
main.py
  ↓ for q × s → tasks
asyncio.gather(tasks, max_concurrency=4)
  ↓ per task (Semaphore 守护)
_run_question(q, scenario)
  ├→ service.chat() → PgChunkVectorRetriever → get_embedding_with_timeout
  │    (受 _EMB_SEMAPHORE=2 约束，run 间并行但 provider 端 ≤ 2 并发)
  └→ _compute_semantic_embedding_coverage
        └→ _get_cached_embeddings_batch([answer + candidates], batch_size=10)
              ├─ cache hits → 直接返回（_EMB_STATS["hit"]++）
              └─ cache misses (典型 ≤ 10) → 1 batch HTTP → provider
                    └─ batch 失败 → 逐条 get_embedding_with_timeout 回退
```

## 5. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | `embedding_service.get_embeddings_with_timeout_batch` 实现 + 4 单测通过（batch 全成功 / 部分失败降级 / 全失败 None list / timeout 兜底） | `pytest tests/contexts/knowledge/test_embedding_service.py -q` 退出码 0；4 个新 case 全绿 |
| AC-2 | `coverage._compute_semantic_embedding_coverage` 改 batch 后行为不变：`_EMB_STATS` 命中数对得上（10 样例 × 6 scenario 一次 dry-run 比对，cache hit 计数与改造前一致） | dry-run 比对脚本：跑前/后各 1 次，比较 `_EMB_STATS["hit"|"miss"|"timeout"|"error"]` |
| AC-3 | `main.py` 改 `asyncio.gather` + `--concurrency` CLI 后可工作：`--concurrency 4` 跑 60 次 run 无报错；`--concurrency 1` 与原串行行为对齐 | smoke test：`--limit 2 --allow-llm --concurrency 4` 完成（< 1min）+ `--limit 2 --allow-llm --concurrency 1` 完成（结果一致） |
| AC-4 | 回归：跑全量 `--allow-llm --semantic-emb-threshold 0.35` 在 ≤10min 完成；`_EMB_STATS` 命中合理（keypoint 全 hit、answer 几乎全 miss 因无重复）、`timeout=0` `error=0` | `/usr/bin/time` 输出 + 报告 `_EMB_STATS` 段 |
| AC-5 | 现有单测无回归：`test_embedding_service` / `test_pg_chunk_vector_retriever_embedding_fallback` / `test_recall_channels_behavior` / `test_ai_chat_service` / `test_context_packer` / `test_ai_chat_router_req015` | `pytest ... -q` 退出码 0 |
| AC-6 | `ruff check` + `scripts/check-engineering-docs` 退出码 0 | 命令输出 |

## 6. Risks

| 风险 | 缓解 |
|------|------|
| Batch 全批失败 → 整批降级 → 退化为逐条 → 总耗时反超 | 4.1 设计：单 batch 失败回退逐条 `get_embedding_with_timeout`；失败率 < 5% 时净加速仍显著 |
| Provider 限流被 batch+gather 双重放大导致 429 | `_EMB_SEMAPHORE=2` 在 coverage 层维持；gather 只控 run 维度，provider 端并发仍 ≤ 2 |
| `_get_cached_embeddings_batch` 内部 dedup 改变 cache 命中统计口径 | dedup 在 batch 调用前，cache 仍 per-text；`_EMB_STATS` 语义不变 |
| 60s 单批超时在批内某条极慢时被触发 → 整批 None | 与 TD-070 模式一致；batch_size=10 兜底（典型 5-15 条）；实测可下调到 5 |
| 改了 `coverage._compute_semantic_embedding_coverage` 后破坏 dry-run 报告可复现性 | AC-2 行为不变性 + dry-run 实证可对照（REQ-037 报告 baseline=graph_edge@0.5） |
| `main.py` gather 加大 DB 连接压力 | 复用现有 `session_factory`（不新建）；SQLAlchemy AsyncSession 单 session，gather 提升的是 embedding 并发，DB 仍单连接；如出现压力降至 `--concurrency 2` |
| LLM-as-judge 调用被 `concurrency` 放大 | LLM-as-judge 在 `_run_question` 内 `await llm_callable(...)`，与现状一致；`_EMB_SEMAPHORE` 不管 LLM，但当前 LLM provider（如 siliconflow chat）单 query 限流与 60s wait_for 兜底在 `ai_chat_service._call_llm` 自身；如 LLM 端出现 429，记录为 follow-up |

## 7. Rollback

- 所有改动向后兼容（旧函数保留；`get_embedding_with_timeout` 旧调用点不动）。
- 单 commit PR 可 `git revert` 回退。
- AC-1/AC-2 不达标时回退到 `main` HEAD。

## 8. Out of Scope（确认不做）

- 不做"预计算落盘"（REQ-038 follow-up #2 候选，工程量大，留独立任务）
- 不切本地 sentence-transformers
- 不改 REQ-018 / REQ-025 P2 链路的 retrieval 配置
- 不改 graph_edge 通道决策（维持 REQ-036 禁用）
- 不动 `pg_chunk_vector_retriever` / `pg_vector_recall_channel` / `router.py:278` / `ai_chat_service` 主链路

## 9. 事实源

- REQ-038 阻塞诊断: `docs/01-product-planning/05-requirements/REQ-038-p2-graph-edge-disable-full-llm-verify-supplement.md`
- REQ-037 dry-run 结论: `docs/02-delivery-plans/01-specs/2026-06-21-req-037-graph-edge-disable-real-llm-verify-report.md`
- TD-070 实现: `docs/02-delivery-plans/01-specs/2026-06-21-td-070-vector-recall-timeout.md`
- REQ-031 进程内缓存: `scripts/rag_validation/coverage.py:85-122`
- provider batch API: `packages/server-python/app/shared/llm/providers/siliconflow.py:37-55`
- TD-071 任务卡: `docs/03-engineering-governance/technical-debt.md#td-071`
- REQ-039 接力: `docs/01-product-planning/05-requirements/REQ-039-p2-graph-edge-disable-llm-verify-unblock.md`
