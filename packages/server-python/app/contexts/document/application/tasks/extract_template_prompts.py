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
            item_key = f["items"][0].get("key", "item") if f.get("items") else "item"
            lines.append(f"{prefix}{key}({label})[array型，成员为object，含字段：{item_key}]")
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
