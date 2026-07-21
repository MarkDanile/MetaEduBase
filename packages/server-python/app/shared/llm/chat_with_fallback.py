"""LLM model-level fallback helper.

`app.shared.llm.chat` 已经提供 provider 维度的 fallback（在 PRIORITY_CHAIN 中按
provider 轮询）。本模块在它之上再加一个 model 维度的 fallback：

- 业务侧想要「先尝试快速便宜的模型，失败再用默认强力模型」时，调用
  `chat_with_model_fallback(messages, fast_model=..., fallback_model=...)`。
- helper 内部两次调用 `chat()`，第二次只在第一次失败时执行。
- 两次都失败时抛 `ProviderUnavailable`，由调用方决定业务兜底。

template service 的「deepseek-v4-flash → settings.deepseek_model」两步逻辑就是
这种「快速模型 → 默认模型」fallback 模式的典型用例，本模块就是为它而抽的。
"""

from __future__ import annotations

import logging

from app.config import settings
from app.shared.llm.chat import chat
from app.shared.llm.protocol import ProviderUnavailable

logger = logging.getLogger(__name__)


async def chat_with_model_fallback(
    messages: list[dict],
    *,
    fast_provider: str = "deepseek",
    fast_model: str = "deepseek-v4-flash",
    fallback_provider: str = "deepseek",
    fallback_model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    timeout: float = 60.0,
) -> str:
    """Try a fast model first; on ProviderUnavailable, fall back to a default model.

    Args:
        messages: OpenAI-style messages list.
        fast_provider / fast_model: first attempt.
        fallback_provider / fallback_model: second attempt. `fallback_model=None`
            falls back to `settings.deepseek_model`.
        temperature / max_tokens / timeout: passed through to each `chat()` call.

    Returns:
        The assistant's response content string.

    Raises:
        ProviderUnavailable: both attempts failed with ProviderUnavailable.
        ValueError: `fast_provider`/`fallback_provider` is unknown or not configured
            (raised by the underlying `chat()` call). Callers that previously
            swallowed all exceptions should keep catching both.
    """
    resolved_fallback_model = fallback_model or settings.deepseek_model

    try:
        return await chat(
            messages,
            provider=fast_provider,
            model=fast_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    except ProviderUnavailable as fast_error:
        logger.warning(
            "init_by_ai flash model failed, fallback to default DeepSeek model: %s",
            fast_error,
        )
    except ValueError:
        # Provider not configured (no API key or unknown name) — fall through to fallback
        pass

    try:
        return await chat(
            messages,
            provider=fallback_provider,
            model=resolved_fallback_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    except ProviderUnavailable as fallback_error:
        logger.warning(
            "init_by_ai fallback model also failed: %s",
            fallback_error,
        )
    # ValueError from fallback propagates (unknown/bad provider is a programming error)

    raise ProviderUnavailable(
        f"Both fast ({fast_provider}/{fast_model}) and fallback "
        f"({fallback_provider}/{resolved_fallback_model}) providers unavailable"
    )
