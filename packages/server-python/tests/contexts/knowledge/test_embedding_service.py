from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.contexts.knowledge.application.embedding_service import get_embedding


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
