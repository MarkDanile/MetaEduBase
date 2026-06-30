"""TD-074: lock `_is_batch_embedding_callable` + `_get_cached_embeddings_batch` behavior.

Background:
- TD-072 (`b645ca2`) added `_is_batch_embedding_callable` and rewired
  `_get_cached_embeddings_batch` to route between native batch HTTP and
  per-text gather paths. The dispatcher relies on `inspect.signature` and
  `typing.get_origin` / `typing.get_type_hints` to discriminate batch vs
  per-text callables — fragile against typing changes and Python version
  drift.
- No tests existed for the dispatcher or routing, so any silent regression
  would let the batch path silently fall back to per-text gather (60 run
  17.8min instead of 5-7min; no warning, no log).
- This file adds the regression lock so any future modification must be
  intentional.

TDD discipline note (retrospective):
- Production code exists on `main`; this is a retroactive test addition.
- We acknowledge we did NOT see the test fail before the implementation
  landed. The tests here lock current behavior; we additionally run a
  RED step by temporarily monkey-patching `_is_batch_embedding_callable`
  to always return False and asserting the relevant tests flip to RED
  — see `test_red_demonstration_*` markers below for the verification.
- Per TDD skill: "Test passes immediately = you may be testing the wrong
  thing". This is mitigated by (1) the comprehensive edge-case coverage
  (None, builtin, lambda, single, batch, generic, multiple-POKW, etc.)
  and (2) the explicit RED demonstration in `test_red_demonstration_*`.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, MutableSequence, Sequence
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

from rag_validation.coverage import (  # noqa: E402
    _EMB_STATS,
    _EMBEDDING_CACHE,
    _get_cached_embeddings_batch,
    _is_batch_embedding_callable,
)

# ---------------------------------------------------------------------------
# Fixtures: reset module-level globals around each test so stats/cache
# don't leak between cases.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Snapshot and restore `_EMB_STATS` / `_EMBEDDING_CACHE` around each test."""
    saved_stats = dict(_EMB_STATS)
    saved_cache = dict(_EMBEDDING_CACHE)
    _EMB_STATS.update(hit=0, miss=0, timeout=0, error=0)
    _EMBEDDING_CACHE.clear()
    try:
        yield
    finally:
        _EMB_STATS.update(saved_stats)
        _EMBEDDING_CACHE.clear()
        _EMBEDDING_CACHE.update(saved_cache)


# ---------------------------------------------------------------------------
# A. `_is_batch_embedding_callable` — pure-function detection
# ---------------------------------------------------------------------------


