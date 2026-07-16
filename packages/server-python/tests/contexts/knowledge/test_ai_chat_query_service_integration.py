"""REQ-056 Task 2 — AIChatService 注入 request-bound QueryService + 真实 user_id。

REQ-052 Task 7 把 QueryService.ask 接到了 AI Chat 工具调用流程，但当时
``chat()`` 接收的是 ``user_id`` / ``role`` / ``tenant_id`` 三个分散
keyword 参数，由调用方各自塞。REQ-056 Task 2 改为统一接收
``current_user: dict``，由 router 直接把 ``Depends(get_current_user)``
拿到的认证用户整体传进来——``user_id`` 必须来自认证用户（不能再退到
``uuid.uuid4()``）。

核心断言：

1. ``current_user`` 提供时，``QueryService.ask`` 收到的 ``user_id``
   严格等于 ``current_user["id"]``（不是随机 UUID）。
2. ``role`` 取自 ``current_user["role"]``。
3. ``tenant_id`` 取自 ``current_user["tenant_id"]``。

为最小依赖，复用 ``test_ai_chat_tool_calling.py`` 的 FakeSession /
FakeChunkRetriever / FakeGraphRetriever / FakeMetadataFilter /
FakeSemanticRepo 模式（这些已在 REQ-052 Task 7 测试中验证过）。
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
# Test fakes (kept local to avoid coupling with sibling test module changes)
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
    """Minimal AsyncSession stand-in for AIChatService.chat SQL."""

    def __init__(self, *, files: list[dict] | None = None) -> None:
        self.files = files or []

    async def execute(self, stmt, params=None):  # noqa: ANN001
        stmt_text = str(stmt)
        if "FROM metaedu.files" in stmt_text:
            return _FakeResult(self.files)
        return _FakeResult([])


def _chunk_evidence(file_id, idx, score=0.9, content="RAG context " * 30) -> EvidenceItem:
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


def _make_tool_call_payload(
    function_name: str = "query_internal_data",
    arguments: dict[str, Any] | None = None,
    tool_call_id: str = "call_req056_t2",
) -> dict:
    return {
        "content": None,
        "tool_calls": [
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": function_name,
                    "arguments": json.dumps(
                        arguments
                        or {"question": "test query", "entity_hint": "bill"}
                    ),
                },
            }
        ],
    }


def _make_text_payload(content: str) -> dict:
    return {"content": content, "tool_calls": None}


def _make_fake_semantic_model() -> MagicMock:
    sm = MagicMock()
    sm.entity_type = "bill"
    sm.entity_name = "账单"
    sm.data_source_config = {"type": "imported_dataset", "dataset_id": "ds-req056"}
    sm.id = uuid.uuid4()
    sm.tenant_id = uuid.uuid4()
    return sm


def _make_service_with_query_service(
    query_service: AsyncMock,
) -> tuple[AIChatService, FakeSession]:
    fid = uuid.uuid4()
    chunk = _chunk_evidence(fid, 1, score=0.9)
    chunk_retriever = FakeChunkRetriever()
    chunk_retriever.return_value = [chunk]

    service = AIChatService(
        chunk_retriever=chunk_retriever,
        graph_retriever=FakeGraphRetriever(),
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=SimpleFrequencyFusion(),
    )
    service.query_service = query_service

    semantic_repo = MagicMock()
    semantic_repo.get_active_by_entity_type = AsyncMock(
        return_value=_make_fake_semantic_model()
    )
    service.semantic_model_repository_factory = lambda s: semantic_repo

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
# 1) current_user → QueryService.ask carries the authenticated user_id
# ---------------------------------------------------------------------------


async def test_ai_chat_evidence_calls_query_service_with_auth_user() -> None:
    """Pass ``current_user`` to ``AIChatService.chat`` → ``QueryService.ask``
    must receive the SAME ``user_id`` as ``current_user["id"]`` — not a
    random ``uuid.uuid4()``.

    This is the regression guard for REQ-056 Task 2: prior to this change
    the chat() method defaulted ``effective_user_id = user_id or
    uuid.uuid4()``, breaking audit traceability.
    """
    first_payload = _make_tool_call_payload()
    second_payload = _make_text_payload("查询结果已生成。")

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
            "result_rows": [{"amount": 100}],
            "result_count": 1,
            "summary": "test summary",
            "metric_values": {},
            "filters_applied": {},
            "caveats": [],
            "confidence": "high",
            "duration_ms": 10,
        }
    )

    auth_user_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    auth_tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    auth_user = {
        "id": auth_user_id,
        "tenant_id": auth_tenant_id,
        "role": "manager",
        "username": "test_manager",
    }

    service, session = _make_service_with_query_service(query_service)

    with patch.object(AIChatService, "_call_llm", fake_llm), patch.object(
        AIChatService, "_call_llm_with_tools", fake_llm_with_tools
    ):
        result = await service.chat(
            ServiceChatRequest(message="这企业欠费多少", context_window=3),
            current_user=auth_user,
            session=session,  # type: ignore[arg-type]
        )

    # QueryService.ask must be invoked exactly once
    assert query_service.ask.await_count == 1, (
        f"QueryService.ask should be called once; got "
        f"{query_service.ask.await_count}"
    )
    ask_kwargs = query_service.ask.await_args.kwargs

    # The auth user_id propagates verbatim — not a random UUID
    assert ask_kwargs["user_id"] == auth_user_id, (
        f"QueryService.ask received user_id={ask_kwargs['user_id']!r}; "
        f"expected auth user_id={auth_user_id!r}"
    )
    assert isinstance(ask_kwargs["user_id"], uuid.UUID)
    assert ask_kwargs["user_id"] != uuid.uuid4()  # not a fresh random

    # role and tenant_id propagate from current_user as well
    assert ask_kwargs["role"] == "manager"
    assert ask_kwargs["tenant_id"] == auth_tenant_id

    # Reply is the second LLM's text (post-tool-result summary)
    assert result.reply == "查询结果已生成。"


# ---------------------------------------------------------------------------
# 2) chat() accepts current_user as a kwarg and tolerates legacy user_id
# ---------------------------------------------------------------------------


async def test_ai_chat_chat_accepts_current_user_kwarg() -> None:
    """``AIChatService.chat`` must accept a ``current_user`` kwarg without
    raising. The signature change in REQ-056 Task 2 must remain
    backward-compatible with callers that pass the legacy
    ``user_id``/``role``/``tenant_id`` kwargs.
    """
    first_payload = _make_tool_call_payload()
    second_payload = _make_text_payload("ok")

    async def fake_llm(self, system: str, user: str) -> str:
        return "ok"

    async def fake_llm_with_tools(
        self, messages: list[dict], *, tools=None, tool_choice="auto"
    ) -> dict:
        # First call has 2 messages (system+user); second call has 4
        # (system+user+assistant+tool) — distinguish by length.
        return second_payload if len(messages) > 2 else first_payload

    query_service = AsyncMock()
    query_service.ask = AsyncMock(
        return_value={
            "ok": True,
            "result_rows": [],
            "result_count": 0,
            "summary": "no data",
            "metric_values": {},
            "filters_applied": {},
            "caveats": [],
            "confidence": "low",
            "duration_ms": 1,
        }
    )

    service, session = _make_service_with_query_service(query_service)

    auth_user = {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000042"),
        "tenant_id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "role": "data_admin",
        "username": "admin1",
    }

    with patch.object(AIChatService, "_call_llm", fake_llm), patch.object(
        AIChatService, "_call_llm_with_tools", fake_llm_with_tools
    ):
        # Should not raise TypeError — chat() must accept current_user kwarg
        await service.chat(
            ServiceChatRequest(message="test", context_window=2),
            current_user=auth_user,
            session=session,  # type: ignore[arg-type]
        )

    # QueryService.ask should be called with auth user's data_admin role
    ask_kwargs = query_service.ask.await_args.kwargs
    assert ask_kwargs["role"] == "data_admin"
    assert ask_kwargs["user_id"] == auth_user["id"]
    assert ask_kwargs["tenant_id"] == auth_user["tenant_id"]


# ---------------------------------------------------------------------------
# 3) current_user overrides stale user_id/role kwargs (current_user wins)
# ---------------------------------------------------------------------------


async def test_current_user_overrides_legacy_kwargs() -> None:
    """When BOTH ``current_user`` AND legacy ``user_id`` are passed,
    ``current_user`` must win — this prevents a caller from accidentally
    passing a stale/mock ``user_id`` alongside a real ``current_user``
    dict. The whole point of REQ-056 Task 2 is that ``current_user`` is
    the source of truth for audit identity.
    """
    first_payload = _make_tool_call_payload()
    second_payload = _make_text_payload("ok")

    async def fake_llm(self, system: str, user: str) -> str:
        return "ok"

    async def fake_llm_with_tools(
        self, messages: list[dict], *, tools=None, tool_choice="auto"
    ) -> dict:
        # First call has 2 messages (system+user); second call has 4
        # (system+user+assistant+tool) — distinguish by length.
        return second_payload if len(messages) > 2 else first_payload

    query_service = AsyncMock()
    query_service.ask = AsyncMock(
        return_value={
            "ok": True,
            "result_rows": [],
            "result_count": 0,
            "summary": "ok",
            "metric_values": {},
            "filters_applied": {},
            "caveats": [],
            "confidence": "low",
            "duration_ms": 1,
        }
    )

    auth_user_id = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
    auth_tenant_id = uuid.UUID("00000000-0000-0000-0000-0000000000bb")
    stale_user_id = uuid.UUID("00000000-0000-0000-0000-0000000dead0")

    auth_user = {
        "id": auth_user_id,
        "tenant_id": auth_tenant_id,
        "role": "leader",
        "username": "leader1",
    }

    service, session = _make_service_with_query_service(query_service)

    with patch.object(AIChatService, "_call_llm", fake_llm), patch.object(
        AIChatService, "_call_llm_with_tools", fake_llm_with_tools
    ):
        await service.chat(
            ServiceChatRequest(message="test", context_window=2),
            current_user=auth_user,
            session=session,  # type: ignore[arg-type]
            user_id=stale_user_id,  # legacy kwarg — must NOT win
            role="employee",  # legacy kwarg — must NOT win
            tenant_id=auth_tenant_id,
        )

    ask_kwargs = query_service.ask.await_args.kwargs
    assert ask_kwargs["user_id"] == auth_user_id, (
        "current_user['id'] must win over legacy user_id kwarg"
    )
    assert ask_kwargs["user_id"] != stale_user_id
    assert ask_kwargs["role"] == "leader", (
        "current_user['role'] must win over legacy role kwarg"
    )
    assert ask_kwargs["role"] != "employee"
