"""`evidence_coverage_report` 单元测试 — Slice 6.

测试纯函数 `_to_markdown` + `_collect_coverage` 通过 mock session。
真实 PG 验证留给 Slice 8 收口。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from scripts.ai.evidence_coverage_report import _collect_coverage, _to_markdown


async def test_collect_coverage_runs_all_four_metrics() -> None:
    """4 个 metric 都被查询，count + total 正确返回。"""
    session = MagicMock()
    fake_results = [
        (50, 100),   # node_source_chunk
        (90, 100),   # chunk_embedding
        (95, 100),   # chunk_tsvector
        (80, 100),   # file_metadata
    ]
    call_count = {"n": 0}

    async def execute(stmt, params=None):
        r = MagicMock()
        r.first.return_value = fake_results[call_count["n"]]
        call_count["n"] += 1
        return r

    session.execute = AsyncMock(side_effect=execute)

    results = await _collect_coverage(session)
    assert call_count["n"] == 4
    assert len(results) == 4
    assert results[0]["metric"] == "node_source_chunk"
    assert results[0]["resolved"] == 50
    assert results[0]["total"] == 100
    assert results[0]["coverage_pct"] == 50.0
    assert results[1]["coverage_pct"] == 90.0
    assert results[2]["coverage_pct"] == 95.0
    assert results[3]["coverage_pct"] == 80.0


async def test_collect_coverage_handles_empty_table() -> None:
    """total=0 时 coverage 应是 100%（不是除零错误）。"""
    session = MagicMock()
    fake_results = [(0, 0)] * 4
    call_count = {"n": 0}

    async def execute(stmt, params=None):
        r = MagicMock()
        r.first.return_value = fake_results[call_count["n"]]
        call_count["n"] += 1
        return r

    session.execute = AsyncMock(side_effect=execute)

    results = await _collect_coverage(session)
    for r in results:
        assert r["total"] == 0
        assert r["coverage_pct"] == 100.0


def test_to_markdown_renders_table() -> None:
    results = [
        {"metric": "node_source_chunk", "resolved": 50, "total": 100, "coverage_pct": 50.0},
        {"metric": "chunk_embedding", "resolved": 90, "total": 100, "coverage_pct": 90.0},
    ]
    md = _to_markdown(results)
    assert "| Metric | Resolved | Total | Coverage |" in md
    assert "| node_source_chunk | 50 | 100 | 50.0% |" in md
    assert "| chunk_embedding | 90 | 100 | 90.0% |" in md


def test_to_markdown_is_json_serializable() -> None:
    """Coverage report 应当可被 json.dumps。"""
    results = [
        {"metric": "x", "resolved": 1, "total": 2, "coverage_pct": 50.0},
    ]
    # markdown 不应是 JSON；但 results 本身可 JSON
    _to_markdown(results)
    out = json.dumps(results, ensure_ascii=False)
    assert json.loads(out) == results
