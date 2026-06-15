from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.contexts.knowledge.domain.entities.knowledge_node import KnowledgeDomain, KnowledgeLevel


class KnowledgeNodeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    domain: KnowledgeDomain
    level: KnowledgeLevel
    parent_id: uuid.UUID | None = None
    tags: list[str] = []
    metadata: dict[str, Any] = {}


class KnowledgeNodeUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class KnowledgeNodeDTO(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    description: str | None
    domain: KnowledgeDomain
    level: KnowledgeLevel
    parent_id: uuid.UUID | None
    path: str | None
    tags: list[str]
    metadata: dict[str, Any]

    model_config = {"from_attributes": True}


class KnowledgeSearchDTO(BaseModel):
    query: str
    domain: KnowledgeDomain | None = None
    top_k: int = Field(default=5, ge=1, le=50)
    search_mode: str = "hybrid"


class SearchResultDTO(BaseModel):
    node: KnowledgeNodeDTO
    score: float


class KnowledgeEdgeDTO(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    relation_type: str
    weight: float
    metadata: dict[str, Any]


class KgBundleDTO(BaseModel):
    """BUG-006 #4: 原子返回某文件的 KG nodes + edges, 保证 edges 的
    source_id / target_id 都在 nodes 列表中 (双端 IN 过滤 SQL 实现)."""

    nodes: list[KnowledgeNodeDTO]
    edges: list[KnowledgeEdgeDTO]
