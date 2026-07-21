"""TD-051: chunker metadata correctness tests.

Verifies that:
- section_path / section_title are correctly preserved through chunking
- char_start / char_end are globally monotonic and cover chunk content
- _enforce_size_limit splits with correct offsets
- MIN_CHUNK_CHARS merging works correctly
"""

from app.shared.parsing.chunker import (
    MIN_CHUNK_CHARS,
    TARGET_CHUNK_CHARS,
    Chunk,
    chunk_by_structure,
)
from app.shared.parsing.pdf_parser import DocumentSection, ParsedDocument

# --- Helpers ---


def make_parsed(sections: list[DocumentSection], full_text: str) -> ParsedDocument:
    return ParsedDocument(sections=sections, full_text=full_text)


def chunk_text(text: str, **kwargs) -> list[Chunk]:
    doc = make_parsed(
        [DocumentSection(title="Section 1", level=1, content=text, page=0, path="1")],
        text,
    )
    return chunk_by_structure(doc, **kwargs)


# --- Section metadata ---


def test_section_path_preserved_in_chunks():
    """TD-051 AC-2: section_path is correctly passed to every Chunk."""
    text = "这是第一句话。这是第二句话。" * 50  # ~400 chars
    chunks = chunk_text(text, target_chars=200)

    for c in chunks:
        assert c.section_path == "1"
        assert c.section_title == "Section 1"


def test_section_path_multiple_sections():
    """TD-051 AC-2: each section's path is preserved for its chunks."""
    # The full_text must exactly correspond to how sections are rendered:
    # "## title\ncontent" per section, joined by "\n\n"
    s1_content = "第一章内容。" * 20  # ~240 chars
    s2_content = "第二章内容。" * 20  # ~240 chars
    full_text = f"## 第一章\n{s1_content}\n\n## 第二章\n{s2_content}"
    doc = make_parsed(
        [
            DocumentSection(title="第一章", level=1, content=s1_content, page=0, path="1"),
            DocumentSection(title="第二章", level=1, content=s2_content, page=1, path="2"),
        ],
        full_text,
    )
    chunks = chunk_by_structure(doc, target_chars=200)

    paths = [c.section_path for c in chunks]
    assert "1" in paths
    assert "2" in paths


# --- char_start / char_end correctness ---


def test_char_start_end_cover_content():
    """TD-051 AC-3: char_end - char_start == len(content) for every chunk."""
    text = "这是第一句话。这是第二句话。" * 50
    chunks = chunk_text(text, target_chars=200)

    for c in chunks:
        assert c.char_end - c.char_start == len(c.content), (
            f"chunk {c.index}: char_end({c.char_end}) - char_start({c.char_start}) "
            f"!= len(content)({len(c.content)})"
        )


def test_char_start_monotonic():
    """TD-051 AC-3: char_start is monotonically non-decreasing across chunks."""
    text = "这是第一句话。这是第二句话。" * 50
    chunks = chunk_text(text, target_chars=200)

    for i in range(1, len(chunks)):
        assert chunks[i].char_start >= chunks[i - 1].char_start, (
            f"chunk {i}: char_start({chunks[i].char_start}) < "
            f"chunk {i-1}.char_start({chunks[i-1].char_start})"
        )


def test_char_end_consistent_with_char_start():
    """TD-051 AC-3: char_end = char_start + len(content) holds exactly."""
    text = "这是第一句话。这是第二句话。" * 50
    chunks = chunk_text(text, target_chars=200)

    for c in chunks:
        assert c.char_end == c.char_start + len(c.content), (
            f"chunk {c.index}: char_end({c.char_end}) != "
            f"char_start({c.char_start}) + len({len(c.content)})"
        )


# --- _enforce_size_limit offset preservation ---


def test_enforce_size_limit_preserves_char_offsets():
    """TD-051 AC-3: _enforce_size_limit gives correct offsets to sub-chunks."""
    # A single long sentence exceeding target_chars
    text = "这是句子。" * 200  # ~600 chars, will be split
    chunks = chunk_text(text, target_chars=200)

    # After _enforce_size_limit all chunks should still be valid
    for c in chunks:
        assert c.char_end - c.char_start == len(c.content)
        assert c.char_end > c.char_start


def test_enforce_size_limit_merges_tiny_chunks():
    """TD-051 AC-4 / MIN_CHUNK_CHARS: chunks below threshold are merged with previous."""
    # Create two chunks: first ~50 chars, second ~20 chars (below MIN_CHUNK_CHARS)
    from app.shared.parsing.chunker import _merge_small_chunks

    tiny = Chunk(
        content="短", section_title="T", section_path="1",
        char_start=0, char_end=2, index=1,
    )
    prev = Chunk(
        content="这是一段比较长的内容用于测试。" * 3,
        section_title="T", section_path="1",
        char_start=0, char_end=90, index=0,
    )
    result = _merge_small_chunks([prev, tiny], min_size=MIN_CHUNK_CHARS)

    # tiny should have been merged into prev
    assert len(result) == 1
    assert "短" in result[0].content


# --- section_offset parameter (Slice 2) ---


def test_section_offset_applies_absolute_offset():
    """TD-051 AC-3: section_offset makes chunks start at a non-zero char_start."""
    doc = make_parsed(
        [DocumentSection(title="", level=0, content="内容", page=0, path="")],
        "内容",
    )
    chunks = chunk_by_structure(doc, section_offset=1000)

    assert chunks[0].char_start == 1000
    assert chunks[0].char_end == 1000 + len("内容")


def test_section_offset_cross_section_boundary():
    """TD-051 AC-3: char_start continues monotonically across section boundaries."""
    # Two sections: first 200 chars, second starts at section_offset
    doc = make_parsed(
        [
            DocumentSection(title="S1", level=1, content="一" * 100, page=0, path="1"),
            DocumentSection(title="S2", level=1, content="二" * 100, page=1, path="2"),
        ],
        "一" * 100 + "\n\n" + "二" * 100,
    )
    chunks = chunk_by_structure(doc, section_offset=0)

    # Last chunk of section 1 should have char_end <= first chunk of section 2's char_start
    s1_chunks = [c for c in chunks if c.section_path == "1"]
    s2_chunks = [c for c in chunks if c.section_path == "2"]

    if s1_chunks and s2_chunks:
        last_s1 = max(s1_chunks, key=lambda c: c.char_end)
        first_s2 = min(s2_chunks, key=lambda c: c.char_start)
        assert last_s1.char_end <= first_s2.char_start


# --- MIN_CHUNK_CHARS constant ---


def test_min_chunk_chars_constant_exists():
    """TD-051 AC-4: MIN_CHUNK_CHARS is a documented constant."""
    assert isinstance(MIN_CHUNK_CHARS, int)
    assert MIN_CHUNK_CHARS == 80


def test_target_chunk_chars_constant_exists():
    """TD-051 AC-4: TARGET_CHUNK_CHARS is a documented constant."""
    assert isinstance(TARGET_CHUNK_CHARS, int)
    assert TARGET_CHUNK_CHARS == 500
