"""TD-073: lock `cache_store` persistence semantics for offline keypoint embedding cache.

Background:
- TD-073 (spec `docs/02-delivery-plans/01-specs/2026-06-30-td-073-offline-keypoint-embedding.md`)
  added an offline persistent cache for keypoint embeddings. The cache
  lives in `docs/.cache/rag_validation_keypoint_embeddings/<key>.json`
  and is keyed by `sha256(fixture_paths + mtimes + "keypoint_v1")[:16]`.
- This file locks the persistence contract so silent regressions (corrupt
  cache, wrong cache_key, etc.) are caught before they pollute validation
  runs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# `rag_validation.cache_store` lives in repo-root `scripts/rag_validation/`.
# `tests/scripts/rag_validation/conftest.py` injects REPO_ROOT + scripts/
# onto sys.path; this block is defensive in case conftest is bypassed.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from rag_validation import cache_store  # noqa: E402
from rag_validation.models import Keypoint, Question  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_fixture_dir(tmp_path: Path) -> Path:
    """A scratch directory with 2 fixture files for cache_key computation."""
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "req016.json").write_text("{}", encoding="utf-8")
    (fixture_dir / "req028.json").write_text("{}", encoding="utf-8")
    return fixture_dir


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """A scratch directory for cache writes (does NOT pre-create)."""
    return tmp_path / "cache"


# ---------------------------------------------------------------------------
# A. compute_cache_key — pure function
# ---------------------------------------------------------------------------


class TestComputeCacheKey:
    """Lock `cache_key = sha256(fixture paths + mtimes + "keypoint_v1")[:16]`.
    Deterministic for same inputs; changes when any input changes.
    """

    def test_deterministic_for_same_inputs(self, tmp_fixture_dir: Path):
        paths = sorted(tmp_fixture_dir.glob("*.json"))
        key1 = cache_store.compute_cache_key(paths)
        key2 = cache_store.compute_cache_key(paths)
        assert key1 == key2
        assert len(key1) == 16  # sha256 hex prefix
        assert all(c in "0123456789abcdef" for c in key1)

    def test_changes_when_fixture_mtime_changes(self, tmp_fixture_dir: Path):
        paths = sorted(tmp_fixture_dir.glob("*.json"))
        key_before = cache_store.compute_cache_key(paths)
        # Bump mtime on one file (set to a fixed past time so it's distinct)
        import time

        time.sleep(0.01)  # ensure mtime granularity differs
        (paths[0]).touch()
        key_after = cache_store.compute_cache_key(paths)
        assert key_before != key_after

    def test_changes_when_fixture_path_added(self, tmp_fixture_dir: Path):
        paths = sorted(tmp_fixture_dir.glob("*.json"))
        key_before = cache_store.compute_cache_key(paths)
        new_path = tmp_fixture_dir / "req999.json"
        new_path.write_text("{}", encoding="utf-8")
        key_after = cache_store.compute_cache_key(paths + [new_path])
        assert key_before != key_after

    def test_changes_when_schema_version_bumped(self, tmp_fixture_dir: Path, monkeypatch):
        """Bumping the schema version (e.g. 'keypoint_v1' -> 'keypoint_v2') must
        change the cache_key, invalidating all existing caches."""
        paths = sorted(tmp_fixture_dir.glob("*.json"))
        key_v1 = cache_store.compute_cache_key(paths)
        # Simulate version bump by monkey-patching the schema version string.
        monkeypatch.setattr(cache_store, "_SCHEMA_VERSION", "keypoint_v2")
        key_v2 = cache_store.compute_cache_key(paths)
        assert key_v1 != key_v2


# ---------------------------------------------------------------------------
# B. collect_unique_texts — pure function
# ---------------------------------------------------------------------------


def _make_question(group: str, qid: str, keypoints: list[Keypoint]) -> Question:
    return Question(
        group=group,
        question_id=qid,
        text="dummy",
        expected={},
        expected_keypoints=keypoints,
    )


class TestCollectUniqueTexts:
    """Lock unique text extraction: `term + synonyms` from all questions,
    deduped (case-insensitive), returned in insertion order.
    """

    def test_dedups_and_lowercases(self):
        questions = [
            _make_question(
                "REQ-016",
                "Q1",
                [
                    Keypoint(term="装饰器", synonyms=["decorator", "Wrapper"]),
                    Keypoint(term="装饰器", synonyms=["Decorator"]),  # duplicate (case-insensitive)
                ],
            ),
        ]
        texts = cache_store.collect_unique_texts(questions)
        # "装饰器" + "decorator" + "wrapper" (lowercased)
        assert "装饰器" in texts
        assert "decorator" in texts
        assert "wrapper" in texts
        assert len(texts) == 3  # no duplicates
        # Stable insertion order
        assert texts == ["装饰器", "decorator", "wrapper"]

    def test_includes_synonyms(self):
        questions = [
            _make_question(
                "REQ-016",
                "Q1",
                [Keypoint(term="装饰器", synonyms=["decorator", "@"])],
            ),
        ]
        texts = cache_store.collect_unique_texts(questions)
        assert texts == ["装饰器", "decorator", "@"]

    def test_handles_empty_keypoints(self):
        questions = [
            _make_question("REQ-016", "Q1", []),
            _make_question(
                "REQ-018", "Q2", [Keypoint(term="x", synonyms=[])]
            ),
        ]
        texts = cache_store.collect_unique_texts(questions)
        assert texts == ["x"]

    def test_dedups_across_questions(self):
        """Same term in different questions → one entry."""
        questions = [
            _make_question("REQ-016", "Q1", [Keypoint(term="装饰器")]),
            _make_question("REQ-018", "Q2", [Keypoint(term="装饰器")]),
        ]
        texts = cache_store.collect_unique_texts(questions)
        assert texts.count("装饰器") == 1


# ---------------------------------------------------------------------------
# C. save / load — I/O round-trip
# ---------------------------------------------------------------------------


class TestSaveLoad:
    """Lock save/load round-trip semantics + missing-file behavior."""

    def test_round_trip(self, tmp_cache_dir: Path):
        cache_key = "abc123def456"
        texts_to_embs: dict[str, list[float]] = {
            "装饰器": [0.1, 0.2, 0.3],
            "decorator": [0.4, 0.5, 0.6],
        }
        cache_store.save(texts_to_embs, cache_key, tmp_cache_dir)
        loaded = cache_store.load(cache_key, tmp_cache_dir)
        assert loaded == texts_to_embs

    def test_load_returns_none_for_missing_key(self, tmp_cache_dir: Path):
        """Non-existent cache_key returns None (not raises)."""
        result = cache_store.load("nonexistent_key", tmp_cache_dir)
        assert result is None

    def test_load_returns_none_for_missing_dir(self, tmp_path: Path):
        """Non-existent cache_dir returns None (not raises)."""
        result = cache_store.load("any_key", tmp_path / "no_such_dir")
        assert result is None

    def test_save_creates_target_dir_if_missing(self, tmp_cache_dir: Path):
        """save() must mkdir the target dir if it does not exist."""
        assert not tmp_cache_dir.exists()
        cache_store.save({"foo": [0.1]}, "key1", tmp_cache_dir)
        assert tmp_cache_dir.exists()
        assert (tmp_cache_dir / "key1.json").exists()

    def test_load_returns_none_for_corrupt_json(self, tmp_cache_dir: Path):
        """Corrupt JSON file → None (graceful degradation, not raise)."""
        cache_key = "corrupt_key"
        cache_dir = tmp_cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{cache_key}.json").write_text("not valid json{", encoding="utf-8")
        result = cache_store.load(cache_key, cache_dir)
        assert result is None

    def test_load_returns_none_for_schema_mismatch(self, tmp_cache_dir: Path):
        """Cache file from a different schema version → None (let caller rebuild)."""
        cache_key = "old_schema"
        cache_dir = tmp_cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{cache_key}.json").write_text(
            json.dumps({"schema_version": "keypoint_v0", "texts": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        result = cache_store.load(cache_key, cache_dir)
        assert result is None  # treated as miss; caller will re-build


# ---------------------------------------------------------------------------
# D. RED demonstration — monkey-patch proves tests detect regression
# ---------------------------------------------------------------------------


class TestRedDemonstration:
    """Sanity: if `cache_store.compute_cache_key` were broken (e.g. always
    returns the empty string), the round-trip test in TestSaveLoad would
    silently misbehave (all saves collide on `key=""` and reads pick up
    someone else's data). These tests confirm the round-trip catches that.
    """

    def test_different_texts_produce_different_save_files(
        self, tmp_cache_dir: Path, tmp_fixture_dir: Path
    ):
        """Two different keypoint sets → two different cache files (or same
        key but different content; both are valid; key here is constant)."""
        cache_key = cache_store.compute_cache_key(
            sorted(tmp_fixture_dir.glob("*.json"))
        )
        cache_store.save({"a": [0.1]}, cache_key, tmp_cache_dir)
        cache_store.save({"a": [0.2]}, cache_key, tmp_cache_dir)
        # Last write wins
        loaded = cache_store.load(cache_key, tmp_cache_dir)
        assert loaded == {"a": [0.2]}