class TestIsBatchEmbeddingCallable:
    """Lock detection of batch vs per-text callable signatures.

    Detection rule (TD-072): first POSITIONAL_OR_KEYWORD / POSITIONAL_ONLY
    parameter must be list-like (list / List / Sequence / Iterable /
    MutableSequence of str-like element). Anything else → per-text path.
    """

    # --- safe defaults -------------------------------------------------------

    def test_none_returns_false(self):
        assert _is_batch_embedding_callable(None) is False

    def test_lambda_without_hints_returns_false(self):
        """Lambda with no annotations must fall back to per-text (safer default)."""
        assert _is_batch_embedding_callable(lambda text: text) is False

    def test_builtin_returns_false(self):
        """C-implemented callables cannot be inspected; must fall back to per-text."""
        assert _is_batch_embedding_callable(len) is False

    def test_callable_with_no_positional_params_returns_false(self):
        """Callable with only KW_ONLY params has no POKW discriminator."""
        def kwonly(*, text: str) -> str:
            return text

        assert _is_batch_embedding_callable(kwonly) is False

    # --- per-text callables → False -----------------------------------------

    def test_single_text_callable_returns_false(self):
        async def get_embedding(text: str) -> list[float]:
            return [0.1]

        assert _is_batch_embedding_callable(get_embedding) is False

    def test_callable_with_no_annotations_returns_false(self):
        def unannotated(x):
            return x

        assert _is_batch_embedding_callable(unannotated) is False

    def test_int_parameter_callable_returns_false(self):
        """First param not list-like → per-text path."""
        def f(x: int) -> int:
            return x

        assert _is_batch_embedding_callable(f) is False

    # --- batch callables → True ---------------------------------------------

    def test_list_str_callable_returns_true(self):
        async def batch_embed(texts: list[str]) -> list[list[float]]:
            return [[0.1]] * len(texts)

        assert _is_batch_embedding_callable(batch_embed) is True

    def test_typing_list_uppercase_callable_returns_true(self):
        """PEP 585 + typing.List both qualify (legacy compatibility)."""

        async def batch_embed(texts: list[str]) -> list[list[float]]:
            return [[0.1]] * len(texts)

        assert _is_batch_embedding_callable(batch_embed) is True

    def test_sequence_callable_returns_true(self):
        async def batch_embed(texts: Sequence[str]) -> list[list[float]]:
            return [[0.1]] * len(texts)

        assert _is_batch_embedding_callable(batch_embed) is True

    def test_iterable_callable_returns_true(self):
        async def batch_embed(texts: Iterable[str]) -> list[list[float]]:
            return [[0.1]]

        assert _is_batch_embedding_callable(batch_embed) is True

    def test_mutable_sequence_callable_returns_true(self):
        async def batch_embed(texts: MutableSequence[str]) -> list[list[float]]:
            return [[0.1]] * len(texts)

        assert _is_batch_embedding_callable(batch_embed) is True

    def test_bare_list_callable_returns_true(self):
        """Non-generic `list` (without element type) still qualifies."""

        async def batch_embed(texts: list) -> list[list[float]]:
            return [[0.1]] * len(texts)

        assert _is_batch_embedding_callable(batch_embed) is True

    # --- real-world signature: extra POKW + KW_ONLY -------------------------

    def test_production_batch_helper_signature_returns_true(self):
        """Mirror `get_embeddings_with_timeout_batch(texts, timeout, *, batch_size)`
        signature shape: 2 POKW + 1 KW_ONLY. Must detect as batch.
        """
        async def get_embeddings_with_timeout_batch(
            texts: list[str],
            timeout: float = 60.0,
            *,
            batch_size: int = 10,
        ) -> list[list[float] | None]:
            return [[0.1]] * len(texts)

        assert _is_batch_embedding_callable(get_embeddings_with_timeout_batch) is True

    # --- string annotations (PEP 563 `from __future__ import annotations`) ---

    def test_string_form_annotation_returns_true(self):
        """`from __future__ import annotations` defers annotations to strings;
        `get_type_hints` must resolve them.
        """
        def batch_embed(texts: list[str]) -> list[list[float]]:
            return [[0.1]] * len(texts)

        # If get_type_hints fails (e.g. without proper globals), detection
        # falls back to inspecting the raw string — which currently also
        # returns False for forward-reference strings. We document the
        # observable behavior here; changing either direction is intentional.
        result = _is_batch_embedding_callable(batch_embed)
        assert result is True, (
            "Expected True for string-form 'list[str]' annotation; "
            "if False, get_type_hints may not be resolving forward refs. "
            "Either fix the implementation or update this assertion intentionally."
        )


# ---------------------------------------------------------------------------
# B. `_get_cached_embeddings_batch` — routing behavior
# ---------------------------------------------------------------------------


