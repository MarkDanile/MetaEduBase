import os
import httpx
import logging

from app.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536


async def get_embedding(text: str) -> list[float] | None:
    api_key = settings.qwen_api_key or os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return None

    base_url = settings.qwen_base_url
    model = settings.embedding_model

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "input": [text]},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
    except Exception as e:
        logger.warning(f"Embedding 生成失败: {e}")
        return None
