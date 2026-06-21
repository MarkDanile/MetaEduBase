from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.contexts.knowledge.application.embedding_service import (
    get_embedding,
    get_embedding_with_timeout,
)


@pytest.mark.asyncio
async def test_get_embedding_no_api_key():
    with patch("app.contexts.knowledge.application.embedding_service.settings") as mock_settings:
        mock_settings.qwen_api_key = ""
        with patch.dict("os.environ", {"DASHSCOPE_API_KEY": ""}):
            result = await get_embedding("测试文本")
            assert result is None


@pytest.mark.asyncio
async def test_get_embedding_with_api_key():
    fake_embedding = [0.1] * 1536
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [{"embedding": fake_embedding}],
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.contexts.knowledge.application.embedding_service.settings") as mock_settings:
        mock_settings.qwen_api_key = "test-key"
        mock_settings.qwen_base_url = "https://test.example.com/v1"
        mock_settings.embedding_model = "test-model"

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await get_embedding("测试文本")
            assert result == fake_embedding
            assert len(result) == 1536


@pytest.mark.asyncio
async def test_get_embedding_api_failure():
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("API Error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.contexts.knowledge.application.embedding_service.settings") as mock_settings:
        mock_settings.qwen_api_key = "test-key"
        mock_settings.qwen_base_url = "https://test.example.com/v1"
        mock_settings.embedding_model = "test-model"

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await get_embedding("测试文本")
            assert result is None


# TD-070: get_embedding_with_timeout — outer hard timeout for vector recall.


@pytest.mark.asyncio
async def test_get_embedding_with_timeout_success_passthrough():
    """Fast get_embedding → helper returns the embedding unchanged."""
    fake_embedding = [0.1] * 4096

    async def _fast(_text: str) -> list[float]:
        return fake_embedding

    with patch(
        "app.contexts.knowledge.application.embedding_service.get_embedding",
        side_effect=_fast,
    ):
        result = await get_embedding_with_timeout("测试", timeout=60.0)
    assert result == fake_embedding


@pytest.mark.asyncio
async def test_get_embedding_with_timeout_returns_none_on_timeout():
    """Slow get_embedding (>timeout) → helper returns None (keyword fallback)."""
    import asyncio as _asyncio

    async def _slow(_text: str) -> list[float]:
        await _asyncio.sleep(10.0)
        return [0.1] * 4096

    with patch(
        "app.contexts.knowledge.application.embedding_service.get_embedding",
        side_effect=_slow,
    ):
        result = await get_embedding_with_timeout("测试", timeout=0.1)
    assert result is None


@pytest.mark.asyncio
async def test_get_embedding_with_timeout_none_passthrough():
    """get_embedding returning None (no key / all providers fail) → helper
    returns None without raising (preserves existing contract)."""
    with patch(
        "app.contexts.knowledge.application.embedding_service.get_embedding",
        return_value=None,
    ):
        result = await get_embedding_with_timeout("测试", timeout=60.0)
    assert result is None