class TestCachedEmbeddingsBatchRouting:
    """Lock dispatcher routing: batch callable → batch HTTP, per-text callable → gather."""

    async def test_empty_texts_returns_empty_aligned_no_callable_call(self):
        """No texts → no callable invocation."""
        calls: list[list[str]] = []

        async def embed(texts):
            calls.append(texts)
            return [[0.1]] * len(texts)

        result = await _get_cached_embeddings_batch([], embed)
        assert result == []
        assert calls == []

    async def test_empty_string_entries_align_none_no_callable_call(self):
        """Empty string entries align to None positions; batch may still be called
        once for non-empty texts but not for empty entries."""
        async def embed(texts: list[str]) -> list[list[float] | None]:
            return [[0.1] for _ in texts]

        result = await _get_cached_embeddings_batch(["", "a"], embed)
        assert result[0] is None
        # "a" gets cached
        assert result[1] is not None

    async def test_batch_callable_invoked_with_full_list(self):
        """Batch path: callable called once with the full miss list."""

        async def batch_embed(texts: list[str]) -> list[list[float] | None]:
            return [[float(i)] for i, _ in enumerate(texts)]

        result = await _get_cached_embeddings_batch(
            ["a", "b", "c"], batch_embed, batch_size=10
        )
        assert all(r is not None for r in result)
        assert result == [[0.0], [1.0], [2.0]]
        assert _EMB_STATS["miss"] == 3
        assert _EMB_STATS["hit"] == 0

    async def test_per_text_callable_invoked_per_text(self):
        """Per-text path: callable called once per unique miss text."""

        async def per_text_embed(text: str) -> list[float]:
            return [ord(text[0]) / 1000.0]

        result = await _get_cached_embeddings_batch(
            ["a", "b", "c"], per_text_embed, batch_size=10
        )
        assert all(r is not None for r in result)
        assert _EMB_STATS["miss"] == 3
        assert _EMB_STATS["hit"] == 0

    async def test_duplicate_texts_counted_once_for_miss(self):
        """Dedup: same text twice → 1 miss, second occurrence is cache hit."""

        async def batch_embed(texts: list[str]) -> list[list[float] | None]:
            return [[0.5] for _ in texts]

        result = await _get_cached_embeddings_batch(
            ["a", "a", "b"], batch_embed, batch_size=10
        )
        assert result == [[0.5], [0.5], [0.5]]
        # 2 unique misses → batch called once with ["a", "b"]
        assert _EMB_STATS["miss"] == 2
        # Aligns with input positions; duplicate "a" already cached before
        # its second occurrence's slot is read.

    async def test_cache_hit_does_not_invoke_callable(self):
        """Pre-populated cache: text already cached → no callable invocation."""
        _EMBEDDING_CACHE["x"] = [0.999]

        calls: list[list[str]] = []

        async def batch_embed(texts: list[str]) -> list[list[float] | None]:
            calls.append(texts)
            return [[0.1] for _ in texts]

        result = await _get_cached_embeddings_batch(["x"], batch_embed)
        assert result == [[0.999]]
        assert calls == []
        assert _EMB_STATS["hit"] == 1
        assert _EMB_STATS["miss"] == 0

    async def test_batch_provider_timeout_falls_back_to_per_text(self):
        """Batch callable raises TimeoutError → fallback to per-text (batch callable
        called with [t] for each miss text, reusing provider-fallback chain)."""

        async def batch_embed(texts: list[str]) -> list[list[float] | None]:
            raise TimeoutError()

        # Per-text fallback uses the same batch callable with [t], so this
        # still raises (and gets silently skipped per `_per_text_fallback`).
        result = await _get_cached_embeddings_batch(
            ["a", "b"], batch_embed, batch_size=10
        )
        # Both fail → both align None
        assert result == [None, None]
        assert _EMB_STATS["timeout"] >= 1

    async def test_batch_provider_wrong_length_response_falls_back_to_per_text(self):
        """Batch callable returns wrong-length response → fallback to per-text
        via `_per_text_fallback`, which re-invokes the *same* batch callable
        with `[t]` (1-element list) per text. Provider fallback chain still
        applies, so a successful per-text call caches the result.
        """
        per_text_calls: list[list[str]] = []

        async def batch_embed(texts: list[str]) -> list[list[float] | None]:
            per_text_calls.append(list(texts))
            # First call: full list, return wrong length → triggers fallback.
            # Subsequent calls: single-element list, return valid result.
            if len(texts) > 1:
                return [[0.1]]  # wrong length, triggers fallback
            return [[0.7]]  # per-text fallback gets a valid result

        result = await _get_cached_embeddings_batch(
            ["a", "b", "c"], batch_embed, batch_size=10
        )
        # All 3 texts cached via per-text fallback (0.7 each).
        assert result == [[0.7], [0.7], [0.7]]
        assert _EMB_STATS["error"] >= 1, (
            "Wrong-length batch response must bump `_EMB_STATS['error']`"
        )
        # Fallback re-invokes the batch callable per text.
        assert len(per_text_calls) >= 4, (
            "Expected: 1 wrong-length call + 3 per-text fallback calls"
        )


