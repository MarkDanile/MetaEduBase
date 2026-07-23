"""TD-055: cleanup_orphan_chunks task must return the deleted row count.

The task body builds a `_do(session)` coroutine that returns the SQL
rowcount of the DELETE statement. `run_in_session` already passes the
coroutine's return value back through (`return await coro(session)`).
The bug was at the outer call site — `asyncio.run(_run_in_session(_do))`
discarded the return value, so direct callers (and any sync tests)
got `None` instead of the deleted count.

We don't need a real DB. We patch `asyncio.run` to return a known int
to simulate the whole async chain returning that value. This way the
test only exercises the outer `asyncio.run(...)` call at the task
site — the actual fix target.

Note: pytest may emit a `RuntimeWarning: coroutine ... was never awaited`
during garbage collection. This is a benign mock side-effect: patching
`asyncio.run` means the inner `_run_in_session(_do)` coroutine is
created but never driven to completion (since `asyncio.run` returns
our fake int directly). The real production path runs the coroutine
to completion. The warning is filtered at the module level below.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.contexts.document.application.tasks import rebuild_chunks

# Filter the gc coroutine-not-awaited warning that arises from mocking
# asyncio.run. Production code awaits the coroutine; tests do not.
pytestmark = pytest.mark.filterwarnings(
    "ignore::RuntimeWarning",
)


_TENANT_STR = "00000000-0000-0000-0000-000000000001"


def test_cleanup_orphan_chunks_returns_deleted_rowcount() -> None:
    """`cleanup_orphan_chunks` must return the int that the inner
    async chain yields, not None.

    Without TD-055 fix, the outer `asyncio.run(_run_in_session(_do))`
    call discards the result — caller gets None.
    """
    with patch("asyncio.run", side_effect=lambda c, r=42: (c.close(), r)[1]):
        result = rebuild_chunks.cleanup_orphan_chunks(_TENANT_STR)

    assert result == 42, (
        f"cleanup_orphan_chunks must return the deleted rowcount; "
        f"got {result!r} (None means asyncio.run's return was discarded)"
    )
    assert isinstance(result, int), (
        f"return type must be int, got {type(result).__name__}"
    )


def test_cleanup_orphan_chunks_zero_returns_zero() -> None:
    """When no orphans exist, the return value is 0 (idempotent re-run)."""
    with patch("asyncio.run", side_effect=lambda c, r=0: (c.close(), r)[1]):
        result = rebuild_chunks.cleanup_orphan_chunks(_TENANT_STR)

    assert result == 0
    assert isinstance(result, int)


def test_cleanup_orphan_chunks_zero_does_not_return_none() -> None:
    """Regression lock against the exact TD-055 bug."""
    for fake_deleted in (0, 1, 7, 100, 1000):
        with patch("asyncio.run", side_effect=lambda c, r=fake_deleted: (c.close(), r)[1]):
            result = rebuild_chunks.cleanup_orphan_chunks(_TENANT_STR)
        assert result is not None, (
            f"cleanup_orphan_chunks returned None for deleted={fake_deleted}; "
            f"this is the TD-055 bug"
        )
        assert result == fake_deleted


def test_cleanup_orphan_chunks_accepts_uuid_string() -> None:
    """Locks the task signature accepts UUID-string tenant_id_str."""
    parsed = uuid.UUID(_TENANT_STR)
    assert parsed is not None  # sanity: this UUID parses

    with patch("asyncio.run", side_effect=lambda c, r=5: (c.close(), r)[1]):
        result = rebuild_chunks.cleanup_orphan_chunks(_TENANT_STR)
    assert result == 5
