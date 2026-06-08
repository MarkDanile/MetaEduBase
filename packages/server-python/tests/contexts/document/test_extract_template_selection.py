"""Three-layer template selection regression tests.

These tests intentionally avoid the DB and HTTP layer: they construct
``Template`` instances directly and inject a fake ``ai_chat`` coroutine.
"""

from __future__ import annotations

from typing import Awaitable, Callable
from uuid import uuid4

import pytest

from app.contexts.document.application.template_selector import (
    SelectionResult,
    select_template,
)
from app.contexts.template.domain.entity import Template


# --- helpers ---------------------------------------------------------------


def _tpl(name: str, doc_types: list[str]) -> Template:
    return Template(
        id=uuid4(),
        tenant_id=uuid4(),
        name=name,
        doc_types=doc_types,
        fields=[],
    )


def _ai(respond: str | BaseException) -> Callable[[str], Awaitable[str]]:
    async def _call(_prompt: str) -> str:
        if isinstance(respond, BaseException):
            raise respond
        return respond

    return _call


# --- AC-2: priority --------------------------------------------------------


@pytest.mark.asyncio
async def test_l1_wins_over_l2_and_l3():
    t_lesson = _tpl("教案-精确", ["教案"])
    t_filename = _tpl("教案-文件", ["课程标准"])
    templates = [t_filename, t_lesson]
    # doc_type already matches L1; filename also matches t_filename
    res = await select_template(
        chunks_text="x", doc_type="教案",
        filename="课程标准.docx", templates=templates,
        ai_chat=_ai("教案\n0.99"),
    )
    assert res.layer == "L1"
    assert res.template is t_lesson


# --- L1 --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_l1_exact_match():
    tpl = _tpl("教案-精确", ["教案", "教学设计"])
    res = await select_template(
        chunks_text="x", doc_type="教案", filename="",
        templates=[tpl], ai_chat=_ai(""),
    )
    assert res == SelectionResult(
        template=tpl, layer="L1", matched_type="教案",
        confidence=None, reason="exact doc_type match",
    )


# --- L2 --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_l2_filename_substring_match():
    tpl = _tpl("课程标准-文件", ["课程标准"])
    res = await select_template(
        chunks_text="x", doc_type=None,
        filename="2024春季课程标准.docx", templates=[tpl],
        ai_chat=_ai(""),
    )
    assert res.layer == "L2"
    assert res.template is tpl
    assert res.matched_type == "课程标准"


# --- L3 hit / miss ---------------------------------------------------------


@pytest.mark.asyncio
async def test_l3_ai_high_confidence_match():
    tpl = _tpl("教案-AI", ["教案"])
    res = await select_template(
        chunks_text="x", doc_type="", filename="misc.docx",
        templates=[tpl], ai_chat=_ai("教案\n0.92"),
    )
    assert res.layer == "L3"
    assert res.template is tpl
    assert res.confidence == 0.92


@pytest.mark.asyncio
async def test_l3_ai_below_threshold_returns_none():
    tpl = _tpl("教案-AI", ["教案"])
    res = await select_template(
        chunks_text="x", doc_type="", filename="",
        templates=[tpl], ai_chat=_ai("教案\n0.65"),
    )
    assert res.layer == "L3"  # L3 was reached
    assert res.template is None
    assert res.confidence == 0.65
    assert "below threshold" in res.reason


@pytest.mark.asyncio
async def test_l3_ai_single_line_uses_default_confidence():
    tpl = _tpl("教案-AI", ["教案"])
    res = await select_template(
        chunks_text="x", doc_type="", filename="",
        templates=[tpl], ai_chat=_ai("教案"),
    )
    # default 0.5 < 0.7 threshold → none
    assert res.layer == "L3"
    assert res.template is None
    assert res.confidence == 0.5


@pytest.mark.asyncio
async def test_l3_ai_matched_type_not_in_tenant_templates():
    tpl = _tpl("教案-tenant", ["教案"])
    res = await select_template(
        chunks_text="x", doc_type="", filename="",
        templates=[tpl], ai_chat=_ai("未知类型\n0.95"),
    )
    assert res.layer == "none"
    assert res.template is None
    assert res.matched_type == "未知类型"
    assert res.confidence == 0.95


@pytest.mark.asyncio
async def test_l3_ai_call_raises_returns_none():
    tpl = _tpl("教案-AI", ["教案"])
    res = await select_template(
        chunks_text="x", doc_type="", filename="",
        templates=[tpl], ai_chat=_ai(RuntimeError("network down")),
    )
    assert res.layer == "none"
    assert res.template is None
    assert "AI call raised" in res.reason


# --- empty / no templates --------------------------------------------------


@pytest.mark.asyncio
async def test_no_doc_type_no_filename_no_templates_returns_none():
    res = await select_template(
        chunks_text="x", doc_type=None, filename="",
        templates=[], ai_chat=_ai(""),
    )
    assert res.layer == "none"
    assert res.template is None
    assert res.reason == "no templates registered"
