"""`/knowledge/graph/retrieve` 端点 — REQ-010 Slice 4 业务代码同步迁到 GraphRetriever 接口。

P1 阶段：MCP / 第三方工具按 GraphRetriever 抽象调用，新写的检索入口走此
端点；旧的 `/knowledge/search` 端点行为保留（直接 SQL repository），以
避免破坏现有测试。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.knowledge.application.ner_service import RuleBasedNER
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.contexts.knowledge.infrastructure.retrievers.pg_graph_retriever import (
    PgGraphRetriever,
)
from app.shared.infrastructure.database import get_session
from app.shared.infrastructure.tenant_context import get_tenant_id

logger = logging.getLogger(__name__)
router = APIRouter()

_graph_retriever = PgGraphRetriever()
_ner = RuleBasedNER()


class GraphRetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


class GraphRetrieveResponse(BaseModel):
    items: list[EvidenceItem]


@router.post("/graph/retrieve", response_model=GraphRetrieveResponse)
async def graph_retrieve(
    data: GraphRetrieveRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _current_user: dict = Depends(get_current_user),  # noqa: B008
):
    """REQ-010 Slice 4 — knowledge graph 检索入口走 GraphRetriever 接口。

    返回 `EvidenceItem[]`（每条 source_type="knowledge_node"）。MCP / 第三方
    工具按 RAG 证据模型消费；KG 视图前端仍走旧 `/knowledge/search` 端点。
    """
    tid = str(get_tenant_id())
    ner_result = await _ner.extract(data.query)
    items = await _graph_retriever.retrieve(
        data.query,
        ner_result,
        tid,
        session,
        top_k=data.top_k,
    )
    return GraphRetrieveResponse(items=items)
