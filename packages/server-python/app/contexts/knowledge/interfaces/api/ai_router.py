import logging
import re

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.knowledge.application.embedding_service import get_embedding as get_embedding_vec

logger = logging.getLogger(__name__)
router = APIRouter()


def _clean_llm_output(content: str) -> str:
    content = re.sub(r'考量.*?生成', '', content, flags=re.DOTALL)
    content = re.sub(r'思路.*?回复', '', content, flags=re.DOTALL)
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    return content.strip()


class ChatRequest(BaseModel):
    message: str
    context_window: int = 5


class ChatResponse(BaseModel):
    reply: str
    sources: list[dict]


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(
    data: ChatRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
):
    tid = get_tenant_id()

    embedding = await get_embedding_vec(data.message)

    contexts: list[dict] = []

    if embedding:
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
        result = await session.execute(
            text(
                "SELECT n.id, n.title, n.description, n.domain, n.level, n.path, "
                "1 - (n.embedding <=> :vec::vector) AS score "
                "FROM metaedu.knowledge_nodes n "
                "WHERE n.tenant_id = :tid AND n.embedding IS NOT NULL "
                "ORDER BY n.embedding <=> :vec::vector LIMIT :lim"
            ),
            {"tid": tid, "vec": vec_str, "lim": data.context_window},
        )
        for row in result.mappings().all():
            contexts.append({
                "id": str(row["id"]),
                "title": row["title"],
                "description": row["description"],
                "domain": row["domain"],
                "level": row["level"],
                "score": round(float(row["score"]), 4),
            })
    else:
        raw_words = re.split(r'[，。？、！\s,?.!]+', data.message[:80])
        keywords = []
        for w in raw_words:
            if len(w) >= 2:
                keywords.append(w)
            if len(w) > 6:
                for i in range(0, len(w) - 1, 2):
                    keywords.append(w[i:i + 4])
        keywords = list(dict.fromkeys(keywords))[:8]
        if keywords:
            params = {"tid": tid, "lim": data.context_window}
            for i, kw in enumerate(keywords):
                params[f"q{i}"] = f"%{kw}%"
            conditions = " OR ".join([f"(n.title ILIKE :q{i} OR n.description ILIKE :q{i})" for i in range(len(keywords))])
            result = await session.execute(
                text(
                    "SELECT n.id, n.title, n.description, n.domain, n.level "
                    "FROM metaedu.knowledge_nodes n "
                    f"WHERE n.tenant_id = :tid AND ({conditions}) "
                    "LIMIT :lim"
                ),
                params,
            )
            for row in result.mappings().all():
                contexts.append({
                    "id": str(row["id"]),
                    "title": row["title"],
                    "description": row["description"],
                    "domain": row["domain"],
                    "level": row["level"],
                })

    context_text = ""
    if contexts:
        context_text = "\n\n相关知识点：\n"
        for ctx in contexts:
            context_text += f"- [{ctx['domain']}/{ctx['level']}] {ctx['title']}"
            if ctx.get("description"):
                context_text += f"：{ctx['description']}"
            context_text += "\n"

    system_prompt = (
        "你是 MetaEduBase 元知职教基座的 AI 助手，专注于职业教育领域的知识问答。"
        "请基于提供的知识库上下文进行回答，如果上下文不足以回答问题，请如实说明。"
        "回答请使用中文，结构清晰，适合教学场景使用。"
    )

    user_content = data.message
    if context_text:
        user_content = f"{context_text}\n\n学生问题：{data.message}"

    reply = await _call_llm(system_prompt, user_content)

    return ChatResponse(reply=reply, sources=contexts)


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
        return "⚠️ 尚未配置 LLM API Key，请在 .env 中设置 MINIMAX_API_KEY / DEEPSEEK_API_KEY / QWEN_API_KEY。当前仅支持知识库关键词检索模式。"

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
