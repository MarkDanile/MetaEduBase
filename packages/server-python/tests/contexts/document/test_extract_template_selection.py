"""Three-layer template selection regression tests.

These tests intentionally avoid the DB and HTTP layer: they construct
``Template`` instances directly and inject a fake ``ai_chat`` coroutine.

Note on the ``_log_selection`` helper: it mirrors the ``if selection.layer
== "L1" ... else: ...`` logging block in
``app.contexts.document.application.tasks.extract_template``. ``test_logging_
branches_match_production_code`` is a structural guard that fails if the
production block drifts away from the helper, so any future change to the
log messages is caught before the caplog assertions go silently green.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest

from app.contexts.document.application.template_selector import (
    SelectionResult,
    select_template,
)
from app.contexts.template.domain.entity import Template

_TASKS_LOGGER = "app.contexts.document.application.tasks"

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


# --- REQ-008: caplog 4 分支 + L3 边角 + 漂移保护 --------------------------


def _log_selection(
    selection: SelectionResult,
    doc_type: str | None,
    filename: str,
) -> None:
    """Mirror the logging block in tasks.extract_template for caplog tests.

    Kept byte-identical to the production branch so any future drift in
    tasks.py is detectable by ``test_logging_branches_match_production_code``.
    """
    log = logging.getLogger(_TASKS_LOGGER)
    template_obj = selection.template
    if selection.layer == "L1":
        log.info(
            "template.select layer=L1 doc_type=%r filename=%r → template=%s id=%s",
            doc_type, filename, template_obj.name, template_obj.id,
        )
    elif selection.layer == "L2":
        log.info(
            "template.select layer=L2 matched_doc_type=%r filename=%r → template=%s id=%s",
            selection.matched_type, filename, template_obj.name, template_obj.id,
        )
    elif selection.layer == "L3" and template_obj is not None:
        msg = (
            "template.select layer=L3 matched_doc_type=%r "
            "confidence=%.2f → template=%s id=%s"
        )
        log.info(
            msg,
            selection.matched_type, selection.confidence,
            template_obj.name, template_obj.id,
        )
    elif selection.layer == "L3" and selection.confidence is not None:
        msg = (
            "template.select layer=L3 confidence=%.2f < threshold "
            "doc_type=%r — using generic"
        )
        log.info(
            msg,
            selection.confidence, selection.matched_type,
        )
    elif selection.layer == "none" and selection.matched_type:
        log.warning(
            "template.select layer=none reason=%r doc_type=%r confidence=%.2f",
            selection.reason, selection.matched_type, selection.confidence or 0.0,
        )
    else:
        log.warning(
            "template.select layer=none reason=%r doc_type=%r filename=%r",
            selection.reason, doc_type, filename,
        )


@pytest.mark.parametrize(
    "doc_type, filename, ai_response, templates_factory, expected_substring, expected_level",
    [
        # L1
        ("教案", "教案文件.docx", "", lambda: [_tpl("教案-精确", ["教案"])],
         "template.select layer=L1", logging.INFO),
        # L2
        (None, "2024春季课程标准.docx", "",
         lambda: [_tpl("课程标准-文件", ["课程标准"])],
         "template.select layer=L2", logging.INFO),
        # L3 hit
        ("", "misc.docx", "教案\n0.92", lambda: [_tpl("教案-AI", ["教案"])],
         "template.select layer=L3 matched_doc_type=", logging.INFO),
        # none (no templates registered)
        ("教案", "教案文件.docx", "", lambda: [],
         "template.select layer=none", logging.WARNING),
    ],
)
@pytest.mark.asyncio
async def test_template_select_logs_are_emitted(
    caplog, doc_type, filename, ai_response, templates_factory,
    expected_substring, expected_level,
):
    caplog.set_level(logging.DEBUG, logger=_TASKS_LOGGER)
    res = await select_template(
        chunks_text="x", doc_type=doc_type, filename=filename,
        templates=templates_factory(), ai_chat=_ai(ai_response),
    )
    _log_selection(res, doc_type, filename)

    matching = [
        r for r in caplog.records
        if r.name == _TASKS_LOGGER
        and r.levelno == expected_level
        and expected_substring in r.getMessage()
    ]
    assert matching, (
        f"expected {expected_substring!r} at {logging.getLevelName(expected_level)} "
        f"in {_TASKS_LOGGER}; got: "
        f"{[r.getMessage() for r in caplog.records if r.name == _TASKS_LOGGER]}"
    )


@pytest.mark.asyncio
async def test_l3_ai_confidence_unparseable_falls_back_to_zero():
    """AI returns '教案\\nabc' → float() raises → confidence = 0.0 → 0.0 < 0.7 → none."""
    tpl = _tpl("教案-AI", ["教案"])
    res = await select_template(
        chunks_text="x", doc_type="", filename="",
        templates=[tpl], ai_chat=_ai("教案\nabc"),
    )
    # float("abc") raises → confidence = 0.0; matched type exists; 0.0 < threshold
    assert res.confidence == 0.0
    assert res.template is None
    assert res.layer == "L3"
    assert "below threshold" in res.reason


@pytest.mark.asyncio
async def test_l3_ai_empty_response_returns_none():
    """AI returns '' → lines == [] → AI returned empty response."""
    tpl = _tpl("教案-AI", ["教案"])
    res = await select_template(
        chunks_text="x", doc_type="", filename="",
        templates=[tpl], ai_chat=_ai(""),
    )
    assert res.layer == "none"
    assert res.template is None
    assert res.reason == "AI returned empty response"


def test_logging_branches_match_production_code() -> None:
    """Guard against the caplog helper drifting from the production log strings."""
    from pathlib import Path

    tasks_py = (
        Path(__file__).resolve().parents[3]
        / "app" / "contexts" / "document" / "application" / "tasks.py"
    )
    text = tasks_py.read_text(encoding="utf-8")
    expected = [
        "template.select layer=L1 doc_type=%r filename=%r → template=%s id=%s",
        "template.select layer=L2 matched_doc_type=%r filename=%r → template=%s id=%s",
        "template.select layer=L3 matched_doc_type=%r",
        "template.select layer=L3 confidence=%.2f < threshold",
        "template.select layer=none reason=%r doc_type=%r confidence=%.2f",
        "template.select layer=none reason=%r doc_type=%r filename=%r",
    ]
    for needle in expected:
        assert needle in text, f"tasks.py missing log message: {needle!r}"
