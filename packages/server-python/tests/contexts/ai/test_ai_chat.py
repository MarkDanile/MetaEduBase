"""TD-048: 旧 /ai/chat 端点 + SourceItem 契约已被删除；
测试改打 /ai/chat/evidence 并断言 EvidenceItem 形状。
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.contexts.knowledge.interfaces.api.ai_router import (
    LLMProviderCallError,
    _call_llm_with_tools,
    _clean_llm_output,
)


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
async def test_tool_aware_provider_failure_is_sanitized(caplog):
    provider = MagicMock(
        model="test-model",
        base_url="https://provider.invalid",
        api_key="secret-key",
    )
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.side_effect = RuntimeError("SECRET-PROVIDER-DIAGNOSTIC")

    with (
        patch(
            "app.contexts.knowledge.interfaces.api.ai_router.resolve_chat_provider",
            return_value=provider,
        ),
        patch(
            "app.contexts.knowledge.interfaces.api.ai_router.httpx.AsyncClient",
            return_value=client,
        ),
        pytest.raises(LLMProviderCallError, match="LLM provider call failed"),
    ):
        await _call_llm_with_tools([{"role": "user", "content": "hello"}])

    assert "SECRET-PROVIDER-DIAGNOSTIC" not in caplog.text
    assert "secret-key" not in caplog.text


def _fake_evidence_service(reply: str = "这是AI的回答", sources: list[EvidenceItem] | None = None):
    """Build a fake AIChatService whose .chat() returns the given reply/sources.

    TD-048: replaces the legacy `_vector_channel` / `_keyword_channel` mock
    harness. The evidence endpoint routes through `_evidence_service.chat`
    (REQ-010 Slice 3), so we stub the service directly.
    """
    if sources is None:
        sources = []
    service = MagicMock()
    service.chat = AsyncMock(
        return_value=MagicMock(reply=reply, sources=sources, diagnostics={"query": "你好"}),
    )
    return service


@pytest.mark.asyncio
async def test_chat_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/ai/chat/evidence",
        json={"message": "测试消息"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_chat_with_mock_llm(client: AsyncClient, auth_headers: dict):
    fake_service = _fake_evidence_service(
        reply="这是AI的回答",
        sources=[
            EvidenceItem(
                evidence_id="ev-1",
                source_type="knowledge_node",
                file_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                node_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                title="教学目标",
                snippet="理解函数",
                score=0.92,
                channels=["vector"],
            ),
        ],
    )
    with patch(
        "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
        new=fake_service,
    ):
        resp = await client.post(
            "/api/v1/ai/chat/evidence",
            headers=auth_headers,
            json={"message": "你好"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
    assert "sources" in data
    assert data["diagnostics"]["query"] == "你好"
