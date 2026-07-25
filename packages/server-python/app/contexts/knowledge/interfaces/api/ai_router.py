import asyncio
import json
import logging
import os
import re
import uuid
from dataclasses import replace

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.direct_rag_compatibility import (
    DirectRagCompatibilityAdapter,
    DirectRagCompatibilityError,
    DirectRagExecutionPendingError,
    DirectRagOutputTooLargeError,
    DirectRagRecording,
    DirectRagTurnPendingError,
    PreparedDirectRagTurn,
)
from app.contexts.agent_execution.domain import AgentExecutionError
from app.contexts.agent_workspace.domain import AgentWorkspaceError
from app.contexts.document.infrastructure.chunk_repository import ChunkRepository
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.knowledge.application.ai_chat_service import (
    AIChatService,
)
from app.contexts.knowledge.application.ai_chat_service import (
    ChatRequest as ServiceChatRequest,
)
from app.contexts.knowledge.application.ai_chat_service import (
    ChatResponse as ServiceChatResponse,
)
from app.contexts.knowledge.application.composite_retriever import (
    CompositeChunkRetriever,
)
from app.contexts.knowledge.application.context_packer import ContextPacker
from app.contexts.knowledge.application.evidence_fusion import RRFFusion
from app.contexts.knowledge.application.fusion_service import FrequencyFusion
from app.contexts.knowledge.application.recall_service import (
    PgKeywordRecallChannel,
    PgMetadataRecallChannel,
    PgVectorRecallChannel,
)
from app.contexts.knowledge.domain.evidence import DocumentSource, EvidenceItem
from app.contexts.knowledge.infrastructure.retrievers.pg_chunk_keyword_retriever import (
    PgChunkKeywordRetriever,
)
from app.contexts.knowledge.infrastructure.retrievers.pg_chunk_vector_retriever import (
    PgChunkVectorRetriever,
)
from app.contexts.knowledge.infrastructure.retrievers.pg_graph_retriever import (
    PgEdgeRetriever,
    PgGraphRetriever,
)
from app.contexts.knowledge.infrastructure.retrievers.pg_metadata_filter import (
    PgMetadataFilter,
)
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id
from app.shared.llm.provider_resolver import resolve_chat_provider

logger = logging.getLogger(__name__)
router = APIRouter()

_vector_channel = PgVectorRecallChannel()
_keyword_channel = PgKeywordRecallChannel()
_metadata_channel = PgMetadataRecallChannel()
_fusion = FrequencyFusion()

# REQ-017 Slice 1 — weighted RRF defaults.
# Override with RRF_CHANNEL_WEIGHTS env var (JSON dict).
_RRF_DEFAULT_WEIGHTS: dict[str, float] = {
    "vector": 1.0,
    "keyword": 1.0,
    "graph_node": 0.5,
    "graph_edge": 0.5,  # REQ-018 Slice 2: edge recall channel
}


def _get_rrf_channel_weights() -> dict[str, float]:
    """Read RRF_CHANNEL_WEIGHTS from environment, fall back to defaults."""
    raw = os.environ.get("RRF_CHANNEL_WEIGHTS", "")
    if not raw:
        return _RRF_DEFAULT_WEIGHTS.copy()
    try:
        parsed: dict[str, float] = json.loads(raw)
        # Merge with defaults so unspecified channels get the default weight
        return {**_RRF_DEFAULT_WEIGHTS, **parsed}
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("RRF_CHANNEL_WEIGHTS=%r parse failed, using defaults", raw)
        return _RRF_DEFAULT_WEIGHTS.copy()


