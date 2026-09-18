"""TD-085 Slice A — OpenAI-compatible LLM provider adapter.

This adapter implements the ``LlmProvider`` port against the existing
``knowledge.interfaces.api.ai_router`` HTTP client. It is wired at
composition time — the constructor accepts the two async callables
exposed by ``ai_router`` (``_call_llm`` and ``_call_llm_with_tools``)
plus an optional output-cleaner hook. The adapter performs only
*transport shape* translation (port Protocol -> router callables) and
never builds its own HTTP client, credentials, or retry policy.

Why callables instead of importing the router module directly:

1. Keeps ``app.runtime`` free of any reverse dependency on
   ``app.contexts.knowledge.interfaces.api`` (the very inversion TD-085
   Slice A is removing).
2. Makes the adapter trivially testable: tests pass a
   ``Mock(return_value=...)`` for the callables and assert the adapter
   shapes arguments / returns identically to the router would.
3. Composition root is the single wiring point: when a future Slice
   swaps the underlying client (e.g. onto ``shared.llm.chat``), only
   the wiring changes — the adapter and port remain stable.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.runtime.application.llm_provider import (
    LlmUnavailableError,
    ToolCall,
    ToolCallingResult,
)

logger = logging.getLogger(__name__)


# Public alias so composition code can spell the dependency without
# importing the private ``_call_llm`` symbols from ``ai_router``.
ChatTextCallable = Callable[[str, str], Awaitable[str]]
ChatWithToolsCallable = Callable[..., Awaitable[dict[str, Any]]]


class OpenAIProvider:
    """Adapter that fulfills the ``LlmProvider`` port via injected callables.

    The constructor accepts:

    - ``chat_text``: a 2-arg async callable with signature
      ``(system_prompt, user_content) -> str``. Equivalent to the
      existing ``ai_router._call_llm``.
    - ``chat_with_tools``: a keyword-only async callable compatible with
      ``ai_router._call_llm_with_tools(messages, *, tools, tool_choice,
      temperature, max_tokens) -> dict``. The returned dict has the
      shape ``{"content": str | None, "tool_calls": list | None}`` where
      each ``tool_calls`` entry is OpenAI's nested function object:
      ``{"id": ..., "type": "function", "function": {"name": ...,
      "arguments": "<json-string>"}}``.
    """

    def __init__(
        self,
        *,
        chat_text: ChatTextCallable,
        chat_with_tools: ChatWithToolsCallable,
    ) -> None:
        self._chat_text = chat_text
        self._chat_with_tools = chat_with_tools

    async def chat_text(self, system_prompt: str, user_content: str) -> str:
        """Synchronous-style chat completion.

        Errors raised by the underlying callable are normalized into
        ``LlmUnavailableError`` so callers can handle a single failure
        mode without leaking provider-specific exception types.
        """
        try:
            return await self._chat_text(system_prompt, user_content)
        except LlmUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 — boundary normalization
            logger.error("LLM chat_text call failed: %s", type(exc).__name__)
            raise LlmUnavailableError("LLM provider chat_text failed") from exc

    async def chat_with_tools(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> ToolCallingResult:
        """Tool-calling-aware chat completion.

        Returns a ``ToolCallingResult`` whose ``tool_calls`` is a flat
        list of ``ToolCall`` dataclasses (not the nested OpenAI shape).
        ``content`` is ``None`` when the model short-circuits to a tool
        call.
        """
        try:
            raw = await self._chat_with_tools(
                messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except LlmUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 — boundary normalization
            logger.error("LLM chat_with_tools call failed: %s", type(exc).__name__)
            raise LlmUnavailableError(
                "LLM provider chat_with_tools failed"
            ) from exc

        content = raw.get("content") if isinstance(raw, dict) else None
        raw_calls = raw.get("tool_calls") if isinstance(raw, dict) else None
        flat_calls: list[ToolCall] = []
        if isinstance(raw_calls, list):
            for entry in raw_calls:
                flat_calls.append(_flatten_tool_call(entry))
        return ToolCallingResult(content=content, tool_calls=flat_calls)


def _flatten_tool_call(entry: Any) -> ToolCall:
    """Normalize a provider-specific tool_call entry to ``ToolCall``.

    OpenAI's wire format nests the function under ``"function"`` and
    serializes arguments as a JSON string. The port contract exposes a
    flat ``(id, name, arguments_json)`` triple so callers don't have to
    know provider shapes.
    """
    if not isinstance(entry, dict):
        # Defensive fallback: unknown shape — preserve a stable id so
        # downstream tooling can still match against logs.
        return ToolCall(id="", name="", arguments_json="")

    call_id = entry.get("id") or ""
    function = entry.get("function") if isinstance(entry.get("function"), dict) else None
    if function is not None:
        name = function.get("name") or ""
        arguments = function.get("arguments")
    else:
        # Some providers flatten at the top level.
        name = entry.get("name") or ""
        arguments = entry.get("arguments")

    if isinstance(arguments, str):
        arguments_json = arguments
    elif arguments is None:
        arguments_json = ""
    else:
        arguments_json = json.dumps(arguments, ensure_ascii=False)
    return ToolCall(id=call_id, name=name, arguments_json=arguments_json)
