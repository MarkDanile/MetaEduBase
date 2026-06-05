"""Structured-data container contract tests for document tasks.

TD-009 keeps the public FileDTO response compatible while locking the
internal JSON container shape written by parse/extract tasks.
"""

import json

import pytest

from app.contexts.document.application.tasks import (
    _build_parsed_structured_data,
    _merge_template_structured_data,
)


def test_build_parsed_structured_data_uses_stable_container_keys() -> None:
    data = _build_parsed_structured_data("## 第一章\n内容", 3)

    assert data == {
        "full_text": "## 第一章\n内容",
        "section_count": 3,
    }
    assert isinstance(data["full_text"], str)
    assert isinstance(data["section_count"], int)


def test_merge_template_structured_data_preserves_parse_fields() -> None:
    existing = {"full_text": "正文", "section_count": 2, "custom": ["keep"]}
    template = {"title": "课程标准", "sections": ["一", "二"]}

    data = _merge_template_structured_data(existing, template)

    assert data == {
        "full_text": "正文",
        "section_count": 2,
        "custom": ["keep"],
        "template": {"title": "课程标准", "sections": ["一", "二"]},
    }
    assert data["template"] is not template


def test_merge_template_structured_data_accepts_legacy_json_string() -> None:
    existing = json.dumps({"full_text": "正文", "section_count": 1}, ensure_ascii=False)

    data = _merge_template_structured_data(existing, {"summary": "摘要"})

    assert data == {
        "full_text": "正文",
        "section_count": 1,
        "template": {"summary": "摘要"},
    }


def test_merge_template_structured_data_requires_template_object() -> None:
    with pytest.raises(TypeError, match="template_data must be a dict"):
        _merge_template_structured_data({}, ["not", "object"])  # type: ignore[arg-type]
