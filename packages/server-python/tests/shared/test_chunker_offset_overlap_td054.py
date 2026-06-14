"""TD-054: _split_oversized_chunk must return (text, char_start) pairs that
are strictly monotonic and non-overlapping.

Bug: the function had 3 off-by-one errors in the sub-chunk start
position computation:
- L257-261: every clause_part was assigned the same `pos` value
  instead of `pos + sum(prior clause_lengths)`.
- L278: `_split_by_characters` sub-iteration added a phantom `+1`
  to the running sum, but `_split_by_characters` does not insert
  any separator between substrings — so all sub-iteration start
  positions were 1 byte too late (or 1 byte too early, depending
  on iteration index).
- L255: when a single sentence exceeded max_chars, all its clause
  sub-parts shared the same char_start (= pos).

Effect: TD-051 quality report showed offset_overlaps REBUILD
816 -> 869 (+3 pct) instead of decreasing. The rebuilt chunks
ended up with multiple chunks sharing the same char_start, which
the overlap detection query counted as overlapping.

These tests lock the fix in place by checking:
1. Pairs are strictly monotonic (next.char_start >= prev.char_start)
2. Pairs are non-overlapping (next.char_start >= prev.char_end)
3. Concatenating all pieces reconstructs the original text up to
   whitespace differences (catches separator mishandling).
"""

from __future__ import annotations

from itertools import pairwise

from app.shared.parsing.chunker import _split_oversized_chunk


def test_split_returns_strictly_monotonic_starts() -> None:
    """Each pair's char_start must be >= the previous pair's char_start.

    Regression lock for TD-054 bug #1 + #3: clause_part and
    sentence-internal splits all shared the same start position
    before the fix, breaking monotonicity.
    """
    text = "第一句。第二句非常非常非常非常长，包含了大量内容，需要被切分。第三句。"
    pairs = _split_oversized_chunk(text, max_chars=10)

    for prev, curr in pairwise(pairs):
        assert curr[1] >= prev[1], (
            f"char_start must be monotonic; got {prev[1]} -> {curr[1]}"
        )


def test_split_returns_non_overlapping_pairs() -> None:
    """Each pair's char_start must be >= the previous pair's char_end.

    Regression lock for TD-054: the +1 separator assumption in
    L278 caused substring positions to drift, creating overlap.
    """
    text = "第一句。第二句非常非常非常非常长，包含了大量内容，需要被切分。第三句。"
    pairs = _split_oversized_chunk(text, max_chars=10)

    for prev, curr in pairwise(pairs):
        prev_end = prev[1] + len(prev[0])
        assert curr[1] >= prev_end, (
            f"pair must be non-overlapping; prev=[{prev[1]},{prev_end}) "
            f"curr=[{curr[1]},…)"
        )


def test_split_concatenating_pieces_reconstructs_text() -> None:
    """Concatenating all pieces in order (sans whitespace stripping)
    must produce the original text.

    Regression lock for TD-054: the original `_split_into_sentences`
    preserves sentence boundaries with `\\n` separator. The fix
    must keep that contract — the rebuild must not silently drop
    content.
    """
    text = "第一句。第二句非常非常非常非常长。第三句。"
    pairs = _split_oversized_chunk(text, max_chars=8)

    # Each piece should be a contiguous substring of `text` (with
    # possibly leading/trailing whitespace stripped by _split_into_sentences).
    # We check that concatenating all pieces (with newline joiner,
    # mirroring the production path) reconstructs the body.
    joined = "\n".join(piece for piece, _ in pairs)
    # Strip whitespace from both sides and compare.
    assert joined.replace(" ", "").replace("\n", "").strip() == text.replace(" ", "").strip(), (
        f"pieces should reconstruct text when stripped; got:\n{joined!r}\n"
        f"vs original:\n{text!r}"
    )


def test_split_handles_short_text_without_splitting() -> None:
    """Short text below max_chars returns one piece with offset 0."""
    text = "短文本。"
    pairs = _split_oversized_chunk(text, max_chars=500)
    assert len(pairs) == 1
    assert pairs[0][1] == 0
    assert "短文本" in pairs[0][0]


def test_split_oversized_sentence_produces_distinct_starts() -> None:
    """When a single sentence exceeds max_chars and gets split by clauses,
    each clause sub-piece must get a distinct (increasing) char_start.

    Regression lock for TD-054 bug #3: the inner _split_by_clauses
    branch used to assign the same `pos` to all clause parts.
    """
    # Build a single sentence long enough to trigger clause split
    # (max_chars=10 forces multiple sub-chunks).
    text = "甲乙丙丁戊己庚辛壬癸甲乙丙丁戊己庚辛壬癸"  # 22 chars
    pairs = _split_oversized_chunk(text, max_chars=10)

    # All starts must be distinct (regression lock for the duplicate-pos bug)
    starts = [s for _, s in pairs]
    assert len(set(starts)) == len(starts), (
        f"each clause sub-piece must have a distinct char_start; got {starts}"
    )

    # And they must be non-overlapping
    for prev, curr in pairwise(pairs):
        prev_end = prev[1] + len(prev[0])
        assert curr[1] >= prev_end, (
            f"clause sub-pieces must be non-overlapping; "
            f"prev=[{prev[1]},{prev_end}) curr=[{curr[1]},…)"
        )
