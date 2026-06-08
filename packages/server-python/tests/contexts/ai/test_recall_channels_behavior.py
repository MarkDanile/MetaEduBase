from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.contexts.knowledge.application.recall_service import (
    PgKeywordRecallChannel,
    PgMetadataRecallChannel,
    PgVectorRecallChannel,
)
from app.shared.domain.ner_pipeline import NERResult

# --- helpers ---------------------------------------------------------------

class _FakeRow(dict):
    """Behaves like SQLAlchemy Row + supports attribute access via __getitem__."""


def _row(node_id: str, **overrides) -> _FakeRow:
    base = {
        "id": node_id,
        "title": f"title-{node_id}",
        "description": f"desc-{node_id}",
        "domain": "smart_manufacturing",
        "level": "course",
        "path": None,
    }
    base.update(overrides)
    return _FakeRow(base)


def _fake_session_with_rows(rows: list[_FakeRow]) -> MagicMock:
    """返回一个 MagicMock session，session.execute 异步返回包含 rows 的结果。"""
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    execute = AsyncMock(return_value=result)
    session = MagicMock()
    session.execute = execute
    return session, execute


def _ner_with(domains: list[str] | None = None, levels: list[str] | None = None) -> NERResult:
    return NERResult(
        domains=domains or [],
        levels=levels or [],
        raw_entities=[],
    )


# --- PgVectorRecallChannel -----------------------------------------------

@pytest.mark.asyncio
async def test_pg_vector_recall_returns_recall_results_with_score_and_channel():
    ch = PgVectorRecallChannel()
    session, execute = _fake_session_with_rows([
        _row("n1", score=0.92),
        _row("n2", score=0.81),
    ])

    with patch(
        "app.contexts.knowledge.application.recall_service.get_embedding_vec",
        AsyncMock(return_value=[0.1] * 8),
    ):
        results = await ch.recall(
            "智能制造",
            _ner_with(domains=["smart_manufacturing"]),
            tenant_id="t-1",
            session=session,
            top_k=5,
        )

    assert len(results) == 2
    assert all(r.channel == "vector" for r in results)
    assert [r.node_id for r in results] == ["n1", "n2"]
    assert results[0].score == pytest.approx(0.92, abs=1e-4)
    assert results[1].score == pytest.approx(0.81, abs=1e-4)
    # description / domain / level 都被正确映射
    assert results[0].domain == "smart_manufacturing"
    assert results[0].level == "course"


@pytest.mark.asyncio
async def test_pg_vector_recall_passes_tenant_topk_and_vector_to_sql():
    ch = PgVectorRecallChannel()
    session, execute = _fake_session_with_rows([])

    with patch(
        "app.contexts.knowledge.application.recall_service.get_embedding_vec",
        AsyncMock(return_value=[0.1, 0.2, 0.3]),
    ):
        await ch.recall(
            "anything",
            _ner_with(),
            tenant_id="tenant-xyz",
            session=session,
            top_k=7,
        )

    assert execute.await_count == 1
    stmt, params = execute.await_args.args
    # stmt 是 sqlalchemy TextClause
    assert "knowledge_nodes" in str(stmt)
    assert ":tid" in str(stmt)
    assert params["tid"] == "tenant-xyz"
    assert params["lim"] == 7
    # vec 是 8 元素数组，PG vector 字面量形如 "[0.1,0.2,0.3]"
    assert params["vec"].startswith("[")
    assert params["vec"].endswith("]")


@pytest.mark.asyncio
async def test_pg_vector_recall_returns_empty_when_embedding_unavailable():
    ch = PgVectorRecallChannel()
    session, execute = _fake_session_with_rows([])

    with patch(
        "app.contexts.knowledge.application.recall_service.get_embedding_vec",
        AsyncMock(return_value=None),
    ):
        results = await ch.recall(
            "anything",
            _ner_with(),
            tenant_id="t",
            session=session,
            top_k=5,
        )

    assert results == []
    assert execute.await_count == 0  # 没有真去查 DB


# --- PgKeywordRecallChannel -----------------------------------------------

