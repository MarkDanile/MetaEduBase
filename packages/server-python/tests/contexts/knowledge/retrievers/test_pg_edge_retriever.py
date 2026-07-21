"""REQ-018 Slice 1 — PgEdgeRetriever behavior tests."""

from __future__ import annotations

import uuid

from app.contexts.knowledge.application.retrievers import GraphRetriever
from app.contexts.knowledge.infrastructure.retrievers.pg_graph_retriever import (
    PgEdgeRetriever,
)
from app.shared.domain.ner_pipeline import NERResult

# ---------------------------------------------------------------------------
# Mock SQLAlchemy session
# ---------------------------------------------------------------------------


class _RowCursor:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def all(self) -> list[dict]:
        return self._rows


class _Result:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self) -> _RowCursor:
        return _RowCursor(self._rows)


class _Session:
    """Minimal AsyncSession mock that returns preset rows per call index."""

    def __init__(self, rows_by_call: list[list[dict]]) -> None:
        self._rows_by_call = rows_by_call
        self._call_index = 0

    async def execute(self, stmt, params=None):  # noqa: ANN001
        idx = self._call_index
        self._call_index += 1
        rows = self._rows_by_call[idx] if idx < len(self._rows_by_call) else []
        return _Result(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_edge_retriever_returns_evidence_items() -> None:
    """PgEdgeRetriever returns EvidenceItem(source_type=knowledge_edge)."""
    seed_node_id = uuid.uuid4()
    related_node_id = uuid.uuid4()
    target_file_id = uuid.uuid4()
    target_chunk_id = uuid.uuid4()
    edge_id = uuid.uuid4()

    tid = str(uuid.uuid4())

    # Three-query sequence: seed nodes → edges → related nodes
    session = _Session(
        [
            # Query 1: seed node lookup
            [
                {
                    "id": seed_node_id,
                    "title": "Python 函数",
                    "description": "函数定义",
                    "domain": "编程",
                    "level": "初级",
                    "path": "/python",
                    "source_file_id": target_file_id,
                    "source_chunk_id": target_chunk_id,
                }
            ],
            # Query 2: edge lookup
            [
                {
                    "id": edge_id,
                    "source_id": seed_node_id,
                    "target_id": related_node_id,
                    "relation_type": "先导知识",
                    "weight": 0.9,
                    "related_node_id": related_node_id,
                }
            ],
            # Query 3: hydrate related node
            [
                {
                    "id": related_node_id,
                    "title": "Python 基础",
                    "description": "Python 入门内容",
                    "domain": "编程",
                    "level": "入门",
                    "path": "/python/基础",
                    "source_file_id": target_file_id,
                    "source_chunk_id": target_chunk_id,
                }
            ],
        ]
    )

    retriever = PgEdgeRetriever()
    items = await retriever.retrieve(
        query="Python 函数",
        ner_result=NERResult(),
        tenant_id=tid,
        session=session,
        top_k=5,
    )

    assert len(items) == 1
    item = items[0]
    assert item.source_type == "knowledge_edge"
    assert item.edge_id == edge_id
    assert item.title == "Python 基础"
    assert "graph_edge" in item.channels
    assert item.score is not None


async def test_edge_retriever_falls_back_gracefully_when_no_seed_nodes() -> None:
    """No seed nodes → empty list (not an exception)."""
    tid = str(uuid.uuid4())

    session = _Session([[]])  # seed node query returns empty

    retriever = PgEdgeRetriever()
    items = await retriever.retrieve(
        query="完全不存在的查询术语 xyz123",
        ner_result=NERResult(),
        tenant_id=tid,
        session=session,
        top_k=5,
    )

    assert items == []


async def test_edge_retriever_falls_back_on_edge_query_failure() -> None:
    """Edge query returns empty → empty list (graceful degradation)."""
    tid = str(uuid.uuid4())
    seed_node_id = uuid.uuid4()

    session = _Session(
        [
            # Seed node found
            [
                {
                    "id": seed_node_id,
                    "title": "课程A",
                    "description": "desc",
                    "domain": "课程",
                    "level": "中级",
                    "path": "/course",
                    "source_file_id": None,
                    "source_chunk_id": None,
                }
            ],
            # Edge query returns empty
            [],
        ]
    )

    retriever = PgEdgeRetriever()
    items = await retriever.retrieve(
        query="课程A",
        ner_result=NERResult(),
        tenant_id=tid,
        session=session,
        top_k=5,
    )

    assert items == []


def test_edge_retriever_satisfies_graph_retriever_protocol() -> None:
    """PgEdgeRetriever satisfies the runtime_checkable GraphRetriever Protocol."""
    retriever = PgEdgeRetriever()
    assert isinstance(retriever, GraphRetriever)


async def test_edge_retriever_deduplicates_edges_by_id() -> None:
    """Same edge appearing twice (via source and target hit) is deduplicated."""
    tid = str(uuid.uuid4())
    seed_node_id = uuid.uuid4()
    related_node_id = uuid.uuid4()
    edge_id = uuid.uuid4()
    target_file_id = uuid.uuid4()
    target_chunk_id = uuid.uuid4()

    # Both seed and related appear in edge result, but dedup should keep only one
    session = _Session(
        [
            [
                {
                    "id": seed_node_id,
                    "title": "课程A",
                    "description": "desc",
                    "domain": "课程",
                    "level": "初级",
                    "path": "/course",
                    "source_file_id": target_file_id,
                    "source_chunk_id": target_chunk_id,
                }
            ],
            [
                {
                    "id": edge_id,
                    "source_id": seed_node_id,
                    "target_id": related_node_id,
                    "relation_type": "先导知识",
                    "weight": 0.8,
                    "related_node_id": related_node_id,
                }
            ],
            [
                {
                    "id": related_node_id,
                    "title": "课程B",
                    "description": "desc",
                    "domain": "课程",
                    "level": "中级",
                    "path": "/course/b",
                    "source_file_id": target_file_id,
                    "source_chunk_id": target_chunk_id,
                }
            ],
        ]
    )

    retriever = PgEdgeRetriever()
    items = await retriever.retrieve(
        query="课程A",
        ner_result=NERResult(),
        tenant_id=tid,
        session=session,
        top_k=5,
    )

    # Exactly one item despite one edge
    assert len(items) == 1
    edge_ids = [item.edge_id for item in items]
    assert edge_id in edge_ids
