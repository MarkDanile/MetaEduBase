"""REQ-056 Task 3 — AI Chat tool 接收 catalog_id 参数实现双键路由。

测试覆盖两个核心场景：

1. ``test_ai_chat_tool_with_catalog_id_routes_to_correct_semantic_model`` —
   同一租户下有两个 catalog（"教育" 与 "园区"）都注册了 ``bill`` entity_type
   的 active semantic model。当 AI Chat 工具调用 ``query_internal_data`` 时
   显式传入 ``catalog_id="park_uuid"`` → AI Chat 必须路由到园区 catalog
   的 semantic model，而不是只按 entity_type 匹配到任意一个。

2. ``test_ai_chat_tool_without_catalog_id_uses_entity_type_only_fallback`` —
   LLM 不传 ``catalog_id``（最常见的 V1 行为）→ AI Chat 走 entity_type
   单键回退，与 REQ-052 Task 7 的历史行为一致。

设计要点（与 brief 对齐）：

- ``_QUERY_INTERNAL_DATA_TOOL.parameters.properties.catalog_id`` 是 string,
  optional；LLM 显式传时按 UUID 解析。
- SemanticModel 必须显式带 ``catalog_id`` 属性（域 dataclass 自 REQ-054 起
  持有该字段），QueryService.ask 通过 ``semantic_model.catalog_id`` 写到
  audit row — 这条链路在 REQ-054 Task 6 已经接通。
- 测试通过 ``service.semantic_model_repository_factory`` 注入 fake
  ``SemanticModelRepository``，mock
  ``get_active_by_catalog_and_entity_type`` 和
  ``get_active_by_entity_type`` 分别被调用次数与参数。
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
# Minimal fakes — mirror the seam pattern from test_ai_chat_tool_calling.py
# so this file does not pull in the real PostgreSQL adapter stack.
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
    arguments: dict[str, Any],
    *,
    tool_call_id: str = "call_test_1",
    content: str | None = None,
) -> dict:
    """Build the OpenAI-shaped tool_call response payload."""
    return {
        "content": content,
        "tool_calls": [
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": "query_internal_data",
                    "arguments": json.dumps(arguments),
                },
            }
        ],
    }


def _make_text_response(content: str) -> dict:
    return {"content": content, "tool_calls": None}


def _make_fake_semantic_model(
    *,
    entity_type: str = "bill",
    catalog_id: uuid.UUID | None = None,
) -> MagicMock:
    """SemanticModel mock — the AI Chat service only needs ``entity_type`` /
    ``entity_name`` / ``data_source_config`` / ``catalog_id`` attributes to
    forward to QueryService.ask and the audit log."""
    sm = MagicMock()
    sm.entity_type = entity_type
    sm.entity_name = "账单"
    sm.data_source_config = {"type": "imported_dataset", "dataset_id": "ds-test"}
    sm.id = uuid.uuid4()
    sm.tenant_id = uuid.uuid4()
    sm.catalog_id = catalog_id
    return sm


def _make_service_with_repo(
    *,
    semantic_repo: MagicMock,
    query_service: AsyncMock | None = None,
) -> tuple[AIChatService, FakeSession]:
    """Build an AIChatService wired with fakes and an injected SemanticModel
    repository that we control per-test."""
    fid = uuid.uuid4()
    chunk = _chunk_evidence(fid, 1, score=0.9, content="RAG 上下文 " * 30)
    cr = FakeChunkRetriever()
    cr.return_value = [chunk]
    service = AIChatService(
        chunk_retriever=cr,
        graph_retriever=FakeGraphRetriever(),
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=SimpleFrequencyFusion(),
    )
    service.query_service = query_service or AsyncMock()
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
# Schema — catalog_id must be declared on the tool so the LLM can fill it
# ---------------------------------------------------------------------------


def test_query_internal_data_tool_schema_declares_catalog_id() -> None:
    """REQ-056 Task 3: ``_QUERY_INTERNAL_DATA_TOOL`` parameters schema 必须
    显式声明 ``catalog_id``（string, optional），让 LLM 可以按 catalog 路由。

    这是一个 contract-level 的断言 — 任何回归（例如后续有人把
    ``catalog_id`` 从 schema 里移除）都会立即被这个测试抓住。
    """
    tool = AIChatService._QUERY_INTERNAL_DATA_TOOL
    params = tool["function"]["parameters"]
    props = params["properties"]
    assert "catalog_id" in props, (
        "query_internal_data tool parameters schema must declare catalog_id; "
        f"current properties: {list(props.keys())}"
    )
    catalog_id_schema = props["catalog_id"]
    assert catalog_id_schema.get("type") == "string"
    # "required" must NOT include catalog_id — it's optional. V1 lets the LLM
    # skip it; in that case we fall back to entity_type-only resolution.
    assert "catalog_id" not in params.get("required", []), (
        "catalog_id must be optional; the LLM may legitimately omit it and "
        "let the chat service fall back to entity_type-only routing."
    )


# ---------------------------------------------------------------------------
# Test 1 — 2 catalogs, same entity_type, LLM picks the right one
# ---------------------------------------------------------------------------


async def test_ai_chat_tool_with_catalog_id_routes_to_correct_semantic_model() -> None:
    """同一租户有两个 catalog（"education" + "park"），都注册了 ``bill``
    entity_type 的 active semantic model。AI Chat 显式传
    ``catalog_id=park_uuid`` → 必须路由到园区 catalog 的 semantic model，
    而不是只按 entity_type 匹配到任意一个（防 REQ-054 修复前的
    MultipleResultsFound 风险）。

    关键断言：

    - ``semantic_repo.get_active_by_catalog_and_entity_type`` 被调用 1 次，
      参数是 ``catalog_id=park_uuid, entity_type="bill"``。
    - ``semantic_repo.get_active_by_entity_type``（legacy 单键方法）**不被调用** —
      一旦 LLM 显式传 catalog_id，就走双键路由。
    - QueryService.ask 收到的 ``semantic_model.catalog_id`` 等于 park_uuid，
      证明 audit 行能正确归属园区 catalog。
    """
    park_catalog_id = uuid.uuid4()
    edu_catalog_id = uuid.uuid4()

    # The two catalogs each have their own bill semantic model. We must only
    # return the park one when (catalog_id=park, entity_type=bill) is queried.
    park_bill = _make_fake_semantic_model(
        entity_type="bill", catalog_id=park_catalog_id
    )
    park_bill.id = uuid.uuid4()
    park_bill.entity_name = "园区账单"
    park_bill.data_source_config = {
        "type": "imported_dataset",
        "dataset_id": "ds-park",
    }

    edu_bill = _make_fake_semantic_model(
        entity_type="bill", catalog_id=edu_catalog_id
    )
    edu_bill.entity_name = "教育账单"

    semantic_repo = MagicMock()
    semantic_repo.get_active_by_catalog_and_entity_type = AsyncMock(
        return_value=park_bill
    )
    semantic_repo.get_active_by_entity_type = AsyncMock(return_value=edu_bill)

    first_payload = _make_tool_call_response(
        arguments={
            "question": "园区上季度欠费多少",
            "entity_hint": "bill",
            "catalog_id": str(park_catalog_id),
        },
        tool_call_id="call_park_1",
    )
    second_payload = _make_text_response("园区上季度累计欠费 5 万。")

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
            "result_rows": [{"total_unpaid": 50000.0}],
            "result_count": 1,
            "summary": "园区上季度累计欠费 5 万",
            "metric_values": {},
            "filters_applied": {},
            "caveats": [],
            "confidence": "high",
            "duration_ms": 30,
        }
    )

    service, session = _make_service_with_repo(
        semantic_repo=semantic_repo, query_service=query_service
    )

    tenant_id = uuid.uuid4()
    with patch.object(AIChatService, "_call_llm", fake_llm), patch.object(
        AIChatService, "_call_llm_with_tools", fake_llm_with_tools
    ):
        await service.chat(
            ServiceChatRequest(message="园区上季度欠费多少", context_window=3),
            tenant_id=tenant_id,
            user_id=uuid.uuid4(),
            role="manager",
            session=session,  # type: ignore[arg-type]
        )

    # 1) 双键路由被正确调用,参数包含 park catalog id 与 bill entity_type
    assert semantic_repo.get_active_by_catalog_and_entity_type.await_count == 1, (
        "AI Chat must call get_active_by_catalog_and_entity_type when LLM "
        "provides catalog_id — dual-key routing is the whole point of "
        "REQ-054 / REQ-056 Task 3."
    )
    dual_kwargs = semantic_repo.get_active_by_catalog_and_entity_type.await_args.kwargs
    assert dual_kwargs["catalog_id"] == park_catalog_id
    assert dual_kwargs["entity_type"] == "bill"
    assert dual_kwargs["tenant_id"] == tenant_id

    # 2) Legacy 单键 fallback 不被调用 — 一旦 LLM 传 catalog_id,就走双键路由
    assert semantic_repo.get_active_by_entity_type.await_count == 0, (
        "AI Chat must NOT call the legacy single-key get_active_by_entity_type "
        "when the LLM has already supplied a catalog_id — that would defeat "
        "the dual-key routing guarantee."
    )

    # 3) QueryService.ask 收到的 semantic_model 是园区 catalog 的那个,
    #    且 catalog_id 字段透传到了 audit 链路
    assert query_service.ask.await_count == 1
    ask_kwargs = query_service.ask.await_args.kwargs
    sm = ask_kwargs["semantic_model"]
    assert sm is park_bill, (
        "QueryService.ask must receive the park-catalog semantic model, "
        f"got id={sm.id} entity={sm.entity_name}"
    )
    assert sm.catalog_id == park_catalog_id
    # Entity name reflects the park catalog — proves we did NOT pick up the
    # education catalog's bill model by mistake.
    assert sm.entity_name == "园区账单"


# ---------------------------------------------------------------------------
# Test 2 — LLM omits catalog_id → fall back to entity_type-only lookup
# ---------------------------------------------------------------------------


async def test_ai_chat_tool_without_catalog_id_uses_entity_type_only_fallback() -> None:
    """LLM 不传 ``catalog_id``（V1 最常见行为）→ AI Chat 必须走 entity_type
    单键回退（与 REQ-052 Task 7 历史行为兼容），而不是抛错。

    这个 fallback 路径是必要的：
    - 旧模型/小模型可能不知道 ``catalog_id`` 字段
    - 系统 prompt 没有强制要求 catalog_id → LLM 可能省略
    - 多 catalog 尚未普及的租户应该继续走原路径

    关键断言：
    - ``semantic_repo.get_active_by_entity_type`` 被调用 1 次
    - ``get_active_by_catalog_and_entity_type`` 不被调用
    - QueryService.ask 收到的 semantic_model 与单键 lookup 返回的一致
    """
    semantic_repo = MagicMock()
    fallback_bill = _make_fake_semantic_model(entity_type="bill")
    fallback_bill.entity_name = "默认账单"
    fallback_bill.catalog_id = uuid.uuid4()
    semantic_repo.get_active_by_entity_type = AsyncMock(return_value=fallback_bill)
    semantic_repo.get_active_by_catalog_and_entity_type = AsyncMock(
        return_value=None
    )

    # LLM only fills question + entity_hint (no catalog_id)
    first_payload = _make_tool_call_response(
        arguments={
            "question": "这企业欠费多少",
            "entity_hint": "bill",
        },
        tool_call_id="call_no_catalog",
    )
    second_payload = _make_text_response("该企业欠费 12.5 万。")

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
            "result_rows": [{"total_unpaid": 125000.0}],
            "result_count": 1,
            "summary": "欠费 12.5 万",
            "metric_values": {},
            "filters_applied": {},
            "caveats": [],
            "confidence": "high",
            "duration_ms": 20,
        }
    )

    service, session = _make_service_with_repo(
        semantic_repo=semantic_repo, query_service=query_service
    )

    tenant_id = uuid.uuid4()
    with patch.object(AIChatService, "_call_llm", fake_llm), patch.object(
        AIChatService, "_call_llm_with_tools", fake_llm_with_tools
    ):
        await service.chat(
            ServiceChatRequest(message="这企业欠费多少", context_window=3),
            tenant_id=tenant_id,
            user_id=uuid.uuid4(),
            role="employee",
            session=session,  # type: ignore[arg-type]
        )

    # 1) Single-key fallback is used
    assert semantic_repo.get_active_by_entity_type.await_count == 1, (
        "AI Chat must call get_active_by_entity_type when LLM omits catalog_id "
        "— that's the V1 backward-compatible fallback."
    )
    fallback_kwargs = semantic_repo.get_active_by_entity_type.await_args.kwargs
    assert fallback_kwargs["entity_type"] == "bill"
    assert fallback_kwargs["tenant_id"] == tenant_id

    # 2) Dual-key path NOT used
    assert semantic_repo.get_active_by_catalog_and_entity_type.await_count == 0, (
        "AI Chat must NOT call the dual-key lookup when LLM does not provide "
        "catalog_id."
    )

    # 3) QueryService.ask receives the single-key lookup's semantic model
    assert query_service.ask.await_count == 1
    sm = query_service.ask.await_args.kwargs["semantic_model"]
    assert sm is fallback_bill
    # catalog_id still flows to audit (resolved from the returned semantic model)
    assert sm.catalog_id is not None
