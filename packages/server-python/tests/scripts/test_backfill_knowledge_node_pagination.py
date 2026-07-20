"""TD-075: ``backfill_knowledge_node_embeddings`` pagination regression tests.

The old script used ``WHERE embedding IS NULL ORDER BY created_at LIMIT :limit
OFFSET :offset`` and incremented ``offset`` after each batch. Because each
successful UPDATE shrinks the result set, accumulating OFFSET skipped rows
that were still NULL. These tests prove the fix (re-query fresh each batch,
no OFFSET) and the remaining-count / non-zero-exit contract.

The mock ``_FakeDB`` simulates ``metaedu.knowledge_nodes`` in memory: it
tracks each row's embedding state so ``SELECT ... WHERE embedding IS NULL``
reflects UPDATEs made during the backfill - exactly the mutable-predicate
behavior the buggy OFFSET approach got wrong. No real PG / LLM is used.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.scripts.backfill_knowledge_node_embeddings import BackfillResult, backfill_loop


class _FakeDB:
    """In-memory simulation of ``metaedu.knowledge_nodes`` for backfill tests.

    Tracks each row's embedding state so ``SELECT ... WHERE embedding IS NULL``
    reflects UPDATEs made during the backfill - exactly the mutable-predicate
    behavior the buggy OFFSET approach got wrong.
    """

    def __init__(self, rows: list[dict]) -> None:
        # rows: [{"id": UUID, "title": str, "created_at": int}]
        # created_at defaults to the insertion index for a stable order.
        self._rows: dict[uuid.UUID, dict] = {}
        for i, r in enumerate(rows):
            self._rows[r["id"]] = {
                "id": r["id"],
                "title": r["title"],
                "created_at": r.get("created_at", i),
                "embedding": None,
            }
        # Captured UPDATE params (one entry per successful UPDATE call).
        self.updates: list[dict] = []

    def pending(
        self, limit: int, *, force: bool = False, offset: int = 0
    ) -> list[dict]:
        sorted_rows = sorted(self._rows.values(), key=lambda r: r["created_at"])
        filtered = (
            sorted_rows
            if force
            else [r for r in sorted_rows if r["embedding"] is None]
        )
        return [
            {"id": r["id"], "title": r["title"]}
            for r in filtered[offset : offset + limit]
        ]

    def count_null(self) -> int:
        return sum(1 for r in self._rows.values() if r["embedding"] is None)

    def count_all(self) -> int:
        return len(self._rows)

    def count_processable_remaining(self) -> int:
        return sum(
            1
            for r in self._rows.values()
            if r["embedding"] is None and (r["title"] or "")
        )

    def apply_update(self, node_id: uuid.UUID, emb_str: str) -> None:
        self._rows[node_id]["embedding"] = emb_str
        self.updates.append({"id": node_id, "emb": emb_str})


def _mock_session(db: _FakeDB, *, force: bool = False):
    """Build a mock AsyncSession that routes SQL to the in-memory ``_FakeDB``.

    Distinguishes the three SQL shapes the backfill loop emits:
    - ``SELECT COUNT(*) ... WHERE embedding IS NULL AND COALESCE(title,...)``
      -> remaining processable count (only queried when force=False)
    - ``SELECT COUNT(*) ... [WHERE embedding IS NULL]`` -> initial target count
    - ``SELECT id, title ... [WHERE embedding IS NULL] ORDER BY ... LIMIT``
      -> pending rows (with optional OFFSET for force=True)
    - ``UPDATE metaedu.knowledge_nodes SET embedding = ...`` -> apply_update
    """
    session = MagicMock()

    async def execute(stmt, params=None):
        stmt_str = str(stmt)
        if "SELECT COUNT(*)" in stmt_str:
            if "COALESCE" in stmt_str:
                count = db.count_processable_remaining()
            elif "WHERE embedding IS NULL" in stmt_str:
                count = db.count_null()
            else:
                count = db.count_all()
            r = MagicMock()
            r.scalar.return_value = count
            return r
        if "SELECT id, title" in stmt_str:
            limit = (params or {}).get("limit", 50)
            offset = (params or {}).get("offset", 0)
            rows = db.pending(limit, force=force, offset=offset)
            r = MagicMock()
            r.mappings.return_value.all.return_value = rows
            return r
        if "UPDATE metaedu.knowledge_nodes" in stmt_str:
            db.apply_update(params["id"], params["emb"])
            return MagicMock()
        return MagicMock()

    session.execute = AsyncMock(side_effect=execute)
    session.commit = AsyncMock()
    return session


# ─────────────────────────────────────────────────────────────────────────
# Test 1: >2 batches, every ID processed exactly once (no skip)
# ─────────────────────────────────────────────────────────────────────────


async def test_backfill_processes_all_rows_across_multiple_batches_without_skip() -> None:
    """125 rows / batch_size=50 -> 3 batches, all 125 IDs UPDATEd exactly once.

    TD-075 regression: the old OFFSET approach skipped rows because each
    successful UPDATE shrank the result set while OFFSET kept advancing.
    With the fix, re-querying ``WHERE embedding IS NULL LIMIT :limit`` each
    batch picks up the next pending row with no skip and no duplicate.
    """
    rows = [
        {"id": uuid.uuid4(), "title": f"node-{i}", "created_at": i}
        for i in range(125)
    ]
    db = _FakeDB(rows)
    session = _mock_session(db, force=False)

    async def fake_embedding(title: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    result = await backfill_loop(
        session, batch_size=50, force=False, embedding_fn=fake_embedding
    )

    assert result.total == 125
    assert result.skipped == 0
    assert result.failed == 0
    assert result.remaining == 0
    # Each ID should be UPDATEd exactly once (no skip, no duplicate).
    assert len(db.updates) == 125
    updated_ids = [u["id"] for u in db.updates]
    assert len(set(updated_ids)) == 125
    assert set(updated_ids) == {r["id"] for r in rows}


# ─────────────────────────────────────────────────────────────────────────
# Test 2: empty title does not block other rows
# ─────────────────────────────────────────────────────────────────────────


async def test_backfill_empty_title_does_not_block_other_rows() -> None:
    """A row with an empty title is skipped; other rows are still processed.

    The empty-title row stays NULL but is excluded from ``remaining``
    (processable) because it cannot be embedded. The run exits clean
    (remaining=0) since no processable row was left behind.
    """
    rows = [
        {"id": uuid.uuid4(), "title": "alpha", "created_at": 0},
        {"id": uuid.uuid4(), "title": "", "created_at": 1},
        {"id": uuid.uuid4(), "title": "gamma", "created_at": 2},
    ]
    db = _FakeDB(rows)
    session = _mock_session(db, force=False)

    async def fake_embedding(title: str) -> list[float]:
        return [0.1, 0.2]

    result = await backfill_loop(
        session, batch_size=50, force=False, embedding_fn=fake_embedding
    )

    assert result.total == 2
    assert result.skipped == 1
    assert result.failed == 0
    assert result.remaining == 0
    updated_ids = {u["id"] for u in db.updates}
    assert updated_ids == {rows[0]["id"], rows[2]["id"]}
    # Empty-title row was never UPDATEd.
    assert rows[1]["id"] not in updated_ids


# ─────────────────────────────────────────────────────────────────────────
# Test 3: provider returns empty for some rows -> skipped, remaining reported
# ─────────────────────────────────────────────────────────────────────────


async def test_backfill_provider_empty_for_some_rows_reports_remaining() -> None:
    """Provider returns None for some rows -> those skipped, others continue.

    ``remaining`` reports the processable rows still NULL (have a title but
    no embedding). The no-progress guard stops the loop once the same failed
    rows re-appear without any successful UPDATE.
    """
    rows = [
        {"id": uuid.uuid4(), "title": f"node-{i}", "created_at": i}
        for i in range(10)
    ]
    db = _FakeDB(rows)
    session = _mock_session(db, force=False)

    fail_titles = {"node-3", "node-5", "node-7"}

    async def fake_embedding(title: str) -> list[float] | None:
        if title in fail_titles:
            return None
        return [0.1, 0.2]

    result = await backfill_loop(
        session, batch_size=50, force=False, embedding_fn=fake_embedding
    )

    assert result.total == 7
    assert result.skipped == 3
    assert result.failed == 0
    assert result.remaining == 3
    updated_ids = {u["id"] for u in db.updates}
    assert len(updated_ids) == 7
    # Failed rows are exactly the ones whose titles were in fail_titles.
    failed_ids = {r["id"] for r in rows if r["title"] in fail_titles}
    assert updated_ids.isdisjoint(failed_ids)


# ─────────────────────────────────────────────────────────────────────────
# Test 4: partial failure + re-run -> converges
# ─────────────────────────────────────────────────────────────────────────


async def test_backfill_rerun_converges_after_partial_failure() -> None:
    """First run leaves some rows NULL; second run picks them up and converges.

    TD-075 contract: re-running the backfill converges to ``remaining=0``
    once the provider works for previously-failed rows. The same in-memory
    DB persists across both runs, so the second run's re-query only returns
    the rows the first run left NULL.
    """
    rows = [
        {"id": uuid.uuid4(), "title": f"node-{i}", "created_at": i}
        for i in range(10)
    ]
    fail_titles_run1 = {f"node-{i}" for i in range(6, 10)}

    # ── First run: provider fails for node-6..node-9 ──
    db = _FakeDB(rows)
    session1 = _mock_session(db, force=False)

    async def provider_run1(title: str) -> list[float] | None:
        if title in fail_titles_run1:
            return None
        return [0.1, 0.2]

    result1 = await backfill_loop(
        session1, batch_size=50, force=False, embedding_fn=provider_run1
    )

    assert result1.total == 6
    assert result1.skipped == 4
    assert result1.remaining == 4
    assert result1.remaining == result1.skipped  # all skipped are processable

    # ── Second run: provider now works for every row ──
    # Same db instance: rows 0-5 already have embeddings, only 6-9 remain.
    session2 = _mock_session(db, force=False)

    async def provider_run2(title: str) -> list[float]:
        return [0.3, 0.4]

    result2 = await backfill_loop(
        session2, batch_size=50, force=False, embedding_fn=provider_run2
    )

    assert result2.total == 4  # the 4 previously-failed rows
    assert result2.skipped == 0
    assert result2.failed == 0
    assert result2.remaining == 0  # converged


# ─────────────────────────────────────────────────────────────────────────
# Test 5 (bonus): single-row exception does not block other rows
# ─────────────────────────────────────────────────────────────────────────


async def test_backfill_single_row_exception_does_not_block_other_rows() -> None:
    """If the embedding call raises for one row, other rows are still processed.

    TD-075 completion criteria: "单行失败不得让成功行被跳过". The exception is
    caught, the row is counted as ``failed``, and the loop continues.
    """
    rows = [
        {"id": uuid.uuid4(), "title": "ok-1", "created_at": 0},
        {"id": uuid.uuid4(), "title": "boom", "created_at": 1},
        {"id": uuid.uuid4(), "title": "ok-2", "created_at": 2},
    ]
    db = _FakeDB(rows)
    session = _mock_session(db, force=False)

    async def fake_embedding(title: str) -> list[float]:
        if title == "boom":
            raise RuntimeError("provider exploded")
        return [0.1, 0.2]

    result = await backfill_loop(
        session, batch_size=50, force=False, embedding_fn=fake_embedding
    )

    assert result.total == 2
    assert result.failed == 1
    assert result.skipped == 0
    assert result.remaining == 1  # "boom" row still NULL with a title
    updated_ids = {u["id"] for u in db.updates}
    assert updated_ids == {rows[0]["id"], rows[2]["id"]}


# ─────────────────────────────────────────────────────────────────────────
# Test 6 (bonus): BackfillResult dataclass shape
# ─────────────────────────────────────────────────────────────────────────


def test_backfill_result_defaults() -> None:
    """BackfillResult defaults to all-zero stats."""
    r = BackfillResult()
    assert r.total == 0
    assert r.skipped == 0
    assert r.failed == 0
    assert r.remaining == 0