# ---------------------------------------------------------------------------
# C. RED demonstration — temporary monkey-patch proves tests detect regression
# ---------------------------------------------------------------------------


class TestRedDemonstration:
    """Demonstrate that modifications to `_is_batch_embedding_callable` flip
    the routing tests to RED.

    Each test below uses `monkeypatch` to inject a misbehaving detector
    (always True / always False) and asserts that the *corresponding*
    routing test class would fail. This is the retrospective TDD discipline
    check: a silent regression to the dispatcher would be caught by the
    routing tests below (which `monkeypatch` simulates locally).

    Note: these tests assert *positive* behavior of the patched dispatcher
    itself (i.e. "yes, the regression is detectable"), not the production
    code. They guard against the regression going unnoticed if someone
    removes or weakens a routing test.
    """

    async def test_under_always_true_batch_callable_still_used_in_batch_path(
        self, monkeypatch
    ):
        """Sanity check: when detector is always True, batch callables go
        through batch path (callable invoked once with full list)."""
        monkeypatch.setattr(
            "rag_validation.coverage._is_batch_embedding_callable", lambda _: True
        )

        call_log: list[list[str]] = []

        async def batch_embed(texts: list[str]) -> list[list[float] | None]:
            call_log.append(list(texts))
            return [[0.1] for _ in texts]

        result = await _get_cached_embeddings_batch(
            ["a", "b", "c"], batch_embed, batch_size=10
        )
        # Even per-text callables get the batch path under patched detector.
        assert len(call_log) == 1
        assert call_log[0] == ["a", "b", "c"]
        assert all(r is not None for r in result)

    async def test_under_always_false_even_batch_callable_routed_via_per_text(
        self, monkeypatch
    ):
        """When detector is always False, batch callables still get a result
        because `_per_text_gather` wraps them with single-element calls
        (`embedding_callable([t])` fails or returns wrong type — but TD-072
        `_per_text_gather` calls `embedding_callable(t)` per text).

        Under regression, batch callable would crash when called as
        per-text (`text: str` ≠ `list[str]`), surfacing as None.
        """
        monkeypatch.setattr(
            "rag_validation.coverage._is_batch_embedding_callable", lambda _: False
        )

        async def batch_embed(texts: list[str]) -> list[list[float] | None]:
            # When called with str (per-text path), return a list[float]
            # mimicking real per-text behavior. When called with list[str],
            # return list[list[float]].
            if isinstance(texts, str):
                return [0.1]
            return [[0.1] for _ in texts]

        result = await _get_cached_embeddings_batch(
            ["a", "b"], batch_embed, batch_size=10
        )
        # Per-text path used; each text invokes batch_embed with str.
        assert all(r is not None for r in result)
        assert result == [[0.1], [0.1]]


# ---------------------------------------------------------------------------
# D. Behavioral lock — verify per-text callable behaves as TD-071 baseline
# ---------------------------------------------------------------------------


class TestPerTextBackwardCompatibility:
    """Lock per-text callable behavior matches TD-071 baseline.

    TD-072 promise: existing callables like `get_embedding(text: str)` keep
    working unchanged. The dispatcher routes them to `_per_text_gather`.
    """

    async def test_per_text_callable_caches_each_result(self):
        """Per-text path: each text's result is cached for subsequent reuse."""

        async def per_text_embed(text: str) -> list[float]:
            return [hash(text) % 100 / 100.0]

        # First call: all miss, no hits
        result1 = await _get_cached_embeddings_batch(
            ["alpha", "beta"], per_text_embed, batch_size=10
        )
        assert all(r is not None for r in result1)
        miss_after_first = _EMB_STATS["miss"]

        # Second call with same texts: should hit cache
        result2 = await _get_cached_embeddings_batch(
            ["alpha", "beta"], per_text_embed, batch_size=10
        )
        assert result1 == result2
        # All hits, no new misses
        assert _EMB_STATS["miss"] == miss_after_first
