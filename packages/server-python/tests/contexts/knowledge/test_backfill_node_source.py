"""`backfill_knowledge_node_source` 单元测试 — Slice 6。

REQ-010 AC-10：幂等（重复执行不产生重复节点 / 边 / 来源）。
AC-9：输出 scanned / updated / skipped / failed 统计。

测试通过 mock AsyncSession.execute 模拟 SQL 执行 + 验证 UPDATE params。
不依赖真 PG（沙箱拒绝 e2e + init-test-db）；真 PG 集成留给 Slice 8。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.contexts.knowledge.application.backfill_node_source import (
    BackfillStats,
    _find_chunk_for_node,
    backfill_knowledge_node_source,
)


def _mock_session(
    pending_nodes: list[dict],
    chunk_match_id: uuid.UUID | None,
):
    """Build a mock AsyncSession simulating fetch + UPDATE.

    `pending_nodes` 是首次 SELECT 的结果（缺 source_chunk_id / resolution）；
    `chunk_match_id` 是 _find_chunk_for_node 的 SELECT 返回（None = 不匹配）。
    """
    session = MagicMock()
    captured_updates: list[dict] = []

    async def execute(stmt, params=None):
        stmt_str = str(stmt)
        if "SELECT id, title, source_file_id" in stmt_str:
            r = MagicMock()
            r.mappings.return_value.all.return_value = pending_nodes
            return r
        if "SELECT id FROM metaedu.document_chunks" in stmt_str:
            r = MagicMock()
            r.first.return_value = (chunk_match_id,) if chunk_match_id else None
            return r
        if "UPDATE metaedu.knowledge_nodes" in stmt_str:
            captured_updates.append(params)
            r = MagicMock()
            return r
        return MagicMock()

    session.execute = AsyncMock(side_effect=execute)
    session.commit = AsyncMock()
    return session, captured_updates


async def test_backfill_updates_chunks_resolved_when_chunk_match() -> None:
    """Step 6.1: title 命中 chunk → 写 source_chunk_id + chunk_resolved。"""
    tenant = uuid.uuid4()
    fid = uuid.uuid4()
    cid = uuid.uuid4()
    node = {
        "id": uuid.uuid4(),
        "title": "智能制造",
        "source_file_id": fid,
        "source_chunk_id": None,
        "node_source_resolution": None,
    }
    session, updates = _mock_session([node], cid)
    stats = await backfill_knowledge_node_source(session, tenant)

    assert stats.scanned == 1
    assert stats.updated == 1
    assert stats.skipped_file_only == 0
    assert stats.failed == 0
    assert len(updates) == 1
    assert updates[0]["scid"] == cid
    assert updates[0]["res"] == "chunk_resolved"
    assert session.commit.called


async def test_backfill_marks_file_only_when_no_chunk_match() -> None:
    """Step 6.1: 找不到 chunk → 仅写 node_source_resolution='file_only'。"""
    tenant = uuid.uuid4()
    fid = uuid.uuid4()
    node = {
        "id": uuid.uuid4(),
        "title": "未知实体",
        "source_file_id": fid,
        "source_chunk_id": None,
        "node_source_resolution": None,
    }
    session, updates = _mock_session([node], None)
    stats = await backfill_knowledge_node_source(session, tenant)

    assert stats.scanned == 1
    assert stats.updated == 0
    assert stats.skipped_file_only == 1
    assert updates[0]["scid"] is None
    assert updates[0]["res"] == "file_only"


async def test_backfill_handles_node_with_no_file_id() -> None:
    """source_file_id 为 NULL → 无法定位 chunk，标记 file_only。"""
    tenant = uuid.uuid4()
    node = {
        "id": uuid.uuid4(),
        "title": "孤儿节点",
        "source_file_id": None,
        "source_chunk_id": None,
        "node_source_resolution": None,
    }
    session, updates = _mock_session([node], None)
    stats = await backfill_knowledge_node_source(session, tenant)

    assert stats.skipped_file_only == 1
    assert updates[0]["scid"] is None
    assert updates[0]["res"] == "file_only"


async def test_backfill_dry_run_does_not_call_commit_or_update() -> None:
    """dry_run=True: 不写 DB，不 commit，只计算统计。"""
    tenant = uuid.uuid4()
    fid = uuid.uuid4()
    cid = uuid.uuid4()
    node = {
        "id": uuid.uuid4(),
        "title": "智能制造",
        "source_file_id": fid,
        "source_chunk_id": None,
        "node_source_resolution": None,
    }
    session, updates = _mock_session([node], cid)
    stats = await backfill_knowledge_node_source(session, tenant, dry_run=True)

    assert stats.updated == 1
    assert not session.commit.called
    assert len(updates) == 0  # no UPDATE executed


async def test_backfill_is_idempotent_on_repeat_run() -> None:
    """AC-10: 重复执行第二次 → scanned=0（WHERE 过滤已 resolved）。"""
    tenant = uuid.uuid4()
    # Second run: SELECT returns empty list (all nodes resolved by first run)
    session, updates = _mock_session([], None)
    stats = await backfill_knowledge_node_source(session, tenant)

    assert stats.scanned == 0
    assert stats.updated == 0
    assert stats.skipped_file_only == 0
    assert len(updates) == 0
    # commit still called but no-ops
    assert session.commit.called


async def test_find_chunk_for_node_returns_first_match() -> None:
    """_find_chunk_for_node: file_id + title → SELECT chunk 命中。"""

    tenant = uuid.uuid4()
    fid = uuid.uuid4()
    cid = uuid.uuid4()
    session = MagicMock()

    async def execute(stmt, params=None):
        r = MagicMock()
        r.first.return_value = (cid,)
        return r

    session.execute = AsyncMock(side_effect=execute)
    result = await _find_chunk_for_node(session, tenant, fid, "智能制造")
    assert result == cid


async def test_find_chunk_for_node_returns_none_when_no_file_id() -> None:
    """_find_chunk_for_node: file_id=None → None without SQL。"""

    tenant = uuid.uuid4()
    session = MagicMock()
    result = await _find_chunk_for_node(session, tenant, None, "智能制造")
    assert result is None
    # session.execute 不应被调用
    assert not session.execute.called


def test_backfill_stats_as_dict() -> None:
    s = BackfillStats(scanned=10, updated=7, skipped_file_only=2, failed=1)
    assert s.as_dict() == {
        "scanned": 10,
        "updated": 7,
        "skipped_file_only": 2,
        "failed": 1,
    }
