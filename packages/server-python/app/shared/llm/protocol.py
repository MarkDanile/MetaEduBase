from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChatOptions:
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout: float = 60.0


@dataclass
class EmbedOptions:
    model: str
    timeout: float = 60.0


@dataclass
class ProviderConfig:
    """Resolved LLM provider configuration.

    Returned by `provider_resolver.resolve_chat_provider()` so business code
    that needs raw `base_url` / `api_key` (e.g. ai_router's direct httpx
    call) does not have to re-derive the provider from `settings`.
    """

    provider_name: str
    base_url: str
    model: str
    api_key: str


class ProviderError(Exception):
    """General provider error."""


class ProviderUnavailable(ProviderError):  # noqa: N818
    """Provider is not available (no API key, network error, etc.)."""


# Provider names
PROVIDER_MINIMAX = "minimax"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_DASHSCOPE = "dashscope"
PROVIDER_SILICONFLOW = "siliconflow"
