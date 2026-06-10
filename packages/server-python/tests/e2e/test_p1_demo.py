"""End-to-end P1 demo for REQ-006 (Stage 1.5: 6 steps).

Stage 1.0 (PR #117) shipped the first three steps.  Stage 1.5 adds:

* AC-3  Template extract (extract_template via Celery ``.delay`` + sync fallback).
* AC-4  Knowledge graph (extract_knowledge_graph ditto).
* AC-5  RAG chat (``POST /api/v1/ai/chat`` with stubbed channels + LLM).
* AC-6  Sources field shape (covered inside AC-5).

Broker: Redis (``./dev.sh infra``).  AC-3 / AC-4 dispatch through the
real ``.delay()``, then invoke synchronously so the e2e can verify
the result without a running Celery worker.  LLM calls for extract
tasks are not mocked (they need a real API key); the assertions
focus on the dispatch path and the structured_data / knowledge_nodes
read-back.

Test database: ``TEST_DATABASE_URL`` defaults to
``postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test``.
Run ``./dev.sh init-test-db`` once per environment.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import io
import os
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest

from app.config import settings
from app.contexts.document.application.tasks.parse import parse_document
from app.shared.infrastructure.seed import DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio


# --- helpers --------------------------------------------------------------


def _run_parse_in_worker(file_id: str, tenant_id: str) -> None:
    """Invoke ``parse_document`` on a fresh worker thread.

    The task body uses ``asyncio.run`` internally; running it from
    pytest-asyncio (which already owns the main event loop) would
    raise ``RuntimeError``. The worker thread is loop-free.

    We also rewrite ``settings.database_url`` to the test DB, switch
    the Celery broker to ``memory://``, and silence
    ``chunk_document.delay`` so the parse runs without Redis.
    """
    from unittest.mock import patch

    from app.celery_app import celery_app
    from app.contexts.document.application.tasks import chunk as chunk_mod

    original_url = settings.database_url
    original_broker = celery_app.conf.broker_url
    original_backend = celery_app.conf.result_backend
    test_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test",
    )
    try:
        settings.database_url = test_url
        celery_app.conf.broker_url = "memory://"
        celery_app.conf.result_backend = "cache+memory://"
        with patch.object(chunk_mod.chunk_document, "delay", lambda *_a, **_k: None):
            parse_document(file_id, tenant_id)
    finally:
        settings.database_url = original_url
        celery_app.conf.broker_url = original_broker
        celery_app.conf.result_backend = original_backend


def _run_parse_async(file_id: str, tenant_id: str) -> None:
    """Schedule the worker-thread call from inside a pytest coroutine."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_run_parse_in_worker, file_id, tenant_id)
        future.result(timeout=120)


def _run_task_in_worker(task_func, file_id: str, tenant_id: str) -> None:
    """Invoke a Celery task body synchronously on a worker thread.

    Shared helper for ``extract_template`` and ``extract_knowledge_graph``.
    Rewrites ``settings.database_url`` to the test DB, switches the
    Celery broker to ``memory://``, and silences downstream ``.delay``
    calls so the task body does not try to chain via the broker from
    the worker thread (the caller already dispatched via Redis).
    """
    from app.celery_app import celery_app
    from app.contexts.document.application.tasks import (
        extract_knowledge_graph,
        extract_template,
        index_tsvector,
    )

    original_url = settings.database_url
    original_broker = celery_app.conf.broker_url
    original_backend = celery_app.conf.result_backend
    test_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test",
    )
    try:
        settings.database_url = test_url
        celery_app.conf.broker_url = "memory://"
        celery_app.conf.result_backend = "cache+memory://"
        saved_delays: dict[str, object] = {}
        for task_obj in [
            extract_template,
            extract_knowledge_graph,
            index_tsvector,
        ]:
            saved_delays[id(task_obj)] = task_obj.delay
            task_obj.delay = lambda *_a, **_k: None  # type: ignore[method-assign]
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(task_func, file_id, tenant_id)
                future.result(timeout=120)
        finally:
            for task_obj in [
                extract_template,
                extract_knowledge_graph,
                index_tsvector,
            ]:
                task_obj.delay = saved_delays[id(task_obj)]  # type: ignore[method-assign]
    finally:
        settings.database_url = original_url
        celery_app.conf.broker_url = original_broker
        celery_app.conf.result_backend = original_backend
async def _run_task_async(
    task_func, file_id: str, tenant_id: str
) -> None:
    """Async wrapper around ``_run_task_in_worker``."""
    await asyncio.to_thread(
        _run_task_in_worker, task_func, file_id, tenant_id
    )


