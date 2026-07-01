"""TD-073: lock `_load_keypoint_cache` + `_save_keypoint_cache` integration in `coverage.py`.

Background:
- TD-073 added an offline persistent cache for keypoint embeddings
  (see `test_cache_store.py` for the storage layer; see
  `docs/02-delivery-plans/01-specs/2026-06-30-td-073-offline-keypoint-embedding.md`
  for the spec).
- This file locks the **integration points** in `coverage.py`:
  - `_load_keypoint_cache(questions, cache_dir, fixture_paths)` populates
    `_EMBEDDING_CACHE` from disk on startup.
  - `_get_cached_embeddings_batch` records misses to `_KEYPOINT_CACHE_PENDING`.
  - `_save_keypoint_cache(cache_dir, fixture_paths)` merges pending +
    in-memory and persists.

These are the behavior changes that future modifications must preserve.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# `rag_validation.coverage` lives in repo-root `scripts/rag_validation/`.
# `tests/scripts/rag_validation/conftest.py` injects REPO_ROOT + scripts/
# onto sys.path; this block is defensive in case conftest is bypassed.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from rag_validation import coverage  # noqa: E402
from rag_validation.models import Keypoint, Question  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Snapshot and restore `_EMBEDDING_CACHE` / `_KEYPOINT_CACHE_PENDING`
    around each test so global state doesn't leak between cases."""
    saved_cache = dict(coverage._EMBEDDING_CACHE)
    pending = getattr(coverage, "_KEYPOINT_CACHE_PENDING", None)
    saved_pending = dict(pending) if pending is not None else None
    coverage._EMBEDDING_CACHE.clear()
    if saved_pending is not None:
        coverage._KEYPOINT_CACHE_PENDING.clear()
    try:
        yield
    finally:
        coverage._EMBEDDING_CACHE.clear()
        coverage._EMBEDDING_CACHE.update(saved_cache)
        if saved_pending is not None and getattr(
            coverage, "_KEYPOINT_CACHE_PENDING", None
        ) is not None:
            coverage._KEYPOINT_CACHE_PENDING.clear()
            coverage._KEYPOINT_CACHE_PENDING.update(saved_pending)


@pytest.fixture
def tmp_fixture_paths(tmp_path: Path) -> list[Path]:
    """Two fixture files for cache_key computation."""
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    paths = []
    for name in ("req016.json", "req028.json"):
        p = fixture_dir / name
        p.write_text("{}", encoding="utf-8")
        paths.append(p)
    return sorted(paths)


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def _make_question(group: str, qid: str, keypoints: list[Keypoint]) -> Question:
    return Question(
        group=group,
        question_id=qid,
        text="dummy",
        expected={},
        expected_keypoints=keypoints,
    )


# ---------------------------------------------------------------------------
# A. _load_keypoint_cache — startup hook
# ---------------------------------------------------------------------------


