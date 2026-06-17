"""REQ-012 chunk keyword retriever SQL behavior tests."""

from __future__ import annotations

import uuid

from app.contexts.knowledge.infrastructure.retrievers.keyword_query import tokenize_query
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


def test_tokenize_query_keeps_python_basic_data_type_terms() -> None:
    terms = tokenize_query("Python 的 基本数据类型有哪些？")

    assert "python" in terms
    assert "数据类型" in terms or "基本数据类型" in terms
    assert "有哪些" not in terms
    assert "基本数据" not in terms


def test_tokenize_query_normalizes_function_parameter_natural_question() -> None:
    terms = tokenize_query("帮我介绍下，Python 的关于函数参数方面的知识")

    assert "python" in terms
    assert "函数参数" in terms
    assert "函数" in terms
    assert "参数" in terms
    assert "默认参数" in terms
    assert "可变参数" in terms
    assert "关键字参数" in terms
    assert "命名关键字参数" in terms
    assert "帮我" not in terms
    assert "关于函数参数方面" not in terms
    assert "知识" not in terms


def test_tokenize_query_keeps_same_core_terms_for_equivalent_parameter_question() -> None:
    natural_terms = tokenize_query("帮我介绍下，Python 的关于函数参数方面的知识")
    concise_terms = tokenize_query("Python 中函数的参数 的介绍")

    for term in ("python", "函数", "参数"):
        assert term in natural_terms
        assert term in concise_terms


async def test_pg_chunk_keyword_retriever_uses_chinese_tsvector() -> None:
    fid = uuid.uuid4()
    cid = uuid.uuid4()
    row = {
        "id": cid,
        "file_id": fid,
        "chunk_index": 3,
        "content": "Python 的基本数据类型包括数字、字符串、列表、元组、字典和集合。",
        "section_title": "基本数据类型",
        "section_path": "1.2",
        "keyword_rank": 0.42,
        "lexical_score": 16,
        "toc_penalty": 0,
    }
    session = _Session([[row], [row]])

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
    assert "lexical_score" in sql
    assert "toc_penalty" in sql
    assert "ORDER BY toc_penalty ASC, lexical_score DESC, keyword_rank DESC" in sql
    assert len(session.statements) == 2
    assert result[0].channels == ["keyword"]
    assert result[0].metadata["keyword_rank"] == 0.42
    assert result[0].metadata["search_mode"] in {"tsvector", "hybrid"}
    assert result[0].metadata["lexical_score"] == 16.0


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
    assert "toc_penalty" in session.statements[1]
    assert "lexical_score" in session.statements[1]
    assert "ORDER BY toc_penalty ASC, lexical_score DESC, c.chunk_index" in session.statements[1]
    assert "ORDER BY c.chunk_index" not in session.statements[1]
    assert result[0].file_id == fid
    assert result[0].metadata["search_mode"] == "lexical"


async def test_pg_chunk_keyword_retriever_supplements_tsvector_with_lexical_rows() -> None:
    """BUG-009: non-empty tsvector can still miss the best body chunk."""
    fid = uuid.uuid4()
    wrong_id = uuid.uuid4()
    body_id = uuid.uuid4()
    session = _Session(
        [
            [
                {
                    "id": wrong_id,
                    "file_id": fid,
                    "chunk_index": 325,
                    "content": "基本类型都可以用 type() 判断。",
                    "section_title": "获取对象信息",
                    "section_path": "45",
                    "keyword_rank": 0.8,
                    "lexical_score": 4,
                    "toc_penalty": 0,
                }
            ],
            [
                {
                    "id": body_id,
                    "file_id": fid,
                    "chunk_index": 54,
                    "content": (
                        "在Python中，能够直接处理的数据类型有以下几种："
                        "整数、浮点数、字符串。"
                    ),
                    "section_title": "数据类型和变量",
                    "section_path": "11",
                    "keyword_rank": 0.0,
                    "lexical_score": 16,
                    "toc_penalty": 0,
                }
            ],
        ]
    )

    result = await PgChunkKeywordRetriever().retrieve(
        "Python 的基本数据类型有哪些？",
        NERResult(),
        "default",
        session,  # type: ignore[arg-type]
        top_k=5,
    )

    assert len(session.statements) == 2
    assert result[0].chunk_id == body_id
    assert result[0].title == "数据类型和变量"
    assert result[0].metadata["search_mode"] == "lexical"


async def test_pg_chunk_keyword_retriever_ranks_function_parameter_body_before_intro() -> None:
    """BUG-010: natural function-parameter question must not fall back to intro chunks."""
    fid = uuid.uuid4()
    intro_id = uuid.uuid4()
    body_id = uuid.uuid4()
    session = _Session(
        [
            [
                {
                    "id": intro_id,
                    "file_id": fid,
                    "chunk_index": 3,
                    "content": "Python 的起源、设计哲学、优缺点以及应用领域。",
                    "section_title": "Python 简介",
                    "section_path": "1",
                    "keyword_rank": 0.9,
                    "lexical_score": 4,
                    "toc_penalty": 1,
                }
            ],
            [
                {
                    "id": body_id,
                    "file_id": fid,
                    "chunk_index": 120,
                    "content": (
                        "Python 函数参数包括默认参数、可变参数、"
                        "关键字参数、命名关键字参数和参数组合。"
                    ),
                    "section_title": "函数参数",
                    "section_path": "6.2",
                    "keyword_rank": 0.0,
                    "lexical_score": 36,
                    "toc_penalty": 0,
                }
            ],
        ]
    )

    result = await PgChunkKeywordRetriever().retrieve(
        "帮我介绍下，Python 的关于函数参数方面的知识",
        NERResult(),
        "default",
        session,  # type: ignore[arg-type]
        top_k=5,
    )

    assert result[0].chunk_id == body_id
    assert result[0].title == "函数参数"
    assert result[0].metadata["search_mode"] == "lexical"
