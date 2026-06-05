"""LLM provider resolver.

`factory.get_provider()` already provides provider auto-selection with a
global `PRIORITY_CHAIN`, but that chain is geared toward the openai-
compatible chat abstraction (`chat()`). Business code that needs raw
`base_url` / `api_key` (e.g. `ai_router._call_llm`'s direct httpx call)
cannot reuse `get_provider()`'s output directly because:

1. The returned provider instance is opaque (no public `.base_url` /
   `.api_key` accessors).
2. `ai_router` cares about a *subset* of the factory provider list
   (`minimax` / `deepseek` / `qwen` only) and a different fallback
   order; this is the documented TD-016 behavior change.
3. `ai_router` wants `None` to mean "no API key configured" so it can
   return a Chinese guidance message instead of throwing.

To avoid two parallel sources of truth for the resolver subset and its
ordering, this module:

- pulls the resolver candidate set and the default-provider
  normalization from `factory.RESOLVER_PROVIDER_NAMES` and
  `factory.resolver_default_provider()`;
- keeps the alias-name → `settings.<alias>_*` field mapping local,
  because only the resolver needs the raw `api_key` / `base_url` /
  `model` triple and `factory` operates on opaque provider instances.
"""

from __future__ import annotations

from app.config import settings
from app.shared.llm.factory import RESOLVER_PROVIDER_NAMES, resolver_default_provider
from app.shared.llm.protocol import ProviderConfig

# Map each resolver-visible alias to the three `settings` fields that
# must all be non-empty for the alias to be considered configured.
_COMPLETENESS_FIELDS: dict[str, tuple[str, str, str]] = {
    "minimax": ("minimax_api_key", "minimax_base_url", "minimax_model"),
    "deepseek": ("deepseek_api_key", "deepseek_base_url", "deepseek_model"),
    "qwen": ("qwen_api_key", "qwen_base_url", "qwen_model"),
}


def _settings_for(name: str) -> tuple[str | None, str | None, str | None] | None:
    """Return (api_key, base_url, model) for a resolver alias, or
    `None` if the alias is not part of the resolver subset."""
    fields = _COMPLETENESS_FIELDS.get(name)
    if fields is None:
        return None
    api_key, base_url, model = (getattr(settings, field) for field in fields)
    return api_key, base_url, model


def resolve_chat_provider() -> ProviderConfig | None:
    """Pick the first configured LLM provider from
    `factory.resolver_default_provider()` (if it is one of
    `RESOLVER_PROVIDER_NAMES`) followed by `RESOLVER_PROVIDER_NAMES` in
    declaration order.

    Returns:
        ProviderConfig: the first provider with a non-empty API key,
            base URL, and model.
        None: none of the candidates have an API key configured.
    """
    default = resolver_default_provider()
    candidates = list(RESOLVER_PROVIDER_NAMES)
    if default and default in candidates:
        candidates.remove(default)
        candidates.insert(0, default)

    for name in candidates:
        cfg = _settings_for(name)
        if cfg is None:
            continue
        api_key, base_url, model = cfg
        if api_key and base_url and model:
            return ProviderConfig(
                provider_name=name,
                base_url=base_url,
                model=model,
                api_key=api_key,
            )
    return None
