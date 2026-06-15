"""Prompt construction + JSON parsing helpers for `extract_template` task.

`build_fields_desc` recursively describes nested field structure for LLM.
`try_parse` parses the LLM response into a dict, tolerating markdown fences and
MiniMax-M2 thinking tags.
`_build_parsed_structured_data` and `_merge_template_structured_data` keep the
stable structured_data container contract used by parse_document → extract_template.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.shared.schemas.document import TEMPLATE_META_RESERVED_KEYS

logger = logging.getLogger("app.contexts.document.application.tasks")

# REQ-002-3: meta key whitelist for `_merge_template_structured_data`.
# Single source of truth: scripts/codegen/gen_shared_schemas.py → app/shared/schemas/document.py
_TEMPLATE_META_KEYS = tuple(TEMPLATE_META_RESERVED_KEYS)
# Core keys whose absence triggers a fallback to the legacy shape (AC-4).
_TEMPLATE_META_CORE_KEYS = ("id", "version", "layer")


def _build_parsed_structured_data(
    full_text: str,
    section_count: int,
    sections: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Build the stable structured_data container written by parse_document.

    sections: list of section dicts from ParsedDocument.sections, each containing
    title, level, path, page, content. When None (legacy path), only full_text
    and section_count are stored.
    """
    result: dict[str, object] = {"full_text": full_text, "section_count": section_count}
    if sections is not None:
        result["sections"] = sections
    return result


def _merge_template_structured_data(
    existing: object,
    template_data: dict[str, object],
    meta: dict[str, object] | None = None,
) -> dict[str, object]:
    """Merge template extraction output into the structured_data container.

    meta (REQ-002-3): when provided and contains the core keys
    (id, version, layer), the meta fields are written to the top of
    merged["template"], BEFORE the extracted template_data fields. Keys
    outside _TEMPLATE_META_KEYS are silently dropped (with one WARNING
    log per unknown key). If any core key is missing, meta is ignored
    and the legacy shape is preserved (with one WARNING log).
    """
    if not isinstance(template_data, dict):
        raise TypeError("template_data must be a dict")

    if isinstance(existing, str):
        existing = json.loads(existing)

    if isinstance(existing, dict):
        merged: dict[str, object] = dict(existing)
    else:
        merged = {}

    # 浅拷贝契约：外层新 dict，内嵌 list / dict 仍是同一引用
    template_out: dict[str, object] = {}

    if meta is not None:
        unknown = [k for k in meta if k not in _TEMPLATE_META_KEYS]
        for k in unknown:
            logger.warning(
                "extract_template.merge_template: ignored unknown meta key %r", k
            )
        if all(k in meta for k in _TEMPLATE_META_CORE_KEYS):
            for k in _TEMPLATE_META_CORE_KEYS:
                if k in meta:
                    template_out[k] = meta[k]
            for k in ("matched_type", "confidence", "reason"):
                if k in meta:
                    template_out[k] = meta[k]
        else:
            logger.warning(
                "extract_template.merge_template: meta incomplete "
                "(missing one of %s), falling back to legacy shape",
                _TEMPLATE_META_CORE_KEYS,
            )

    for k, v in template_data.items():
        template_out[k] = v

    merged["template"] = template_out
    return merged


def build_fields_desc(fields: list[Any], indent: int = 0) -> str:
    """Recursively describe nested field structure for LLM.

    Schema:
      - object型 + children: "(label)[object型，含子字段：…]"
      - array型: "(label)[array型，成员为object，含字段：…]"
        - items present and non-empty → uses first item's key
        - items absent or empty → fallback key "item"
        - The "成员为object" hint is always emitted for array型 because the
          LLM prompt contract requires "每个成员是包含子字段的object".
          See TD-034.
      - table型 + columns: "(label)[table型，列：…]"
      - 其他: "(label)[type型]"
    """
    lines = []
    for f in fields:
        key = f.get("key", "")
        label = f.get("label", "")
        ftype = f.get("type", "text")
        prefix = "  " * indent
        if ftype == "object" and f.get("children"):
            children_desc = build_fields_desc(f["children"], indent + 1)
            lines.append(f"{prefix}{key}({label})[object型，含子字段：{children_desc}]")
        elif ftype == "array":
            items = f.get("items") or []
            if items:
                item = items[0]
                item_children = item.get("children") or []
                if item_children:
                    children_desc = build_fields_desc(item_children, indent + 1)
                    lines.append(f"{prefix}{key}({label})[array型，成员含字段：{children_desc}]")
                else:
                    item_key = item.get("key", "item")
                    lines.append(f"{prefix}{key}({label})[array型，成员含字段：{item_key}]")
            else:
                lines.append(f"{prefix}{key}({label})[array型]")
        elif ftype == "table" and f.get("columns"):
            col_names = ", ".join(c["key"] for c in f["columns"])
            lines.append(f"{prefix}{key}({label})[table型，列：{col_names}]")
        else:
            lines.append(f"{prefix}{key}({label})[{ftype}型]")
    return ", ".join(lines)


