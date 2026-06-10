"""REQ-010 retriever adapter protocols.

`ChunkRetriever` / `GraphRetriever` / `MetadataFilter` 是 P1 AI Chat 编排层
依赖的 retriever 抽象。P1 由 PostgreSQL adapter 实现（详见
`app.contexts.knowledge.infrastructure.retrievers.*` 命名空间，本 Slice 不
引入）；P2 / P3 可替换为 Milvus / Qdrant / Elasticsearch / Neo4j / GraphRAG
而不改 AI Chat 业务编排。

每个 Protocol 的 `retrieve` / `filter` 方法形参命名严格 — 下游契约测试
`tests/contexts/knowledge/retrievers/test_*_contract.py` 用
`set(sig.parameters)` 与本 Protocol 对齐（参考 `RecallChannel` Protocol 风格，
见 TD-030）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.shared.domain.ner_pipeline import NERResult


@runtime_checkable
class ChunkRetriever(Protocol):
    """Chunk 级召回契约：返回 `EvidenceItem` 列表，`source_type="chunk"`。

    实现要点：
    - 同一 `(file_id, chunk_id)` 在多通道下应生成同一 `evidence_id`（由
      `EvidenceItem` 派生规则保证）。
    - `file_filter` 是可选预过滤（来自上游 MetadataFilter）；不传时按
      `tenant_id` 全量召回。
    """

    async def retrieve(
        self,
        query: str,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        *,
        top_k: int = 5,
        file_filter: list[str] | None = None,
    ) -> list[EvidenceItem]: ...


@runtime_checkable
class GraphRetriever(Protocol):
    """知识图谱召回契约：返回 `EvidenceItem` 列表，`source_type="knowledge_node"`。

    P1 阶段实现（PgGraphRetriever）应尽量回填 `source_chunk_id` /
    `source_file_id`，使前端能跳到文件 / chunk。
    """

    async def retrieve(
        self,
        query: str,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        *,
        top_k: int = 5,
    ) -> list[EvidenceItem]: ...


@runtime_checkable
class MetadataFilter(Protocol):
    """元数据过滤契约：读 `files.doc_type` / `tags` / `structured_data` 顶层 key。

    设计：filter 收 `candidates` (list[EvidenceItem]) + 读 files 元数据，对
    candidate 的 `file_id` 做打分加权或硬过滤。返回过滤后 EvidenceItem 列表
    （保持原顺序或重排均可，但需在协议文档中说明）。
    """

    async def filter(
        self,
        ner_result: NERResult,
        tenant_id: str,
        session: AsyncSession,
        candidates: list[EvidenceItem],
    ) -> list[EvidenceItem]: ...
