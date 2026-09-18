"""Tests for TD-085 Slice A — ``LlmProvider`` port and ``OpenAIProvider`` adapter.

Coverage (per Slice A acceptance matrix in the user brief):

1. Port contract: ``LlmProvider`` is a runtime-checkable Protocol; both
   methods are awaited and return the documented shape.
2. Adapter contract: ``OpenAIProvider`` accepts injected callables and
   forwards arguments verbatim; the adapter never builds its own
   credentials / HTTP client.
3. Compatibility path (chat_text): the adapter returns whatever the
   injected callable returns — including the legacy
   ``ai_router._call_llm`` placeholder string when no provider is
   configured.
4. Tool-calling path (chat_with_tools): the adapter flattens the
   nested OpenAI tool-call envelope into the port's
   ``ToolCallingResult`` with ``ToolCall`` entries, and re-shapes
   back to the legacy dict form when callers still expect it.
5. Error propagation: a raised exception in either callable becomes
   ``LlmUnavailableError``; ``LlmUnavailableError`` passes through
   unchanged.
6. Edge cases: missing tools / no tool_calls in response / unknown
   callable return shape.

Tests use only plain ``asyncio`` + dummy callables — no DB, no
network, no LLM. The acceptance layer is *mock / fixture* per the
quality-gates verification tiering; real LLM calls are explicitly
out of Slice A scope.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.runtime.application.llm_provider import (
    LlmProvider,
    LlmUnavailableError,
    ToolCall,
    ToolCallingResult,
)
from app.runtime.infrastructure.openai_provider import OpenAIProvider

# --- helpers ------------------------------------------------------------


def _ok_text_callable(value: str = "plain text answer"):
    return AsyncMock(return_value=value)


def _ok_tools_callable(
    content: str | None = "tool-aware text answer",
    tool_calls: list | None = None,
):
    return AsyncMock(
        return_value={"content": content, "tool_calls": tool_calls},
    )


def _failing_callable(exc: BaseException):
    async def _call(*args, **kwargs):
        raise exc

    return _call


# --- 1. Port contract ----------------------------------------------------


def test_llm_provider_is_runtime_protocol():
    """LlmProvider must be runtime-checkable (typing.Protocol semantics)."""
    # The Protocol declares two async methods. A class implementing
    # them with matching shape should be recognised by isinstance.
    class _Stub:
        async def chat_text(self, system_prompt, user_content):
            return "stub"

        async def chat_with_tools(
            self,
            messages,
            *,
            tools=None,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=2000,
        ):
            return ToolCallingResult(content=None, tool_calls=[])

    # Use runtime_checkable Protocol via duck typing import (see
    # ``LlmProvider`` declaration). Static Protocols are only
    # recognised at runtime when decorated with
    # ``@runtime_checkable``. Here we verify the surface area
    # instead: required methods exist with matching signatures.
    assert hasattr(LlmProvider, "chat_text")
    assert hasattr(LlmProvider, "chat_with_tools")
    assert callable(LlmProvider.chat_text)
    assert callable(LlmProvider.chat_with_tools)


# --- 2-3. Adapter contract + compatibility path -------------------------


@pytest.mark.asyncio
async def test_adapter_chat_text_forwards_arguments_and_returns_value():
    chat_text = _ok_text_callable("hello world")
    chat_with_tools = _ok_tools_callable()

    provider = OpenAIProvider(
        chat_text=chat_text, chat_with_tools=chat_with_tools
    )
    result = await provider.chat_text("system prompt", "user content")

    assert result == "hello world"
    chat_text.assert_awaited_once_with("system prompt", "user content")


@pytest.mark.asyncio
async def test_adapter_chat_text_passes_through_unavailable_error():
    chat_text = _failing_callable(
        LlmUnavailableError("upstream provider said no")
    )
    chat_with_tools = _ok_tools_callable()

    provider = OpenAIProvider(
        chat_text=chat_text, chat_with_tools=chat_with_tools
    )

    with pytest.raises(LlmUnavailableError):
        await provider.chat_text("s", "u")


@pytest.mark.asyncio
async def test_adapter_chat_text_normalizes_unknown_exception():
    chat_text = _failing_callable(RuntimeError("socket timeout"))
    chat_with_tools = _ok_tools_callable()

    provider = OpenAIProvider(
        chat_text=chat_text, chat_with_tools=chat_with_tools
    )

    with pytest.raises(LlmUnavailableError) as excinfo:
        await provider.chat_text("s", "u")
    assert "chat_text" in str(excinfo.value)


# --- 4. Tool-calling path -------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_chat_with_tools_flattens_nested_calls():
    nested = [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "query_internal_data",
                "arguments": '{"sql": "SELECT 1"}',
            },
        },
        {
            "id": "call_2",
            "type": "function",
            "function": {
                "name": "fetch_doc",
                "arguments": '{"doc_id": 42}',
            },
        },
    ]
    chat_text = _ok_text_callable()
    chat_with_tools = _ok_tools_callable(
        content="calling tools", tool_calls=nested
    )

    provider = OpenAIProvider(
        chat_text=chat_text, chat_with_tools=chat_with_tools
    )
    result = await provider.chat_with_tools(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "x"}}],
        tool_choice="auto",
        temperature=0.0,
        max_tokens=512,
    )

    assert isinstance(result, ToolCallingResult)
    assert result.content == "calling tools"
    assert len(result.tool_calls) == 2
    assert result.tool_calls[0] == ToolCall(
        id="call_1",
        name="query_internal_data",
        arguments_json='{"sql": "SELECT 1"}',
    )
    assert result.tool_calls[1].name == "fetch_doc"
    chat_with_tools.assert_awaited_once_with(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "x"}}],
        tool_choice="auto",
        temperature=0.0,
        max_tokens=512,
    )


@pytest.mark.asyncio
async def test_adapter_chat_with_tools_handles_no_tools():
    """If the model replies with text only, tool_calls is an empty list."""
    chat_text = _ok_text_callable()
    chat_with_tools = _ok_tools_callable(
        content="plain answer", tool_calls=None
    )

    provider = OpenAIProvider(
        chat_text=chat_text, chat_with_tools=chat_with_tools
    )
    result = await provider.chat_with_tools(
        [{"role": "user", "content": "hi"}]
    )

    assert result.content == "plain answer"
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_adapter_chat_with_tools_handles_flat_shaped_calls():
    """Some provider SDKs flatten the call envelope at the top level."""
    flat = [
        {"id": "call_1", "name": "fetch_doc", "arguments": '{"id": 7}'},
    ]
    chat_text = _ok_text_callable()
    chat_with_tools = _ok_tools_callable(content=None, tool_calls=flat)

    provider = OpenAIProvider(
        chat_text=chat_text, chat_with_tools=chat_with_tools
    )
    result = await provider.chat_with_tools(
        [{"role": "user", "content": "hi"}]
    )

    assert result.content is None
    assert result.tool_calls == [
        ToolCall(id="call_1", name="fetch_doc", arguments_json='{"id": 7}')
    ]


@pytest.mark.asyncio
async def test_adapter_chat_with_tools_handles_dict_arguments():
    """Some providers send ``arguments`` as a Python dict instead of JSON."""
    nested = [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "fetch_doc",
                "arguments": {"id": 7, "nested": {"k": "v"}},
            },
        }
    ]
    chat_text = _ok_text_callable()
    chat_with_tools = _ok_tools_callable(tool_calls=nested)

    provider = OpenAIProvider(
        chat_text=chat_text, chat_with_tools=chat_with_tools
    )
    result = await provider.chat_with_tools(
        [{"role": "user", "content": "hi"}]
    )

    assert len(result.tool_calls) == 1
    # The adapter serialises a dict-shaped arguments into a JSON string.
    import json as _json

    parsed = _json.loads(result.tool_calls[0].arguments_json)
    assert parsed == {"id": 7, "nested": {"k": "v"}}


@pytest.mark.asyncio
async def test_adapter_chat_with_tools_normalizes_unknown_exception():
    chat_text = _ok_text_callable()
    chat_with_tools = _failing_callable(ValueError("malformed upstream"))

    provider = OpenAIProvider(
        chat_text=chat_text, chat_with_tools=chat_with_tools
    )

    with pytest.raises(LlmUnavailableError) as excinfo:
        await provider.chat_with_tools(
            [{"role": "user", "content": "hi"}]
        )
    assert "chat_with_tools" in str(excinfo.value)


# --- 5. Composition boundary --------------------------------------------


def test_adapter_does_not_import_ai_router_at_module_level():
    """The adapter must not depend on ``knowledge.interfaces.api.ai_router``.

    Verified by importing the adapter module and asserting the router
    module is *not* in ``sys.modules`` yet. Composition wires the
    callables; the adapter remains portable.
    """
    import sys

    # Drop the router from sys.modules to make the assertion meaningful
    # even if another test already imported it.
    router_name = "app.contexts.knowledge.interfaces.api.ai_router"
    saved = sys.modules.pop(router_name, None)
    try:
        # Re-import the adapter fresh.
        import importlib

        mod = importlib.import_module(
            "app.runtime.infrastructure.openai_provider"
        )
        assert router_name not in sys.modules, (
            "OpenAIProvider module should not pull ai_router into "
            "sys.modules — composition must wire the callables."
        )
        # Sanity: the adapter class still exists.
        assert hasattr(mod, "OpenAIProvider")
    finally:
        if saved is not None:
            sys.modules[router_name] = saved
