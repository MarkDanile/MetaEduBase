"""Tests for TD-085 Slice B — ``knowledge/application/ai_chat_diagnostics.py``.

判别点（锁定拆分前 ``AIChatService`` trace / 诊断装配行为）：

1. ``trace_evidence``：index 从 1 起、UUID → str 转换、snippet 240 截断、
   channels/metadata 拷贝语义。
2. ``trace_packed_blocks``：chars 为未截断长度、content 500 截断、
   chunk_ids str 转换。
3. ``enrich_fusion_diagnostics``：RRF 属性（k / channel_weights）有/无两态、
   channel_ranks 1-based、fusion_scores 映射、fusion_method 类名。
4. ``build_chat_diagnostics``：retrieval_topn / fusion_topn / packed_blocks /
   prompt_preview 1200 截断 / query_understanding 有无两态。
5. ``AIChatDiagnostics.model_config["extra"] == "forbid"`` 保持。
6. ``AIChatService._enrich_fusion_diagnostics`` 兼容方法仍可用且委托到
   新模块（同一片 packed 对象被富化返回）。

不连接 DB / 真实 LLM。
"""

from __future__ import annotations

import uuid

import pytest

from app.contexts.knowledge.application.ai_chat_diagnostics import (
    AIChatDiagnostics,
    build_chat_diagnostics,
    enrich_fusion_diagnostics,
    trace_evidence,
    trace_packed_blocks,
)
from app.contexts.knowledge.application.ai_chat_service import AIChatService
from app.contexts.knowledge.application.context_packer import (
    PackedContext,
    PackedContextBlock,
    PackedContextDiagnostics,
)
from app.contexts.knowledge.application.retrievers_fake import (
    FakeChunkRetriever,
    FakeGraphRetriever,
    FakeMetadataFilter,
)
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.shared.domain.ner_pipeline import NERResult


def _evidence(**overrides) -> EvidenceItem:
    defaults = dict(
        evidence_id="ev-1",
        source_type="chunk",
        title="标题",
        content="正文",
        snippet="摘要",
        score=0.9,
        channels=["vector"],
        metadata={"k": "v"},
    )
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def _packed(blocks, evidence) -> PackedContext:
    return PackedContext(
        blocks=blocks,
        evidence=evidence,
        diagnostics=PackedContextDiagnostics(fused_count=len(evidence)),
    )


# --- 1. trace_evidence ------------------------------------------------------


def test_trace_evidence_maps_fields_and_truncates_snippet():
    fid, cid = uuid.uuid4(), uuid.uuid4()
    item = _evidence(
        file_id=fid,
        chunk_id=cid,
        source_chunk_id=uuid.uuid4(),
        snippet="x" * 300,
    )
    traced = trace_evidence([item])
    assert len(traced) == 1
    t = traced[0]
    assert t.index == 1
    assert t.file_id == str(fid)
    assert t.chunk_id == str(cid)
    assert t.source_chunk_id == str(item.source_chunk_id)
    assert len(t.snippet) == 240
    assert t.channels == ["vector"]
    assert t.metadata == {"k": "v"}
    # 拷贝语义：修改原 metadata 不影响 trace
    item.metadata["k"] = "changed"
    assert t.metadata == {"k": "v"}


def test_trace_evidence_snippet_falls_back_to_content():
    item = _evidence(snippet="", content="c" * 300)
    traced = trace_evidence([item])
    assert len(traced[0].snippet) == 240


# --- 2. trace_packed_blocks -------------------------------------------------


def test_trace_packed_blocks_chars_is_untruncated_length():
    block = PackedContextBlock(
        evidence_index=1,
        source_type="chunk",
        title="t",
        content="y" * 600,
        expansion_type="hit",
    )
    traced = trace_packed_blocks(_packed([block], []))
    assert traced[0].chars == 600
    assert len(traced[0].content) == 500


# --- 3. enrich_fusion_diagnostics -------------------------------------------


class _RRFFusionFake:
    k = 60
    channel_weights = {"vector": 0.7, "keyword": 0.3}


class _PlainFusion:
    pass


