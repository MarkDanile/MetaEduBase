"""`backfill_chunk_embedding` 单元测试 — Slice 6.

REQ-010 AC-9 / AC-10：覆盖率统计 + 幂等。
mock AsyncSession + 注入 fake embedding fn，不依赖真 PG / LLM。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.contexts.document.application.backfill_chunk_embedding import (
    backfill_chunk_embedding,
)


def _mock_session_with_chunks(chunks: list[dict]):
    session = MagicMock()
    captured_updates: list[dict] = []
    call_count = {"n": 0}

    async def execute(stmt, params=None):
        stmt_str = str(stmt)
        if "SELECT id, content" in stmt_str and "document_chunks" in stmt_str:
            r = MagicMock()
            # First call returns chunks; subsequent calls return empty
            # (simulating "all pending processed")
            if call_count["n"] == 0:
                r.mappings.return_value.all.return_value = chunks
                call_count["n"] += 1
            else:
                r.mappings.return_value.all.return_value = []
            return r
        if "UPDATE metaedu.document_chunks" in stmt_str:
            captured_updates.append(params)
            return MagicMock()
        return MagicMock()

    session.execute = AsyncMock(side_effect=execute)
    session.commit = AsyncMock()
    return session, captured_updates


async def test_backfill_chunk_embedding_updates_pending_chunks() -> None:
    cid = uuid.uuid4()
    chunks = [
        {
            "id": cid,
            "content": "电子信息工程专业介绍。",
            "embedding": None,
            "content_tsvector": None,
        }
    ]
    session, updates = _mock_session_with_chunks(chunks)

    async def fake_emb(text: str):
        return [0.1, 0.2, 0.3]

    stats = await backfill_chunk_embedding(
        session, uuid.uuid4(), fake_emb, dry_run=True
    )

    assert stats.scanned == 1
    assert stats.updated == 1
    assert stats.failed == 0
    # dry_run → no UPDATE
    assert len(updates) == 0


async def test_backfill_chunk_embedding_skips_already_present() -> None:
    """chunk 已有 embedding + tsvector → 跳过。"""
    cid = uuid.uuid4()
    chunks = [
        {
            "id": cid,
            "content": "already done",
            "embedding": "[0.1,0.2,0.3]",
            "content_tsvector": "'alreadi':1 'done':2",
        }
    ]
    session, updates = _mock_session_with_chunks(chunks)

    async def fake_emb(text: str):
        return [0.4]

    stats = await backfill_chunk_embedding(
        session, uuid.uuid4(), fake_emb
    )

    assert stats.scanned == 1
    assert stats.updated == 0
    assert stats.skipped_already_present == 1


async def test_backfill_chunk_embedding_handles_empty_embedding() -> None:
    """embedding_fn 返回 None → 标记 failed，不 UPDATE。"""
    chunks = [
        {
            "id": uuid.uuid4(),
            "content": "no api key",
            "embedding": None,
            "content_tsvector": None,
        }
    ]
    session, updates = _mock_session_with_chunks(chunks)

    async def fake_emb(text: str):
        return None

    stats = await backfill_chunk_embedding(
        session, uuid.uuid4(), fake_emb
    )

    assert stats.failed == 1
    assert stats.updated == 0
    assert len(updates) == 0


async def test_backfill_chunk_embedding_is_idempotent() -> None:
    """AC-10: 第二次 SELECT 返回空 → updated=0, scanned=0。"""
    session, updates = _mock_session_with_chunks([])  # empty pending

    async def fake_emb(text: str):
        return [0.1]

    stats = await backfill_chunk_embedding(
        session, uuid.uuid4(), fake_emb
    )

    assert stats.scanned == 0
    assert stats.updated == 0
