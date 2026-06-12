"""`EvidenceItem` — REQ-010 统一证据模型。

AI Chat 多源召回（chunk vector / chunk keyword / knowledge node / metadata
filter）统一为 `EvidenceItem` 后再交给 fusion + LLM 编排。每条 evidence 必须
能从 `source_type` + 唯一主键派生稳定的 `evidence_id`，便于：

- fusion 去重：多条通道命中同一 chunk 时合并成一条；
- sources shape 校验：前端 evidence card 按 `evidence_id` 渲染；
- e2e 断言：基于 `evidence_id` 验证 LLM 回答里的 `[1] / [2]` 与 sources
  列表一一对应。

`evidence_id` 派生规则：

- `chunk`: `chunk:{file_id}:{chunk_id}`
- `knowledge_node`: `knowledge_node:{file_id}:{node_id}`
- `knowledge_edge`: `knowledge_edge:{edge_id}`
- `structured_field`: `structured_field:{file_id}:{structured_path}`

派生在 `__init__` / `model_post_init` 中执行；调用方传 `evidence_id=""` 即
触发自动派生（unit test 覆盖），传固定字符串则原样使用（允许未来基于业务
逻辑构造非派生 id）。
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

SourceType = Literal["chunk", "knowledge_node", "knowledge_edge", "structured_field"]


def _derive_evidence_id(
    source_type: str,
    file_id: uuid.UUID | None,
    chunk_id: uuid.UUID | None,
    node_id: uuid.UUID | None,
    edge_id: uuid.UUID | None,
    structured_path: str | None,
) -> str:
    if source_type == "chunk":
        if chunk_id is None:
            raise ValueError("chunk evidence requires chunk_id")
        return f"chunk:{file_id}:{chunk_id}"
    if source_type == "knowledge_node":
        if node_id is None:
            raise ValueError("knowledge_node evidence requires node_id")
        return f"knowledge_node:{file_id}:{node_id}"
    if source_type == "knowledge_edge":
        if edge_id is None:
            raise ValueError("knowledge_edge evidence requires edge_id")
        return f"knowledge_edge:{edge_id}"
    if source_type == "structured_field":
        if not structured_path:
            raise ValueError("structured_field evidence requires structured_path")
        return f"structured_field:{file_id}:{structured_path}"
    raise ValueError(f"unknown source_type: {source_type!r}")


class EvidenceItem(BaseModel):
    """REQ-010 unified evidence DTO.

    Pydantic BaseModel — 与 RecallResult 风格保持一致；模型层不动 RecallResult
    （保留 node-shaped 旧契约），新 RAG 编排全部走 EvidenceItem。
    """

    evidence_id: str = ""
    source_type: SourceType
    file_id: uuid.UUID | None = None
    chunk_id: uuid.UUID | None = None
    node_id: uuid.UUID | None = None
    edge_id: uuid.UUID | None = None
    structured_path: str | None = None
    title: str
    content: str = ""
    snippet: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None
    channels: list[str] = Field(default_factory=list)
    # TD-050: 仅 source_type=="knowledge_node" 时填充；与 chunk_id 同值
    # (chunk_id 承载该 node 的 source_chunk_id)。其他 source_type 时为 None。
    # 不参与 evidence_id 派生（详见 spec §3.1 末尾「AC-3 解读说明」）。
    source_chunk_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _ensure_evidence_id(self) -> EvidenceItem:
        if self.evidence_id:
            return self
        self.evidence_id = _derive_evidence_id(
            self.source_type,
            self.file_id,
            self.chunk_id,
            self.node_id,
            self.edge_id,
            self.structured_path,
        )
        return self


class DocumentSourceChunk(BaseModel):
    """A matched chunk shown under a document-level citation source."""

    evidence_index: int
    chunk_id: uuid.UUID | None = None
    chunk_index: int | None = None
    title: str | None = None
    snippet: str = ""
    score: float | None = None
    channels: list[str] = Field(default_factory=list)


class DocumentSource(BaseModel):
    """Document-level reference source for AI Chat.

    `EvidenceItem[]` remains the inline citation sequence. `DocumentSource[]`
    groups those evidence items by file so the UI can display references as
    documents, with matched chunks nested underneath.
    """

    file_id: uuid.UUID
    title: str
    file_name: str | None = None
    doc_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    best_score: float | None = None
    channels: list[str] = Field(default_factory=list)
    evidence_indices: list[int] = Field(default_factory=list)
    chunks: list[DocumentSourceChunk] = Field(default_factory=list)
