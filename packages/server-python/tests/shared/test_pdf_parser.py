"""Tests for pdf_parser Chinese heading detection (BUG-006 #2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import fitz as _real_fitz

from app.shared.parsing.pdf_parser import (
    _detect_chinese_heading_level,
    extract_pdf_text,
)

# ---------------------------------------------------------------------------
# Unit tests for _detect_chinese_heading_level
# ---------------------------------------------------------------------------


class TestDetectChineseHeadingLevel:
    """Test _detect_chinese_heading_level directly."""

    def test_chapter_di_zhang(self) -> None:
        assert _detect_chinese_heading_level("第一章 专业名称与代码") == 1
        assert _detect_chinese_heading_level("第十二章 教学进程") == 1

    def test_chapter_di_bian_bu_fen(self) -> None:
        assert _detect_chinese_heading_level("第一编 基础理论") == 1
        assert _detect_chinese_heading_level("第三部分 实践教学") == 1
        assert _detect_chinese_heading_level("第二部 课程体系") == 1

    def test_section_di_jie(self) -> None:
        assert _detect_chinese_heading_level("第二节 教学方法") == 2
        assert _detect_chinese_heading_level("第十节 实训安排") == 2

    def test_numeral_comma(self) -> None:
        assert _detect_chinese_heading_level("一、专业名称与代码") == 1
        assert _detect_chinese_heading_level("十、教学进度安排") == 1
        assert _detect_chinese_heading_level("三、修业年限") == 1

    def test_fullwidth_parenthesized(self) -> None:
        assert _detect_chinese_heading_level("（一）教学目标") == 2
        assert _detect_chinese_heading_level("（十）毕业要求") == 2

    def test_halfwidth_parenthesized(self) -> None:
        assert _detect_chinese_heading_level("(一) 教学目标") == 2
        assert _detect_chinese_heading_level("(三) 实训安排") == 2

    def test_no_match(self) -> None:
        assert _detect_chinese_heading_level("本专业培养德智体美劳全面发展的人才") == 0
        assert _detect_chinese_heading_level("课程设置如下：") == 0
        assert _detect_chinese_heading_level("") == 0
        assert _detect_chinese_heading_level("环境监测技术") == 0


# ---------------------------------------------------------------------------
# Integration tests with mocked fitz
# ---------------------------------------------------------------------------


def _make_span(text: str, size: float = 10.0, font: str = "SimSun") -> dict:
    return {"text": text, "size": size, "font": font}


def _make_line(spans: list[dict]) -> dict:
    return {"spans": spans}


def _make_text_block(lines: list[dict]) -> dict:
    return {"type": 0, "lines": lines}


def _make_non_text_block() -> dict:
    return {"type": 1}


def _mock_fitz_doc(lines_per_page: list[list[dict]]) -> MagicMock:
    """Build a mock fitz document whose pages yield the given lines."""
    mock_doc = MagicMock()
    mock_doc.__len__ = lambda self: len(lines_per_page)
    pages = []
    for page_lines in lines_per_page:
        mock_page = MagicMock()
        blocks = [_make_text_block(page_lines)]
        mock_page.get_text.return_value = {"blocks": blocks}
        pages.append(mock_page)
    mock_doc.__getitem__ = lambda self, idx: pages[idx]
    mock_doc.close = MagicMock()
    return mock_doc


class TestChineseChapterHeadingIdentified:
    """BUG-006 #2: Chinese heading patterns should be detected when font-size+bold miss."""

    def test_chinese_chapter_heading_identified(self) -> None:
        """A PDF with Chinese numeral headings should produce multiple sections."""
        lines = [
            _make_line([_make_span("一、专业名称与代码")]),
            _make_line([_make_span("环境监测技术专业")]),
            _make_line([_make_span("二、入学要求")]),
            _make_line([_make_span("初中毕业或具有同等学力者")]),
            _make_line([_make_span("三、修业年限")]),
            _make_line([_make_span("学制三年")]),
        ]
        mock_doc = _mock_fitz_doc([lines])

        with patch.object(_real_fitz, "open", return_value=mock_doc):
            result = extract_pdf_text("/fake/path.pdf")

        assert len(result.sections) >= 3, f"Expected >= 3 sections, got {len(result.sections)}"
        assert result.sections[0].title == "一、专业名称与代码"
        assert result.sections[1].title == "二、入学要求"
        assert result.sections[2].title == "三、修业年限"

    def test_font_size_heading_takes_priority(self) -> None:
        """When both font-size+bold and regex match, font-size level should win."""
        # A bold 22pt line that also starts with "一、" → should use font-size level (1)
        lines = [
            _make_line([_make_span("一、大标题", size=22.0, font="SimHei-Bold")]),
            _make_line([_make_span("正文内容")]),
        ]
        mock_doc = _mock_fitz_doc([lines])

        with patch.object(_real_fitz, "open", return_value=mock_doc):
            result = extract_pdf_text("/fake/path.pdf")

        # Font-size detected level 1 (22→1), regex also level 1 — both agree
        assert len(result.sections) == 1
        assert result.sections[0].title == "一、大标题"
        assert result.sections[0].level == 1  # from font-size, but regex also says 1

    def test_mixed_chinese_and_font_headings(self) -> None:
        """A document with both Chinese regex headings and font-size headings."""
        lines = [
            _make_line([_make_span("一、专业名称", size=10.0, font="SimSun")]),  # regex only
            _make_line([_make_span("专业介绍内容")]),
            _make_line([_make_span("BIG SECTION", size=22.0, font="Arial-Bold")]),  # font-size only
            _make_line([_make_span("大节内容")]),
            _make_line([_make_span("二、入学要求", size=10.0, font="SimSun")]),  # regex only
            _make_line([_make_span("要求内容")]),
        ]
        mock_doc = _mock_fitz_doc([lines])

        with patch.object(_real_fitz, "open", return_value=mock_doc):
            result = extract_pdf_text("/fake/path.pdf")

        assert len(result.sections) == 3
        assert result.sections[0].title == "一、专业名称"
        assert result.sections[0].level == 1  # regex level
        assert result.sections[1].title == "BIG SECTION"
        assert result.sections[1].level == 1  # font-size level
        assert result.sections[2].title == "二、入学要求"
        assert result.sections[2].level == 1  # regex level

    def test_subsection_parenthesized(self) -> None:
        """（一）/（二） sub-section headings should create level-2 sections."""
        lines = [
            _make_line([_make_span("一、培养目标")]),
            _make_line([_make_span("（一）知识目标")]),
            _make_line([_make_span("掌握基础理论知识")]),
            _make_line([_make_span("（二）能力目标")]),
            _make_line([_make_span("具备实践操作能力")]),
        ]
        mock_doc = _mock_fitz_doc([lines])

        with patch.object(_real_fitz, "open", return_value=mock_doc):
            result = extract_pdf_text("/fake/path.pdf")

        # 3 headings: 一 (level 1), （一）(level 2), （二）(level 2)
        assert len(result.sections) == 3
        assert result.sections[0].title == "一、培养目标"
        assert result.sections[0].level == 1
        assert result.sections[1].title == "（一）知识目标"
        assert result.sections[1].level == 2
        assert result.sections[2].title == "（二）能力目标"
        assert result.sections[2].level == 2
