"""TD-085 Slice B — 通用 Tool Calling 编排（两轮 LLM 调用循环）。

从 ``knowledge.application.ai_chat_service.chat`` 拆出的 tool-calling
编排职责（spec ADR-085-2：Tool Calling + Dispatch → runtime）。

通用性约束（本模块不携带具体业务 Query 语义）：

- 工具 schema 由调用方通过 ``tools`` 参数传入（knowledge 侧持有
  ``query_internal_data`` 等业务工具定义）。
- 工具执行能力通过 ``dispatch`` callable 注入（knowledge 侧实现
  SemanticModel 解析 / QueryService.ask / 审计关联）。
- 不支持的工具名回退文案由调用方通过 ``unsupported_fallback_reply``
  注入。

行为保持（与拆分前 ``AIChatService.chat`` 内联编排逐字等价）：

1. 第一次调用携带 ``tools=`` + ``tool_choice=``（默认 "auto"）。
2. 无 tool_calls → 直接以 first content 作答，trace 为 ``None``。
3. 有 tool_calls 但函数名不在 ``supported_tool_names`` → 不执行工具、
   不发起第二次调用，回退 first content（为空时用 fallback 文案），
   trace 记 ``skipped: True, reason: unsupported_function_name``。
4. 支持的工具调用 → trace 记 ``skipped: False``，解析 arguments
   （非法 JSON 降级为空 dict），``dispatch`` 产出 payload，第二次调用
   携带完整 4 条消息历史（system → user → assistant+tool_call →
   tool result，OpenAI 嵌套信封逐字保持），以 second content 作答。

调用接缝：``call_llm_with_tools`` 由调用方在调用时传入（生产路径为
``AIChatService._call_llm_with_tools`` 绑定方法），因此既有
``patch.object(AIChatService, "_call_llm_with_tools", ...)`` 测试缝
不受影响。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Legacy dict envelope returned by ``AIChatService._call_llm_with_tools``:
# ``{"content": str | None, "tool_calls": list | None}`` where each entry is
# the nested OpenAI shape ``{"id", "type", "function": {"name", "arguments"}}``.
CallLlmWithTools = Callable[..., Awaitable[dict[str, Any]]]

# Business capability port: (function_name, parsed_arguments) -> result payload
# that will be JSON-encoded into the tool result message.
ToolDispatcher = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ToolOrchestrationResult:
    """编排结果：未清洗的回复文本 + diagnostics 用 tool_calls trace。"""

    reply_text: str
    tool_calls_trace: list[dict[str, Any]] | None


async def run_tool_calling(
    call_llm_with_tools: CallLlmWithTools,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]],
    supported_tool_names: set[str],
    dispatch: ToolDispatcher,
    unsupported_fallback_reply: str,
    tool_choice: str = "auto",
) -> ToolOrchestrationResult:
    """Two-round tool-calling orchestration with legacy-exact semantics."""
    first_result = await call_llm_with_tools(
        messages,
        tools=tools,
        tool_choice=tool_choice,
    )
    tool_calls = first_result.get("tool_calls")
    first_content = first_result.get("content")

    if not tool_calls:
        # LLM answered directly — no tool invocation, no second LLM call.
        return ToolOrchestrationResult(
            reply_text=first_content or "",
            tool_calls_trace=None,
        )

    # We have at least one tool call. Only the first is handled (V1).
    tool_call = tool_calls[0]
    fn_name = (tool_call.get("function") or {}).get("name")
    if fn_name not in supported_tool_names:
        # Unknown / unsupported tool — fall back to first-response content
        # (or the caller-provided fallback if the model returned None).
        logger.warning(
            "tool_orchestrator: unsupported tool_call name=%r; "
            "falling back to direct content.",
            fn_name,
        )
        return ToolOrchestrationResult(
            reply_text=first_content or unsupported_fallback_reply,
            tool_calls_trace=[
                {
                    "name": fn_name,
                    "skipped": True,
                    "reason": "unsupported_function_name",
                }
            ],
        )

    tool_calls_trace: list[dict[str, Any]] = [{"name": fn_name, "skipped": False}]
    arguments_raw = (tool_call.get("function") or {}).get("arguments", "{}")
    try:
        arguments = json.loads(arguments_raw)
    except (TypeError, ValueError):
        logger.warning(
            "tool_orchestrator: invalid tool_call arguments=%r; "
            "treating as empty dict.",
            arguments_raw,
        )
        arguments = {}

    tool_result_payload = await dispatch(fn_name, arguments)

    # Second LLM call with full conversation history (system → user →
    # assistant+tool_call → tool result).
    second_messages = [
        *messages,
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [tool_call],
        },
        {
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": json.dumps(tool_result_payload, ensure_ascii=False),
        },
    ]
    second_result = await call_llm_with_tools(second_messages)
    second_content = second_result.get("content")
    return ToolOrchestrationResult(
        reply_text=second_content or "",
        tool_calls_trace=tool_calls_trace,
    )
