"""`EvidenceItem` unit tests.

REQ-010 Slice 1 — 统一证据模型。EvidenceItem 是 AI Chat 多源召回的统一
输出格式，覆盖 chunk / knowledge_node / knowledge_edge / structured_field
四种 source_type，每条 evidence 必须能从 `source_type` + `file_id` + 主键
派生稳定的 `evidence_id`，便于 fusion 去重、sources shape 校验和 e2e 断言。
"""

from __future__ import annotations

import uuid

import pytest

from app.contexts.knowledge.domain.evidence import EvidenceItem


def test_evidence_id_is_deterministic_for_chunk() -> None:
    fid = uuid.uuid4()
    cid = uuid.uuid4()
    a = EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=cid,
        title="section",
        content="hello world",
    )
    b = EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=cid,
        title="section",
        content="hello world",
    )
    assert a.evidence_id == b.evidence_id
    assert a.evidence_id == f"chunk:{fid}:{cid}"


def test_evidence_id_uses_node_id_for_knowledge_node() -> None:
    fid = uuid.uuid4()
    nid = uuid.uuid4()
    item = EvidenceItem(
        evidence_id="",
        source_type="knowledge_node",
        file_id=fid,
        node_id=nid,
        title="node title",
        content="desc",
    )
    assert item.evidence_id == f"knowledge_node:{fid}:{nid}"


def test_evidence_id_uses_edge_id_for_knowledge_edge() -> None:
    eid = uuid.uuid4()
    item = EvidenceItem(
        evidence_id="",
        source_type="knowledge_edge",
        edge_id=eid,
        title="edge",
    )
    assert item.evidence_id == f"knowledge_edge:{eid}"


def test_evidence_id_uses_structured_path() -> None:
    fid = uuid.uuid4()
    item = EvidenceItem(
        evidence_id="",
        source_type="structured_field",
        file_id=fid,
        structured_path="template.basic_info.course_name",
        title="course_name",
        content="智能制造",
    )
    assert item.evidence_id == (
        f"structured_field:{fid}:template.basic_info.course_name"
    )


def test_chunk_evidence_round_trip_preserves_score_and_channels() -> None:
    fid = uuid.uuid4()
    cid = uuid.uuid4()
    item = EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=cid,
        title="section A",
        content="content text",
        snippet="snippet text",
        score=0.87,
        channels=["vector", "keyword"],
        metadata={"section_path": "1.2"},
    )
    dumped = item.model_dump()
    restored = EvidenceItem(**dumped)
    assert restored.evidence_id == item.evidence_id
    assert restored.score == 0.87
    assert restored.channels == ["vector", "keyword"]
    assert restored.metadata == {"section_path": "1.2"}


def test_evidence_item_rejects_empty_source_identifiers() -> None:
    """An EvidenceItem must have at least one identifying id (chunk/node/edge/structured_path)."""
    with pytest.raises(ValueError):
        EvidenceItem(
            evidence_id="",
            source_type="chunk",
            file_id=None,
            chunk_id=None,
            title="orphan",
            content="",
        )


def test_evidence_item_default_channels_is_empty_list() -> None:
    fid = uuid.uuid4()
    cid = uuid.uuid4()
    item = EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=cid,
        title="t",
        content="c",
    )
    assert item.channels == []
    assert item.metadata == {}
