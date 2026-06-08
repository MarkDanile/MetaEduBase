from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.contexts.knowledge.application.fusion_service import FrequencyFusion
from app.contexts.knowledge.application.ner_service import RuleBasedNER
from app.contexts.knowledge.application.recall_service import (
    PgKeywordRecallChannel,
    PgMetadataRecallChannel,
    PgVectorRecallChannel,
)
from app.contexts.knowledge.interfaces.api import ai_router
from app.shared.domain.ner_pipeline import NERResult
from app.shared.domain.recall_channel import RecallResult


# --- helpers ---------------------------------------------------------------

class _FakeRow(dict):
    pass


def _row(node_id: str, score: float | None = None):
    r = _FakeRow()
    r["id"] = node_id
    r["title"] = f"title-{node_id}"
    r["description"] = f"desc-{node_id}"
    r["domain"] = "smart_manufacturing"
    r["level"] = "course"
    r["path"] = None
    if score is not None:
        r["score"] = score
    return r


def _session_with_rows(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    execute = AsyncMock(return_value=result)
    session = MagicMock()
    session.execute = execute
    return session


def _build_app():
    app = FastAPI()
    app.include_router(ai_router.router, prefix="/api/v1/ai")

    async def _override_user():
        return {"id": "u", "tenant_id": "t", "role": "student"}

    async def _override_session():
        yield MagicMock()

    from app.contexts.knowledge.interfaces.api.ai_router import get_session  # noqa
    app.dependency_overrides[get_session] = _override_session
    from app.contexts.identity.interfaces.api.dependencies import get_current_user  # noqa
    app.dependency_overrides[get_current_user] = _override_user
    return app


def _mock_llm_response(content: str = "这是AI的回答"):
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": content}}]}
    mock_response.raise_for_status = MagicMock()

    client = AsyncMock()
    client.post = AsyncMock(return_value=mock_response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# --- AC-7: single channel failure does not break chat --------------------

@pytest.mark.asyncio
async def test_ai_chat_degrades_when_one_channel_raises():
    session = _session_with_rows([_row("n1", 0.9)])

    async def vector_ok(*_a, **_k):
        return [RecallResult(
            node_id="n1", title="t", description=None,
            domain="smart_manufacturing", level="course",
            score=0.9, channel="vector", path=None,
        )]

    async def keyword_raise(*_a, **_k):
        raise RuntimeError("db down")

    async def metadata_ok(*_a, **_k):
        return [RecallResult(
            node_id="n2", title="t2", description=None,
            domain="smart_manufacturing", level="course",
            score=0.7, channel="metadata", path=None,
        )]

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(ai_router, "_vector_channel", SimpleNamespace(
            name="vector", recall=vector_ok,
        )), patch.object(ai_router, "_keyword_channel", SimpleNamespace(
            name="keyword", recall=keyword_raise,
        )), patch.object(ai_router, "_metadata_channel", SimpleNamespace(
            name="metadata", recall=metadata_ok,
        )), patch.object(ai_router, "_ner", RuleBasedNER()), \
             patch("app.contexts.knowledge.interfaces.api.ai_router.httpx.AsyncClient",
                   return_value=_mock_llm_response()):
            resp = await ac.post("/api/v1/ai/chat", json={"message": "智能制造专业的课程"})

    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    ids = [s["id"] for s in data["sources"]]
    # 失败的 keyword 通道不能拖垮整体
    assert "n1" in ids
    assert "n2" in ids


# --- AC-8: sources schema --------------------------------------------------

@pytest.mark.asyncio
async def test_ai_chat_sources_have_required_fields():
    async def vector_ok(query, ner_result, tenant_id, session, top_k=5):
        return [RecallResult(
            node_id="n1", title="title-n1", description="d",
            domain="smart_manufacturing", level="course",
            score=0.9, channel="vector", path=None,
        )]

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(ai_router, "_vector_channel", SimpleNamespace(
            name="vector", recall=vector_ok,
        )), patch.object(ai_router, "_keyword_channel", SimpleNamespace(
            name="keyword", recall=AsyncMock(return_value=[]),
        )), patch.object(ai_router, "_metadata_channel", SimpleNamespace(
            name="metadata", recall=AsyncMock(return_value=[]),
        )), patch.object(ai_router, "_ner", RuleBasedNER()), \
             patch("app.contexts.knowledge.interfaces.api.ai_router.httpx.AsyncClient",
                   return_value=_mock_llm_response()):
            resp = await ac.post("/api/v1/ai/chat", json={"message": "智能制造"})

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["sources"], list)
    assert len(data["sources"]) == 1
    src = data["sources"][0]
    for field in ("id", "title", "domain", "level", "score", "channel"):
        assert field in src, f"sources[0] missing {field}"
    assert set(src.keys()) == {"id", "title", "description", "domain", "level", "score", "channel"}


# --- AC-9: e2e fusion dedup ------------------------------------------------

@pytest.mark.asyncio
async def test_ai_chat_fuses_duplicate_node_id_across_channels():
    shared = RecallResult(
        node_id="shared", title="shared-title", description=None,
        domain="smart_manufacturing", level="course",
        score=0.9, channel="vector", path=None,
    )
    only_keyword = RecallResult(
        node_id="kw-only", title="kw", description=None,
        domain="smart_manufacturing", level="course",
        score=0.6, channel="keyword", path=None,
    )

    async def vector_ok(*_a, **_k):  return [shared]
    async def keyword_ok(*_a, **_k): return [shared, only_keyword]
    async def metadata_ok(*_a, **_k): return []

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(ai_router, "_vector_channel", SimpleNamespace(
            name="vector", recall=vector_ok,
        )), patch.object(ai_router, "_keyword_channel", SimpleNamespace(
            name="keyword", recall=keyword_ok,
        )), patch.object(ai_router, "_metadata_channel", SimpleNamespace(
            name="metadata", recall=metadata_ok,
        )), patch.object(ai_router, "_ner", RuleBasedNER()), \
             patch("app.contexts.knowledge.interfaces.api.ai_router.httpx.AsyncClient",
                   return_value=_mock_llm_response()):
            resp = await ac.post("/api/v1/ai/chat", json={"message": "智能制造专业的知识点"})

    assert resp.status_code == 200
    data = resp.json()
    ids = [s["id"] for s in data["sources"]]
    assert ids.count("shared") == 1, f"expected dedup, got {ids}"
    assert "kw-only" in ids
    shared_src = next(s for s in data["sources"] if s["id"] == "shared")
    assert set(shared_src["channel"].split(",")) == {"vector", "keyword"}
