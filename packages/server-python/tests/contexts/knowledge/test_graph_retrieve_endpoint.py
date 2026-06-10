"""`POST /api/v1/knowledge/graph/retrieve` 端点测试 — Slice 4。

REQ-010 AC-13：MCP / 业务代码同步迁到 GraphRetriever 接口。
测试用 module-level singleton 替换 PgGraphRetriever 实例，验证端点
行为不依赖具体实现（fake retriever 验证编排）。

覆盖：
- 端点接受 query + top_k → 调 GraphRetriever.retrieve，返回 EvidenceItem[]
- 端点 shape 正确（items 字段）
- fake retriever 调用记录 tenant_id / query / top_k 正确传递
- 无候选时返回空 items
- top_k 越界被 Pydantic 拒绝
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest_asyncio

from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.main import app


class _FakeGraphRetriever:
    """Stand-in for PgGraphRetriever, captures call args."""

    name = "fake-graph-endpoint"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.return_value: list[EvidenceItem] = []

    async def retrieve(
        self,
        query: str,
        ner_result: Any,
        tenant_id: str,
        session: Any,
        *,
        top_k: int = 5,
    ) -> list[EvidenceItem]:
        self.calls.append(
            {
                "query": query,
                "ner_domains": list(ner_result.domains),
                "tenant_id": tenant_id,
                "top_k": top_k,
            }
        )
        return list(self.return_value)[:top_k]


@pytest_asyncio.fixture
async def fake_retriever() -> _FakeGraphRetriever:
    fake = _FakeGraphRetriever()
    import app.contexts.knowledge.interfaces.api.graph_retrieve_router as mod

    original = mod._graph_retriever
    mod._graph_retriever = fake  # type: ignore[assignment]
    try:
        yield fake
    finally:
        mod._graph_retriever = original  # type: ignore[assignment]


@pytest_asyncio.fixture
async def http_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client


async def test_graph_retrieve_endpoint_uses_graph_retriever(
    http_client, fake_retriever, auth_token
):
    """AC-13: 端点调 GraphRetriever 接口；不依赖具体实现。"""
    fid = uuid.uuid4()
    nid = uuid.uuid4()
    fake_retriever.return_value = [
        EvidenceItem(
            evidence_id="",
            source_type="knowledge_node",
            file_id=fid,
            node_id=nid,
            title="智能制造",
            content="专业方向描述",
            score=0.85,
            channels=["vector"],
        )
    ]

    resp = await http_client.post(
        "/api/v1/knowledge/graph/retrieve",
        json={"query": "智能制造", "top_k": 3},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    assert len(body["items"]) == 1
    assert body["items"][0]["source_type"] == "knowledge_node"
    assert body["items"][0]["title"] == "智能制造"
    # fake retriever 收到了正确参数
    assert len(fake_retriever.calls) == 1
    call = fake_retriever.calls[0]
    assert call["query"] == "智能制造"
    assert call["top_k"] == 3


async def test_graph_retrieve_endpoint_returns_empty_on_no_results(
    http_client, fake_retriever, auth_token
):
    """AC-13 fallback: 无候选时返回空 items 列表。"""
    fake_retriever.return_value = []
    resp = await http_client.post(
        "/api/v1/knowledge/graph/retrieve",
        json={"query": "niche question", "top_k": 5},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


async def test_graph_retrieve_endpoint_validates_top_k(
    http_client, fake_retriever, auth_token
):
    """Pydantic Field(ge=1, le=50) 验证 top_k 范围。"""
    resp = await http_client.post(
        "/api/v1/knowledge/graph/retrieve",
        json={"query": "test", "top_k": 0},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 422

    resp = await http_client.post(
        "/api/v1/knowledge/graph/retrieve",
        json={"query": "test", "top_k": 100},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 422
