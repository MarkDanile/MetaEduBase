"""Regression tests for ``extract_template_prompts`` nested-structure contract.

The helpers under test (``build_fields_desc``, ``try_parse``,
``_merge_template_structured_data``) are pure functions invoked in the
``extract_template`` Celery task. This file locks their behavior on
object / array / table nested shapes so the LLM-extraction pipeline can
be regression-tested without a live LLM or PostgreSQL connection.

Conventions:
  * Import helpers directly from ``extract_template_prompts``; the
    re-export in ``app.contexts.document.application.tasks`` is kept for
    historical tests only.
  * Build ``Field`` / ``TableColumn`` instances via
    ``app.contexts.template.domain.entity``.
  * No DB, no LLM, no Celery: every test runs offline.
"""

from __future__ import annotations

import json

from app.contexts.document.application.tasks.extract_template_prompts import (
    _merge_template_structured_data,
    build_fields_desc,
    try_parse,
)
from app.contexts.template.domain.entity import Field, TableColumn

# --- AC-1: build_fields_desc on object nesting -----------------------------


def test_build_fields_desc_object_nesting_includes_children() -> None:
    fields = [
        Field(
            key="basic_info",
            label="基本信息",
            type="object",
            children=[
                Field(key="subject", label="学科", type="text"),
                Field(key="grade", label="年级", type="text"),
            ],
        )
    ]

    desc = build_fields_desc([f.to_dict() for f in fields])

    assert "basic_info(基本信息)[object型，含子字段：" in desc
    assert "subject(学科)[text型]" in desc
    assert "grade(年级)[text型]" in desc
    assert desc.endswith("]")


def test_build_fields_desc_two_level_object_nesting() -> None:
    fields = [
        Field(
            key="outer",
            label="外层",
            type="object",
            children=[
                Field(
                    key="inner",
                    label="内层",
                    type="object",
                    children=[Field(key="leaf", label="叶子", type="text")],
                )
            ],
        )
    ]

    desc = build_fields_desc([f.to_dict() for f in fields])

    assert "outer(外层)[object型，含子字段：" in desc
    assert "inner(内层)[object型，含子字段：" in desc
    assert "leaf(叶子)[text型]" in desc


# --- AC-2: build_fields_desc on array nesting ------------------------------


def test_build_fields_desc_array_uses_first_item_key() -> None:
    fields = [
        Field(
            key="teaching_process",
            label="教学过程",
            type="array",
            items=[
                Field(
                    key="step",
                    label="步骤",
                    type="object",
                    children=[Field(key="activity", label="活动", type="text")],
                )
            ],
        )
    ]

    desc = build_fields_desc([f.to_dict() for f in fields])

    # array 行只声明"成员为object，含字段：step"，不展开 step 内部 children
    assert desc == "teaching_process(教学过程)[array型，成员为object，含字段：step]"


def test_build_fields_desc_array_without_items_falls_back_to_item_key() -> None:
    # TD-034 (Route A): ``f.get("items") is not None`` replaces the old falsy
    # check so that ``items=[]`` still enters the array branch and falls back
    # to the generic key "item".  This preserves the "成员为object" hint for
    # LLM, avoiding the degradation to bare ``[array型]``.
    fields = [
        Field(key="empty_array", label="空数组", type="array", items=[]),
    ]

    desc = build_fields_desc([f.to_dict() for f in fields])

    assert desc == "empty_array(空数组)[array型，成员为object，含字段：item]"


# --- AC-3: build_fields_desc on table nesting ------------------------------


def test_build_fields_desc_table_lists_columns_in_order() -> None:
    fields = [
        Field(
            key="assessment",
            label="评价",
            type="table",
            columns=[
                TableColumn(key="criterion", label="标准", type="text"),
                TableColumn(key="score", label="分数", type="number"),
                TableColumn(key="remark", label="备注", type="textarea"),
            ],
        )
    ]

    desc = build_fields_desc([f.to_dict() for f in fields])

    assert desc == "assessment(评价)[table型，列：criterion, score, remark]"


# --- AC-4: build_fields_desc on mixed nesting ------------------------------


