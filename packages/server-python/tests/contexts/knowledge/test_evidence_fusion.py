"""`EvidenceFusion` 契约 + 两种实现（SimpleFrequencyFusion / RRFFusion）单测。

REQ-010 Slice 1 — 融合排序只处理统一 evidence，不关心底层通道来自 PostgreSQL
还是 ES / Milvus / Neo4j。

- `SimpleFrequencyFusion` 沿用现有 `FrequencyFusion` 算法（按命中通道数 +
  best score 排序），但输入/输出升级到 `EvidenceItem`；
- `RRFFusion` 占位实现：按 `1 / (k + rank)` 聚合通道排名，k=60 默认。
  Slice 1 不接入 ai_router，只保证实现存在 + 排序可解释。
"""

from __future__ import annotations

import uuid

from app.contexts.knowledge.application.evidence_fusion import (
    EvidenceFusion,
    RRFFusion,
    SimpleFrequencyFusion,
)
from app.contexts.knowledge.domain.evidence import EvidenceItem


def _chunk(file_id: uuid.UUID, idx: int, score: float) -> EvidenceItem:
    return EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=file_id,
        chunk_id=uuid.uuid4(),
        title=f"chunk-{idx}",
        content=f"content-{idx}",
        score=score,
        channels=[],
    )


def _chunk_with_id(file_id: uuid.UUID, chunk_id: uuid.UUID, idx: int, score: float) -> EvidenceItem:
    return EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=file_id,
        chunk_id=chunk_id,
        title=f"chunk-{idx}",
        content=f"content-{idx}",
        score=score,
        channels=[],
    )


def test_simple_fusion_dedupes_evidence_across_channels() -> None:
    fid = uuid.uuid4()
    shared = uuid.uuid4()
    e_v = _chunk_with_id(fid, shared, 1, 0.9)
    e_k = _chunk_with_id(fid, shared, 1, 0.6)  # same evidence_id
    e_other = _chunk(fid, 2, 0.7)

    fused = SimpleFrequencyFusion().fuse(
        {
            "vector": [e_v],
            "keyword": [e_k],
            "metadata": [e_other],
        },
        top_k=10,
    )
    assert len(fused) == 2
    by_id = {e.evidence_id for e in fused}
    assert e_v.evidence_id in by_id
    assert e_other.evidence_id in by_id


def test_simple_fusion_aggregates_channels() -> None:
    fid = uuid.uuid4()
    shared = uuid.uuid4()
    e_v = _chunk_with_id(fid, shared, 1, 0.9)
    e_k = _chunk_with_id(fid, shared, 1, 0.6)  # same evidence_id

    fused = SimpleFrequencyFusion().fuse(
        {"vector": [e_v], "keyword": [e_k]},
        top_k=10,
    )
    assert len(fused) == 1
    assert sorted(fused[0].channels) == ["keyword", "vector"]


def test_simple_fusion_keeps_best_score() -> None:
    fid = uuid.uuid4()
    shared = uuid.uuid4()
    e_v = _chunk_with_id(fid, shared, 1, 0.9)
    e_k = _chunk_with_id(fid, shared, 1, 0.4)

    fused = SimpleFrequencyFusion().fuse(
        {"vector": [e_v], "keyword": [e_k]},
        top_k=10,
    )
    assert len(fused) == 1
    assert fused[0].score == 0.9


def test_simple_fusion_respects_top_k() -> None:
    fid = uuid.uuid4()
    results = {"vector": [_chunk(fid, i, 0.5 + i * 0.01) for i in range(5)]}
    fused = SimpleFrequencyFusion().fuse(results, top_k=2)
    assert len(fused) == 2


def test_simple_fusion_empty_input() -> None:
    fused = SimpleFrequencyFusion().fuse({}, top_k=10)
    assert fused == []


def test_rrf_fusion_ranks_by_aggregate_score() -> None:
    """RRF: 同一 evidence 在多个通道出现 → 累计 `1/(k+rank)` 分数。"""
    fid = uuid.uuid4()
    a_id = uuid.uuid4()
    b_id = uuid.uuid4()
    c_id = uuid.uuid4()
    a = _chunk_with_id(fid, a_id, 1, 0.9)
    b = _chunk_with_id(fid, b_id, 2, 0.8)
    c = _chunk_with_id(fid, c_id, 3, 0.7)

    # vector ranks: a > b > c
    # keyword ranks: b > a > c
    # a 和 b 都出现在 2 个通道，a 因为在 vector 排第 1，RRF 总分应大于 b
    fused = RRFFusion().fuse(
        {"vector": [a, b, c], "keyword": [b, a, c]},
        top_k=10,
    )
    assert len(fused) == 3
    # a and b tied on frequency (2 channels), but a's higher vector rank
    # pushes a ahead in RRF
    assert fused[0].evidence_id == a.evidence_id
    assert fused[1].evidence_id == b.evidence_id
    assert fused[2].evidence_id == c.evidence_id


def test_rrf_fusion_dedupes_by_evidence_id() -> None:
    fid = uuid.uuid4()
    shared = uuid.uuid4()
    e_v = _chunk_with_id(fid, shared, 1, 0.9)
    e_k = _chunk_with_id(fid, shared, 1, 0.6)  # same evidence_id

    fused = RRFFusion().fuse(
        {"vector": [e_v], "keyword": [e_k]},
        top_k=10,
    )
    assert len(fused) == 1
    assert sorted(fused[0].channels) == ["keyword", "vector"]


def test_evidence_fusion_protocol_accepts_both_implementations() -> None:
    """Both fusion classes are usable as EvidenceFusion Protocol."""
    f1: EvidenceFusion = SimpleFrequencyFusion()
    f2: EvidenceFusion = RRFFusion()
    assert callable(f1.fuse)
    assert callable(f2.fuse)