class TestLoadKeypointCache:
    """Lock startup behavior: pre-existing cache files populate
    `_EMBEDDING_CACHE`; missing files are silent no-ops."""

    def test_load_populates_embedding_cache_from_disk(
        self, tmp_cache_dir: Path, tmp_fixture_paths: list[Path]
    ):
        """Pre-populate cache file → `_load_keypoint_cache` fills the
        in-memory cache so subsequent misses become hits."""
        cache_key = coverage._keypoint_cache_key(tmp_fixture_paths)
        coverage.cache_store.save(
            {"装饰器": [0.1, 0.2], "wrapper": [0.3, 0.4]},
            cache_key,
            tmp_cache_dir,
        )

        questions = [
            _make_question(
                "REQ-016",
                "Q1",
                [Keypoint(term="装饰器", synonyms=["wrapper"])],
            ),
        ]
        coverage._load_keypoint_cache(questions, tmp_cache_dir, tmp_fixture_paths)

        assert coverage._EMBEDDING_CACHE.get("装饰器") == [0.1, 0.2]
        assert coverage._EMBEDDING_CACHE.get("wrapper") == [0.3, 0.4]

    def test_load_with_no_existing_file_is_noop(
        self, tmp_cache_dir: Path, tmp_fixture_paths: list[Path]
    ):
        """Cache dir does not exist → silent no-op (no raise, cache empty)."""
        questions = [
            _make_question("REQ-016", "Q1", [Keypoint(term="装饰器")]),
        ]
        coverage._load_keypoint_cache(questions, tmp_cache_dir, tmp_fixture_paths)
        # In-memory cache stays empty; caller proceeds to build via HTTP.
        assert "装饰器" not in coverage._EMBEDDING_CACHE

    def test_load_with_cache_key_mismatch_is_noop(
        self, tmp_cache_dir: Path, tmp_fixture_paths: list[Path]
    ):
        """Cache file present but for different fixtures → silent miss
        (cache_key changed since last save)."""
        cache_key = coverage._keypoint_cache_key(tmp_fixture_paths)
        # Save with one cache_key, then mutate a fixture (mtime changes → new key).
        coverage.cache_store.save({"装饰器": [0.1]}, cache_key, tmp_cache_dir)
        import time as _time

        _time.sleep(0.01)
        tmp_fixture_paths[0].touch()  # mtime bump → cache_key changes

        questions = [
            _make_question("REQ-016", "Q1", [Keypoint(term="装饰器")]),
        ]
        coverage._load_keypoint_cache(questions, tmp_cache_dir, tmp_fixture_paths)
        # Different cache_key → save file ignored
        assert "装饰器" not in coverage._EMBEDDING_CACHE


# ---------------------------------------------------------------------------
# B. Miss accumulation into _KEYPOINT_CACHE_PENDING
# ---------------------------------------------------------------------------