def try_parse(content: str) -> dict:
    """Parse LLM JSON response, tolerating markdown fences and thinking tags."""
    # Strip MiniMax-M2 thinking tags that may appear before JSON
    stripped = re.sub(
        r"<think>.*?</think>", "", content, flags=re.DOTALL
    ).strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    try:
        json_start = stripped.index("{")
        json_end = stripped.rindex("}") + 1
        return json.loads(stripped[json_start:json_end])
    except (ValueError, json.JSONDecodeError):
        return {}


# TD-067: few-shot examples for nested-schema LLM extraction.
# The LLM successfully extracts simple types (object/text/array of strings)
# but returns "-" for complex shapes (array[object], table, object[children]).
# These examples anchor the schema and output format.
#
# The output is a stable Markdown string injected into the prompt after
# the "要求" rules. Each example is a small, hand-curated JSON snippet
# matching the field's expected shape (truncated where natural).


def _example_nested_array(field: dict[str, Any]) -> str:
    """Few-shot for `array[object]` fields (e.g. teaching_plan).

    Outer key is the field's own key; inner structure is built from
    items[0].children — recursed so nested object children are fully
    visible to the LLM.
    """
    field_key = field.get("key", "array_field")
    items = field.get("items") or []
    item_obj = items[0] if items else {}
    children = item_obj.get("children") or []

    def _build_child_snippet(child: dict[str, Any]) -> str:
        """Recursively build a JSON value snippet for a child field."""
        ctype = child.get("type", "text")
        if ctype == "object" and child.get("children"):
            inner = ", ".join(
                f'"{sc.get("key", "?")}": {_build_child_snippet(sc)}'
                for sc in child["children"]
            )
            return f"{{{inner}}}"
        return f'"<{child.get("label", child.get("key", "?"))}>"'

    if children:
        child_lines = ", ".join(
            f'"{c.get("key", "?")}": {_build_child_snippet(c)}'
            for c in children
        )
        inner = (
            f'[\n'
            f'    {{{child_lines}}},\n'
            f'    {{{child_lines}}}\n'
            f'  ]'
        )
    else:
        inner = '[\n    {},\n    {}\n  ]'
    return (
        f'示例（嵌套 array）：\n```json\n{{\n'
        f'  "{field_key}": {inner}\n'
        f'}}\n```\n'
    )


def _example_table(field: dict[str, Any]) -> str:
    """Few-shot for `table` fields (e.g. practice_links)."""
    field_key = field.get("key", "table_field")
    columns = field.get("columns") or []
    if columns:
        col_obj = ", ".join(
            f'"{c.get("key", "?")}": "<{c.get("label", c.get("key", "?"))}>"'
            for c in columns
        )
    else:
        col_obj = '"col1": "<值>", "col2": "<值>"'
    return (
        f'示例（table 表格）：\n```json\n{{\n'
        f'  "{field_key}": [\n'
        f'    {{{col_obj}}},\n'
        f'    {{{col_obj}}}\n'
        f'  ]\n'
        f'}}\n```\n'
    )


def _example_object(field: dict[str, Any]) -> str:
    """Few-shot for `object` fields with children (e.g. degree_requirements)."""
    field_key = field.get("key", "object_field")
    children = field.get("children") or []
    if children:
        child_lines = ", ".join(
            f'"{c.get("key", "?")}": "<{c.get("label", c.get("key", "?"))}>"'
            for c in children
        )
    else:
        child_lines = '"key": "<值>"'
    return (
        f'示例（object 多字段）：\n```json\n{{\n'
        f'  "{field_key}": {{{child_lines}}}\n'
        f'}}\n```\n'
    )


def build_few_shot_examples(fields: list[Any]) -> str:
    """TD-067: Build few-shot JSON examples for nested schema fields.

    Scans ``fields`` (list of field dicts from ``Field.to_dict()``) and
    emits one Markdown snippet per complex-shape field. Simple text/array
    fields (no items, no children, no columns) are skipped — the LLM
    already handles those correctly.

    Returns an empty string when no complex field is present (zero overhead
    for simple templates).

    Output format (joined with blank lines):

        示例（嵌套 array）：
        ```json
        { ... }
        ```

        示例（table 表格）：
        ```json
        { ... }
        ```
    """
    snippets: list[str] = []
    for f in fields:
        ftype = f.get("type", "")
        if ftype == "array" and f.get("items"):
            snippets.append(_example_nested_array(f))
        elif ftype == "table" and f.get("columns"):
            snippets.append(_example_table(f))
        elif ftype == "object" and f.get("children"):
            snippets.append(_example_object(f))
    return "\n".join(snippets)
