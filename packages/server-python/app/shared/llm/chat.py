from __future__ import annotations

import logging

from app.shared.llm.factory import PRIORITY_CHAIN, get_provider
from app.shared.llm.protocol import ChatOptions, ProviderUnavailable

logger = logging.getLogger(__name__)


async def chat(
    messages: list[dict],
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    timeout: float = 60.0,
) -> str:
    """Unified chat completion API with automatic fallback on provider failure.

    Args:
        messages: List of {"role": "...", "content": "..."} messages.
        provider: Provider name (None = auto-select first available).
        model: Override model (None = use provider default).
        temperature: Sampling temperature.
        max_tokens: Max tokens to generate (None = let provider decide).
        timeout: Request timeout in seconds.

    Returns:
        The assistant's response content string.

    Raises:
        RuntimeError: No provider available.
        ProviderUnavailable: All attempted providers failed.
    """
    if provider:
        # Specific provider requested — no fallback
        try:
            p = get_provider(provider)
        except ValueError:
            raise
        options = ChatOptions(
            model=model or "",
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        return await p.chat(messages, options)

    # Auto-select with fallback: try providers in priority chain order
    tried: list[str] = []
    for pname in PRIORITY_CHAIN:
        try:
            p = get_provider(pname)
        except ValueError:
            continue  # Provider not configured
        tried.append(pname)
        options = ChatOptions(
            model=model or "",
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        try:
            return await p.chat(messages, options)
        except ProviderUnavailable as e:
            logger.warning(f"Provider {pname} unavailable: {e}, trying next provider")
            continue

    raise ProviderUnavailable(f"All providers failed: {tried}")