def test_enrich_fusion_diagnostics_with_rrf_attributes():
    ev = _evidence(evidence_id="e1")
    packed = _packed([], [ev])
    out = enrich_fusion_diagnostics(
        _RRFFusionFake(), packed, {"vector": [ev], "keyword": [ev]}, [ev]
    )
    assert out is packed
    assert packed.diagnostics.fusion_method == "_RRFFusionFake"
    assert packed.diagnostics.rrf_k == 60
    assert packed.diagnostics.rrf_weights_used == {"vector": 0.7, "keyword": 0.3}
    assert packed.diagnostics.channel_ranks == {
        "vector": {"e1": 1},
        "keyword": {"e1": 1},
    }
    assert packed.diagnostics.fusion_scores == {"e1": 0.9}


def test_enrich_fusion_diagnostics_without_rrf_attributes():
    packed = _packed([], [])
    enrich_fusion_diagnostics(_PlainFusion(), packed, {}, [])
    assert packed.diagnostics.fusion_method == "_PlainFusion"
    assert packed.diagnostics.rrf_k is None
    # 默认值为空 dict（PackedContextDiagnostics 声明），无 channel_weights 时保持默认
    assert packed.diagnostics.rrf_weights_used == {}


# --- 4. build_chat_diagnostics ----------------------------------------------


def test_build_chat_diagnostics_assembles_all_sections():
    ev = _evidence()
    block = PackedContextBlock(
        evidence_index=1, source_type="chunk", title="t",
        content="c", expansion_type="hit",
    )
    packed = _packed([block], [ev])
    ner = NERResult(domains=["d"], levels=[], raw_entities=[])
    diag = build_chat_diagnostics(
        query="问",
        channel_results={"vector": [ev]},
        fused=[ev],
        packed=packed,
        context_text="z" * 1500,
        ner_result=ner,
    )
    assert diag.query == "问"
    assert list(diag.retrieval_topn.keys()) == ["vector"]
    assert len(diag.fusion_topn) == 1
    assert len(diag.packed_blocks) == 1
    assert len(diag.prompt_preview) == 1200
    assert diag.packed == packed.diagnostics.model_dump(mode="json")
    # 无 query_understanding 属性 → None
    assert diag.query_understanding is None
    assert diag.tool_calls is None


def test_build_chat_diagnostics_includes_query_understanding_when_present():
    class _QU:
        method = "llm"
        confidence = 0.8
        normalized_query = "nq"
        core_terms = ["a"]
        expanded_terms = ["b"]
        entities = []
        filters = {}

    # NERResult 不携带 query_understanding（该属性由
    # HybridQueryUnderstandingResult 子类注入）；用带属性的轻量对象验证
    # duck-typed 读取路径。
    class _NerLike:
        domains: list = []
        levels: list = []
        raw_entities: list = []
        query_understanding = _QU()
        trigger_reason = "rule_miss_and_long_query"

    packed = _packed([], [])
    diag = build_chat_diagnostics(
        query="q",
        channel_results={},
        fused=[],
        packed=packed,
        context_text="",
        ner_result=_NerLike(),  # type: ignore[arg-type]
    )
    assert diag.query_understanding == {
        "method": "llm",
        "confidence": 0.8,
        "normalized_query": "nq",
        "core_terms": ["a"],
        "expanded_terms": ["b"],
        "entities": [],
        "filters": {},
        "trigger_reason": "rule_miss_and_long_query",
    }


# --- 5. DTO 契约 ------------------------------------------------------------


def test_diagnostics_model_forbids_extra_fields():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AIChatDiagnostics(query="q", unknown_field=1)  # type: ignore[call-arg]


# --- 6. 服务兼容方法委托 ----------------------------------------------------


@pytest.mark.asyncio
async def test_service_enrich_method_delegates_to_diagnostics_module():
    service = AIChatService(
        chunk_retriever=FakeChunkRetriever(),
        graph_retriever=FakeGraphRetriever(),
        metadata_filter=FakeMetadataFilter(),
        evidence_fusion=_RRFFusionFake(),
    )
    ev = _evidence(evidence_id="e9")
    packed = _packed([], [ev])
    out = service._enrich_fusion_diagnostics(packed, {"vector": [ev]}, [ev])
    assert out is packed
    assert packed.diagnostics.fusion_method == "_RRFFusionFake"
    assert packed.diagnostics.channel_ranks == {"vector": {"e9": 1}}
