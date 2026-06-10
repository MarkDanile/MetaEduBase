import asyncio
import logging
import re

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.contexts.knowledge.application.evidence_fusion import SimpleFrequencyFusion
from app.contexts.knowledge.application.fusion_service import FrequencyFusion
from app.contexts.knowledge.application.ner_service import RuleBasedNER
from app.contexts.knowledge.application.recall_service import (
    PgKeywordRecallChannel,
    PgMetadataRecallChannel,
    PgVectorRecallChannel,
)
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.contexts.knowledge.infrastructure.retrievers.pg_chunk_vector_retriever import (
    PgChunkVectorRetriever,
)
from app.contexts.knowledge.infrastructure.retrievers.pg_graph_retriever import (
    PgGraphRetriever,
)
from app.contexts.knowledge.infrastructure.retrievers.pg_metadata_filter import (
    PgMetadataFilter,
)
from app.shared.domain.recall_channel import RecallResult
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id
from app.shared.llm.provider_resolver import resolve_chat_provider

logger = logging.getLogger(__name__)
router = APIRouter()

_ner = RuleBasedNER()
_vector_channel = PgVectorRecallChannel()
_keyword_channel = PgKeywordRecallChannel()
_metadata_channel = PgMetadataRecallChannel()
_fusion = FrequencyFusion()

# REQ-010 Slice 3 — new evidence-aware AI Chat service (default PG adapters).
_evidence_service = AIChatService(
    chunk_retriever=PgChunkVectorRetriever(),
    graph_retriever=PgGraphRetriever(),
    metadata_filter=PgMetadataFilter(),
    evidence_fusion=SimpleFrequencyFusion(),
)


def _clean_llm_output(content: str) -> str:
    content = re.sub(r"考量.*?生成", "", content, flags=re.DOTALL)
    content = re.sub(r"思路.*?回复", "", content, flags=re.DOTALL)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    return content.strip()


class ChatRequest(BaseModel):
    message: str
    context_window: int = 5


class SourceItem(BaseModel):
    id: str
    title: str
    description: str | None = None
    domain: str | None = None
    level: str | None = None
    score: float | None = None
    channel: str = ""


class ChatResponse(BaseModel):
    reply: str
    sources: list[SourceItem]


class EvidenceChatResponse(BaseModel):
    """REQ-010 Slice 3 — new /chat/evidence endpoint response shape.

    Uses `EvidenceItem` (unified evidence DTO) instead of node-shaped
    `SourceItem`. Frontend evidence card consumes this directly.
    """

    reply: str
    sources: list[EvidenceItem]


def _recall_to_source(r: RecallResult) -> SourceItem:
    return SourceItem(
        id=r.node_id,
        title=r.title,
        description=r.description,
        domain=r.domain,
        level=r.level,
        score=r.score,
        channel=r.channel,
    )


async def _run_channel(
    channel,
    query: str,
    ner_domains: list[str],
    ner_levels: list[str],
    tenant_id: str,
    session: AsyncSession,
    top_k: int,
) -> list[RecallResult]:
    from app.shared.domain.ner_pipeline import NERResult

    ner_result = NERResult(domains=ner_domains, levels=ner_levels, raw_entities=[])
    try:
        return await channel.recall(query, ner_result, tenant_id, session, top_k)
    except Exception as e:
        logger.warning(f"召回通道 {channel.name} 失败: {e}")
        return []


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(
    data: ChatRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = str(get_tenant_id())

    ner_result = await _ner.extract(data.message)

    top_k = data.context_window

    vector_coro = _run_channel(
        _vector_channel, data.message,
        ner_result.domains, ner_result.levels, tid, session, top_k,
    )
    keyword_coro = _run_channel(
        _keyword_channel, data.message,
        ner_result.domains, ner_result.levels, tid, session, top_k,
    )
    metadata_coro = _run_channel(
        _metadata_channel, data.message,
        ner_result.domains, ner_result.levels, tid, session, top_k,
    )
    vector_results, keyword_results, metadata_results = await asyncio.gather(
        vector_coro, keyword_coro, metadata_coro,
        return_exceptions=False,
    )

    channel_results: dict[str, list[RecallResult]] = {}
    if vector_results:
        channel_results["vector"] = vector_results
    if keyword_results:
        channel_results["keyword"] = keyword_results
    if metadata_results:
        channel_results["metadata"] = metadata_results

    fused = _fusion.fuse(channel_results, top_k=min(top_k * 2, 15))

    context_text = ""
    if fused:
        context_text = "\n\n相关知识点：\n"
        for idx, ctx in enumerate(fused, 1):
            channel_label = ctx.channel.replace(",", "+")
            context_text += f"[{idx}] [{ctx.domain}/{ctx.level}] {ctx.title}"
            if ctx.description:
                context_text += f"：{ctx.description}"
            context_text += f" (来源: {channel_label})\n"

    # REQ-010 diagnostic log (Slice 1): query, NER, candidate counts, fusion
    # outcome, and prompt summary. No LLM full prompt — only first 200 chars
    # to keep logs lean. See plan Slice 1 "证据模型 + 诊断日志".
    logger.info(
        "ai_chat: query=%r ner_domains=%r ner_levels=%r "
        "vector=%d keyword=%d metadata=%d fused=%d prompt_chars=%d",
        data.message[:120],
        ner_result.domains,
        ner_result.levels,
        len(vector_results),
        len(keyword_results),
        len(metadata_results),
        len(fused),
        len(context_text),
    )

    system_prompt = (
        "你是 MetaEduBase 元知职教基座的 AI 助手，专注于职业教育领域的知识问答。"
        "请基于提供的知识库上下文进行回答，如果上下文不足以回答问题，请如实说明。"
        "回答请使用中文，结构清晰，适合教学场景使用。"
        "如果引用了上下文中的知识点，请在引用处标注 [来源编号]，如 [1]、[2] 等。"
    )

    user_content = data.message
    if context_text:
        user_content = f"{context_text}\n\n学生问题：{data.message}"

    reply = await _call_llm(system_prompt, user_content)

    return ChatResponse(
        reply=reply,
        sources=[_recall_to_source(r) for r in fused],
    )


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

    Old `/chat` endpoint (node-shaped SourceItem) is preserved for backward
    compat; deprecation scheduled for a later iteration.
    """
    tid = str(get_tenant_id())

    result: ServiceChatResponse = await _evidence_service.chat(
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
