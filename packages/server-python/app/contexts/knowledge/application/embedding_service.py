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
