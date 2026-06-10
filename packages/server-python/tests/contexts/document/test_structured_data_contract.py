"""Structured-data container contract tests for document tasks.

TD-009 keeps the public FileDTO response compatible while locking the
internal JSON container shape written by parse/extract tasks.
"""

import json
import logging

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
    # REQ-002-3: this test pins the legacy meta=None shape. The helper now
    # accepts an optional ``meta`` kwarg, but omitting it (or passing None)
    # must keep the previous container shape so existing callers and the
    # public FileDTO contract stay stable. Assertions are intentionally not
    # updated — they encode the pre-meta contract.
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


# --- REQ-002-3: meta 路径 --------------------------------------------------


def test_merge_template_structured_data_writes_meta_at_top() -> None:
    """REQ-002-3 AC-2: meta 字段写入 template 顶部，data 字段紧随其后。"""
    existing = {"full_text": "正文", "section_count": 1}
    template = {"title": "课程", "sections": ["一"]}
    meta = {"id": "tmpl-1", "version": 1, "layer": "L1"}

    data = _merge_template_structured_data(existing, template, meta)

    assert data["template"] == {
        "id": "tmpl-1",
        "version": 1,
        "layer": "L1",
        "title": "课程",
        "sections": ["一"],
    }
    # 顺序：先 meta 后 data
    assert list(data["template"].keys()) == ["id", "version", "layer", "title", "sections"]


def test_merge_template_structured_data_ignores_unknown_meta_keys(caplog) -> None:
    """REQ-002-3 AC-3: 未知 meta 键被忽略 + WARNING 日志。"""
    existing = {"full_text": "正文"}
    template = {"title": "课程"}
    meta = {"id": "tmpl-1", "version": 1, "layer": "L1", "foo": "bar"}

    with caplog.at_level(logging.WARNING, logger="app.contexts.document.application.tasks"):
        data = _merge_template_structured_data(existing, template, meta)

    assert "foo" not in data["template"]
    assert any("ignored unknown meta key" in rec.message for rec in caplog.records)


def test_merge_template_structured_data_meta_incomplete_falls_back(caplog) -> None:
    """REQ-002-3 AC-4: meta 缺核心键时回退旧 shape + WARNING 日志。"""
    existing = {"full_text": "正文"}
    template = {"title": "课程"}

    # 缺 layer
    with caplog.at_level(logging.WARNING, logger="app.contexts.document.application.tasks"):
        data = _merge_template_structured_data(
            existing, template, {"id": "tmpl-1", "version": 1}
        )

    assert data["template"] == {"title": "课程"}
    assert any("meta incomplete" in rec.message for rec in caplog.records)


def test_merge_template_structured_data_meta_none_legacy_shape() -> None:
    """REQ-002-3 AC-1 / AC-4: meta=None 完全保留旧行为。"""
    existing = {"full_text": "正文"}
    template = {"title": "课程"}

    data = _merge_template_structured_data(existing, template, None)

    assert data == {"full_text": "正文", "template": {"title": "课程"}}


def test_merge_template_structured_data_meta_preserves_shallow_copy() -> None:
    """REQ-002-3 AC-5: meta 写入后内嵌 list / dict 仍同引用。"""
    existing = {"full_text": "正文"}
    template = {
        "teaching_process": [{"step": "1"}],
        "assessment": [{"criterion": "理解", "score": 4}],
    }
    meta = {"id": "tmpl-1", "version": 1, "layer": "L1"}

    data = _merge_template_structured_data(existing, template, meta)

    assert data["template"] is not template
    assert data["template"]["teaching_process"] is template["teaching_process"]
    assert data["template"]["teaching_process"][0] is template["teaching_process"][0]
    assert data["template"]["assessment"] is template["assessment"]
    assert data["template"]["assessment"][0] is template["assessment"][0]
    # 核心键写入
    assert data["template"]["id"] == "tmpl-1"
    assert data["template"]["layer"] == "L1"
