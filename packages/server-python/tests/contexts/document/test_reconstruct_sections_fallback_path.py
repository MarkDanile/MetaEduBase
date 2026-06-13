"""TD-053: _reconstruct_sections_from_full_text must assign a non-empty
hierarchical path to each DocumentSection.

Bug: the function only constructed `DocumentSection(title, level, content,
page)` and never set `path`, so the rebuild fallback for legacy data
(structured_data without the `sections` key) produced chunks with
`section_path == ""`. The TD-051 quality report showed
section_path_empty = 100% after rebuild (0 improvement).

Spec AC-1 (option A, recommended): generate hierarchical paths like
"0/0", "0/1", "1/0" based on heading level + sibling index, so legacy
data gets meaningful paths even when the original DocumentSection.path
was discarded.
"""

from __future__ import annotations

from app.contexts.document.application.tasks.rebuild_chunks import (
    _reconstruct_sections_from_full_text,
)


def test_reconstruct_sections_assigns_non_empty_path_to_each_section() -> None:
    """Every reconstructed section must have a non-empty path.

    Regression lock for TD-053: the bug was that path was left as
    DocumentSection's default "" — this locks the fix in place.
    """
    full_text = (
        "## 1. 介绍\n"
        "第一段内容。\n"
        "## 2. 方法\n"
        "第二段内容。\n"
    )
    sections = _reconstruct_sections_from_full_text(full_text)

    assert len(sections) >= 1
    for sec in sections:
        assert sec.path, (
            f"DocumentSection.path must be non-empty; "
            f"got {sec.path!r} for section title={sec.title!r}"
        )


def test_reconstruct_sections_assigns_unique_paths() -> None:
    """Sibling sections must have distinct paths (no duplicate IDs)."""
    full_text = (
        "## 第一章\n"
        "内容一。\n"
        "## 第二章\n"
        "内容二。\n"
        "## 第三章\n"
        "内容三。\n"
    )
    sections = _reconstruct_sections_from_full_text(full_text)
    paths = [s.path for s in sections if s.path]
    assert len(set(paths)) == len(paths), (
        f"sibling sections must have unique paths; got {paths}"
    )


def test_reconstruct_sections_hierarchical_path_for_nested_headings() -> None:
    """Headings of different levels must produce hierarchical paths.

    The function uses regex `## ` (level 1 only) in TD-051, so this
    test only locks level-1 sibling indexing (e.g. "0/0", "0/1").
    A future enhancement to detect nested headings would extend
    the test cases.
    """
    full_text = (
        "## 1. 介绍\n"
        "第一段。\n"
        "## 2. 方法\n"
        "第二段。\n"
        "## 3. 结果\n"
        "第三段。\n"
    )
    sections = _reconstruct_sections_from_full_text(full_text)
    paths = [s.path for s in sections]

    # Lock the specific shape: 3 level-1 sections → 3 distinct paths.
    # We don't lock the exact path format ("0/0" vs "0" vs "1") to
    # leave room for choice A variant — but we lock count and uniqueness.
    assert len(paths) == 3
    assert len(set(paths)) == 3


def test_reconstruct_sections_empty_input_returns_empty() -> None:
    """Empty / blank full_text returns an empty list — must not raise."""
    assert _reconstruct_sections_from_full_text("") == []
    assert _reconstruct_sections_from_full_text("   \n\n  ") == []


def test_reconstruct_sections_preserves_title_and_content() -> None:
    """The fix must not regress title/content capture."""
    full_text = (
        "## 介绍\n"
        "这是介绍段的内容。\n"
    )
    sections = _reconstruct_sections_from_full_text(full_text)
    assert len(sections) == 1
    assert sections[0].title == "介绍"
    assert "这是介绍段的内容" in sections[0].content
