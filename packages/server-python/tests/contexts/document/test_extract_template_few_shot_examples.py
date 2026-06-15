"""TD-067: extract_template_prompts.build_few_shot_examples must emit examples for complex shapes.

Background: LLM extraction returns "-" for nested array[object] / table /
object[children] fields (TD-067 复测发现). Few-shot examples anchor the
harder shapes. This file locks:

  * array[object] with children → "示例（嵌套 array）" snippet
  * table with columns → "示例（table 表格）" snippet
  * object with children → "示例（object 多字段）" snippet
  * simple text / array-of-strings → NO snippet (zero overhead)

The function is pure: takes a list of field dicts (from Field.to_dict()),
returns a Markdown string. No DB, no LLM, no Celery.
"""

from __future__ import annotations

from app.contexts.document.application.tasks.extract_template_prompts import (
    build_few_shot_examples,
)
from app.contexts.template.domain.entity import Field, TableColumn


def _to_dicts(fields: list[Field]) -> list[dict]:
    return [f.to_dict() for f in fields]


def test_few_shot_skips_simple_text_field() -> None:
    """text field alone → no example emitted (overhead-free for simple templates)."""
    fields = _to_dicts([Field(key="title", label="标题", type="text")])
    out = build_few_shot_examples(fields)
    assert out == ""


def test_few_shot_skips_array_without_items() -> None:
    """array field with no items declared → no example (cannot anchor shape)."""
    fields = _to_dicts([Field(key="tags", label="标签", type="array", items=[])])
    out = build_few_shot_examples(fields)
    assert out == ""


def test_few_shot_emits_nested_array_example() -> None:
    """array[object] with children → '示例（嵌套 array）' markdown snippet."""
    fields = _to_dicts(
        [
            Field(
                key="teaching_plan",
                label="教学计划",
                type="array",
                items=[
                    Field(
                        key="semester",
                        label="学期",
                        type="object",
                        children=[
                            Field(key="course", label="课程", type="text"),
                            Field(key="hours", label="课时", type="number"),
                        ],
                    )
                ],
            )
        ]
    )
    out = build_few_shot_examples(fields)

    assert "示例（嵌套 array）" in out
    assert "```json" in out
    assert "teaching_plan" in out
    # Items' children are expanded directly as array elements
    assert "course" in out
    assert "hours" in out


def test_few_shot_emits_table_example() -> None:
    """table with columns → '示例（table 表格）' markdown snippet."""
    fields = _to_dicts(
        [
            Field(
                key="practice_links",
                label="实践环节",
                type="table",
                columns=[
                    TableColumn(key="category", label="类别", type="text"),
                    TableColumn(key="weeks", label="周数", type="number"),
                ],
            )
        ]
    )
    out = build_few_shot_examples(fields)

    assert "示例（table 表格）" in out
    assert "```json" in out
    assert "practice_links" in out
    assert "category" in out
    assert "weeks" in out


def test_few_shot_emits_object_with_children_example() -> None:
    """object field with children → '示例（object 多字段）' markdown snippet."""
    fields = _to_dicts(
        [
            Field(
                key="degree_requirements",
                label="学位要求",
                type="object",
                children=[
                    Field(key="min_credits", label="最低毕业学分", type="number"),
                    Field(key="gpa", label="平均绩点要求", type="number"),
                    Field(key="english_level", label="英语水平要求", type="text"),
                ],
            )
        ]
    )
    out = build_few_shot_examples(fields)

    assert "示例（object 多字段）" in out
    assert "```json" in out
    assert "degree_requirements" in out
    assert "min_credits" in out
    assert "gpa" in out
    assert "english_level" in out


def test_few_shot_emits_all_three_for_mixed_template() -> None:
    """End-to-end on the actual 人才培养方案 template shape:
    array[object] + table + object[children] all emit distinct snippets.
    """
    fields = _to_dicts(
        [
            Field(
                key="curriculum_system",
                label="课程体系",
                type="array",
                items=[
                    Field(
                        key="course",
                        label="课程",
                        type="object",
                        children=[Field(key="name", label="课程名", type="text")],
                    )
                ],
            ),
            Field(
                key="teaching_plan",
                label="教学计划",
                type="array",
                items=[
                    Field(
                        key="semester",
                        label="学期",
                        type="object",
                        children=[
                            Field(key="course", label="课程", type="text"),
                            Field(key="hours", label="周课时", type="number"),
                        ],
                    )
                ],
            ),
            Field(
                key="practice_links",
                label="实践环节",
                type="table",
                columns=[
                    TableColumn(key="category", label="类别", type="text"),
                    TableColumn(key="weeks", label="周数", type="number"),
                ],
            ),
            Field(
                key="degree_requirements",
                label="学位要求",
                type="object",
                children=[
                    Field(key="min_credits", label="最低学分", type="number"),
                ],
            ),
        ]
    )
    out = build_few_shot_examples(fields)

    # all 4 emit examples (curriculum_system + teaching_plan → array, practice_links → table,
    # degree_requirements → object)
    assert out.count("```json") == 4
    assert "curriculum_system" in out
    assert "teaching_plan" in out
    assert "practice_links" in out
    assert "degree_requirements" in out
    # snippets are joined with blank lines
    assert "\n\n" in out


def test_few_shot_does_not_emit_for_object_without_children() -> None:
    """object without children is meaningless; skip (no shape to anchor)."""
    fields = _to_dicts([Field(key="empty_obj", label="空对象", type="object")])
    out = build_few_shot_examples(fields)
    assert out == ""


def test_few_shot_does_not_emit_for_table_without_columns() -> None:
    """table without columns cannot be anchored; skip."""
    fields = _to_dicts([Field(key="empty_tbl", label="空表", type="table")])
    out = build_few_shot_examples(fields)
    assert out == ""
