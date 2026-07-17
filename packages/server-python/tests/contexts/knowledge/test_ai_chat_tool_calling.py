"""REQ-052 Task 7 — AI Chat tool calling 接入。

测试 AI Chat 在 REQ-052 问数闭环中的 tool calling 编排：

1. ``test_ai_chat_triggers_query_internal_data_tool`` — 用户问"欠费多少" →
   LLM 第一步返回 ``tool_call`` (``query_internal_data``) → AI Chat 触发
   QueryService.ask → LLM 第二步拿到 tool result → 生成最终回复。
2. ``test_ai_chat_first_response_has_no_tool_call_returns_directly`` —
   LLM 第一步直接给文本（无需查内部数据）→ 只调一次 LLM，QueryService 不被调用。
3. ``test_ai_chat_second_llm_call_gets_conversation_history`` — 第二步 LLM
   调用必须把 system + user + assistant+tool_call + tool result 这 4 条消息
   全部传给模型。
4. ``test_ai_chat_tool_call_audit_log_entry_persisted`` — 每次内部数据查询
   都必须经过 QueryService.ask → 审计行入库（mock QueryService 验证
   ask 被调用过；QueryService.ask 内部会写 audit log，见
   ``QueryService._audit``）。
5. ``test_ai_chat_tool_call_unsupported_function_name_is_ignored`` — 当
   LLM 返回一个未声明的 tool_call（不是 ``query_internal_data``）→ AI Chat
   回退到第一步 ``content``，不再二次调用 LLM，QueryService 不被调用。

设计要点（TDD 锚点）：

- ``_call_llm`` 现有签名 ``async def _call_llm(system_prompt, user_content) -> str``
  必须保持向后兼容 — 这是 plan global constraint。本测试只 patch service 级
  ``_call_llm``（现有 test seam）and 新增 ``_call_llm_with_tools`` seam。
- ``QueryService.ask`` 必须执行实际查询（含 audit row）— 通过 AsyncMock 验证
  ``ask`` 被调用时传入 ``question``/``semantic_model``/``business_purpose``
  等正确参数。
- 第二步 LLM 调用必须把完整对话历史（包括 tool_call id）传给模型。
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.contexts.knowledge.application.ai_chat_service import AIChatService
from app.contexts.knowledge.application.ai_chat_service import (
    ChatRequest as ServiceChatRequest,
)
from app.contexts.knowledge.application.evidence_fusion import SimpleFrequencyFusion
from app.contexts.knowledge.application.retrievers_fake import (
    FakeChunkRetriever,
    FakeGraphRetriever,
    FakeMetadataFilter,
)
from app.contexts.knowledge.domain.evidence import EvidenceItem

# ---------------------------------------------------------------------------
# Test fakes — re-use minimal scaffolding from test_ai_chat_service.py so we
# don't depend on the real PostgreSQL adapter stack.
# ---------------------------------------------------------------------------


class _FakeRows:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def all(self) -> list[dict]:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeRows:
        return _FakeRows(self._rows)


class FakeSession:
    """最小 AsyncSession 替身 — 只响应 ai_chat_service.chat 内部的 SQL。"""

    def __init__(self, *, files: list[dict] | None = None) -> None:
        self.files = files or []

    async def execute(self, stmt, params=None):  # noqa: ANN001
        stmt_text = str(stmt)
        if "FROM metaedu.files" in stmt_text:
            return _FakeResult(self.files)
        return _FakeResult([])


def _chunk_evidence(file_id, idx, score=0.9, content="some content " * 20) -> EvidenceItem:
    return EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=file_id,
        chunk_id=uuid.uuid4(),
        title=f"section-{idx}",
        content=content,
        snippet=content[:50],
        score=score,
        metadata={"section_path": f"1.{idx}"},
    )


def _make_tool_call_response(
    function_name: str = "query_internal_data",
    arguments: dict[str, Any] | None = None,
    tool_call_id: str = "call_test_1",
    content: str | None = None,
) -> dict:
    """Build the OpenAI-shaped tool_call response payload.

    Returns the structured ``{"content": ..., "tool_calls": ...}`` shape that
    the AIChatService expects from ``_call_llm_with_tools`` — i.e. the same
    shape the production ``ai_router._call_llm_with_tools`` returns.
    """
    return {
        "content": content,
        "tool_calls": [
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": function_name,
                    "arguments": json.dumps(
                        arguments
                        or {"question": "这企业欠费多少", "entity_hint": "bill"}
                    ),
                },
            }
        ],
    }


def _make_text_response(content: str) -> dict:
    return {"content": content, "tool_calls": None}


def _make_fake_semantic_model() -> MagicMock:
    """SemanticModel mock — the AI Chat service only needs ``entity_type`` /
    ``entity_name`` / ``data_source_config`` attributes to forward to
    QueryService.ask."""
    sm = MagicMock()
    sm.entity_type = "bill"
    sm.entity_name = "账单"
    sm.data_source_config = {"type": "imported_dataset", "dataset_id": "ds-test"}
    sm.id = uuid.uuid4()
    sm.tenant_id = uuid.uuid4()
    return sm


def _make_service(
    *,
    chunk_retriever: FakeChunkRetriever | None = None,
    query_service: AsyncMock | None = None,
) -> tuple[AIChatService, FakeSession]:
    """Build an AIChatService wired with fakes and an injected QueryService."""
    fid = uuid.uuid4()
    chunk = _chunk_evidence(fid, 1, score=0.9, content="RAG 上下文 " * 30)
    cr = chunk_retriever or FakeChunkRetriever()
    cr.return_value = [chunk]
    service = AIChatService(
        chunk_retriever=cr,
        graph_retriever=FakeGraphRetriever(),
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=SimpleFrequencyFusion(),
    )
    # The service currently has no `query_service` attribute — the chat flow
    # in REQ-052 Task 7 will look up a SemanticModel via the request session
    # and call QueryService.ask. Inject via constructor attribute (Task 7
    # implementation).
    service.query_service = query_service or AsyncMock()
    # Inject a fake SemanticModelRepository — Task 7 implementation calls
    # ``SemanticModelRepository(session).get_active_by_entity_type(...)``.
    semantic_repo = MagicMock()
    semantic_repo.get_active_by_entity_type = AsyncMock(
        return_value=_make_fake_semantic_model()
    )
    service.semantic_model_repository_factory = lambda session: semantic_repo
    session = FakeSession(
        files=[
            {
                "id": fid,
                "filename": "test.pdf",
                "doc_type": "test",
                "tags": [],
            }
        ]
    )
    return service, session


# ---------------------------------------------------------------------------
# 1) Tool calling happy path — query_internal_data triggers QueryService.ask
# ---------------------------------------------------------------------------


async def test_ai_chat_triggers_query_internal_data_tool() -> None:
    """用户问"欠费多少" → LLM 第一次返回 tool_call(query_internal_data) →
    AI Chat 调 QueryService.ask → LLM 第二次拿到 tool result → 生成最终回复。

    关键断言：
    - QueryService.ask 被调用，且参数包含 question / semantic_model /
      business_purpose / role / user_id / tenant_id。
    - LLM 被调 2 次（first + second）。
    - 最终 reply 是第二次 LLM 的回复（带审计摘要的味道）。
    """
    first_payload = _make_tool_call_response(
        function_name="query_internal_data",
        arguments={"question": "这企业欠费多少", "entity_hint": "bill"},
        tool_call_id="call_001",
    )
    second_payload = _make_text_response("该企业过去三年累计欠费 12.5 万元。")

    call_log: list[dict] = []

    async def fake_llm(self, system: str, user: str) -> str:
        call_log.append({"kind": "legacy", "system": system, "user": user})
        return "ok"

    async def fake_llm_with_tools(
        self, messages: list[dict], *, tools=None, tool_choice="auto"
    ) -> dict:
        call_log.append({"kind": "tools", "messages": messages, "tools": tools})
        if len([c for c in call_log if c["kind"] == "tools"]) == 1:
            return first_payload
        return second_payload

    query_service = AsyncMock()
    query_service.ask = AsyncMock(
        return_value={
            "ok": True,
            "result_rows": [{"total_unpaid": 125000.0}],
            "result_count": 1,
            "summary": "过去三年累计欠费 12.5 万元",
            "metric_values": {"total_unpaid": {"value": 125000.0, "label": "累计欠费"}},
            "filters_applied": {},
            "caveats": [],
            "confidence": "high",
            "duration_ms": 42,
        }
    )

    service, session = _make_service(query_service=query_service)

    with patch.object(AIChatService, "_call_llm", fake_llm), patch.object(
        AIChatService, "_call_llm_with_tools", fake_llm_with_tools
    ):
        result = await service.chat(
            ServiceChatRequest(message="这企业欠费多少", context_window=3),
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role="employee",
            session=session,  # type: ignore[arg-type]
        )

    # 1. QueryService.ask fired once with the question from the tool_call
    assert query_service.ask.await_count == 1, (
        f"QueryService.ask should be called exactly once; got "
        f"{query_service.ask.await_count}"
    )
    ask_kwargs = query_service.ask.await_args.kwargs
    assert ask_kwargs["question"] == "这企业欠费多少"
    assert ask_kwargs["semantic_model"] is not None
    assert ask_kwargs["business_purpose"]  # non-empty
    assert ask_kwargs["role"] == "employee"
    assert ask_kwargs["user_id"] is not None
    assert ask_kwargs["tenant_id"] is not None

    # 2. LLM was called twice — both via the tool-aware path
    tools_calls = [c for c in call_log if c["kind"] == "tools"]
    assert len(tools_calls) == 2, f"Expected 2 tool calls, got {len(tools_calls)}"

    # 3. Final reply is the second LLM's text
    assert "12.5 万" in result.reply or "12.5" in result.reply or "欠费" in result.reply


# ---------------------------------------------------------------------------
# 2) No tool call → only one LLM call, QueryService never invoked
# ---------------------------------------------------------------------------


async def test_ai_chat_first_response_has_no_tool_call_returns_directly() -> None:
    """LLM 直接返回文本（无需查内部数据）→ 只调 1 次 LLM，QueryService 不被调。"""
    direct_payload = _make_text_response("这是一个普通知识问答回复。")

    call_log: list[dict] = []

    async def fake_llm(self, system: str, user: str) -> str:
        call_log.append({"kind": "legacy", "system": system, "user": user})
        return "ok"

    async def fake_llm_with_tools(
        self, messages: list[dict], *, tools=None, tool_choice="auto"
    ) -> dict:
        call_log.append({"kind": "tools", "messages": messages, "tools": tools})
        return direct_payload

    query_service = AsyncMock()
    query_service.ask = AsyncMock()

    service, session = _make_service(query_service=query_service)

    with patch.object(AIChatService, "_call_llm", fake_llm), patch.object(
        AIChatService, "_call_llm_with_tools", fake_llm_with_tools
    ):
        result = await service.chat(
            ServiceChatRequest(message="Python 是什么？", context_window=3),
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role="employee",
            session=session,  # type: ignore[arg-type]
        )

    # LLM with tools is called exactly once (the first/only call)
    tools_calls = [c for c in call_log if c["kind"] == "tools"]
    assert len(tools_calls) == 1
    # QueryService.ask NOT called
    assert query_service.ask.await_count == 0
    # Reply is the direct content
    assert "普通知识问答" in result.reply


# ---------------------------------------------------------------------------
# 3) Second LLM call gets full conversation history (system/user/assistant+tool_call/tool)
# ---------------------------------------------------------------------------


async def test_ai_chat_second_llm_call_gets_conversation_history() -> None:
    """第二次 LLM 调用必须把 4 条消息（system + user + assistant+tool_call +
    tool result）按 OpenAI Chat Completions 顺序传给模型。
    """
    first_payload = _make_tool_call_response(
        function_name="query_internal_data",
        arguments={"question": "这企业欠费多少", "entity_hint": "bill"},
        tool_call_id="call_history_test",
    )
    second_payload = _make_text_response("欠费 12.5 万元。")

    captured_messages: list[list[dict]] = []

    async def fake_llm(self, system: str, user: str) -> str:
        return "ok"

    async def fake_llm_with_tools(
        self, messages: list[dict], *, tools=None, tool_choice="auto"
    ) -> dict:
        captured_messages.append(list(messages))
        if len(captured_messages) == 1:
            return first_payload
        return second_payload

    query_service = AsyncMock()
    query_service.ask = AsyncMock(
        return_value={
            "ok": True,
            "result_rows": [],
            "result_count": 0,
            "summary": "无数据",
            "metric_values": {},
            "filters_applied": {},
            "caveats": [],
            "confidence": "low",
            "duration_ms": 1,
        }
    )

    service, session = _make_service(query_service=query_service)

    with patch.object(AIChatService, "_call_llm", fake_llm), patch.object(
        AIChatService, "_call_llm_with_tools", fake_llm_with_tools
    ):
        await service.chat(
            ServiceChatRequest(message="这企业欠费多少", context_window=3),
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role="employee",
            session=session,  # type: ignore[arg-type]
        )

    # The second call must contain 4 messages: system, user, assistant+tool_call, tool
    assert len(captured_messages) == 2
    second_call_messages = captured_messages[1]
    assert len(second_call_messages) == 4, (
        f"Second LLM call must contain 4 messages (system/user/assistant/tool); "
        f"got {len(second_call_messages)}: {second_call_messages}"
    )

    roles = [m["role"] for m in second_call_messages]
    assert roles == ["system", "user", "assistant", "tool"], (
        f"Expected roles [system, user, assistant, tool]; got {roles}"
    )

    # The assistant message must carry tool_calls (not just plain content)
    assistant_msg = second_call_messages[2]
    assert "tool_calls" in assistant_msg
    assert assistant_msg["tool_calls"][0]["id"] == "call_history_test"
    assert assistant_msg["tool_calls"][0]["function"]["name"] == "query_internal_data"

    # The tool result message must reference the same tool_call_id
    tool_msg = second_call_messages[3]
    assert tool_msg["tool_call_id"] == "call_history_test"
    # And the tool result content is the QueryService response (json-encoded)
    parsed_tool_result = json.loads(tool_msg["content"])
    assert parsed_tool_result["ok"] is True
    assert parsed_tool_result["summary"] == "无数据"


# ---------------------------------------------------------------------------
# 4) QueryService.ask actually executes (audit log entry path is exercised)
# ---------------------------------------------------------------------------


async def test_ai_chat_tool_call_query_service_ask_executes_with_correct_args() -> None:
    """AI Chat 必须把正确的语义模型 / 角色 / 业务背景传给 QueryService.ask —
    QueryService.ask 内部会触发 audit log 写入（REQ-052 §12）。这个测试
    通过校验 ask 的入参来间接验证整条 audit 链路被打通。
    """
    first_payload = _make_tool_call_response(
        function_name="query_internal_data",
        arguments={"question": "这企业合同总额", "entity_hint": "contract"},
    )
    second_payload = _make_text_response("合同总额 8 万。")

    call_count = {"llm": 0}

    async def fake_llm(self, system: str, user: str) -> str:
        return "ok"

    async def fake_llm_with_tools(
        self, messages: list[dict], *, tools=None, tool_choice="auto"
    ) -> dict:
        call_count["llm"] += 1
        return first_payload if call_count["llm"] == 1 else second_payload

    query_service = AsyncMock()
    query_service.ask = AsyncMock(
        return_value={
            "ok": True,
            "result_rows": [{"contract_total": 80000.0}],
            "result_count": 1,
            "summary": "合同总额 8 万",
            "metric_values": {},
            "filters_applied": {},
            "caveats": [],
            "confidence": "high",
            "duration_ms": 30,
        }
    )

    fake_semantic_model = _make_fake_semantic_model()
    fake_semantic_model.entity_type = "contract"

    service, session = _make_service(query_service=query_service)
    # Override semantic model lookup to return the contract semantic_model
    semantic_repo = MagicMock()
    semantic_repo.get_active_by_entity_type = AsyncMock(return_value=fake_semantic_model)
    service.semantic_model_repository_factory = lambda s: semantic_repo

    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    with patch.object(AIChatService, "_call_llm", fake_llm), patch.object(
        AIChatService, "_call_llm_with_tools", fake_llm_with_tools
    ):
        await service.chat(
            ServiceChatRequest(message="这企业合同总额多少", context_window=3),
            tenant_id=tenant_id,
            user_id=user_id,
            role="manager",
            session=session,  # type: ignore[arg-type]
        )

    assert query_service.ask.await_count == 1
    ask_kwargs = query_service.ask.await_args.kwargs

    # The audit-relevant fields are forwarded verbatim — this is what makes
    # the audit row match the regulator's expected shape.
    assert ask_kwargs["question"] == "这企业合同总额"
    assert ask_kwargs["semantic_model"] is fake_semantic_model
    assert ask_kwargs["user_id"] == user_id
    assert ask_kwargs["tenant_id"] == tenant_id
    assert ask_kwargs["role"] == "manager"
    assert ask_kwargs["business_purpose"]  # non-empty
    # BUG-015: confirmed_company_name removed from QueryService.ask —
    # ambiguity is resolved entirely by the system prompt + planner.
    assert "confirmed_company_name" not in ask_kwargs


# ---------------------------------------------------------------------------
# 5) Unsupported tool name → fall back to first-response content
# ---------------------------------------------------------------------------


async def test_ai_chat_tool_call_unsupported_function_name_is_ignored() -> None:
    """当 LLM 返回一个未声明的 tool_call（如 ``send_email``）→ AI Chat 必须
    走 fallback：直接返回第一步 ``content``，不再二次调用 LLM，QueryService
    不被调用。
    """
    bad_payload = _make_tool_call_response(
        function_name="send_email",
        arguments={"to": "boss@acme.com"},
        content="抱歉，我暂时无法执行该操作。",
    )

    call_count = {"llm": 0}

    async def fake_llm(self, system: str, user: str) -> str:
        return "ok"

    async def fake_llm_with_tools(
        self, messages: list[dict], *, tools=None, tool_choice="auto"
    ) -> dict:
        call_count["llm"] += 1
        return bad_payload

    query_service = AsyncMock()
    query_service.ask = AsyncMock()

    service, session = _make_service(query_service=query_service)

    with patch.object(AIChatService, "_call_llm", fake_llm), patch.object(
        AIChatService, "_call_llm_with_tools", fake_llm_with_tools
    ):
        result = await service.chat(
            ServiceChatRequest(message="发个邮件给老板", context_window=3),
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role="employee",
            session=session,  # type: ignore[arg-type]
        )

    # LLM called exactly once — the fallback path skips the second call
    assert call_count["llm"] == 1
    # QueryService never invoked
    assert query_service.ask.await_count == 0
    # Reply is the fallback content
    assert "抱歉" in result.reply or "无法" in result.reply
