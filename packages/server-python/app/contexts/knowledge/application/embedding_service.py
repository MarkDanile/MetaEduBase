import asyncio
import logging
import os

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# TD-069 schema fix: dev DB embeddings are stored as vector(4096) (siliconflow
# Qwen3-Embedding-8B). DIM constant only matters for callers that need a
# fixed-size sanity check (rare); retriever itself uses whatever the provider
# returns.
EMBEDDING_DIM = 4096


async def get_embedding(text: str) -> list[float] | None:
    """Generate query embedding for vector recall.

    TD-068 / TD-069 fix: try providers in order — qwen (DashScope) first, then
    siliconflow, then MiniMax. This matches the inbound pipeline at
    `tasks/embed.py` (which uses siliconflow + minimax), so query embeddings
    live in the same vector space as chunk embeddings stored in the database.

    Returns None when no provider key is configured or all attempts fail;
    callers (PgChunkVectorRetriever, PgVectorRecallChannel) fall back to
    keyword search and mark `embedding_fallback=True` in evidence metadata.
    """
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
        return None

    for provider_name, api_key, base_url, model in providers:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{base_url}/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model, "input": [text]},
                )
                resp.raise_for_status()
                data = resp.json()
                emb = data["data"][0]["embedding"]
                logger.debug(
                    "get_embedding: provider=%s model=%s dim=%d",
                    provider_name, model, len(emb),
                )
                return emb
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Embedding provider %s failed: %s; trying next provider",
                provider_name,
                exc,
            )
            continue
    return None


async def get_embedding_with_timeout(
    text: str, timeout: float = 60.0
) -> list[float] | None:
    """TD-070: get_embedding with an outer hard timeout.

    Vector recall query-time call sites use this helper so a single query's
    embedding fetch cannot block up to 90s (3 providers × 30s httpx) when
    providers are slow or unreachable. On timeout the helper returns None,
    letting callers fall back to keyword search — identical to get_embedding's
    existing None-on-failure contract.

    Mirrors the REQ-031 `_get_cached_embedding` 60s wait_for pattern.
    """
    try:
        return await asyncio.wait_for(get_embedding(text), timeout=timeout)
    except TimeoutError:
        logger.warning(
            "get_embedding timed out after %.1fs (text len=%d); "
            "falling back to keyword search",
            timeout,
            len(text),
        )
        return None


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
                        for idx, item in zip(batch_indices, items, strict=False):
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
            for idx, txt in zip(batch_indices, batch_texts, strict=False):
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
