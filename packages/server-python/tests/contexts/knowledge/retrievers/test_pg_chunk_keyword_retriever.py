"""REQ-012 chunk keyword retriever SQL behavior tests."""

from __future__ import annotations

import uuid

from app.contexts.knowledge.infrastructure.retrievers.pg_chunk_keyword_retriever import (
    PgChunkKeywordRetriever,
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
    def __init__(self, rows: list[dict] | list[list[dict]]) -> None:
        if rows and isinstance(rows[0], list):
            self.row_batches = list(rows)  # type: ignore[arg-type]
        else:
            self.row_batches = [rows]  # type: ignore[list-item]
        self.statements: list[str] = []
        self.params: list[dict] = []

    async def execute(self, stmt, params=None):  # noqa: ANN001
        self.statements.append(str(stmt))
        self.params.append(params or {})
        rows = self.row_batches.pop(0) if self.row_batches else []
        return _Result(rows)


async def test_pg_chunk_keyword_retriever_uses_chinese_tsvector() -> None:
    fid = uuid.uuid4()
    cid = uuid.uuid4()
    session = _Session(
        [
            {
                "id": cid,
                "file_id": fid,
                "chunk_index": 3,
                "content": "Python 的基本数据类型包括数字、字符串、列表、元组、字典和集合。",
                "section_title": "基本数据类型",
                "section_path": "1.2",
                "keyword_rank": 0.42,
            }
        ]
    )

    result = await PgChunkKeywordRetriever().retrieve(
        "Python 的基本数据类型",
        NERResult(),
        "default",
        session,  # type: ignore[arg-type]
        top_k=3,
    )

    sql = session.statements[0]
    assert "FROM pg_catalog.pg_ts_config" in sql
    assert "cfgname = 'chinese_zh'" in sql
    assert "'pg_catalog.simple'::regconfig" in sql
    assert "plainto_tsquery(keyword_config.cfg, :query)" in sql
    assert "c.content_tsvector::tsvector @@ keyword_query.query" in sql
    assert "ts_rank_cd(c.content_tsvector::tsvector, keyword_query.query)" in sql
    assert "ILIKE" not in sql
    assert len(session.statements) == 1
    assert result[0].channels == ["keyword"]
    assert result[0].metadata["keyword_rank"] == 0.42
    assert result[0].metadata["search_mode"] == "tsvector"


async def test_pg_chunk_keyword_retriever_binds_file_filter() -> None:
    fid = uuid.uuid4()
    session = _Session([])

    await PgChunkKeywordRetriever().retrieve(
        "智能制造 技能",
        NERResult(),
        "default",
        session,  # type: ignore[arg-type]
        top_k=5,
        file_filter=[str(fid)],
    )

    sql = session.statements[0]
    params = session.params[0]
    assert "c.file_id IN (:f0)" in sql
    assert params["f0"] == fid


async def test_pg_chunk_keyword_retriever_falls_back_to_ilike_when_tsvector_empty() -> None:
    fid = uuid.uuid4()
    cid = uuid.uuid4()
    session = _Session(
        [
            [],
            [
                {
                    "id": cid,
                    "file_id": fid,
                    "chunk_index": 5,
                    "content": "智能制造专业需要 PLC 编程、工业机器人和传感器调试能力。",
                    "section_title": "核心技能",
                    "section_path": "2.1",
                    "keyword_rank": 0.0,
                }
            ],
        ]
    )

    result = await PgChunkKeywordRetriever().retrieve(
        "智能制造专业需要哪些技能",
        NERResult(),
        "default",
        session,  # type: ignore[arg-type]
        top_k=5,
    )

    assert len(session.statements) == 2
    assert "c.content_tsvector::tsvector @@ keyword_query.query" in session.statements[0]
    assert "ILIKE" in session.statements[1]
    assert result[0].file_id == fid
    assert result[0].metadata["search_mode"] == "ilike_fallback"
