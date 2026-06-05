"""LLM provider resolver.

`factory.get_provider()` already provides provider auto-selection with a
global PRIORITY_CHAIN, but that chain is geared toward the openai-compatible
chat abstraction (`chat()`). Business code that needs raw `base_url` /
`api_key` (e.g. `ai_router._call_llm`'s direct httpx call) cannot reuse
`get_provider()`'s output directly because:

1. The returned provider instance is opaque (no public `.base_url` /
   `.api_key` accessors).
2. ai_router's legacy priority order is
   `llm_default_provider → qwen → minimax → deepseek` (not factory's
   `deepseek → minimax → siliconflow → dashscope`).
3. ai_router wants `None` to mean "no API key configured" so it can return
   a Chinese guidance message instead of throwing.

This module provides `resolve_chat_provider()` returning a
`ProviderConfig` (or `None`) that ai_router can consume directly.
"""

from __future__ import annotations

from app.config import settings
from app.shared.llm.protocol import ProviderConfig

# ai_router's original priority order (kept in spec for the documented
# TD-016 behavior change). The default provider (if set and in this list)
# is moved to the front.
_PROVIDER_CANDIDATES: list[str] = ["minimax", "deepseek", "qwen"]


def _candidate_settings(name: str) -> tuple[str | None, str | None, str | None] | None:
    """Return (api_key, base_url, model) for a candidate provider name, or
    None if the name is not in the resolver's supported set."""
    if name == "minimax":
        return (
            settings.minimax_api_key,
            settings.minimax_base_url,
            settings.minimax_model,
        )
    if name == "deepseek":
        return (
            settings.deepseek_api_key,
            settings.deepseek_base_url,
            settings.deepseek_model,
        )
    if name == "qwen":
        return (
            settings.qwen_api_key,
            settings.qwen_base_url,
            settings.qwen_model,
        )
    return None


def resolve_chat_provider() -> ProviderConfig | None:
    """Pick the first configured LLM provider from `llm_default_provider`
    (if it is one of `minimax` / `deepseek` / `qwen`) followed by
    `[minimax, deepseek, qwen]`.

    Returns:
        ProviderConfig: the first provider with a non-empty API key, base
            URL, and model.
        None: none of the candidates have an API key configured.
    """
    default = (settings.llm_default_provider or "").strip().lower()
    candidates = list(_PROVIDER_CANDIDATES)
    if default and default in candidates:
        # Move the default to the front so it wins.
        candidates.remove(default)
        candidates.insert(0, default)
    elif default:
        # Default is set but not in our candidate set; ignore it. This
        # preserves the legacy behavior where unknown default values
        # silently fall back to the in-set order.
        pass

    for name in candidates:
        cfg = _candidate_settings(name)
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