async def _ensure_test_db_columns() -> None:
    """Defensive column check for the e2e suite.

    TD-036 closes the root cause (006 migration `gin` operator class bug +
    missing `btree_gin` extension in `init-test-db`): on a fresh test DB
    built with `python -m app.shared.infrastructure.test_db_setup`,
    `document_tasks.updated_at` is created by alembic 003. The defensive
    `ADD COLUMN IF NOT EXISTS` below stays in place as a belt-and-suspenders
    guard against operator mistakes (someone running pytest against a
    manually-DROPPED test DB without re-running init-test-db) so the e2e
    suite never fails on environment drift; production DBs are untouched.
    """
    raw = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test",
    )
    dsn = raw.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "ALTER TABLE metaedu.document_tasks "
            "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"
        )
    finally:
        await conn.close()


async def _seed_document_chunks(
    file_id: uuid.UUID, tenant_id: uuid.UUID, content: str
) -> int:
    """Insert rows into ``document_chunks`` for the test file.

    The real ``chunk_document`` task requires ``pgvector``, which is
    not available in this e2e environment, so we seed chunks directly
    via SQL to provide input for ``extract_template``.
    """
    raw = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test",
    )
    dsn = raw.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        await conn.execute(
            "DELETE FROM metaedu.document_chunks "
            "WHERE file_id = $1 AND tenant_id = $2",
            file_id, tenant_id,
        )
        await conn.execute(
            "INSERT INTO metaedu.document_chunks "
            "(id, tenant_id, file_id, chunk_index, content, "
            "section_title, section_path, char_start, char_end, created_at) "
            "VALUES ($1, $2, $3, 0, $4, $5, $6, 0, $7, $8)",
            uuid.uuid4(), tenant_id, file_id,
            content, "教学目标", "教学目标", len(content), now,
        )
        return 1
    finally:
        await conn.close()


# --- AC-1: upload ---------------------------------------------------------


