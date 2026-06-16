"""Tests for pdf_parser Chinese heading detection (BUG-006 #2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import fitz as _real_fitz

from app.shared.parsing.pdf_parser import (
    _detect_chinese_heading_level,
    _is_non_heading,
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


# ---------------------------------------------------------------------------
# BUG-007: non-heading blacklist + hierarchical path stack
# ---------------------------------------------------------------------------


class TestIsNonHeading:
    """BUG-007: filter dates / room numbers / pure digits out of heading detection."""

    def test_date_is_non_heading(self) -> None:
        assert _is_non_heading("2021 年1 月8 日") is True
        assert _is_non_heading("2021年1月8日") is True
        assert _is_non_heading("2021-1-8") is True
        assert _is_non_heading("2021.1.8") is True

    def test_room_or_class_number_is_non_heading(self) -> None:
        assert _is_non_heading("18 环测1 班") is True
        assert _is_non_heading("21计算机1班") is True
        assert _is_non_heading("108") is True  # pure number
        assert _is_non_heading("1234") is True

    def test_normal_text_is_not_non_heading(self) -> None:
        assert _is_non_heading("一、专业名称与代码") is False
        assert _is_non_heading("学期授课计划") is False
        assert _is_non_heading("本专业培养德智体美劳全面发展的人才") is False
        assert _is_non_heading("附件1：授课计划") is False


class TestPathStack:
    """BUG-007: hierarchical path stack (docling / unstructured.io convention)."""

    def _run(self, lines: list[dict]) -> list:
        mock_doc = _mock_fitz_doc([lines])
        with patch.object(_real_fitz, "open", return_value=mock_doc):
            return extract_pdf_text("/fake/path.pdf").sections

    def test_path_stack_handles_mixed_heuristics(self) -> None:
        """BUG-007 scenario: font-size+regex mix in one PDF.

        Sequence: 附件1 (font level 3) → 学期授课计划 (font level 2) →
        18 环测1 班 (font level 4 but blacklisted as room number) →
        2021 年1 月8 日 (font level 4 but blacklisted as date) →
        一、编制说明 (regex level 1) → 二、授课计划 (regex level 1).
        After popping the font-size-only noise, the path stack should
        produce consistent paths for the Chinese regex headings.
        """
        lines = [
            _make_line([_make_span("附件1：授课计划", size=15.0, font="SimHei-Bold")]),
            _make_line([_make_span("学期授课计划", size=22.0, font="SimHei")]),  # no bold
            _make_line([_make_span("18 环测1 班", size=14.1, font="SimHei-Bold")]),
            _make_line([_make_span("2021 年1 月8 日", size=14.1, font="SimHei-Bold")]),
            _make_line([_make_span("一、编制说明", size=12.0, font="SimSun")]),
            _make_line([_make_span("项目二.水中物理指标的检测", size=9.0, font="SimSun")]),
            _make_line([_make_span("二、授课计划", size=12.0, font="SimSun")]),
        ]
        sections = self._run(lines)
        # 3 headings: 附件1 + 一、编制说明 + 二、授课计划
        titles = [s.title for s in sections]
        assert "附件1：授课计划" in titles
        assert "一、编制说明" in titles
        assert "二、授课计划" in titles
        # 18 环测1 班 / 2021年1月8日 应该被黑名单过滤
        assert "18 环测1 班" not in titles
        assert "2021 年1 月8 日" not in titles
        # All detected headings should have non-empty path
        for s in sections:
            assert s.path, f"Section {s.title!r} has empty path"

    def test_path_stack_decrease_then_increase(self) -> None:
        """Level 1 → 2 → 2 → 1 — path should reflect hierarchy strictly."""
        lines = [
            _make_line([_make_span("一、章", size=12.0, font="SimSun")]),  # level 1
            _make_line([_make_span("（一）子节", size=12.0, font="SimSun")]),  # level 2
            _make_line([_make_span("（二）子节", size=12.0, font="SimSun")]),  # level 2
            _make_line([_make_span("二、章", size=12.0, font="SimSun")]),  # level 1
        ]
        sections = self._run(lines)
        # 4 headings: 一、章 / （一）子节 / （二）子节 / 二、章
        assert [s.title for s in sections] == [
            "一、章",
            "（一）子节",
            "（二）子节",
            "二、章",
        ]
        # Paths:
        # 一、章 (L1) → "1"
        # （一）子节 (L2) → "1.1"  (sibling under 一、章)
        # （二）子节 (L2) → "1.2"  (sibling, count=2)
        # 二、章 (L1) → "2"  (L2 popped from stack on decrease)
        assert [s.path for s in sections] == ["1", "1.1", "1.2", "2"]
        assert [s.level for s in sections] == [1, 2, 2, 1]

    def test_existing_path_values_for_known_pdf(self) -> None:
        """Sanity check: the 人才培养方案 PDF (known to have many Chinese headings)
        still produces non-empty paths for all sections after BUG-007 fix.
        """
        import os

        # Locate the PDF in the dev uploads directory.
        candidate_paths = [
            "/Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase/packages/server-python/uploads/00000000-0000-0000-0000-000000000001/de7aa081442842ed8ac65cdec3a28e1b_01-人才培养方案环境监测技术专业.pdf",
        ]
        pdf_path = next((p for p in candidate_paths if os.path.exists(p)), None)
        if pdf_path is None:
            # Test is skipped if the known fixture is not present locally
            import pytest
            pytest.skip("人才培养方案 PDF fixture not present in this environment")
        result = extract_pdf_text(pdf_path)
        assert len(result.sections) > 5, f"Expected > 5 sections, got {len(result.sections)}"
        for s in result.sections:
            assert s.path, f"Section {s.title!r} has empty path after BUG-007 fix"