@pytest.mark.asyncio
async def test_pg_keyword_recall_maps_rows_and_uses_decrementing_score():
    ch = PgKeywordRecallChannel()
    session, _ = _fake_session_with_rows([
        _row("n1"),
        _row("n2"),
        _row("n3"),
    ])

    results = await ch.recall(
        "电子信息专业的课程",
        _ner_with(),
        tenant_id="t-2",
        session=session,
        top_k=5,
    )

    assert [r.node_id for r in results] == ["n1", "n2", "n3"]
    assert all(r.channel == "keyword" for r in results)
    # score 按 1.0 - idx*0.05 递减
    assert results[0].score == pytest.approx(1.0, abs=1e-4)
    assert results[1].score == pytest.approx(0.95, abs=1e-4)
    assert results[2].score == pytest.approx(0.90, abs=1e-4)


@pytest.mark.asyncio
async def test_pg_keyword_recall_passes_tenant_topk_and_keywords():
    ch = PgKeywordRecallChannel()
    session, execute = _fake_session_with_rows([])

    await ch.recall(
        "电子信息专业的课程有哪些？",
        _ner_with(),
        tenant_id="tenant-abc",
        session=session,
        top_k=4,
    )

    assert execute.await_count == 1
    stmt, params = execute.await_args.args
    assert "knowledge_nodes" in str(stmt)
    assert "ILIKE" in str(stmt)
    assert params["tid"] == "tenant-abc"
    assert params["lim"] == 4
    # 至少有一个 q{i} keyword 参数被传进去
    assert any(k.startswith("q") and v.startswith("%") and v.endswith("%")
               for k, v in params.items())


@pytest.mark.asyncio
async def test_pg_keyword_recall_returns_empty_when_no_keywords_extracted():
    ch = PgKeywordRecallChannel()
    session, execute = _fake_session_with_rows([])

    # 单字符 query 切不出长度 >=2 的关键词
    results = await ch.recall(
        "你",
        _ner_with(),
        tenant_id="t",
        session=session,
        top_k=5,
    )

    assert results == []
    assert execute.await_count == 0


# --- PgMetadataRecallChannel ----------------------------------------------

@pytest.mark.asyncio
async def test_pg_metadata_recall_filters_by_domain_and_level():
    ch = PgMetadataRecallChannel()
    session, execute = _fake_session_with_rows([
        _row("n1"),
        _row("n2"),
    ])

    results = await ch.recall(
        "anything",  # query 在 metadata 通道被忽略
        _ner_with(domains=["smart_manufacturing"], levels=["course"]),
        tenant_id="t-3",
        session=session,
        top_k=5,
    )

    assert [r.node_id for r in results] == ["n1", "n2"]
    assert all(r.channel == "metadata" for r in results)
    assert all(r.domain == "smart_manufacturing" for r in results)
    assert all(r.level == "course" for r in results)
    # score 按 0.8 - idx*0.04 递减
    assert results[0].score == pytest.approx(0.8, abs=1e-4)
    assert results[1].score == pytest.approx(0.76, abs=1e-4)


@pytest.mark.asyncio
async def test_pg_metadata_recall_passes_domain_level_tenant_topk_to_sql():
    ch = PgMetadataRecallChannel()
    session, execute = _fake_session_with_rows([])

    await ch.recall(
        "x",
        _ner_with(domains=["smart_manufacturing"], levels=["course", "chapter"]),
        tenant_id="tenant-meta",
        session=session,
        top_k=3,
    )

    assert execute.await_count == 1
    stmt, params = execute.await_args.args
    assert "knowledge_nodes" in str(stmt)
    assert "domain IN" in str(stmt)
    assert "level IN" in str(stmt)
    assert params["tid"] == "tenant-meta"
    assert params["lim"] == 3
    assert params["d0"] == "smart_manufacturing"
    assert params["l0"] == "course"
    assert params["l1"] == "chapter"


@pytest.mark.asyncio
async def test_pg_metadata_recall_returns_empty_when_no_ner_signal():
    ch = PgMetadataRecallChannel()
    session, execute = _fake_session_with_rows([])

    results = await ch.recall(
        "anything",
        _ner_with(domains=[], levels=[]),
        tenant_id="t",
        session=session,
        top_k=5,
    )

    assert results == []
    assert execute.await_count == 0  # 早退，没有 SQL
