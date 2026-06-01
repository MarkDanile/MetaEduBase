from __future__ import annotations

import logging

from app.shared.llm.protocol import (
    PROVIDER_DASHSCOPE,
    PROVIDER_DEEPSEEK,
    PROVIDER_MINIMAX,
    PROVIDER_SILICONFLOW,
)

logger = logging.getLogger(__name__)

# Priority chain: first available wins (when no provider specified)
PRIORITY_CHAIN = [
    PROVIDER_DEEPSEEK,
    PROVIDER_MINIMAX,
    PROVIDER_SILICONFLOW,
    PROVIDER_DASHSCOPE,
]

# Lazy-loaded singletons
_providers: dict = {}


def _load_providers():
    if _providers:
        return
    from app.shared.llm.providers.dashscope import DashScopeProvider
    from app.shared.llm.providers.deepseek import DeepSeekProvider
    from app.shared.llm.providers.minimax import MiniMaxProvider
    from app.shared.llm.providers.siliconflow import SiliconFlowProvider

    _providers[PROVIDER_MINIMAX] = MiniMaxProvider()
    _providers[PROVIDER_DEEPSEEK] = DeepSeekProvider()
    _providers[PROVIDER_DASHSCOPE] = DashScopeProvider()
    _providers[PROVIDER_SILICONFLOW] = SiliconFlowProvider()


def get_provider(name: str | None = None):
    """Get a provider instance by name, or auto-select first available."""
    _load_providers()

    if name:
        if name not in _providers:
            raise ValueError(f"Unknown provider: {name}")
        p = _providers[name]
        if not p.is_available():
            raise ValueError(f"Provider '{name}' is not configured (no API key)")
        return p

    # Auto-select first available in priority chain
    for provider_name in PRIORITY_CHAIN:
        p = _providers[provider_name]
        if p.is_available():
            logger.debug(f"Auto-selected LLM provider: {provider_name}")
            return p

    raise RuntimeError("No LLM provider configured (all API keys are empty)")


def list_available_providers() -> list[str]:
    """Return list of available (configured) provider names."""
    _load_providers()
    return [name for name, p in _providers.items() if p.is_available()]
