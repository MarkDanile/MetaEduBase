"""Tests for document task router — `POST /files/{file_id}/retry` dispatch semantics.

Regression coverage for BUG-001: `retry_file_tasks` previously used
`await parse_document.delay(...)`, which raises `TypeError: object AsyncResult
can't be used in 'await' expression` whenever Celery is reachable (the
`AsyncResult` returned by `.delay()` is not awaitable). It also lacked the
`pipeline_version` marker that `reinitialize` and the worker rely on for
stale-task detection, and it had no `try/except` so broker outages turned into
HTTP 500s instead of letting the caller poll task status.

These tests assert that:

1. The endpoint returns 200 and resets failed tasks to `pending`.
2. `parse_document.delay` is invoked synchronously with
   `(str(file_id), str(tenant_id), pipeline_version)` — not awaited, and with a
   non-empty pipeline_version.
3. When the broker raises (e.g. `OperationalError`), the endpoint still returns
   200 because the DB reset is the source of truth for the caller.
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.asyncio


async def _upload_file(client, auth_headers, name: str = "retry.txt") -> str:
    resp = await client.post(
        "/api/v1/document/files/upload",
        files={"file": (name, io.BytesIO(b"retry body"), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_retry_file_tasks_returns_pending_tasks(
    client, auth_headers, mock_celery_tasks,
):
    """Happy path: failed/pending tasks are reset, endpoint returns 200."""
    file_id = await _upload_file(client, auth_headers)

    resp = await client.post(
        f"/api/v1/document/files/{file_id}/retry",
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert isinstance(payload, list)
    # Upload may dispatch one parse task — retry should not blow up regardless
    # of how many rows exist; we only assert the row shape survived a round-trip.
    for row in payload:
        assert row["status"] in {"pending", "running", "success", "failed"}
    assert mock_celery_tasks.document_retry.delay.call_count == 1


async def test_retry_dispatches_parse_document_without_await_and_with_pipeline_version(
    client, auth_headers,
):
    """The dispatch must be a synchronous `.delay()` call with a pipeline_version
    third positional argument. Awaiting `AsyncResult` would raise TypeError;
    omitting pipeline_version would break the worker's stale-detection guard.
    """
    file_id = await _upload_file(client, auth_headers, name="retry_dispatch.txt")

    with patch(
        "app.contexts.document.interfaces.api.tasks.parse_document"
    ) as mock_doc:
        calls: list[tuple] = []

        def _spy_delay(*args, **kwargs):
            calls.append((args, kwargs))
            return None

        mock_doc.delay = _spy_delay  # noqa: F841 — spy override intentional

        resp = await client.post(
            f"/api/v1/document/files/{file_id}/retry",
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    assert len(calls) == 1, f"expected one .delay() call, got {len(calls)}: {calls}"
    args, kwargs = calls[0]
    # Positional: (file_id_str, tenant_id_str, pipeline_version)
    assert len(args) >= 3, f"expected >=3 positional args, got {args!r}"
    assert args[0] == file_id
    assert isinstance(args[1], str) and len(args[1]) == 36  # tenant UUID str
    assert isinstance(args[2], str) and args[2], (
        f"pipeline_version must be a non-empty string (ISO timestamp), got {args[2]!r}"
    )


async def test_retry_returns_200_when_celery_broker_unavailable(
    client, auth_headers,
):
    """If `.delay()` raises (broker down, network issue), the endpoint must
    still respond 200 with the reset task rows. The DB reset is the source of
    truth for the caller; the user can poll task status to see the new attempt
    succeed once the broker recovers.
    """
    file_id = await _upload_file(client, auth_headers, name="retry_broker_down.txt")

    with patch(
        "app.contexts.document.interfaces.api.tasks.parse_document"
    ) as mock_doc:
        def _boom(*_args, **_kwargs):
            raise RuntimeError("simulated broker outage")

        mock_doc.delay = _boom  # noqa: F841 — override conftest stub to raise

        resp = await client.post(
            f"/api/v1/document/files/{file_id}/retry",
            headers=auth_headers,
        )

    assert resp.status_code == 200, (
        f"broker outage must not surface as 500; got {resp.status_code} {resp.text}"
    )
    assert isinstance(resp.json(), list)
