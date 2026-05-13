import asyncio
import logging
import re

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.knowledge.application.fusion_service import FrequencyFusion
from app.contexts.knowledge.application.ner_service import RuleBasedNER
from app.contexts.knowledge.application.recall_service import (
    PgKeywordRecallChannel,
    PgMetadataRecallChannel,
    PgVectorRecallChannel,
)
from app.shared.domain.recall_channel import RecallResult
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id

logger = logging.getLogger(__name__)
router = APIRouter()

_ner = RuleBasedNER()
_vector_channel = PgVectorRecallChannel()
_keyword_channel = PgKeywordRecallChannel()
_metadata_channel = PgMetadataRecallChannel()
_fusion = FrequencyFusion()


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


async def _call_llm(system_prompt: str, user_content: str) -> str:
    provider = settings.llm_default_provider

    if provider == "minimax" and settings.minimax_api_key:
        api_key = settings.minimax_api_key
        base_url = settings.minimax_base_url
        model = settings.minimax_model
    elif provider == "deepseek" and settings.deepseek_api_key:
        api_key = settings.deepseek_api_key
        base_url = settings.deepseek_base_url
        model = settings.deepseek_model
    elif settings.qwen_api_key:
        api_key = settings.qwen_api_key
        base_url = settings.qwen_base_url
        model = settings.qwen_model
    elif settings.minimax_api_key:
        api_key = settings.minimax_api_key
        base_url = settings.minimax_base_url
        model = settings.minimax_model
    elif settings.deepseek_api_key:
        api_key = settings.deepseek_api_key
        base_url = settings.deepseek_base_url
        model = settings.deepseek_model
    else:
        return (
            "⚠️ 尚未配置 LLM API Key，请在 .env 中设置 "
            "MINIMAX_API_KEY / DEEPSEEK_API_KEY / QWEN_API_KEY。"
            "当前仅支持知识库关键词检索模式。"
        )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
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
