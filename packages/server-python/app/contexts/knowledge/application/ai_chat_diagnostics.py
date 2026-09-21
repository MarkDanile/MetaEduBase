"""TD-085 Slice B — AI Chat Diagnostics（knowledge 保留，spec ADR-085-2）。

从 ``ai_chat_service.py`` 拆出的诊断职责：

- trace DTO：``RetrievalTraceItem`` / ``PackedBlockTraceItem`` /
  ``AIChatDiagnostics``（逐字迁移，字段与 ``extra="forbid"`` 不变）。
- trace 构造函数：``trace_evidence`` / ``trace_packed_blocks``。
- RRF fusion 诊断富化：``enrich_fusion_diagnostics``。
- 装配入口：``build_chat_diagnostics`` 汇总 retrieval_topn / fusion_topn /
  packed_blocks / prompt_preview / packed diagnostics / query_understanding。

行为保持：所有函数体从 ``AIChatService`` 静态/实例方法逐字迁移；既有调用
路径通过 ``AIChatService`` 上的兼容方法继续可用。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.contexts.knowledge.application.context_packer import PackedContext
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.shared.domain.ner_pipeline import NERResult

logger = logging.getLogger(__name__)


class RetrievalTraceItem(BaseModel):
    index: int
    evidence_id: str
    source_type: str
    title: str
    file_id: str | None = None
    chunk_id: str | None = None
    source_chunk_id: str | None = None
    score: float | None = None
    channels: list[str] = Field(default_factory=list)
    snippet: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PackedBlockTraceItem(BaseModel):
    evidence_index: int
    file_id: str | None = None
    chunk_ids: list[str] = Field(default_factory=list)
    source_type: str
    title: str
    section_title: str | None = None
    section_path: str | None = None
    chars: int
    content: str
    channels: list[str] = Field(default_factory=list)
    score: float | None = None
    is_toc_like: bool = False
    expansion_type: str


class AIChatDiagnostics(BaseModel):
    query: str
    retrieval_topn: dict[str, list[RetrievalTraceItem]] = Field(default_factory=dict)
    fusion_topn: list[RetrievalTraceItem] = Field(default_factory=list)
    packed_blocks: list[PackedBlockTraceItem] = Field(default_factory=list)
    prompt_preview: str = ""
    packed: dict[str, Any] = Field(default_factory=dict)
    query_understanding: dict | None = None  # REQ-016 Slice 2
    # REQ-052 Task 7 — tool calling trace (None / list of tool-call summaries).
    tool_calls: list[dict] | None = None

    model_config = {"extra": "forbid"}


def trace_evidence(items: list[EvidenceItem]) -> list[RetrievalTraceItem]:
    traced: list[RetrievalTraceItem] = []
    for index, item in enumerate(items, start=1):
        traced.append(
            RetrievalTraceItem(
                index=index,
                evidence_id=item.evidence_id,
                source_type=item.source_type,
                title=item.title,
                file_id=str(item.file_id) if item.file_id else None,
                chunk_id=str(item.chunk_id) if item.chunk_id else None,
                source_chunk_id=(
                    str(item.source_chunk_id) if item.source_chunk_id else None
                ),
                score=item.score,
                channels=list(item.channels or []),
                snippet=(item.snippet or item.content or "")[:240],
                metadata=dict(item.metadata or {}),
            )
        )
    return traced


def trace_packed_blocks(packed: PackedContext) -> list[PackedBlockTraceItem]:
    traced: list[PackedBlockTraceItem] = []
    for block in packed.blocks:
        traced.append(
            PackedBlockTraceItem(
                evidence_index=block.evidence_index,
                file_id=str(block.file_id) if block.file_id else None,
                chunk_ids=[str(cid) for cid in block.chunk_ids],
                source_type=block.source_type,
                title=block.title,
                section_title=block.section_title,
                section_path=block.section_path,
                chars=len(block.content),
                content=block.content[:500],
                channels=list(block.channels or []),
                score=block.score,
                is_toc_like=block.is_toc_like,
                expansion_type=block.expansion_type,
            )
        )
    return traced


def enrich_fusion_diagnostics(
    evidence_fusion: Any,
    packed: PackedContext,
    channel_results: dict[str, list[EvidenceItem]],
    fused: list[EvidenceItem],
) -> PackedContext:
    """REQ-017 Slice 2: populate RRF fusion diagnostics.

    Fills fusion_method / rrf_k / rrf_weights_used / fusion_scores /
    channel_ranks on packed.diagnostics.
    """
    fusion = evidence_fusion
    diag = packed.diagnostics

    # Identify fusion type
    fusion_name = fusion.__class__.__name__
    diag.fusion_method = fusion_name

    # RRF-specific fields
    if hasattr(fusion, "k"):
        diag.rrf_k = fusion.k
    if hasattr(fusion, "channel_weights"):
        diag.rrf_weights_used = dict(fusion.channel_weights or {})

    # channel_ranks: channel -> evidence_id -> rank (1-based)
    channel_ranks: dict[str, dict[str, int]] = {}
    for ch, items in channel_results.items():
        channel_ranks[ch] = {
            it.evidence_id: rank + 1 for rank, it in enumerate(items)
        }
    diag.channel_ranks = channel_ranks

    # fusion_scores: evidence_id -> score from fusion output
    # NOTE (Slice B): verbatim-moved legacy line. ``EvidenceItem.score`` is
    # ``float | None`` while ``PackedContextDiagnostics.fusion_scores`` is
    # declared ``dict[str, float]`` — this tension existed in
    # ``ai_chat_service.py`` before the split (mypy baseline
    # ``ai_chat_service.py::misc``); resolving the declaration is out of
    # Slice B behavior-preserving scope.
    diag.fusion_scores = {e.evidence_id: e.score for e in fused}  # type: ignore[misc]

    return packed


def log_retrieval_summary(
    message: str,
    ner_result: NERResult,
    channel_results: dict[str, list[EvidenceItem]],
    fused: list[EvidenceItem],
) -> None:
    """REQ-012 diagnostic log: channel labels may be vector/keyword/graph,
    so count source types after grouping to keep the log faithful."""
    all_channel_items = [
        item
        for items in channel_results.values()
        for item in items
    ]
    chunk_count = len(
        {
            item.evidence_id
            for item in all_channel_items
            if item.source_type == "chunk"
        }
    )
    graph_count = len(
        {
            item.evidence_id
            for item in all_channel_items
            if item.source_type == "knowledge_node"
        }
    )
    logger.info(
        "ai_chat_service: query=%r ner_domains=%r ner_levels=%r "
        "chunk=%d graph=%d fused=%d",
        message[:120],
        ner_result.domains,
        ner_result.levels,
        chunk_count,
        graph_count,
        len(fused),
    )


def build_chat_diagnostics(
    *,
    query: str,
    channel_results: dict[str, list[EvidenceItem]],
    fused: list[EvidenceItem],
    packed: PackedContext,
    context_text: str,
    ner_result: NERResult,
) -> AIChatDiagnostics:
    """装配 AIChatDiagnostics（含 REQ-016 query_understanding trace）。"""
    retrieval_topn = {
        channel: trace_evidence(items) for channel, items in channel_results.items()
    }
    # REQ-016 Slice 2: include query_understanding trace when available
    qu = getattr(ner_result, "query_understanding", None)
    query_understanding_diag: dict[str, Any] | None = None
    if qu is not None:
        query_understanding_diag = {
            "method": qu.method,
            "confidence": qu.confidence,
            "normalized_query": qu.normalized_query,
            "core_terms": qu.core_terms,
            "expanded_terms": qu.expanded_terms,
            "entities": qu.entities,
            "filters": qu.filters,
            "trigger_reason": getattr(ner_result, "trigger_reason", None),
        }
    diagnostics_model = AIChatDiagnostics(
        query=query,
        retrieval_topn=retrieval_topn,
        fusion_topn=trace_evidence(fused),
        packed_blocks=trace_packed_blocks(packed),
        prompt_preview=context_text[:1200],
        packed=packed.diagnostics.model_dump(mode="json"),
        query_understanding=query_understanding_diag,
    )
    logger.info(
        "ai_chat_trace: %s",
        json.dumps(diagnostics_model.model_dump(mode="json"), ensure_ascii=False),
    )
    return diagnostics_model
