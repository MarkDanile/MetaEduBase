"""Tests for TD-085 Slice A — ``LlmProvider`` port and ``OpenAIProvider`` adapter.

Coverage (per Slice A acceptance matrix, including the round-2
P1-fix verification matrix):

1. Port contract: ``LlmProvider`` exposes ``chat_text`` and
   ``chat_with_tools`` with the documented shape.
2. Adapter contract: ``OpenAIProvider`` accepts injected callables and
   forwards arguments verbatim; the adapter never builds its own
   credentials / HTTP client.
3. Compatibility path (chat_text): the adapter returns whatever the
   injected callable returns — including the legacy
   ``ai_router._call_llm`` placeholder string when no provider is
   configured.
4. Compatibility path (chat_text passthrough): the adapter does NOT
   normalise arbitrary exceptions into ``LlmUnavailableError``; it
   propagates the underlying callable's exception verbatim.
5. Tool-calling path (chat_with_tools): the adapter flattens the
   nested OpenAI tool-call envelope into ``ToolCallingResult`` and
   re-shapes back to the legacy dict form when callers still expect it.
6. Tool-calling legacy exception passthrough: ``LLMProviderCallError``
   (the legacy ``ai_router._call_llm_with_tools`` exception type) is
   NOT replaced by the adapter — it propagates with the original type.
7. Edge cases: missing tools / no tool_calls in response / unknown
   callable return shape.
8. Module boundary: importing ``openai_provider`` does not pull
   ``ai_router`` into ``sys.modules``.

Tests use only plain ``asyncio`` + dummy callables — no DB, no
network, no LLM. Acceptance layer is *mock / fixture* per the
quality-gates verification tiering; real LLM calls are explicitly
out of Slice A scope.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.runtime.application.llm_provider import (
    LlmProvider,
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


def _raising_callable(exc: BaseException):
    async def _call(*args, **kwargs):
        raise exc

    return _call


# --- 1. Port contract ----------------------------------------------------


def test_llm_provider_declares_required_methods():
    """LlmProvider Protocol declares both async methods with the
    documented surface so application code can rely on duck typing.
    """
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
async def test_adapter_chat_text_passes_through_unconfigured_placeholder():
    """The router returns a Chinese placeholder when no API key is set;
    the adapter must return that string verbatim (no exception wrapping).
    """
    chat_text = _ok_text_callable("⚠️ 尚未配置 LLM API Key")
    chat_with_tools = _ok_tools_callable()

    provider = OpenAIProvider(
        chat_text=chat_text, chat_with_tools=chat_with_tools
    )
    result = await provider.chat_text("system", "user")
    assert result == "⚠️ 尚未配置 LLM API Key"


@pytest.mark.asyncio
async def test_adapter_chat_text_passes_through_failure_string():
    """Legacy ``_call_llm`` catches HTTP errors and returns a
    ``"❌ AI 回答生成失败: ..."`` string. The adapter must propagate
    that string unchanged — not raise.
    """
    failure_string = "❌ AI 回答生成失败: ConnectError"
    chat_text = _ok_text_callable(failure_string)
    chat_with_tools = _ok_tools_callable()

    provider = OpenAIProvider(
        chat_text=chat_text, chat_with_tools=chat_with_tools
    )
    result = await provider.chat_text("system", "user")
    assert result == failure_string


@pytest.mark.asyncio
async def test_adapter_chat_text_propagates_arbitrary_exception_verbatim():
    """Adapter MUST NOT normalise an arbitrary exception into a
    port-level exception type. Whatever the callable raises must
    propagate verbatim, including ``RuntimeError`` / ``ValueError``
    / etc. (TD-085 spec §5.1 behavior-compatibility.)
    """
    chat_text = _raising_callable(RuntimeError("socket timeout"))
    chat_with_tools = _ok_tools_callable()

    provider = OpenAIProvider(
        chat_text=chat_text, chat_with_tools=chat_with_tools
    )

    with pytest.raises(RuntimeError) as excinfo:
        await provider.chat_text("system", "user")
    assert str(excinfo.value) == "socket timeout"


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


# --- 5. Legacy exception passthrough (chat_with_tools) ------------------


@pytest.mark.asyncio
async def test_adapter_chat_with_tools_propagates_legacy_exception_type_verbatim():
    """``ai_router._call_llm_with_tools`` raises ``LLMProviderCallError``
    on HTTP failure. The adapter must propagate that exact exception
    type — not replace it with a generic port-level exception.
    """

    class _LegacyProviderError(RuntimeError):
        """Stand-in for ``app.contexts.knowledge.interfaces.api.ai_router
        .LLMProviderCallError`` — identical inheritance so isinstance
        checks elsewhere keep working.
        """

    legacy_exc = _LegacyProviderError("upstream socket reset")

    chat_text = _ok_text_callable()
    chat_with_tools = _raising_callable(legacy_exc)

    provider = OpenAIProvider(
        chat_text=chat_text, chat_with_tools=chat_with_tools
    )

    with pytest.raises(_LegacyProviderError) as excinfo:
        await provider.chat_with_tools(
            [{"role": "user", "content": "hi"}]
        )
    # Exact same exception object passes through (not wrapped, not
    # replaced). This preserves ``except LLMProviderCallError`` sites in
    # ``ai_router`` callers.
    assert excinfo.value is legacy_exc


# --- 6. Module boundary --------------------------------------------------


def test_adapter_does_not_import_ai_router_at_module_level():
    """Importing the adapter module must not pull ``ai_router`` into
    ``sys.modules`` — composition root is the single wiring point.
    """
    import sys

    router_name = "app.contexts.knowledge.interfaces.api.ai_router"
    saved = sys.modules.pop(router_name, None)
    try:
        import importlib

        mod = importlib.import_module(
            "app.runtime.infrastructure.openai_provider"
        )
        assert router_name not in sys.modules, (
            "OpenAIProvider module should not pull ai_router into "
            "sys.modules — composition must wire the callables."
        )
        assert hasattr(mod, "OpenAIProvider")
    finally:
        if saved is not None:
            sys.modules[router_name] = saved
