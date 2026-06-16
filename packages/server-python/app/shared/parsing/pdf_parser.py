"""PDF text and heading extraction using PyMuPDF."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DocumentSection:
    title: str
    level: int
    content: str
    page: int
    path: str = ""  # e.g. "3.2"


@dataclass
class ParsedDocument:
    sections: list[DocumentSection] = field(default_factory=list)
    full_text: str = ""


_HEADING_SIZES = {22: 1, 18: 2, 15: 3, 13: 4}

# Chinese numbered heading patterns — used as fallback when font-size+bold
# heuristics miss unstyled headings common in Chinese educational PDFs.
_CHINESE_HEADING_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    # 第X章/编/部/分 — formal chapter-level headings
    (re.compile(r"^第[一二三四五六七八九十百千]+[章编部分]"), 1),
    # 第X节 — formal section-level headings
    (re.compile(r"^第[一二三四五六七八九十百千]+节"), 2),
    # 一、二、三、... — Chinese numeral + comma (chapter level)
    (re.compile(r"^[一二三四五六七八九十]+、"), 1),
    # （一）（二）... — full-width parenthesized Chinese numeral
    (re.compile(r"^（[一二三四五六七八九十]+）"), 2),
    # (一)(二)... — half-width parenthesized Chinese numeral
    (re.compile(r"^\([一二三四五六七八九十]+\)"), 2),
]

# BUG-007: Non-heading patterns — text that the font-size+bold heuristic
# might mistake for a heading (e.g. plain dates, room numbers, numeric IDs)
# but that lacks the structural shape of a real section title. Filtered out
# before any heading detection runs.
_NON_HEADING_PATTERNS: list[re.Pattern[str]] = [
    # 纯日期：2021 年1 月8 日 / 2021年1月8日 / 2021-1-8 / 2021.1.8
    re.compile(r"^\d{2,4}\s*[年\-./]\s*\d{1,2}\s*[月\-./]?\s*\d{1,2}\s*日?$"),
    # 纯学号/班号：18 环测1 班 / 21 计算机1 班 / 18环测1班
    re.compile(r"^\d+\s*\S{2,8}\d*\s*班?$"),
    # 纯数字 ≥3 位：108 / 1234 / 2025 等
    re.compile(r"^\d{3,}$"),
]


def _is_non_heading(text: str) -> bool:
    """Return True if *text* matches a known non-heading pattern (date / room / pure number)."""
    return any(pattern.match(text) for pattern in _NON_HEADING_PATTERNS)


def _detect_chinese_heading_level(text: str) -> int:
    """Return heading level (1-4) if *text* starts with a Chinese heading pattern, else 0."""
    for pattern, level in _CHINESE_HEADING_PATTERNS:
        if pattern.match(text):
            return level
    return 0


def extract_pdf_text(file_path: str) -> ParsedDocument:
    """Extract structured text from a PDF file."""
    import fitz

    doc = fitz.open(file_path)
    sections: list[DocumentSection] = []
    full_text_parts: list[str] = []

    current_title = ""
    current_level = 0
    current_path = ""
    current_content_parts: list[str] = []
    current_page = 0
    # BUG-007: replace flat counter dict with hierarchical counters array
    # (docling / unstructured.io convention). Each index represents one
    # nesting level; counters[i] is the sibling index at level i+1. On
    # level decrease, deeper levels are reset to 0 so font-size+regex
    # mismatches cannot pollute the path.
    _path_counters: list[int] = [0, 0, 0, 0, 0]

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] != 0:  # text block only
                continue
            for line in block["lines"]:
                line_text = ""
                max_font_size = 0
                is_bold = False
                for span in line["spans"]:
                    line_text += span["text"]
                    if span["size"] > max_font_size:
                        max_font_size = span["size"]
                    if "bold" in span["font"].lower():
                        is_bold = True

                line_text = line_text.strip()
                if not line_text:
                    continue

                # BUG-007: filter out non-heading patterns (dates, room
                # numbers, pure digits) before any heading heuristic runs.
                if _is_non_heading(line_text):
                    current_content_parts.append(line_text)
                    continue

                # Primary: font-size + bold heuristic (BUG-007: tightened
                # length cap from 200 to 60 — real PDF headings rarely
                # exceed 40 chars; looser cap admitted paragraphs as headings).
                heading_level = 0
                for size, lvl in _HEADING_SIZES.items():
                    if max_font_size >= size:
                        heading_level = lvl
                        break

                is_heading = heading_level > 0 and is_bold and len(line_text) < 60

                # Fallback: Chinese numbered heading patterns
                if not is_heading:
                    regex_level = _detect_chinese_heading_level(line_text)
                    if regex_level > 0 and len(line_text) < 200:
                        heading_level = regex_level
                        is_heading = True

                if is_heading:
                    if current_title:
                        content = "\n".join(current_content_parts).strip()
                        path = current_path or _build_path(_path_counters, heading_level)
                        sections.append(
                            DocumentSection(
                                title=current_title,
                                level=current_level,
                                content=content,
                                page=current_page,
                                path=path,
                            )
                        )
                        full_text_parts.append(f"## {current_title}\n{content}")

                    current_title = line_text
                    current_level = heading_level
                    current_path = _build_path(_path_counters, heading_level)
                    current_content_parts = []
                    current_page = page_num
                else:
                    current_content_parts.append(line_text)

    if current_title:
        content = "\n".join(current_content_parts).strip()
        path = current_path or _build_path(_path_counters, current_level)
        sections.append(
            DocumentSection(
                title=current_title,
                level=current_level,
                content=content,
                page=current_page,
                path=path,
            )
        )
        full_text_parts.append(f"## {current_title}\n{content}")

    if not sections and not full_text_parts:
        all_text = ""
        for page_num in range(len(doc)):
            all_text += doc[page_num].get_text() + "\n"
        if all_text.strip():
            sections.append(
                DocumentSection(title="", level=0, content=all_text.strip(), page=0, path="")
            )
            full_text_parts.append(all_text.strip())

    doc.close()
    return ParsedDocument(sections=sections, full_text="\n\n".join(full_text_parts))


def _build_path(counters: list[int], level: int) -> str:
    """BUG-007: Hierarchical path computation (docling counters-array convention).

    ``counters`` is a 5-element list representing nesting levels 1-5
    (counters[i] = sibling index at level i+1, 0-based + 1 for display).
    When a new heading at level L arrives:
      1. increment counters[L-1]
      2. reset all counters at levels > L to 0
      3. return the dot-joined path of all non-zero counters

    This is robust to font-size+regex level-mismatch pollution because
    every heading event re-establishes a consistent hierarchy from the
    deepest level it has seen so far down to L.
    """
    if level < 1 or level > 5:
        return ""
    counters[level - 1] += 1
    for i in range(level, 5):
        counters[i] = 0
    parts = [str(c) for c in counters[:level] if c > 0]
    return ".".join(parts)