def _graph_edge_recall_enabled() -> bool:
    """REQ-036: graph_edge 通道生产门控。默认 false（REQ-035 决策禁用）。

    生产默认权重 0.5 下 graph_edge 召回 ~8 chunks/样例但 0 进 fusion/packed
    （REQ-034 证惰性），且即使 boosting 亦不改善 Metric B/跨文档（REQ-033）。
    env GRAPH_EDGE_RECALL_ENABLED 真值（"1"/"true"/"yes"/"on"，大小写不敏感）
    → 启用 edge_retriever；否则 None（禁用，省每 query 3 SQL 召回成本）。

    PgEdgeRecallChannel / PgEdgeRetriever 代码保留，可随时经 env 重新启用
    （如 vector 召回退化或图谱扩充时）。
    """
    raw = os.environ.get("GRAPH_EDGE_RECALL_ENABLED", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


# REQ-010 Slice 3 — evidence-aware AI Chat service (default PG adapters).
def _build_evidence_service(
    session: AsyncSession, tenant_id: str, *, use_hybrid_ner: bool = True
) -> AIChatService:
    tenant_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
    rrf_weights = _get_rrf_channel_weights()
    graph_edge_on = _graph_edge_recall_enabled()
    logger.info(
        "ai_router: graph_edge recall %s (GRAPH_EDGE_RECALL_ENABLED=%r)",
        "enabled" if graph_edge_on else "disabled (3-channel production)",
        os.environ.get("GRAPH_EDGE_RECALL_ENABLED", ""),
    )

    # Lazy import to avoid circular dependency with hybrid_ner_service → ai_router
    if use_hybrid_ner:
        from app.contexts.knowledge.application.hybrid_ner_service import (
            HybridQueryUnderstandingService,
        )

        ner_pipeline = HybridQueryUnderstandingService()
    else:
        ner_pipeline = None

    return AIChatService(
        chunk_retriever=CompositeChunkRetriever(
            [
                PgChunkVectorRetriever(),
                PgChunkKeywordRetriever(),
            ]
        ),
        graph_retriever=PgGraphRetriever(),
        metadata_filter=PgMetadataFilter(),
        evidence_fusion=RRFFusion(channel_weights=rrf_weights),
        ner_pipeline=ner_pipeline,
        context_packer=ContextPacker(ChunkRepository(session), tenant_uuid),
        # REQ-036: graph_edge 通道默认禁用（REQ-035 决策）。经
        # GRAPH_EDGE_RECALL_ENABLED env 启用。PgEdgeRetriever 代码保留。
        edge_retriever=PgEdgeRetriever() if graph_edge_on else None,
    )


# Test seam only: production builds the service per request so ContextPacker can
# use the request-bound session and tenant. Existing tests may patch this value.
_evidence_service: AIChatService | None = None


class LLMProviderCallError(RuntimeError):
    """Sanitized provider failure safe to cross the application boundary."""


def _clean_llm_output(content: str) -> str:
    content = re.sub(r"考量.*?生成", "", content, flags=re.DOTALL)
    content = re.sub(r"思路.*?回复", "", content, flags=re.DOTALL)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    return content.strip()


class ChatRequest(BaseModel):
    message: str
    context_window: int = 5
    conversation_id: uuid.UUID | None = None
    client_message_id: uuid.UUID | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value:
            raise ValueError("message must not be empty")
        if "\x00" in value:
            raise ValueError("message cannot contain NUL characters")
        if len(value.encode("utf-8")) > 64 * 1024:
            raise ValueError("message exceeds 65536 UTF-8 bytes")
        return value

    @model_validator(mode="after")
    def validate_idempotency_identity(self) -> "ChatRequest":
        if (self.conversation_id is None) != (self.client_message_id is None):
            raise ValueError(
                "conversation_id and client_message_id must be supplied together"
            )
        return self


class EvidenceChatResponse(BaseModel):
    """REQ-010 Slice 3 — ``/ai/chat/evidence`` endpoint response shape.

    Uses `EvidenceItem` (unified evidence DTO) for ``sources``. Frontend
    evidence card consumes this directly. The legacy node-shaped
    ``SourceItem`` / ``ChatResponse`` were removed by TD-048 once frontend
    and MCP consumers had migrated to this endpoint.
    """

    reply: str
    sources: list[EvidenceItem]
    document_sources: list[DocumentSource] = Field(default_factory=list)
    diagnostics: dict = Field(default_factory=dict)
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    run_id: uuid.UUID
    assistant_message_id: uuid.UUID | None


def _build_direct_rag_compatibility_adapter(
    session: AsyncSession,
) -> DirectRagCompatibilityAdapter:
    return DirectRagCompatibilityAdapter(session)


def _compatibility_http_error(exc: Exception) -> HTTPException:
    if exc.__class__.__name__ == "IdempotencyConflictError":
        code = "idempotency_conflict"
    else:
        code = "direct_rag_recording_conflict"
    return HTTPException(
        status_code=409,
        detail={"code": code, "message": "Direct RAG request conflicts"},
    )


def _evidence_response(
    result: ServiceChatResponse,
    recording: DirectRagRecording,
) -> EvidenceChatResponse:
    return EvidenceChatResponse(
        reply=result.reply,
        sources=result.sources,
        document_sources=(
            getattr(result, "document_sources", [])
            if isinstance(getattr(result, "document_sources", []), list)
            else []
        ),
        diagnostics=(
            getattr(result, "diagnostics", {})
            if isinstance(getattr(result, "diagnostics", {}), dict)
            else {}
        ),
        conversation_id=recording.conversation_id,
        user_message_id=recording.user_message_id,
        run_id=recording.run_id,
        assistant_message_id=recording.assistant_message_id,
    )


def _replay_response(prepared: PreparedDirectRagTurn) -> EvidenceChatResponse:
    assert prepared.replay_reply is not None
    return EvidenceChatResponse(
        reply=prepared.replay_reply,
        sources=list(prepared.replay_sources),
        document_sources=[],
        diagnostics={"compatibility_replay": True},
        conversation_id=prepared.recording.conversation_id,
        user_message_id=prepared.recording.user_message_id,
        run_id=prepared.recording.run_id,
        assistant_message_id=prepared.recording.assistant_message_id,
    )


async def _recover_completed_turn(
    *,
    compatibility: DirectRagCompatibilityAdapter,
    prepared: PreparedDirectRagTurn,
    session: AsyncSession,
) -> EvidenceChatResponse | None:
    reconciled = await compatibility.completed_turn(prepared=prepared)
    if reconciled is None:
        return None
    await session.commit()
    if reconciled.requires_output_publish:
        reconciled = await compatibility.publish_completed_turn(prepared=reconciled)
        await session.commit()
    return _replay_response(reconciled)


async def _execute_direct_rag_turn(
    *,
    data: ChatRequest,
    session: AsyncSession,
    current_user: dict,
    tenant_id: str,
    compatibility: DirectRagCompatibilityAdapter,
    prepared: PreparedDirectRagTurn,
) -> EvidenceChatResponse:
    service = _evidence_service or _build_evidence_service(session, tenant_id)
    try:
        result: ServiceChatResponse = await service.chat(
            ServiceChatRequest(
                message=data.message,
                context_window=data.context_window,
            ),
            tenant_id=tenant_id,
            session=session,
            current_user=current_user,
        )
    except asyncio.CancelledError:
        await session.rollback()
        try:
            await compatibility.fail_turn(
                prepared=prepared,
                code="direct_rag_request_cancelled",
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.error(
                "failed to settle cancelled Direct RAG request run_id=%s",
                prepared.recording.run_id,
            )
        raise
    except Exception:
        await session.rollback()
        try:
            replay = await _recover_completed_turn(
                compatibility=compatibility,
                prepared=prepared,
                session=session,
            )
            if replay is not None:
                return replay
            await compatibility.fail_turn(prepared=prepared)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.error(
                "failed to persist Direct RAG failed terminal run_id=%s",
                prepared.recording.run_id,
            )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "direct_rag_execution_failed",
                "message": "AI service execution failed",
                "run_id": str(prepared.recording.run_id),
            },
        ) from None

    try:
        recording = await compatibility.complete_turn(
            prepared=prepared,
            response=result,
        )
        await session.commit()
    except DirectRagOutputTooLargeError:
        await session.rollback()
        await compatibility.fail_turn(
            prepared=prepared,
            code="direct_rag_output_too_large",
        )
        await session.commit()
        raise HTTPException(
            status_code=502,
            detail={
                "code": "direct_rag_output_too_large",
                "message": "AI answer exceeds the durable output limit",
                "run_id": str(prepared.recording.run_id),
            },
        ) from None
    except Exception as recording_error:
        await session.rollback()
        try:
            replay = await _recover_completed_turn(
                compatibility=compatibility,
                prepared=prepared,
                session=session,
            )
            if replay is not None:
                return replay
            await compatibility.fail_turn(
                prepared=prepared,
                code="direct_rag_recording_failed",
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.error(
                "failed to reconcile Direct RAG terminal recording run_id=%s",
                prepared.recording.run_id,
            )
        if isinstance(recording_error, DirectRagCompatibilityError):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "direct_rag_run_not_active",
                    "message": "Direct RAG request is no longer active",
                    "run_id": str(prepared.recording.run_id),
                },
            ) from None
        raise recording_error

    try:
        published = await compatibility.publish_completed_turn(
            prepared=replace(prepared, recording=recording)
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise HTTPException(
            status_code=503,
            detail={
                "code": "direct_rag_output_pending",
                "message": "AI answer is pending durable projection",
                "run_id": str(recording.run_id),
            },
        ) from None
    return _evidence_response(result, published.recording)


@router.post("/chat/evidence", response_model=EvidenceChatResponse)
async def ai_chat_evidence(
    data: ChatRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _current_user: dict = Depends(get_current_user),  # noqa: B008
):
    """REQ-010 Slice 3 — evidence-aware AI Chat endpoint.

    Uses `AIChatService` (Slice 3) which depends on ChunkRetriever /
    GraphRetriever / MetadataFilter / EvidenceFusion abstractions. P1 default
    PostgreSQL adapters; LLM prompt is built from `EvidenceItem` list with
    [1] / [2] citation numbering. `sources` field is `list[EvidenceItem]`
    (chunk / knowledge_node / knowledge_edge / structured_field).
    """
    tenant_value = get_tenant_id() or _current_user.get("tenant_id")
    tid = str(tenant_value)
    tenant_id = uuid.UUID(tid)
    actor_id = uuid.UUID(str(_current_user["id"]))
    conversation_id = data.conversation_id or uuid.uuid4()
    client_message_id = data.client_message_id or uuid.uuid4()
    compatibility = _build_direct_rag_compatibility_adapter(session)

    try:
        prepared = await compatibility.prepare_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            client_message_id=client_message_id,
            message=data.message,
            context_window=data.context_window,
        )
        await session.commit()
        prepared = await compatibility.activate_turn(prepared=prepared)
        await session.commit()
    except DirectRagTurnPendingError:
        await session.rollback()
        raise HTTPException(
            status_code=503,
            detail={
                "code": "direct_rag_turn_pending",
                "message": "AI request is pending durable execution acceptance",
                "run_id": str(prepared.recording.run_id),
            },
        ) from None
    except (AgentWorkspaceError, AgentExecutionError, DirectRagCompatibilityError) as exc:
        await session.rollback()
        raise _compatibility_http_error(exc) from exc

    if prepared.requires_output_publish:
        try:
            prepared = await compatibility.publish_completed_turn(prepared=prepared)
            await session.commit()
        except Exception:
            await session.rollback()
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "direct_rag_output_pending",
                    "message": "AI answer is pending durable projection",
                    "run_id": str(prepared.recording.run_id),
                },
            ) from None

    if prepared.is_completed_replay:
        return _replay_response(prepared)

    try:
        async with compatibility.execution_claim(prepared=prepared):
            return await _execute_direct_rag_turn(
                data=data,
                session=session,
                current_user=_current_user,
                tenant_id=tid,
                compatibility=compatibility,
                prepared=prepared,
            )
    except DirectRagExecutionPendingError:
        await session.rollback()
        try:
            replay = await _recover_completed_turn(
                compatibility=compatibility,
                prepared=prepared,
                session=session,
            )
            if replay is not None:
                return replay
        except Exception:
            await session.rollback()
        raise HTTPException(
            status_code=503,
            detail={
                "code": "direct_rag_execution_pending",
                "message": "AI request is already executing",
                "run_id": str(prepared.recording.run_id),
            },
        ) from None


