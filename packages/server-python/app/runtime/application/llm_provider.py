"""TD-085 Slice A — LLM Port abstraction.

This module defines the abstract ``LlmProvider`` port used by application
layers (e.g. ``knowledge.application.ai_chat_service``) to invoke an LLM
without coupling to any specific router / API client / SDK.

The port intentionally has two methods:

- ``chat_text(system, user)`` — synchronous-style LLM call returning a
  plain string. Backward-compatible with the legacy ``ai_router._call_llm``
  caller surface used by RAG retrieval, NER, and e2e fixtures.
- ``chat_with_tools(messages, *, tools, tool_choice, temperature,
  max_tokens)`` — tool-calling-aware call returning a structured
  ``ToolCallingResult``.

Naming / scope rules (TD-085 spec §11.1 ADR-085-1 + §11.2 ADR-085-2):

- This module lives under ``app.runtime.application`` — a runtime
  *subpackage*, not a new bounded context.
- It is explicitly NOT the REQ-043 ``AgentTurnLoopRuntime``. The
  agent runtime is a separate REQ-043 target that will consume this
  port via composition; this module only owns the LLM call surface.

Provider implementations (e.g. ``OpenAIProvider``) live under
``app.runtime.infrastructure`` and are wired at composition time, never
imported directly by application code.

Error-propagation contract:

The port does not promise a single canonical exception type. Legacy
callables that the OpenAIProvider adapter wraps have *their own*
exception semantics — ``ai_router._call_llm`` swallows HTTP errors and
returns an error string, while ``ai_router._call_llm_with_tools`` raises
``LLMProviderCallError``. The port contract is therefore:

- ``chat_text`` returns ``str`` (success or failure string).
- ``OpenAIProvider`` propagates whatever exception the underlying
  callable raises. No exception-normalisation layer exists.

This preserves behavior compatibility per TD-085 spec §5.1 (response
shape, token counts, error codes).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class LlmProvider(Protocol):
    """Abstract LLM call port.

    Application layers depend only on this protocol. Concrete providers
    (e.g. OpenAI-compatible HTTP client) are injected at composition
    time, never imported directly.

    The protocol is ``runtime_checkable`` so application code (e.g.
    ``HybridQueryUnderstandingService``) can distinguish a real port
    implementation from a pre-Slice A legacy callable injected via the
    same constructor parameter — see the duck-typing note in
    ``hybrid_ner_service.__init__``.
    """

    async def chat_text(self, system_prompt: str, user_content: str) -> str: ...

    async def chat_with_tools(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> ToolCallingResult: ...


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Structured representation of a single tool invocation request.

    Kept intentionally narrow: the port only needs ``id``, the
    function name, and the JSON-encoded arguments blob. Provider-
    specific raw shapes (e.g. OpenAI's nested function object) are
    flattened at the adapter boundary.
    """

    id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class ToolCallingResult:
    """Result envelope for ``chat_with_tools``.

    ``content`` is the assistant's text reply (may be ``None`` when the
    model short-circuits to a tool call). ``tool_calls`` is a list of
    tool invocation requests; an empty list means the model chose to
    reply with text only.
    """

    content: str | None
    tool_calls: list[ToolCall]
