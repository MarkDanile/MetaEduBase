#!/usr/bin/env python3
"""Import an external SKILL.md into a platform SopTemplate YAML draft (REQ-046 PR-7).

External skills (e.g. the QCC credit-due-diligence SKILL) ship as free
Markdown: an A-layer summary, an MCP dependency section, a numbered workflow
of analysis "维度" each bound to a tool chain, and a strict fill-in report
skeleton. The platform's :class:`SopTemplate` is declarative YAML, so this is
a *heuristic* conversion — it produces a registrable draft for human review,
not a lossless import.

Mapping:
- ``name``            <- the ``/command`` (kebab) or the first ``#`` title.
- ``description``     <- the leading blockquote summary.
- ``mcp_dependencies``<- the distinct servers in ``mcp__{server}__{tool}`` tokens.
- ``steps``           <- one ``mcp`` step per workflow "维度N"; the first tool
                        of its chain becomes ``server``/``tool``, the rest are
                        kept as ``analysis_rules`` so no call is dropped.
- ``report_template`` <- the fenced markdown block under "报告输出格式".

Usage::

    uv run python scripts/import_external_skill.py SKILL.md -o draft.yaml
    # review draft.yaml, then register via POST /api/v1/skills
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

_COMMAND_RE = re.compile(r"`/([a-z0-9][a-z0-9-]*)`")
_TOOL_TOKEN_RE = re.compile(r"mcp__([a-z0-9][a-z0-9-]*)__([a-z0-9_]+)")
_DIMENSION_RE = re.compile(r"^#{2,4}\s*维度[一二三四五六七八九十\d]*[：:]\s*(.+?)\s*$", re.M)
_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _slugify(text: str) -> str:
    """Best-effort kebab-case id from a Chinese/English dimension title."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "step"


def _extract_name(md: str) -> str:
    match = _COMMAND_RE.search(md)
    if match and _KEBAB_RE.match(match.group(1)):
        return match.group(1)
    title = re.search(r"^#\s+(.+?)\s*$", md, re.M)
    if title:
        slug = _slugify(title.group(1))
        if _KEBAB_RE.match(slug):
            return slug
    raise ValueError("无法从 SKILL.md 提取合法 kebab-case name（缺 /command 与英文标题）")


def _extract_description(md: str) -> str:
    for line in md.splitlines():
        line = line.strip()
        if line.startswith(">"):
            text = line.lstrip("> ").strip()
            if text and "核心能力" not in text and len(text) > 8:
                return text[:1000]
    return "外部导入 SKILL（待人工补全描述）"


def _extract_steps(md: str) -> list[dict]:
    dimensions = list(_DIMENSION_RE.finditer(md))
    if not dimensions:
        raise ValueError("SKILL.md 缺少'工作流/维度'小节，无法生成 steps")
    steps: list[dict] = []
    seen_ids: set[str] = set()
    for index, dim in enumerate(dimensions):
        title = dim.group(1)
        # 该维度小节文本 = 到下一个维度或文件尾
        start = dim.end()
        end = dimensions[index + 1].start() if index + 1 < len(dimensions) else len(md)
        section = md[start:end]
        tools = _TOOL_TOKEN_RE.findall(section)
        if not tools:
            continue
        server, tool = tools[0]
        step_id = _slugify(title)
        base, n = step_id, 2
        while step_id in seen_ids:
            step_id = f"{base}-{n}"
            n += 1
        seen_ids.add(step_id)
        extra = [f"{srv}__{tl}" for srv, tl in tools[1:]]
        steps.append(
            {
                "id": step_id,
                "type": "mcp",
                "server": server,
                "tool": tool,
                "title": title,
                "analysis_rules": ([f"工具链后续调用: {', '.join(extra)}"] if extra else []),
                "output": title,
            }
        )
    if not steps:
        raise ValueError("工作流维度内未找到任何 mcp__server__tool 工具 token")
    return steps


def _extract_report_template(md: str) -> str | None:
    marker = re.search(r"报告输出格式", md)
    if not marker:
        return None
    block = re.search(r"```(?:markdown)?\n(.*?)```", md[marker.end():], re.S)
    return block.group(1).strip() if block else None


def convert(md: str) -> dict:
    """Convert SKILL.md text into a SopTemplate draft dict."""
    steps = _extract_steps(md)
    servers = sorted({s["server"] for s in steps})
    draft: dict = {
        "name": _extract_name(md),
        "description": _extract_description(md),
        "mcp_dependencies": [{"server": s, "required": True} for s in servers],
        "steps": steps,
    }
    template = _extract_report_template(md)
    if template:
        draft["report_template"] = template
    return draft


def to_yaml(draft: dict) -> str:
    """Serialize the draft to YAML text (block style for report_template)."""

    class _Dumper(yaml.SafeDumper):
        pass

    def _str_representer(dumper, data):
        style = "|" if "\n" in data else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)

    _Dumper.add_representer(str, _str_representer)
    header = (
        "# 由 scripts/import_external_skill.py 从外部 SKILL.md 启发式转换生成。\n"
        "# 注册前请人工校订：steps 仅保留每个维度工具链首工具，其余见 analysis_rules；\n"
        "# server 需先在本 tenant 的 mcp_registry 注册（step.server 引用闭合校验）。\n"
    )
    return header + yaml.dump(
        draft, Dumper=_Dumper, allow_unicode=True, sort_keys=False
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_md", type=Path, help="外部 SKILL.md 路径")
    parser.add_argument("-o", "--output", type=Path, help="输出 YAML 路径（默认 stdout）")
    args = parser.parse_args()
    md = args.skill_md.read_text(encoding="utf-8")
    yaml_text = to_yaml(convert(md))
    if args.output:
        args.output.write_text(yaml_text, encoding="utf-8")
        print(f"draft written: {args.output}", file=sys.stderr)
    else:
        print(yaml_text)


if __name__ == "__main__":
    main()
