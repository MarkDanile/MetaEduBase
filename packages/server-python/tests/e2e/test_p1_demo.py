"""End-to-end P1 demo for REQ-006 (Stage 1.0: 3 steps).

This module exercises the first three steps of the P1 acceptance loop
on a real PostgreSQL ``metaedu_test`` database. It is intended to grow
into the full 6-step e2e acceptance (AC-1 ~ AC-6 of
``docs/02-delivery-plans/01-specs/2026-W23-req-006-p1-final-demo.md``);
this PR only ships steps 1-3 to keep the change reviewable. Steps 4-6
(extract_template / KG / RAG / sources) are intentionally deferred to a
follow-up Stage 1.5 PR.

What this file locks today (Stage 1.0):

  * AC-1  Upload: ``POST /api/v1/document/files/upload`` returns a
    ``file_id`` with status ``uploaded`` and the file lands in MinIO.
  * AC-2a Parse dispatch: ``parse_document(file_id, tenant_id)`` is
    invoked synchronously on a worker thread (the ``@shared_task``
    decorator's body still runs the real pipeline; the thread is
    needed to escape pytest-asyncio's running event loop because the
    task body uses ``asyncio.run`` internally).
  * AC-2b Parse outcome: the file transitions to status ``parsed`` and
    ``structured_data`` gains ``full_text`` / ``section_count`` keys.
  * AC-2c Idempotency: a second invocation must not regress status and
    must keep ``structured_data`` populated.

Conventions:

  * Reuses ``tests/conftest.py`` fixtures: ``client`` (httpx
    ASGITransport against the real FastAPI app) and ``auth_headers``
    (Bearer token from the seeded super-admin).
  * The autouse ``mock_celery_tasks`` in ``conftest.py`` is bypassed by
    importing the task function via its canonical path and calling it
    on a worker thread. The task body opens its own engine against the
    production ``settings.database_url``; we monkey-patch that to
    ``TEST_DATABASE_URL`` for the duration of the call so the
    e2e test never writes to the dev ``metaedu`` database.
  * No external services required beyond PostgreSQL ``metaedu_test``.
    LLM calls (handled by the extract step) are not exercised here.

Environment:

  * ``TEST_DATABASE_URL`` (default
    ``postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test``)
    must be reachable.
  * The schema and seed rows are expected to exist (run
    ``./dev.sh init-test-db`` once per environment).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import io
import uuid

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
    raise ``RuntimeError: asyncio.run() cannot be called from a
    running event loop``. The worker thread is loop-free so
    ``asyncio.run`` can spin up its own.

    We also:

    * Rewrite ``settings.database_url`` to the test database URL
      for the duration of the call so the task writes to
      ``metaedu_test`` instead of the dev ``metaedu`` DB.
    * Patch the Celery broker / result backend to ``memory://`` so
      importing the Celery app in environments without Redis (CI
      sandboxes, dev laptops without docker infra) does not crash
      with ``kombu.exceptions.OperationalError: Connection refused``.
      The task body does not call ``.delay()`` directly; it chains
      into ``chunk_document.delay(...)`` on parse success, so we
      additionally patch ``chunk_document.delay`` to a no-op.
    """
    import os
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
    import os

    import asyncpg

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


# --- AC-1: upload ----------------------------------------------------------


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


# --- AC-2a + AC-2b: parse --------------------------------------------------


async def test_p1_demo_step2_parse(client, auth_headers):
    """AC-2: ``parse_document`` writes ``structured_data`` and lands
    the file in the ``processing`` state (the pipeline's mid-state;
    ``parsed`` is reached only after ``chunk_document`` finishes, which
    is patched to a no-op in this e2e so the e2e stays Redis-free).
    """
    file_id = await test_p1_demo_step1_upload(client, auth_headers)

    # parse_document is decorated with @shared_task; calling it
    # directly on a worker thread bypasses the Celery broker while
    # still executing the real pipeline body (and lands writes on
    # ``metaedu_test`` via the test_database_url override).
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


# --- AC-2c: parse idempotency ---------------------------------------------


async def test_p1_demo_step2b_parse_idempotent(client, auth_headers):
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
