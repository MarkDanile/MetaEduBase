import logging
import re
import uuid

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

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

# REQ-010 Slice 3 — evidence-aware AI Chat service (default PG adapters).
def _build_evidence_service(session: AsyncSession, tenant_id: str) -> AIChatService:
    tenant_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
    return AIChatService(
        chunk_retriever=CompositeChunkRetriever(
            [
                PgChunkVectorRetriever(),
                PgChunkKeywordRetriever(),
            ]
        ),
        graph_retriever=PgGraphRetriever(),
        metadata_filter=PgMetadataFilter(),
        evidence_fusion=RRFFusion(),
        context_packer=ContextPacker(ChunkRepository(session), tenant_uuid),
    )


# Test seam only: production builds the service per request so ContextPacker can
# use the request-bound session and tenant. Existing tests may patch this value.
_evidence_service: AIChatService | None = None


def _clean_llm_output(content: str) -> str:
    content = re.sub(r"考量.*?生成", "", content, flags=re.DOTALL)
    content = re.sub(r"思路.*?回复", "", content, flags=re.DOTALL)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    return content.strip()


class ChatRequest(BaseModel):
    message: str
    context_window: int = 5


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

    service = _evidence_service or _build_evidence_service(session, tid)
    result: ServiceChatResponse = await service.chat(
        ServiceChatRequest(
            message=data.message,
            context_window=data.context_window,
        ),
        tenant_id=tid,
        session=session,
    )

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
    )


async def _call_llm(system_prompt: str, user_content: str) -> str:
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
        logger.error(f"LLM 调用失败: {e}")
        return f"❌ AI 回答生成失败: {type(e).__name__}"
