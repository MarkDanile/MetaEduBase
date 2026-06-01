from __future__ import annotations

import logging

from app.shared.llm.factory import get_provider
from app.shared.llm.protocol import PROVIDER_SILICONFLOW, ProviderUnavailable

logger = logging.getLogger(__name__)


async def embed_text(
    text: str,
    provider: str = PROVIDER_SILICONFLOW,
    timeout: float = 60.0,
) -> list[float]:
    """Embed a single text and return its vector.

    Raises:
        ProviderUnavailable: Provider failed.
    """
    p = get_provider(provider)
    if not hasattr(p, "embed"):
        raise ProviderUnavailable(f"Provider {provider} does not support embedding")
    return (await p.embed([text], timeout=timeout))[0]


async def embed_batch(
    texts: list[str],
    provider: str = PROVIDER_SILICONFLOW,
    timeout: float = 60.0,
) -> list[list[float]]:
    """Embed a batch of texts and return vectors.

    Raises:
        ProviderUnavailable: Provider failed.
    """
    p = get_provider(provider)
    if not hasattr(p, "embed"):
        raise ProviderUnavailable(f"Provider {provider} does not support embedding")
    return await p.embed(texts, timeout=timeout)
