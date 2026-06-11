"""`PgGraphRetriever` source_chunk_id 透传测试。

TD-050 收口时新增：`PgGraphRetriever.retrieve` 把
`RecallResult.source_file_id` / `source_chunk_id` 透传给 `EvidenceItem.file_id`
/ `chunk_id`，并同步写 `EvidenceItem.source_chunk_id`（与 `chunk_id` 同值）。

本测试用 mock 注入 fake `RecallResult`（避免依赖真实 PostgreSQL + pgvector +
tsvector），断言透传结果与 `source_type="knowledge_node"` 时 `source_chunk_id`
字段一致性。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.contexts.knowledge.infrastructure.retrievers.pg_graph_retriever import (
    PgGraphRetriever,
)
from app.shared.domain.ner_pipeline import NERResult
from app.shared.domain.recall_channel import RecallResult


class _FakeRecallChannel:
    """Fake `RecallChannel` 替身：返回预设的 `RecallResult` 列表。

    不依赖 PostgreSQL / pgvector / tsvector；仅提供 TD-050 透传测试需要的
    `source_file_id` / `source_chunk_id` 字段。
    """

    def __init__(self, results: list[RecallResult], name: str = "fake") -> None:
        self._results = results
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def recall(
        self,
        query: str,
        ner_result: NERResult,
        tenant_id: str,
        session: Any,
        top_k: int = 5,
    ) -> list[RecallResult]:
        return self._results[:top_k]


def _make_ner() -> NERResult:
    return NERResult(domains=[], levels=[], entities=[])


def _patch_pg_graph_retriever_channels(
    monkeypatch: pytest.MonkeyPatch,
    vector_results: list[RecallResult],
    keyword_results: list[RecallResult],
) -> PgGraphRetriever:
    """构造 `PgGraphRetriever` 并把内部 channel 替换为 fake。

    与 `PgGraphRetriever.__init__` 内的 `self._vector_channel` / `self._keyword_channel`
    对齐；fake 实现只需实现 `name` / `recall` 两个接口。
    """
    retriever = PgGraphRetriever()
    monkeypatch.setattr(
        retriever,
        "_vector_channel",
        _FakeRecallChannel(vector_results, name="vector"),
    )
    monkeypatch.setattr(
        retriever,
        "_keyword_channel",
        _FakeRecallChannel(keyword_results, name="keyword"),
    )
    return retriever


@pytest.mark.asyncio
async def test_vector_channel_passes_source_file_id_and_source_chunk_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """vector channel 的 RecallResult.source_file_id/source_chunk_id 透传。"""
    fid = uuid.uuid4()
    scid = uuid.uuid4()
    nid = uuid.uuid4()
    fake_result = RecallResult(
        node_id=str(nid),
        title="node title",
        description="desc text",
        domain="智能制造",
        level="本科",
        score=0.9,
        channel="vector",
        path="1.2.3",
        source_file_id=fid,
        source_chunk_id=scid,
    )
    retriever = _patch_pg_graph_retriever_channels(
        monkeypatch, vector_results=[fake_result], keyword_results=[]
    )
    items = await retriever.retrieve(
        query="智能制造",
        ner_result=_make_ner(),
        tenant_id="tenant-1",
        session=None,  # type: ignore[arg-type]
        top_k=5,
    )
    assert len(items) == 1
    item = items[0]
    assert item.source_type == "knowledge_node"
    assert item.file_id == fid
    assert item.chunk_id == scid
    assert item.source_chunk_id == scid  # TD-050: 与 chunk_id 同值
    assert item.node_id == nid
    assert item.title == "node title"
    assert item.content == "desc text"
    assert item.score == 0.9
    assert item.channels == ["vector"]


@pytest.mark.asyncio
async def test_keyword_channel_passes_source_file_id_and_source_chunk_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """keyword channel 的 RecallResult.source_file_id/source_chunk_id 透传。"""
    fid = uuid.uuid4()
    scid = uuid.uuid4()
    nid = uuid.uuid4()
    fake_result = RecallResult(
        node_id=str(nid),
        title="kw node",
        description="kw desc",
        score=0.8,
        channel="keyword",
        source_file_id=fid,
        source_chunk_id=scid,
    )
    retriever = _patch_pg_graph_retriever_channels(
        monkeypatch, vector_results=[], keyword_results=[fake_result]
    )
    items = await retriever.retrieve(
        query="kw query",
        ner_result=_make_ner(),
        tenant_id="tenant-1",
        session=None,  # type: ignore[arg-type]
        top_k=5,
    )
    assert len(items) == 1
    item = items[0]
    assert item.source_type == "knowledge_node"
    assert item.file_id == fid
    assert item.chunk_id == scid
    assert item.source_chunk_id == scid
    assert item.node_id == nid
    assert item.channels == ["keyword"]


@pytest.mark.asyncio
async def test_file_only_node_passes_none_for_source_chunk_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """file_only 节点（source_chunk_id IS NULL）→ evidence chunk_id/source_chunk_id 为 None。

    不伪造溯源信息。
    """
    fid = uuid.uuid4()
    nid = uuid.uuid4()
    fake_result = RecallResult(
        node_id=str(nid),
        title="file_only node",
        description="node 找不到对应 chunk（file_only 状态）",
        score=0.7,
        channel="vector",
        source_file_id=fid,
        source_chunk_id=None,  # file_only
    )
    retriever = _patch_pg_graph_retriever_channels(
        monkeypatch, vector_results=[fake_result], keyword_results=[]
    )
    items = await retriever.retrieve(
        query="file_only",
        ner_result=_make_ner(),
        tenant_id="tenant-1",
        session=None,  # type: ignore[arg-type]
        top_k=5,
    )
    assert len(items) == 1
    item = items[0]
    assert item.file_id == fid  # file 仍能溯源
    assert item.chunk_id is None
    assert item.source_chunk_id is None


@pytest.mark.asyncio
async def test_two_nodes_sharing_same_chunk_have_distinct_evidence_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TD-050: source_chunk_id 不参与 evidence_id 派生。

    同一 chunk 被多条 knowledge_node 共享时，evidence_id 仍唯一。
    """
    fid = uuid.uuid4()
    scid = uuid.uuid4()
    nid_a = uuid.uuid4()
    nid_b = uuid.uuid4()
    retriever = _patch_pg_graph_retriever_channels(
        monkeypatch,
        vector_results=[
            RecallResult(
                node_id=str(nid_a),
                title="A",
                description="a",
                score=0.9,
                channel="vector",
                source_file_id=fid,
                source_chunk_id=scid,
            ),
        ],
        keyword_results=[
            RecallResult(
                node_id=str(nid_b),
                title="B",
                description="b",
                score=0.8,
                channel="keyword",
                source_file_id=fid,
                source_chunk_id=scid,
            ),
        ],
    )
    items = await retriever.retrieve(
        query="shared chunk",
        ner_result=_make_ner(),
        tenant_id="tenant-1",
        session=None,  # type: ignore[arg-type]
        top_k=5,
    )
    assert len(items) == 2
    assert items[0].source_chunk_id == scid
    assert items[1].source_chunk_id == scid
    assert items[0].evidence_id != items[1].evidence_id
    assert items[0].evidence_id == f"knowledge_node:{fid}:{nid_a}"
    assert items[1].evidence_id == f"knowledge_node:{fid}:{nid_b}"


@pytest.mark.asyncio
async def test_channel_failure_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """channel 抛异常时，`PgGraphRetriever.retrieve` 优雅降级（不冒泡）。

    回归测试：TD-050 改动不应破坏现有的"channel 失败 → warning + empty list"行为。
    """

    class _BoomChannel(_FakeRecallChannel):
        async def recall(  # type: ignore[override]
            self,
            query: str,
            ner_result: NERResult,
            tenant_id: str,
            session: Any,
            top_k: int = 5,
        ) -> list[RecallResult]:
            raise RuntimeError("simulated channel failure")

    retriever = PgGraphRetriever()
    monkeypatch.setattr(retriever, "_vector_channel", _BoomChannel([], name="vector"))
    monkeypatch.setattr(
        retriever, "_keyword_channel", _FakeRecallChannel([], name="keyword")
    )
    items = await retriever.retrieve(
        query="boom",
        ner_result=_make_ner(),
        tenant_id="tenant-1",
        session=None,  # type: ignore[arg-type]
        top_k=5,
    )
    assert items == []