def test_build_fields_desc_mixed_types_preserve_order_and_type_tag() -> None:
    fields = [
        Field(key="title", label="标题", type="text"),
        Field(
            key="basic_info",
            label="基本信息",
            type="object",
            children=[Field(key="subject", label="学科", type="text")],
        ),
        Field(
            key="teaching_process",
            label="教学过程",
            type="array",
            items=[Field(key="step", label="步骤", type="text")],
        ),
        Field(
            key="assessment",
            label="评价",
            type="table",
            columns=[TableColumn(key="criterion", label="标准", type="text")],
        ),
    ]

    desc = build_fields_desc([f.to_dict() for f in fields])

    parts = desc.split(", ")
    assert len(parts) == 4
    assert parts[0] == "title(标题)[text型]"
    assert parts[1].startswith("basic_info(基本信息)[object型，含子字段：")
    assert parts[2] == "teaching_process(教学过程)[array型，成员为object，含字段：step]"
    assert parts[3] == "assessment(评价)[table型，列：criterion]"


# --- AC-5: try_parse preserves nested object / array / table ---------------


def test_try_parse_preserves_nested_structures_from_markdown_fence() -> None:
    payload = {
        "basic_info": {"subject": "数学", "grade": "三年级"},
        "teaching_process": [
            {"step": "导入", "activity": "提问"},
            {"step": "讲授", "activity": "演示"},
        ],
        "assessment": [
            {"criterion": "理解", "score": 4, "remark": "好"},
        ],
    }
    content = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"

    parsed = try_parse(content)

    assert isinstance(parsed["basic_info"], dict)
    assert parsed["basic_info"]["subject"] == "数学"
    assert isinstance(parsed["teaching_process"], list)
    assert all(isinstance(item, dict) for item in parsed["teaching_process"])
    assert parsed["teaching_process"][1]["step"] == "讲授"
    assert isinstance(parsed["assessment"], list)
    assert parsed["assessment"][0]["criterion"] == "理解"


# --- AC-6: try_parse strips <think>...</think> before parsing --------------


def test_try_parse_strips_think_tag_then_parses_nested() -> None:
    payload = {
        "teaching_process": [{"step": "导入", "activity": "提问"}],
    }
    content = (
        "<think>调用 LLM 之前先思考文档结构</think>"
        "```json\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n```"
    )

    parsed = try_parse(content)

    assert "teaching_process" in parsed
    assert isinstance(parsed["teaching_process"], list)
    assert parsed["teaching_process"][0]["activity"] == "提问"


# --- AC-7: try_parse degrades to {} on bad JSON ----------------------------


def test_try_parse_returns_empty_dict_on_malformed_json() -> None:
    content = "```json\n{ this is not valid json\n```"

    parsed = try_parse(content)

    assert parsed == {}


def test_try_parse_returns_empty_dict_on_unclosed_fence() -> None:
    content = "```json\n{\"a\": 1"

    parsed = try_parse(content)

    assert parsed == {}


# --- AC-8: _merge_template_structured_data shallow-copies template --------


def test_merge_template_structured_data_shallow_copies_nested_template() -> None:
    existing = {"full_text": "正文", "section_count": 1}
    template = {
        "teaching_process": [{"step": "导入", "activity": "提问"}],
        "assessment": [{"criterion": "理解", "score": 4}],
    }

    merged = _merge_template_structured_data(existing, template)

    # 外层 template 是新 dict
    assert merged["template"] is not template
    # 但内嵌 list / dict 仍是同一引用（浅拷贝契约）
    assert merged["template"]["teaching_process"] is template["teaching_process"]
    assert merged["template"]["teaching_process"][0] is template["teaching_process"][0]
    # 既有字段不丢
    assert merged["full_text"] == "正文"
    assert merged["section_count"] == 1


# --- REQ-002-3: meta + 嵌套浅拷贝组合 --------------------------------------


def test_merge_template_structured_data_with_meta_preserves_nested_shallow_copy() -> None:
    """REQ-002-3 AC-9: meta 存在时，嵌套 list / dict 仍浅拷贝（外层新 dict）。"""
    template_data = {
        "basic_info": {"subject": "语文", "grade": "高一"},
        "teaching_process": [{"step": "导入", "duration": 5}],
        "assessment": [{"criterion": "理解", "score": 4}],
    }
    meta = {"id": "tmpl-1", "version": 1, "layer": "L1"}

    merged = _merge_template_structured_data({}, template_data, meta)

    # 浅拷贝契约
    assert merged["template"] is not template_data
    assert merged["template"]["basic_info"] is template_data["basic_info"]
    assert merged["template"]["teaching_process"] is template_data["teaching_process"]
    assert merged["template"]["teaching_process"][0] is template_data["teaching_process"][0]
    assert merged["template"]["assessment"] is template_data["assessment"]
    # 核心键写入
    assert merged["template"]["id"] == "tmpl-1"
    assert merged["template"]["layer"] == "L1"
