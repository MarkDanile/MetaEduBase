from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

from app.contexts.knowledge.application.ai_chat_service import AIChatService
from app.contexts.knowledge.application.context_packer import ContextPacker
from app.contexts.knowledge.application.evidence_fusion import RRFFusion
from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.contexts.knowledge.interfaces.api.ai_router import (
    _build_evidence_service,
    _get_rrf_channel_weights,
    _RRF_DEFAULT_WEIGHTS,
)


def test_default_evidence_service_uses_rrf_and_context_packer() -> None:
    service = _build_evidence_service(
        MagicMock(),
        "11111111-1111-1111-1111-111111111111",
    )

    assert isinstance(service.evidence_fusion, RRFFusion)
    assert isinstance(service._context_packer, ContextPacker)


def test_rrf_weights_defaults() -> None:
    """No RRF_CHANNEL_WEIGHTS set → defaults are used."""
    for key in ["RRF_CHANNEL_WEIGHTS"]:
        if key in os.environ:
            del os.environ[key]
    weights = _get_rrf_channel_weights()
    assert weights == _RRF_DEFAULT_WEIGHTS


def test_rrf_weights_from_env_var() -> None:
    """Valid JSON env var overrides defaults partially."""
    os.environ["RRF_CHANNEL_WEIGHTS"] = '{"vector":2.0,"graph_node":0.1}'
    try:
        weights = _get_rrf_channel_weights()
        assert weights["vector"] == 2.0
        assert weights["keyword"] == 1.0  # default preserved
        assert weights["graph_node"] == 0.1
    finally:
        del os.environ["RRF_CHANNEL_WEIGHTS"]


def test_rrf_weights_invalid_json_falls_back() -> None:
    """Invalid JSON env var → defaults are used."""
    os.environ["RRF_CHANNEL_WEIGHTS"] = "not-valid-json{"
    try:
        weights = _get_rrf_channel_weights()
        assert weights == _RRF_DEFAULT_WEIGHTS
    finally:
        del os.environ["RRF_CHANNEL_WEIGHTS"]


def test_build_evidence_service_injects_weights() -> None:
    """Service is built with weighted RRF from environment."""
    os.environ["RRF_CHANNEL_WEIGHTS"] = '{"keyword":3.0}'
    try:
        service = _build_evidence_service(
            MagicMock(),
            "11111111-1111-1111-1111-111111111111",
        )
        assert isinstance(service.evidence_fusion, RRFFusion)
        assert service.evidence_fusion.channel_weights["keyword"] == 3.0
        assert service.evidence_fusion.channel_weights["vector"] == 1.0  # default
    finally:
        del os.environ["RRF_CHANNEL_WEIGHTS"]


def test_enrich_fusion_diagnostics_populates_rrf_fields() -> None:
    """REQ-017 Slice 2: _enrich_fusion_diagnostics fills fusion diagnostics."""
    fid = uuid.uuid4()
    cid_a = uuid.uuid4()
    cid_b = uuid.uuid4()

    fused = [
        EvidenceItem(
            evidence_id="chunk:a", source_type="chunk", file_id=fid,
            chunk_id=cid_a, title="A", content="content a", score=0.9,
            channels=["vector", "keyword"],
        ),
        EvidenceItem(
            evidence_id="chunk:b", source_type="chunk", file_id=fid,
            chunk_id=cid_b, title="B", content="content b", score=0.5,
            channels=["vector"],
        ),
    ]
    channel_results = {
        "vector": [
            EvidenceItem(
                evidence_id="chunk:a", source_type="chunk", file_id=fid,
                chunk_id=cid_a, title="A", content="content a", score=0.9,
                channels=[],
            ),
            EvidenceItem(
                evidence_id="chunk:b", source_type="chunk", file_id=fid,
                chunk_id=cid_b, title="B", content="content b", score=0.5,
                channels=[],
            ),
        ],
        "keyword": [
            EvidenceItem(
                evidence_id="chunk:a", source_type="chunk", file_id=fid,
                chunk_id=cid_a, title="A", content="content a", score=0.8,
                channels=[],
            ),
        ],
    }

    fusion = RRFFusion(k=60, channel_weights={"vector": 1.0, "keyword": 2.0})
    service = AIChatService(
        chunk_retriever=MagicMock(),
        graph_retriever=MagicMock(),
        metadata_filter=MagicMock(),
        evidence_fusion=fusion,
    )

    from app.contexts.knowledge.application.context_packer import (
        PackedContext,
        PackedContextBlock,
        PackedContextDiagnostics,
    )

    packed = PackedContext(
        blocks=[
            PackedContextBlock(
                evidence_index=1, file_id=fid,
                chunk_ids=[cid_a], source_type="chunk",
                title="A", content="content a",
                channels=["vector", "keyword"],
                score=0.9, is_toc_like=False, expansion_type="hit",
            ),
        ],
        evidence=fused,
        diagnostics=PackedContextDiagnostics(fused_count=2),
    )

    result = service._enrich_fusion_diagnostics(packed, channel_results, fused)

    assert result.diagnostics.fusion_method == "RRFFusion"
    assert result.diagnostics.rrf_k == 60
    assert result.diagnostics.rrf_weights_used == {"vector": 1.0, "keyword": 2.0}
    assert result.diagnostics.fusion_scores == {"chunk:a": 0.9, "chunk:b": 0.5}
    assert result.diagnostics.channel_ranks["vector"] == {"chunk:a": 1, "chunk:b": 2}
    assert result.diagnostics.channel_ranks["keyword"] == {"chunk:a": 1}
