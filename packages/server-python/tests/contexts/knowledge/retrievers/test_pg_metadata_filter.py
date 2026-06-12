"""REQ-012 metadata filter behavior tests."""

from __future__ import annotations

import uuid

from app.contexts.knowledge.domain.evidence import EvidenceItem
from app.contexts.knowledge.infrastructure.retrievers.pg_metadata_filter import (
    PgMetadataFilter,
)
from app.shared.domain.ner_pipeline import NERResult


class _Rows:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def all(self) -> list[dict]:
        return self._rows


class _Result:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self) -> _Rows:
        return _Rows(self._rows)


class _Session:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []

    async def execute(self, stmt, params=None):  # noqa: ANN001
        return _Result(self.rows)


async def test_metadata_filter_enriches_without_dropping_unattributed_graph() -> None:
    fid = uuid.uuid4()
    chunk = EvidenceItem(
        evidence_id="",
        source_type="chunk",
        file_id=fid,
        chunk_id=uuid.uuid4(),
        title="Python 基础",
        content="Python 基础内容",
    )
    graph = EvidenceItem(
        evidence_id="",
        source_type="knowledge_node",
        file_id=None,
        node_id=uuid.uuid4(),
        title="来源待细化节点",
        content="图谱补充证据",
    )
    session = _Session(
        [
            {
                "id": fid,
                "doc_type": "操作指南",
                "tags": ["python"],
                "structured_data": {},
            }
        ]
    )

    result = await PgMetadataFilter().filter(
        NERResult(),
        "default",
        session,  # type: ignore[arg-type]
        [chunk, graph],
    )

    assert [item.evidence_id for item in result] == [
        chunk.evidence_id,
        graph.evidence_id,
    ]
    assert result[0].metadata["doc_type"] == "操作指南"
    assert result[1].metadata["source_attribution"] == "pending"
