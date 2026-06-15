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
    current_content_parts: list[str] = []
    current_page = 0
    section_counter: dict[int, int] = {}

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

                # Primary: font-size + bold heuristic
                heading_level = 0
                for size, lvl in _HEADING_SIZES.items():
                    if max_font_size >= size:
                        heading_level = lvl
                        break

                is_heading = heading_level > 0 and is_bold and len(line_text) < 200

                # Fallback: Chinese numbered heading patterns
                if not is_heading:
                    regex_level = _detect_chinese_heading_level(line_text)
                    if regex_level > 0 and len(line_text) < 200:
                        heading_level = regex_level
                        is_heading = True

                if is_heading:
                    if current_title:
                        content = "\n".join(current_content_parts).strip()
                        path = _build_path(section_counter, heading_level)
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
                    current_content_parts = []
                    current_page = page_num
                    section_counter[heading_level] = section_counter.get(heading_level, 0) + 1
                else:
                    current_content_parts.append(line_text)

    if current_title:
        content = "\n".join(current_content_parts).strip()
        path = _build_path(section_counter, current_level)
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


def _build_path(counter: dict[int, int], level: int) -> str:
    parts = []
    for lvl in sorted(counter.keys()):
        if lvl <= level:
            parts.append(str(counter[lvl]))
    return ".".join(parts) if parts else ""
