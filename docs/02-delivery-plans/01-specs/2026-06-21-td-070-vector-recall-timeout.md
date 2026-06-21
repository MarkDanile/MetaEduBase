# TD-070 Spec: vector 召回 query embedding 无超时兜底

> Status: 🟢 完成
> Created: 2026-06-21
> Source: REQ-036 follow-up（真 LLM 全量验收受阻诊断发现）
> Plan: `docs/02-delivery-plans/02-plans/2026-06-21-td-070-vector-recall-timeout-plan.md`
> Ledger: `docs/03-engineering-governance/technical-debt.md#td-070`

## 1. Problem Statement

`get_embedding(text)`（`embedding_service.py`）每次调用最多串行尝试 3 个 provider（qwen → siliconflow → minimax），每个 provider httpx `timeout=30.0`。当 provider 慢或不可达时，单次 `get_embedding` 可阻塞最多 **90s**（3 × 30s）。

vector 召回的 3 个 query-time 调用点**均无外层超时兜底**：

| 调用点 | 文件 | 路径 | 现状 |
|--------|------|------|------|
| `PgVectorRecallChannel.recall` | `recall_service.py:32` | 生产 chat（knowledge_nodes 向量召回，经 PgGraphRetriever） | 无超时，None→`return []` |
| `PgChunkVectorRetriever.retrieve` | `pg_chunk_vector_retriever.py:58` | 生产 chat（chunk 向量召回，经 CompositeChunkRetriever） | 无超时，None→keyword fallback |
| KG 语义/混合搜索 endpoint | `router.py:278` | 用户面 `/knowledge` search API | 无超时，None→keyword-only |

影响：

- **生产 chat 阻塞**：慢 provider 下单 query 向量召回可阻塞最多 90s，AIChatService 串行召回（SQLAlchemy AsyncSession 禁并发）使成本完全叠加，用户体验卡顿。
- **REQ-037 全量真 LLM 验收受阻**：10 样例 × 6 scenario = 60 次 `_run_question`，每次触发向量召回 embedding，慢 provider 下 0% CPU 网络 I/O 等待，全量 run 不可在可接受时间内完成。

对比：REQ-031 的 `_get_cached_embedding`（校验脚本 keypoint coverage 路径）已加 `asyncio.wait_for(..., 60.0)` 外层超时 + 降级。**生产 vector 召回路径无同等兜底**——这是 REQ-031 修复时遗漏的对等缺口。

## 2. Goal

为 vector 召回 query-time 调用点加外层硬超时兜底，与 REQ-031 `_get_cached_embedding` 模式一致（60s `asyncio.wait_for` + TimeoutError→None 降级）。慢 provider 下向量召回 fail-fast 降级为 keyword，不再阻塞 90s。

## 3. Non-Goals

- 不改 `get_embedding` 本身（保留 30s httpx per-provider + 多 provider fallback 契约；batch backfill / node 写入路径保持现状）
- 不改 REQ-031 `_get_cached_embedding`（校验脚本，已有自己的 60s wait_for + stats）
- 不改 `router.py:182`（knowledge_node 写入路径，非 recall）
- 不引入 embedding 结果缓存（REQ-031 的缓存是校验脚本内单例，不在生产范围）
- 不调整 httpx 30s per-provider 超时

## 4. Acceptance Criteria

| ID | 内容 | 验证方式 |
|----|------|----------|
| AC-1 | `embedding_service.py` 新增 `get_embedding_with_timeout(text, timeout=60.0)` helper：`asyncio.wait_for(get_embedding(text), timeout)` + catch `asyncio.TimeoutError` → log warning + return None | 代码审查 + 单测 |
| AC-2 | 3 个 recall 调用点改用 `get_embedding_with_timeout`：`recall_service.py:32` / `pg_chunk_vector_retriever.py:58` / `router.py:278`；现有 None fallback 行为不变 | 代码审查 + 测试 |
| AC-3 | 单测：helper 成功路径透传 embedding；超时路径返回 None（mock 慢 callable） | pytest |
| AC-4 | 现有测试无回归：embedding_service / ai_chat_service / recall 相关测试通过 | pytest |
| AC-5 | `ruff check` + `scripts/check-engineering-docs` 通过 | 门禁 |

## 5. Architecture

### 5.1 helper（embedding_service.py）

```python
async def get_embedding_with_timeout(
    text: str, timeout: float = 60.0
) -> list[float] | None:
    """TD-070: get_embedding with outer hard timeout.

    vector 召回 query-time 调用点用此 helper，防止慢 provider 下单 query
    阻塞最多 90s（3 provider × 30s httpx）。超时返回 None，调用方降级为
    keyword search（与 get_embedding 返回 None 的现有契约一致）。

    与 REQ-031 `_get_cached_embedding` 的 60s wait_for 模式一致。
    """
    try:
        return await asyncio.wait_for(get_embedding(text), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(
            "get_embedding timed out after %.1fs (query len=%d); "
            "falling back to keyword search",
            timeout, len(text),
        )
        return None
```

### 5.2 调用点改造

3 个调用点把 `await get_embedding(...)` 替换为 `await get_embedding_with_timeout(...)`。现有 `if not embedding:` fallback 逻辑不变（None 语义一致）。

### 5.3 不改 get_embedding 的理由

`get_embedding` 被多条路径共用（recall / node 写入 / batch backfill / 校验脚本 coverage）。在其中加超时会改变所有调用方行为（含 batch），且会与 REQ-031 `_get_cached_embedding` 的外层 wait_for 形成嵌套超时，破坏其 timeout/error stats。helper 方式只影响 recall 路径，blast radius 最小。

## 6. Risks

- **60s 超时是否过紧**：httpx per-provider 30s，60s 允许约 2 次 provider 尝试。与 REQ-031 一致，合理。若生产观察到正常 provider 也偶发 >60s（罕见），可经参数上调。
- **超时降级影响召回质量**：超时返回 None → keyword fallback。慢 provider 下 keyword 兜底本就是现有 None 路径行为，TD-070 仅把"阻塞 90s 后降级"改为"60s 后降级"，质量不退步、延迟改善。
- **asyncio.wait_for 取消语义**：超时取消 get_embedding 内部 httpx await，`async with httpx.AsyncClient` context manager 正常清理；`asyncio.CancelledError` 不被 get_embedding 的 `except Exception` 捕获（BaseException），wait_for 抛 TimeoutError 由 helper 捕获。语义正确。

## 7. Slice 划分

| Slice | 内容 | 依赖 |
|-------|------|------|
| Slice 1 | `get_embedding_with_timeout` helper + 3 调用点改造 + 单测 | — |
| Slice 2 | pytest 无回归 + ruff + check-engineering-docs | Slice 1 |
| Slice 3 | 文档收口（ledger / backlog / current-work / work-log）+ commit + PR | Slice 2 |

## 8. References

- REQ-036 实现报告: `docs/02-delivery-plans/01-specs/2026-06-20-req-036-graph-edge-channel-disable-impl-report.md`
- REQ-031 `_get_cached_embedding`: `scripts/rag_validation/coverage.py`
- embedding_service: `packages/server-python/app/contexts/knowledge/application/embedding_service.py`
- recall 调用点: `recall_service.py:32` / `pg_chunk_vector_retriever.py:58` / `router.py:278`
