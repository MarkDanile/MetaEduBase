"""`find_chunk_for_entity` 单元测试 — Slice 5。

REQ-010 AC-14: 模糊匹配 entity name → chunk content 子串。
本测试覆盖纯逻辑，不依赖 PG / LLM / celery task 闭包。
"""

from __future__ import annotations

import uuid

from app.contexts.document.application.tasks.extract_knowledge_graph import (
    find_chunk_for_entity,
)


def _chunk(chunk_id: str, content: str) -> dict:
    return {"id": uuid.UUID(chunk_id), "content": content}


def test_find_chunk_for_entity_returns_first_matching_chunk() -> None:
    chunks = [
        _chunk("11111111-1111-1111-1111-111111111111", "智能制造专业需要掌握电路基础。"),
        _chunk("22222222-2222-2222-2222-222222222222", "电路基础包含基本电路分析方法。"),
    ]
    # "电路基础" 在两个 chunk 都出现 → 返回第一个
    result = find_chunk_for_entity(chunks, "电路基础")
    assert result == uuid.UUID("11111111-1111-1111-1111-111111111111")


def test_find_chunk_for_entity_returns_none_when_no_match() -> None:
    chunks = [
        _chunk("11111111-1111-1111-1111-111111111111", "智能制造"),
    ]
    result = find_chunk_for_entity(chunks, "不存在的实体")
    assert result is None


def test_find_chunk_for_entity_handles_empty_entity_name() -> None:
    chunks = [_chunk("11111111-1111-1111-1111-111111111111", "content")]
    assert find_chunk_for_entity(chunks, "") is None


def test_find_chunk_for_entity_handles_empty_chunk_list() -> None:
    assert find_chunk_for_entity([], "智能制造") is None


def test_find_chunk_for_entity_handles_none_content() -> None:
    """None content should not crash; should be treated as no match."""
    chunks = [
        {"id": uuid.UUID("11111111-1111-1111-1111-111111111111"), "content": None},
    ]
    assert find_chunk_for_entity(chunks, "智能制造") is None

