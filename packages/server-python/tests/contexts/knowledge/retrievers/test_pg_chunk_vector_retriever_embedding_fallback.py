"""`PgChunkVectorRetriever` — embedding 降级行为测试。

BUG-003 (AC-2/AC-3) — 当 `get_embedding` 返回 None（API key 缺失 / 限流 /
网络错误）时，retriever 不应直接 return []，而应降级到 `chinese_zh` tsvector
keyword 路径（复用 `PgChunkKeywordRetriever._tokenize` + ILIKE 回退），
保证 chunk 通道在 embedding 不可达时仍能返回正文 chunk。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from app.contexts.knowledge.infrastructure.retrievers.pg_chunk_vector_retriever import (
    PgChunkVectorRetriever,
)
from app.shared.domain.ner_pipeline import NERResult


class _FakeRows:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def all(self) -> list[dict]:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeRows:
        return _FakeRows(self._rows)


class _FakeSession:
    """记录 session.execute 收到的 SQL，根据 SQL 关键字路由到不同 rows。"""

    def __init__(self, ilike_rows: list[dict] | None = None) -> None:
        self.ilike_rows = ilike_rows or []
        self.statements: list[str] = []

    async def execute(self, stmt, params=None):  # noqa: ANN001
        text = str(stmt)
        self.statements.append(text)
        # 降级路径只走 ILIKE（embedding 空时不进 tsvector 主路径），
        # tsvector 路径不返回（empty tsquery rows）。
        if "ILIKE" in text or "ts_rank" in text or "tsvector" in text:
            return _FakeResult(self.ilike_rows)
        return _FakeResult([])


def _chunk_row(file_id: uuid.UUID, idx: int = 51, content: str | None = None) -> dict:
    return {
        "id": uuid.uuid4(),
        "file_id": file_id,
        "chunk_index": idx,
        "content": content
        or "Python支持多种数据类型，包括整数、浮点数、字符串、布尔值、列表、元组、字典、集合。",
        "section_title": "数据类型和变量",
        "section_path": "5.1",
    }


async def test_embedding_empty_falls_back_to_ilike_keyword() -> None:
    """AC-2: get_embedding 返回 None 时，vector retriever 走 ILIKE 降级并返回 chunk。"""
    fid = uuid.uuid4()
    ilike_rows = [_chunk_row(fid)]
    session = _FakeSession(ilike_rows=ilike_rows)

    with patch(
        "app.contexts.knowledge.infrastructure.retrievers.pg_chunk_vector_retriever.get_embedding",
        AsyncMock(return_value=None),
    ):
        retriever = PgChunkVectorRetriever()
        items = await retriever.retrieve(
            "Python 的基本数据类型有哪些？",
            NERResult(domains=[], levels=[]),
            "default",
            session,  # type: ignore[arg-type]
            top_k=5,
        )

    assert len(items) == 1
    item = items[0]
    assert item.source_type == "chunk"
    assert item.chunk_id == ilike_rows[0]["id"]
    assert "整数" in item.content or "数据类型" in item.content
    # 降级路径必须明确 channels 含 keyword
    assert "keyword" in item.channels
    # 降级 path 在 metadata 里记录 search_mode 以便后续审计
    assert item.metadata.get("search_mode") in {"ilike_fallback", "tsvector"}


async def test_embedding_empty_logs_warning(caplog) -> None:
    """get_embedding 返回 None 时，应记录 empty embedding 警告。"""
    import logging

    session = _FakeSession(ilike_rows=[])

    with caplog.at_level(logging.WARNING), patch(
        "app.contexts.knowledge.infrastructure.retrievers.pg_chunk_vector_retriever.get_embedding",
        AsyncMock(return_value=None),
    ):
        retriever = PgChunkVectorRetriever()
        items = await retriever.retrieve(
            "Python 的基本数据类型有哪些？",
            NERResult(domains=[], levels=[]),
            "default",
            session,  # type: ignore[arg-type]
            top_k=5,
        )

    assert items == []
    assert any("empty embedding" in rec.message for rec in caplog.records)


async def test_embedding_success_uses_vector_path() -> None:
    """get_embedding 正常返回时，仍走 <=> 向量路径（不降级）。"""
    fid = uuid.uuid4()
    row = _chunk_row(fid, idx=56, content="Python整数没有大小限制。")
    # 真实 <-> 路径会算 score；测试 mock 必须补上
    row["score"] = 0.95
    session = _FakeSession()
    # 用 1536 维全 0 向量模拟真实 embedding 返回
    fake_embedding = [0.0] * 1536

    with patch(
        "app.contexts.knowledge.infrastructure.retrievers.pg_chunk_vector_retriever.get_embedding",
        AsyncMock(return_value=fake_embedding),
    ):
        # 让 <=> 路径返回 row，ILIKE 路径返回空
        original_execute = session.execute

        async def routed_execute(stmt, params=None):  # noqa: ANN001
            t = str(stmt)
            if "<=>" in t:
                return _FakeResult([row])
            return await original_execute(stmt, params)

        session.execute = routed_execute  # type: ignore[method-assign]

        retriever = PgChunkVectorRetriever()
        items = await retriever.retrieve(
            "Python 整数",
            NERResult(domains=[], levels=[]),
            "default",
            session,  # type: ignore[arg-type]
            top_k=5,
        )

    assert len(items) == 1
    assert items[0].source_type == "chunk"
    assert items[0].channels == ["vector"]
    assert "整数" in items[0].content
    # vector 路径不走 embedding_fallback 标记
    assert items[0].metadata.get("embedding_fallback") is None or not items[0].metadata.get(
        "embedding_fallback"
    )