class TestPendingCacheAccumulation:
    """Lock that miss paths in `_get_cached_embeddings_batch` record to
    `_KEYPOINT_CACHE_PENDING` for later persistence."""

    async def test_get_cached_embeddings_batch_records_miss_to_pending(
        self, tmp_cache_dir: Path, tmp_fixture_paths: list[Path]
    ):
        """A miss → batch fill → must write to `_KEYPOINT_CACHE_PENDING` so
        save can persist it later."""

        async def batch_embed(texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

        await coverage._get_cached_embeddings_batch(
            ["装饰器", "wrapper"], batch_embed, batch_size=10
        )

        # Both texts should be in pending (lowercased, since collect_unique_texts normalizes).
        assert coverage._KEYPOINT_CACHE_PENDING.get("装饰器") == [0.1, 0.2]
        assert coverage._KEYPOINT_CACHE_PENDING.get("wrapper") == [0.1, 0.2]

    async def test_cache_hit_does_not_write_to_pending(self):
        """Pre-populated in-memory cache → no pending entry written."""

        async def batch_embed(texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

        coverage._EMBEDDING_CACHE["hit_text"] = [0.5, 0.6]
        await coverage._get_cached_embeddings_batch(
            ["hit_text"], batch_embed, batch_size=10
        )
        # Hit path doesn't go through pending
        assert "hit_text" not in coverage._KEYPOINT_CACHE_PENDING


# ---------------------------------------------------------------------------
# C. _save_keypoint_cache — exit-time persistence
# ---------------------------------------------------------------------------


class TestSaveKeypointCache:
    """Lock that `_save_keypoint_cache` merges in-memory + pending and
    persists to disk. Failure modes are graceful (no raise)."""

    async def test_save_persists_merged_pending_and_in_memory(
        self, tmp_cache_dir: Path, tmp_fixture_paths: list[Path]
    ):
        """In-memory cache (hit on first run) + pending (newly added) →
        save writes the merged set to disk."""
        # In-memory cache: from a previous "hit"
        coverage._EMBEDDING_CACHE["existing"] = [0.7, 0.8]

        # Pending: from a fresh miss
        async def batch_embed(texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

        await coverage._get_cached_embeddings_batch(
            ["new_text"], batch_embed, batch_size=10
        )

        coverage._save_keypoint_cache(tmp_cache_dir, tmp_fixture_paths)

        cache_key = coverage._keypoint_cache_key(tmp_fixture_paths)
        loaded = coverage.cache_store.load(cache_key, tmp_cache_dir)
        assert loaded is not None
        assert loaded["existing"] == [0.7, 0.8]
        assert loaded["new_text"] == [0.1, 0.2]

    async def test_save_handles_empty_pending(
        self, tmp_cache_dir: Path, tmp_fixture_paths: list[Path]
    ):
        """No miss happened → save still writes the in-memory cache."""
        coverage._EMBEDDING_CACHE["only_memory"] = [0.9, 0.1]

        coverage._save_keypoint_cache(tmp_cache_dir, tmp_fixture_paths)

        cache_key = coverage._keypoint_cache_key(tmp_fixture_paths)
        loaded = coverage.cache_store.load(cache_key, tmp_cache_dir)
        assert loaded is not None
        assert loaded == {"only_memory": [0.9, 0.1]}

    async def test_save_handles_empty_in_memory_and_pending(
        self, tmp_cache_dir: Path, tmp_fixture_paths: list[Path]
    ):
        """Both empty → save writes empty dict (cache file exists but texts={})."""
        coverage._save_keypoint_cache(tmp_cache_dir, tmp_fixture_paths)

        cache_key = coverage._keypoint_cache_key(tmp_fixture_paths)
        loaded = coverage.cache_store.load(cache_key, tmp_cache_dir)
        assert loaded is not None
        assert loaded == {}


# ---------------------------------------------------------------------------
# D. End-to-end: load → run → save → load again
# ---------------------------------------------------------------------------


class TestEndToEndPersistence:
    """Lock the full persistence cycle: load from disk, process misses,
    save back, and verify second-run hits (i.e. the closed loop)."""

    async def test_second_run_hits_cached_texts(
        self, tmp_cache_dir: Path, tmp_fixture_paths: list[Path]
    ):
        """Run 1: cold cache → fills pending → save. Run 2: load → all hits."""
        # --- Run 1: cold start ---
        questions = [
            _make_question(
                "REQ-016",
                "Q1",
                [Keypoint(term="装饰器", synonyms=["wrapper"])],
            ),
        ]
        coverage._load_keypoint_cache(questions, tmp_cache_dir, tmp_fixture_paths)
        assert "装饰器" not in coverage._EMBEDDING_CACHE  # nothing preloaded

        async def batch_embed(texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

        await coverage._get_cached_embeddings_batch(
            ["装饰器", "wrapper"], batch_embed, batch_size=10
        )
        coverage._save_keypoint_cache(tmp_cache_dir, tmp_fixture_paths)

        # Reset in-memory state for run 2.
        coverage._EMBEDDING_CACHE.clear()
        coverage._KEYPOINT_CACHE_PENDING.clear()

        # --- Run 2: warm start ---
        coverage._load_keypoint_cache(questions, tmp_cache_dir, tmp_fixture_paths)
        assert coverage._EMBEDDING_CACHE.get("装饰器") == [0.1, 0.2]
        assert coverage._EMBEDDING_CACHE.get("wrapper") == [0.1, 0.2]

        # batch_embed would not be called because texts are already cached.
        call_log: list[list[str]] = []

        async def batch_embed_2(texts: list[str]) -> list[list[float]]:
            call_log.append(list(texts))
            return [[0.9, 0.9] for _ in texts]

        await coverage._get_cached_embeddings_batch(
            ["装饰器", "wrapper"], batch_embed_2, batch_size=10
        )
        # All hits → batch_embed_2 never invoked
        assert call_log == []
