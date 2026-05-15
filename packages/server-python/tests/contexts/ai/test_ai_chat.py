from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.contexts.knowledge.interfaces.api.ai_router import _clean_llm_output


@pytest.mark.asyncio
async def test_clean_llm_output_normal():
    assert _clean_llm_output("正常输出") == "正常输出"


@pytest.mark.asyncio
async def test_clean_llm_output_chinese_thinking_tags():
    thinking_output = "考量分析过程。\n\n生成这是正常回答内容。"
    cleaned = _clean_llm_output(thinking_output)
    assert "分析过程" not in cleaned
    assert "正常回答" in cleaned


@pytest.mark.asyncio
async def test_clean_llm_output_another_tag_pair():
    output = "思路解析部分\n\n回复实际的回复内容"
    cleaned = _clean_llm_output(output)
    assert "解析部分" not in cleaned
    assert "实际" in cleaned


@pytest.mark.asyncio
async def test_chat_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/ai/chat",
        json={"message": "测试消息"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_chat_with_mock_llm(client: AsyncClient, auth_headers: dict):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "这是AI的回答"}}]
    }
    mock_response.raise_for_status = MagicMock()

    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.contexts.knowledge.interfaces.api.ai_router.httpx.AsyncClient", return_value=mock_http_client):
        with patch(
            "app.contexts.knowledge.application.recall_service.get_embedding_vec",
            return_value=None,
        ):
            resp = await client.post(
                "/api/v1/ai/chat",
                headers=auth_headers,
                json={"message": "你好"},
            )
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
    assert "sources" in data
