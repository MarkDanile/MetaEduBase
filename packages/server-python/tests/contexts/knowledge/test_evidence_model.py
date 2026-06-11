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


# --- TD-050: EvidenceItem.source_chunk_id 字段访问与派生回归 ---


def test_evidence_item_knowledge_node_supports_source_chunk_id() -> None:
    """TD-050: knowledge_node 类型允许直接传 source_chunk_id 字段。

    与 chunk_id 同值；knowledge_node 类型 evidence 的"原文切片溯源"
    即 source_chunk_id。
    """
    fid = uuid.uuid4()
    nid = uuid.uuid4()
    scid = uuid.uuid4()
    item = EvidenceItem(
        evidence_id="",
        source_type="knowledge_node",
        file_id=fid,
        chunk_id=scid,
        source_chunk_id=scid,
        node_id=nid,
        title="node title",
        content="desc",
    )
    assert item.source_chunk_id == scid
    assert item.chunk_id == scid  # 双字段同值
    assert item.evidence_id == f"knowledge_node:{fid}:{nid}"


def test_evidence_item_chunk_source_chunk_id_must_be_none() -> None:
    """TD-050: chunk 类型 evidence 不携带 source_chunk_id（语义无关）。"""
    fid = uuid.uuid4()
    cid = uuid.uuid4()
    item = EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=cid,
        title="section",
        content="content",
    )
    assert item.source_chunk_id is None


def test_evidence_item_edge_source_chunk_id_must_be_none() -> None:
    """TD-050: knowledge_edge 类型 evidence 不携带 source_chunk_id。"""
    eid = uuid.uuid4()
    item = EvidenceItem(
        evidence_id="",
        source_type="knowledge_edge",
        edge_id=eid,
        title="edge",
    )
    assert item.source_chunk_id is None


def test_evidence_item_structured_field_source_chunk_id_must_be_none() -> None:
    """TD-050: structured_field 类型 evidence 不携带 source_chunk_id。"""
    fid = uuid.uuid4()
    item = EvidenceItem(
        evidence_id="",
        source_type="structured_field",
        file_id=fid,
        structured_path="template.basic_info.course_name",
        title="course_name",
        content="智能制造",
    )
    assert item.source_chunk_id is None


def test_evidence_id_unique_when_two_nodes_share_same_chunk() -> None:
    """TD-050: source_chunk_id 不参与 evidence_id 派生。

    同一 chunk 被多条 knowledge_node 共享时，各 node evidence_id 仍唯一。
    """
    fid = uuid.uuid4()
    scid = uuid.uuid4()
    nid_a = uuid.uuid4()
    nid_b = uuid.uuid4()
    item_a = EvidenceItem(
        evidence_id="",
        source_type="knowledge_node",
        file_id=fid,
        chunk_id=scid,
        source_chunk_id=scid,
        node_id=nid_a,
        title="node A",
        content="desc A",
    )
    item_b = EvidenceItem(
        evidence_id="",
        source_type="knowledge_node",
        file_id=fid,
        chunk_id=scid,
        source_chunk_id=scid,
        node_id=nid_b,
        title="node B",
        content="desc B",
    )
    assert item_a.source_chunk_id == item_b.source_chunk_id
    assert item_a.evidence_id == f"knowledge_node:{fid}:{nid_a}"
    assert item_b.evidence_id == f"knowledge_node:{fid}:{nid_b}"
    assert item_a.evidence_id != item_b.evidence_id
