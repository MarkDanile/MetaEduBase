from __future__ import annotations

import logging

from app.config import settings
from app.shared.llm.protocol import (
    PROVIDER_DASHSCOPE,
    PROVIDER_DEEPSEEK,
    PROVIDER_MINIMAX,
    PROVIDER_SILICONFLOW,
)

logger = logging.getLogger(__name__)

_ALL_PROVIDERS = [
    PROVIDER_DEEPSEEK,
    PROVIDER_MINIMAX,
    PROVIDER_SILICONFLOW,
    PROVIDER_DASHSCOPE,
]

# Resolver subset. `provider_resolver.resolve_chat_provider()` (and the
# business code that consumes it, e.g. `ai_router._call_llm`) only ever
# sees these three provider aliases. The order is the documented fallback
# order; `provider_resolver` may move the configured default to the front,
# but the relative order between non-default candidates is fixed.
#
# Note: the alias is `qwen`, not `dashscope`. `settings` has `qwen_*`
# fields and the openai-compatible DashScopeProvider is reached through
# them; there is no separate `dashscope_*` field on settings. Adding a
# new resolver-visible provider requires updating
# `provider_resolver._COMPLETENESS_FIELDS` in lockstep.
RESOLVER_PROVIDER_NAMES: tuple[str, ...] = (
    PROVIDER_MINIMAX,
    PROVIDER_DEEPSEEK,
    "qwen",
)


def _normalize_default_provider(name: str | None) -> str | None:
    if not name:
        return None
    normalized = name.strip().lower()
    if normalized == "qwen":
        return PROVIDER_DASHSCOPE
    if normalized in _ALL_PROVIDERS:
        return normalized
    return None


def resolver_default_provider() -> str | None:
    """Resolve `settings.llm_default_provider` to a name from
    `RESOLVER_PROVIDER_NAMES`, or `None` if it cannot be honored.

    Note: this is intentionally *not* a thin wrapper over
    `_normalize_default_provider`. The factory's normalization target is
    `dashscope` (a real provider class name); the resolver's alias is
    `qwen` (only `settings.qwen_*` fields exist). Resolving
    `qwen` → `dashscope` → `None` would silently make `llm_default_provider
    = "qwen"` a no-op for `ai_router`, which would surprise operators
    who set that value expecting the documented behavior.

    - `None` / empty / whitespace: `None`.
    - `minimax` / `deepseek` (any case / whitespace): the lowercased
      alias, used by the resolver to move the candidate to the front.
    - `qwen` / `Qwen` / ` qwen `: `"qwen"`.
    - Anything else (`dashscope`, `siliconflow`, `openai`, ...): `None`.
    """
    raw = (settings.llm_default_provider or "").strip().lower()
    if not raw:
        return None
    if raw in RESOLVER_PROVIDER_NAMES:
        return raw
    return None


# Priority chain: configured default first, remaining providers as fallback
_default_provider = _normalize_default_provider(settings.llm_default_provider)
PRIORITY_CHAIN = ([ _default_provider ] if _default_provider else []) + [
    provider for provider in _ALL_PROVIDERS if provider != _default_provider
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