async def _call_llm(system_prompt: str, user_content: str) -> str:
    """Synchronous-style LLM call returning plain text content.

    **REQ-052 Task 7 deviation**: this signature is INTENTIONALLY preserved
    verbatim (no ``tools`` kwarg, return type stays ``str``). The plan's
    global constraint mandates backward compatibility — every existing
    caller (RAG retrieval path, hybrid_ner, e2e fixtures) continues to
    receive plain text. Tool-calling support lives in the new sibling
    :func:`_call_llm_with_tools`.
    """
    config = resolve_chat_provider()
    if config is None:
        return (
            "⚠️ 尚未配置 LLM API Key，请在 .env 中设置 "
            "MINIMAX_API_KEY / DEEPSEEK_API_KEY / QWEN_API_KEY。"
            "当前仅支持知识库关键词检索模式。"
        )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{config.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2000,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return _clean_llm_output(content)
    except Exception as e:
        logger.error("LLM call failed")
        return f"❌ AI 回答生成失败: {type(e).__name__}"


async def _call_llm_with_tools(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    tool_choice: str = "auto",
    temperature: float = 0.7,
    max_tokens: int = 2000,
) -> dict:
    """REQ-052 Task 7 — tool-calling-aware LLM call.

    Accepts a full conversation history (``messages``) so the caller can
    stitch together the multi-turn tool-calling flow (system → user →
    assistant+tool_call → tool result). Returns a structured
    ``{"content": str | None, "tool_calls": list | None}`` dict so the
    AI Chat service can decide whether to invoke the tool or short-circuit
    to a direct text reply.

    This is a sibling of :func:`_call_llm` — it does NOT replace it. The
    legacy ``_call_llm`` path is kept for RAG / NER / e2e callers that
    don't need tool awareness (see plan global constraint: "不修改
    ``ai_router._call_llm`` 现有签名（向后兼容，新增 tools 参数）").
    """
    config = resolve_chat_provider()
    if config is None:
        return {
            "content": (
                "⚠️ 尚未配置 LLM API Key，请在 .env 中设置 "
                "MINIMAX_API_KEY / DEEPSEEK_API_KEY / QWEN_API_KEY。"
            ),
            "tool_calls": None,
        }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload: dict = {
                "model": config.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = tool_choice
            resp = await client.post(
                f"{config.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            message = resp.json()["choices"][0]["message"]
            content = message.get("content")
            tool_calls = message.get("tool_calls")
            if isinstance(content, str):
                content = _clean_llm_output(content)
            return {"content": content, "tool_calls": tool_calls}
    except Exception:
        logger.error("LLM call failed (with tools)")
        raise LLMProviderCallError("LLM provider call failed") from None
