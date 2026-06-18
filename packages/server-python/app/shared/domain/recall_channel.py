from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.ner_pipeline import NERResult


class RecallResult(BaseModel):
    node_id: str
    title: str
    description: str | None = None
    domain: str | None = None
    level: str | None = None
    score: float | None = None
    channel: str = ""
    path: str | None = None
    # TD-050: knowledge_nodes.source_file_id / source_chunk_id 透传字段
    # 始终 optional (None)；当前仅在 `node` 类证据时为非 None
    # (随 P1 RecallChannel 实现演进)。`RecallChannel` Protocol 形参不变。
    source_file_id: uuid.UUID | None = None
    source_chunk_id: uuid.UUID | None = None
    # REQ-018: edge recall — edge id when this result came from a knowledge edge
    edge_id: uuid.UUID | None = None


@runtime_checkable
class RecallChannel(Protocol):
    """召回通道契约。

    实现者必须严格按本 Protocol 形参命名（含 ``session``），下游契约测试
    （``tests/contexts/ai/test_recall_channels_contract.py``）用 ``set(sig.parameters)``
    与本 Protocol 严格对齐（不依赖下划线前缀做兼容）。

    ``session`` 由调用方注入（参见 ``app/contexts/knowledge/interfaces/api/ai_router.py``），
    实现者不要再在内部 ``async_sessionmaker()`` 重新打开连接，以保持与现有 RAG
    链路（同一 session 内可读取知识图谱或文档 chunks 上下文）的事务一致性。
    """

    @property
    def name(self) -> str: ...

    async def recall(
        self,
        query: str,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        top_k: int = 5,
    ) -> list[RecallResult]: ...
