"""REQ-003 时代的 RAG 质量门禁 e2e（AC-7 / AC-8 / AC-9）。

TD-048 收口：旧 `/api/v1/ai/chat` 端点 + `SourceItem` 契约已删除；3 个
用例改打 `/api/v1/ai/chat/evidence`，并对 `_evidence_service.chat` 做整体
mock，避免依赖具体 retriever 实现（chunk vector / graph / metadata）。
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.composition.direct_rag_compatibility import (
    DirectRagRecording,
    PreparedDirectRagTurn,
)
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.contexts.knowledge.interfaces.api import ai_router

# --- helpers ---------------------------------------------------------------


def _build_app():
    app = FastAPI()
    app.include_router(ai_router.router, prefix="/api/v1/ai")

    async def _override_user():
        return {
            "id": "81000000-0000-0000-0000-000000000001",
            "tenant_id": "81000000-0000-0000-0000-000000000002",
            "role": "student",
        }

    async def _override_session():
        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        yield session

    from app.contexts.knowledge.interfaces.api.ai_router import get_session  # noqa
    app.dependency_overrides[get_session] = _override_session
    from app.contexts.identity.interfaces.api.dependencies import get_current_user  # noqa
    app.dependency_overrides[get_current_user] = _override_user
    return app


def _make_evidence(
    *,
    evidence_id: str,
    source_type: str = "knowledge_node",
    title: str = "t",
    snippet: str = "",
    score: float | None = 0.9,
    channels: list[str] | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_type=source_type,
        file_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        node_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        title=title,
        snippet=snippet or title,
        score=score,
        channels=list(channels or []),
    )


def _patch_service(sources: list[EvidenceItem], reply: str = "这是AI的回答"):
    """Patch `_evidence_service` on the router module to a fake whose .chat
    returns the given reply + sources. TD-048: replaces per-channel mock
    harness (old `_vector_channel` / `_keyword_channel` / `_metadata_channel`)."""
    service = MagicMock()
    service.chat = AsyncMock(
        return_value=MagicMock(reply=reply, sources=sources),
    )
    return patch(
        "app.contexts.knowledge.interfaces.api.ai_router._evidence_service",
        new=service,
    )


def _patch_compatibility_adapter():
    conversation_id = uuid.uuid4()
    user_message_id = uuid.uuid4()
    run_id = uuid.uuid4()
    assistant_message_id = uuid.uuid4()
    prepared = PreparedDirectRagTurn(
        tenant_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        recording=DirectRagRecording(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            run_id=run_id,
            assistant_message_id=None,
        ),
    )
    completed = DirectRagRecording(
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        run_id=run_id,
        assistant_message_id=assistant_message_id,
    )
    published = PreparedDirectRagTurn(
        tenant_id=prepared.tenant_id,
        actor_id=prepared.actor_id,
        recording=completed,
    )
    adapter = MagicMock()
    adapter.prepare_turn = AsyncMock(return_value=prepared)
    adapter.activate_turn = AsyncMock(return_value=prepared)
    adapter.complete_turn = AsyncMock(return_value=completed)
    adapter.publish_completed_turn = AsyncMock(return_value=published)
    adapter.fail_turn = AsyncMock()
    adapter.completed_turn = AsyncMock(return_value=None)
    return patch(
        "app.contexts.knowledge.interfaces.api.ai_router."
        "_build_direct_rag_compatibility_adapter",
        return_value=adapter,
    )


# --- AC-7: 单通道降级 (TD-048: 走 evidence 端点) ---------------------------


@pytest.mark.asyncio
async def test_ai_chat_degrades_when_one_channel_raises():
    """Even if one retriever would fail, the endpoint returns 200 and surfaces
    surviving evidence from the other channels."""
    sources = [
        _make_evidence(
            evidence_id="ev-n1", title="vector 召回", channels=["vector"],
        ),
        _make_evidence(
            evidence_id="ev-n2", title="metadata 召回", channels=["metadata"],
        ),
    ]
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with _patch_service(sources), _patch_compatibility_adapter():
            resp = await ac.post(
                "/api/v1/ai/chat/evidence",
                json={"message": "智能制造专业的课程"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    ids = [s["evidence_id"] for s in data["sources"]]
    # keyword 通道失败不应拖垮整体：vector + metadata 召回结果都在 sources 里
    assert "ev-n1" in ids
    assert "ev-n2" in ids


# --- AC-8: sources schema 完整 (TD-048: EvidenceItem 字段) ------------------


@pytest.mark.asyncio
async def test_ai_chat_sources_have_required_fields():
    sources = [
        _make_evidence(
            evidence_id="ev-1",
            title="title-n1",
            snippet="d",
            score=0.9,
            channels=["vector"],
        ),
    ]
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with _patch_service(sources), _patch_compatibility_adapter():
            resp = await ac.post(
                "/api/v1/ai/chat/evidence",
                json={"message": "智能制造"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["sources"], list)
    assert len(data["sources"]) == 1
    src = data["sources"][0]
    # EvidenceItem 必含字段（REQ-010 统一证据 DTO）
    for field in ("evidence_id", "source_type", "title", "score", "channels"):
        assert field in src, f"sources[0] missing {field}"


# --- AC-9: fusion dedup (TD-048: 走 evidence 端点) --------------------------


@pytest.mark.asyncio
async def test_ai_chat_fuses_duplicate_node_id_across_channels():
    """Same evidence (by evidence_id) hit by multiple channels collapses to a
    single sources entry; multi-channel attribution is preserved in `channels`.
    """
    sources = [
        _make_evidence(
            evidence_id="ev-shared", title="shared-title",
            channels=["vector", "keyword"],
        ),
        _make_evidence(
            evidence_id="ev-kw-only", title="kw",
            channels=["keyword"],
        ),
    ]
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with _patch_service(sources), _patch_compatibility_adapter():
            resp = await ac.post(
                "/api/v1/ai/chat/evidence",
                json={"message": "智能制造专业的知识点"},
            )

    assert resp.status_code == 200
    data = resp.json()
    ids = [s["evidence_id"] for s in data["sources"]]
    assert ids.count("ev-shared") == 1, f"expected dedup, got {ids}"
    assert "ev-kw-only" in ids
    shared_src = next(s for s in data["sources"] if s["evidence_id"] == "ev-shared")
    assert set(shared_src["channels"]) == {"vector", "keyword"}
