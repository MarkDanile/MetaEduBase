"""Tests for TD-085 Slice B — ``runtime/application/tool_orchestrator.py``.

判别点（锁定拆分前 ``AIChatService.chat`` 内联 tool-calling 编排的
legacy-exact 语义）：

1. 零工具路径：first content 直接作答；trace=None；仅 1 次 LLM 调用；
   第一次调用携带 ``tools=`` + ``tool_choice="auto"``。
2. 工具调用路径：dispatch 收到解析后的 arguments；第二次调用携带完整
   4 条消息历史（system → user → assistant+tool_call → tool result，
   OpenAI 嵌套信封逐字保持）；回复取 second content。
3. 不支持的工具名：不执行 dispatch、不发起第二次调用；first content
   为空时回退 fallback 文案；trace 记 skipped + reason。
4. arguments 非法 JSON → dispatch 收到空 dict。
5. dispatch 异常逐字向上传播（编排不吞业务异常）。
6. first content 为 None 且无 tool_calls → 回复空字符串。

全部使用 fake callable，不连接 DB / 真实 LLM。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.runtime.application.tool_orchestrator import run_tool_calling

MESSAGES = [
    {"role": "system", "content": "SYS"},
    {"role": "user", "content": "USER"},
]
TOOLS = [{"type": "function", "function": {"name": "query_internal_data"}}]
FALLBACK = "抱歉，我暂时无法执行该操作。"


class _Recorder:
    """Fake ``call_llm_with_tools`` — records calls, replays queued results."""

    def __init__(self, results: list[dict[str, Any]]):
        self._results = list(results)
        self.calls: list[tuple[list[dict], dict[str, Any]]] = []

    async def __call__(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self._results.pop(0)


def _tool_call_response(
    name: str = "query_internal_data",
    arguments: str = '{"question": "q", "entity_hint": "bill"}',
    call_id: str = "call_1",
) -> dict[str, Any]:
    return {
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        ],
    }


async def _dispatch_ok(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": {"name": name, "args": arguments}}


# --- 1. 零工具路径 ----------------------------------------------------------


@pytest.mark.asyncio
async def test_no_tool_calls_returns_first_content_and_skips_second_call():
    llm = _Recorder([{"content": "直接回答", "tool_calls": None}])
    dispatched: list[Any] = []

    async def dispatch(name, arguments):  # pragma: no cover - must not run
        dispatched.append(name)
        return {}

    outcome = await run_tool_calling(
        llm,
        MESSAGES,
        tools=TOOLS,
        supported_tool_names={"query_internal_data"},
        dispatch=dispatch,
        unsupported_fallback_reply=FALLBACK,
    )

    assert outcome.reply_text == "直接回答"
    assert outcome.tool_calls_trace is None
    assert len(llm.calls) == 1
    # 第一次调用携带 tools + tool_choice
    _, kwargs = llm.calls[0]
    assert kwargs["tools"] is TOOLS
    assert kwargs["tool_choice"] == "auto"
    assert dispatched == []


@pytest.mark.asyncio
async def test_no_tool_calls_with_none_content_returns_empty_string():
    llm = _Recorder([{"content": None, "tool_calls": []}])
    outcome = await run_tool_calling(
        llm,
        MESSAGES,
        tools=TOOLS,
        supported_tool_names={"query_internal_data"},
        dispatch=_dispatch_ok,
        unsupported_fallback_reply=FALLBACK,
    )
    assert outcome.reply_text == ""
    assert outcome.tool_calls_trace is None


# --- 2. 工具调用路径 --------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_call_path_builds_legacy_exact_four_message_history():
    llm = _Recorder(
        [
            _tool_call_response(call_id="call_history_test"),
            {"content": "最终回答", "tool_calls": None},
        ]
    )
    captured_args: list[dict[str, Any]] = []

    async def dispatch(name, arguments):
        captured_args.append(arguments)
        return {"ok": True, "rows": 3}

    outcome = await run_tool_calling(
        llm,
        MESSAGES,
        tools=TOOLS,
        supported_tool_names={"query_internal_data"},
        dispatch=dispatch,
        unsupported_fallback_reply=FALLBACK,
    )

    assert outcome.reply_text == "最终回答"
    assert outcome.tool_calls_trace == [
        {"name": "query_internal_data", "skipped": False}
    ]
    assert captured_args == [{"question": "q", "entity_hint": "bill"}]

    assert len(llm.calls) == 2
    second_messages, second_kwargs = llm.calls[1]
    # 第二次调用不带 tools kwargs
    assert second_kwargs == {}
    # 4 条消息：system → user → assistant+tool_call → tool
    assert [m["role"] for m in second_messages] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]
    assert second_messages[0] == MESSAGES[0]
    assert second_messages[1] == MESSAGES[1]
    assistant_msg = second_messages[2]
    assert assistant_msg["content"] is None
    nested = assistant_msg["tool_calls"][0]
    assert nested["id"] == "call_history_test"
    assert nested["type"] == "function"
    assert nested["function"]["name"] == "query_internal_data"
    assert json.loads(nested["function"]["arguments"]) == {
        "question": "q",
        "entity_hint": "bill",
    }
    tool_msg = second_messages[3]
    assert tool_msg["tool_call_id"] == "call_history_test"
    assert json.loads(tool_msg["content"]) == {"ok": True, "rows": 3}


@pytest.mark.asyncio
async def test_tool_call_second_content_none_returns_empty_string():
    llm = _Recorder(
        [_tool_call_response(), {"content": None, "tool_calls": None}]
    )
    outcome = await run_tool_calling(
        llm,
        MESSAGES,
        tools=TOOLS,
        supported_tool_names={"query_internal_data"},
        dispatch=_dispatch_ok,
        unsupported_fallback_reply=FALLBACK,
    )
    assert outcome.reply_text == ""


# --- 3. 不支持的工具名 ------------------------------------------------------


@pytest.mark.asyncio
async def test_unsupported_tool_falls_back_without_second_call():
    llm = _Recorder([_tool_call_response(name="delete_everything")])
    dispatched: list[Any] = []

    async def dispatch(name, arguments):  # pragma: no cover - must not run
        dispatched.append(name)
        return {}

    outcome = await run_tool_calling(
        llm,
        MESSAGES,
        tools=TOOLS,
        supported_tool_names={"query_internal_data"},
        dispatch=dispatch,
        unsupported_fallback_reply=FALLBACK,
    )

    # first content 为 None → 回退 fallback 文案
    assert outcome.reply_text == FALLBACK
    assert outcome.tool_calls_trace == [
        {
            "name": "delete_everything",
            "skipped": True,
            "reason": "unsupported_function_name",
        }
    ]
    assert len(llm.calls) == 1
    assert dispatched == []


@pytest.mark.asyncio
async def test_unsupported_tool_prefers_first_content_when_present():
    llm = _Recorder(
        [
            {
                "content": "我还是直接回答吧",
                "tool_calls": [
                    {
                        "id": "c9",
                        "type": "function",
                        "function": {"name": "unknown_tool", "arguments": "{}"},
                    }
                ],
            }
        ]
    )
    outcome = await run_tool_calling(
        llm,
        MESSAGES,
        tools=TOOLS,
        supported_tool_names={"query_internal_data"},
        dispatch=_dispatch_ok,
        unsupported_fallback_reply=FALLBACK,
    )
    assert outcome.reply_text == "我还是直接回答吧"
    assert len(llm.calls) == 1


# --- 4-5. arguments 解析与异常传播 ------------------------------------------


@pytest.mark.asyncio
async def test_invalid_arguments_json_degrades_to_empty_dict():
    llm = _Recorder(
        [
            _tool_call_response(arguments="{not valid json"),
            {"content": "ok", "tool_calls": None},
        ]
    )
    captured: list[dict[str, Any]] = []

    async def dispatch(name, arguments):
        captured.append(arguments)
        return {"ok": True}

    outcome = await run_tool_calling(
        llm,
        MESSAGES,
        tools=TOOLS,
        supported_tool_names={"query_internal_data"},
        dispatch=dispatch,
        unsupported_fallback_reply=FALLBACK,
    )
    assert captured == [{}]
    assert outcome.reply_text == "ok"


@pytest.mark.asyncio
async def test_dispatch_exception_propagates_verbatim():
    llm = _Recorder([_tool_call_response()])

    async def dispatch(name, arguments):
        raise KeyError("business blew up")

    with pytest.raises(KeyError, match="business blew up"):
        await run_tool_calling(
            llm,
            MESSAGES,
            tools=TOOLS,
            supported_tool_names={"query_internal_data"},
            dispatch=dispatch,
            unsupported_fallback_reply=FALLBACK,
        )