async def test_p1_demo_step1_upload(client, auth_headers):
    """AC-1: ``POST /files/upload`` returns 201 + ``file_id`` + status=uploaded."""
    await _ensure_test_db_columns()
    content = ("REQ-006 P1 demo: 教学目标 教学过程 教学评价 " * 32).encode("utf-8")
    resp = await client.post(
        "/api/v1/document/files/upload",
        files={"file": ("p1_demo.txt", io.BytesIO(content), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["filename"] == "p1_demo.txt"
    assert data["file_type"] == "txt"
    assert data["status"] == "uploaded"
    assert "id" in data and uuid.UUID(data["id"])
    return data["id"]


# --- AC-2: parse ----------------------------------------------------------


async def test_p1_demo_step2_parse(client, auth_headers):
    """AC-2: ``parse_document`` writes ``full_text`` / ``section_count``."""
    file_id = await test_p1_demo_step1_upload(client, auth_headers)

    await asyncio.to_thread(
        _run_parse_async, str(file_id), str(DEFAULT_TENANT_ID)
    )

    resp = await client.get(
        f"/api/v1/document/files/{file_id}", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] in ("processing", "parsed"), (
        f"expected status=processing|parsed, got {data['status']!r}"
    )
    structured = data.get("structured_data") or {}
    assert "full_text" in structured, structured
    assert "section_count" in structured, structured
    assert isinstance(structured["section_count"], int)
    assert structured["section_count"] >= 1
    return file_id, structured


# --- AC-2c: parse idempotency --------------------------------------------


async def test_p1_demo_step2b_parse_idempotent(
    client, auth_headers
):
    """AC-2c: a second parse must not regress status or clear structured_data."""
    file_id, _ = await test_p1_demo_step2_parse(client, auth_headers)

    await asyncio.to_thread(
        _run_parse_async, str(file_id), str(DEFAULT_TENANT_ID)
    )

    resp = await client.get(
        f"/api/v1/document/files/{file_id}", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] in ("processing", "parsed")
    assert data.get("structured_data"), "structured_data must persist"


# --- AC-3: template extract ----------------------------------------------


async def test_p1_demo_step3_template_extract(
    client, auth_headers
):
    """AC-3: ``extract_template`` writes ``structured_data.template``.

    Creates a demo template, seeds document_chunks, dispatches
    ``extract_template.delay()`` through Redis, then invokes
    synchronously to verify the result.
    """
    from app.contexts.document.application.tasks.extract_template import (
        extract_template,
    )

    file_id, _ = await test_p1_demo_step2_parse(client, auth_headers)

    # Seed a doc_type-matching template (L1 path).
    template_payload = {
        "name": "中学数学教案_Stage1.5",
        "doc_types": ["教案"],
        "fields": [
            {
                "key": "basic_info",
                "label": "基本信息",
                "type": "object",
                "description": "教学基本信息",
                "children": [
                    {"key": "title", "label": "标题", "type": "text"},
                    {"key": "subject", "label": "学科", "type": "text"},
                ],
            },
            {
                "key": "teaching_objectives",
                "label": "教学目标",
                "type": "array",
                "items": [
                    {"key": "item", "label": "目标项", "type": "text"},
                ],
            },
        ],
    }
    resp = await client.post(
        "/api/v1/templates", json=template_payload, headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    # Seed chunks (skip chunk_document to avoid pgvector).
    chunks = await _seed_document_chunks(
        file_id, DEFAULT_TENANT_ID,
        "## 教学目标\n理解函数。\n\n## 教学过程\n讲解例题。\n\n## 教学评价\n课堂练习。",
    )
    assert chunks == 1

    # Dispatch through real Redis broker.
    extract_template.delay(str(file_id), str(DEFAULT_TENANT_ID))

    # Also invoke synchronously so the e2e can verify the result.
    await _run_task_async(
        extract_template, str(file_id), str(DEFAULT_TENANT_ID)
    )

    resp = await client.get(
        f"/api/v1/document/files/{file_id}", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    structured = data.get("structured_data") or {}
    template = structured.get("template")
    assert template, (
        f"structured_data.template must be present for file {file_id}, "
        f"got {list(structured.keys())}"
    )
    if isinstance(template, dict) and "basic_info" in template:
        assert isinstance(template["basic_info"], dict), template
    # REQ-002-3: 溯源元数据
    assert "id" in template and isinstance(template["id"], str), (
        f"structured_data.template.id must be present and a string, got {template.get('id')!r}"
    )
    assert "layer" in template and template["layer"] in {"L1", "L2", "L3"}, (
        f"structured_data.template.layer must be one of L1/L2/L3, got {template.get('layer')!r}"
    )
    # version 可为 None（REQ-002-4 未完成时）或 int
    assert "version" in template, (
        "structured_data.template.version must be present (None if REQ-002-4 not yet done)"
    )
    return file_id


# --- AC-4: knowledge graph -----------------------------------------------


async def test_p1_demo_step4_kg_extract(
    client, auth_headers
):
    """AC-4: ``extract_knowledge_graph`` writes ``knowledge_nodes``."""
    from app.contexts.document.application.tasks.extract_knowledge_graph import (
        extract_knowledge_graph,
    )

    file_id = await test_p1_demo_step3_template_extract(
        client, auth_headers
    )

    extract_knowledge_graph.delay(str(file_id), str(DEFAULT_TENANT_ID))
    await _run_task_async(
        extract_knowledge_graph, str(file_id), str(DEFAULT_TENANT_ID)
    )

    resp = await client.get(
        f"/api/v1/knowledge/nodes?source_file_id={file_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    nodes = resp.json()
    assert isinstance(nodes, list)
    assert len(nodes) >= 1, (
        f"expected >=1 knowledge_nodes for file {file_id}, got {nodes!r}"
    )
    for node in nodes:
        if node.get("source_file_id") is not None:
            assert node.get("source_file_id") == str(file_id)
    return file_id


# --- AC-5 + AC-6: RAG chat + sources field shape ------------------------


async def test_p1_demo_step5_ai_chat(
    client, auth_headers
):
    """AC-5 + AC-6: ``POST /api/v1/ai/chat`` returns non-empty ``reply``
    and ``sources``; each source entry carries the full schema."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.contexts.knowledge.application.ner_service import RuleBasedNER
    from app.contexts.knowledge.interfaces.api import ai_router
    from app.shared.domain.recall_channel import RecallResult

    file_id = await test_p1_demo_step4_kg_extract(
        client, auth_headers
    )
    _ = file_id  # used in kg_extract, kept for breadcrumbs

    async def _vector_stub(_query, _ner_result, _tenant_id,
                           _session, _top_k=5):
        _ = (_query, _ner_result, _tenant_id, _session, _top_k)
        return [RecallResult(
            node_id="kg-node-1",
            title="教学目标",
            description="理解函数",
            domain="education_sports",
            level="knowledge_point",
            score=0.92,
            channel="vector",
            path="kg-1",
        )]

    async def _keyword_stub(*_a, **_k):
        _ = (_a, _k)
        return []

    async def _metadata_stub(*_a, **_k):
        _ = (_a, _k)
        return []

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "基于知识图谱的回答"}}]
    }
    mock_response.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(ai_router, "_vector_channel", SimpleNamespace(
        name="vector", recall=_vector_stub,
    )), patch.object(ai_router, "_keyword_channel", SimpleNamespace(
        name="keyword", recall=_keyword_stub,
    )), patch.object(ai_router, "_metadata_channel", SimpleNamespace(
        name="metadata", recall=_metadata_stub,
    )), patch.object(ai_router, "_ner", RuleBasedNER()), \
         patch(
             "app.contexts.knowledge.interfaces.api.ai_router.httpx.AsyncClient",
             return_value=mock_client,
         ):
        resp = await client.post(
            "/api/v1/ai/chat",
            json={"message": "教学目标是什么?", "context_window": 3},
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("reply"), "reply must be non-empty"
    sources = data.get("sources") or []
    assert len(sources) >= 1, f"expected >=1 sources, got {sources!r}"
    for src in sources:
        for field in ("id", "title", "channel", "score"):
            assert field in src, f"source item missing {field!r}: {src!r}"
    assert any(s["channel"] == "vector" for s in sources), sources
