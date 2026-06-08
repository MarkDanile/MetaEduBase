"""`check_scripted_gate_candidates`: 反查 `quality-gates.md#脚本门禁候选清单` 中标为「已实现」的项。"""

from __future__ import annotations

from pathlib import Path

from ._common import (
    Issue,
    read_lines,
    section,
    SCRIPTED_GATE_CANDIDATES,
    split_table_row,
    table_rows,
)


def check_scripted_gate_candidates(root: Path) -> list[Issue]:
    path = root / "docs/03-engineering-governance/01-rules/quality-gates.md"
    lines = read_lines(path)
    _start, body = section(lines, "脚本门禁候选清单")
    issues: list[Issue] = []
    for line_no, row in table_rows(body):
        cells = split_table_row(row)
        if len(cells) < 2 or "已实现" not in cells[1]:
            continue
        candidate = cells[0]
        if candidate in SCRIPTED_GATE_CANDIDATES:
            continue
        issues.append(
            Issue(
                path,
                line_no,
                "scripted-gate-candidate",
                f"脚本门禁候选标为已实现，但脚本未登记反查：{candidate}",
                "要么补充对应脚本检查和 SCRIPTED_GATE_CANDIDATES 映射，要么把状态改为候选或部分实现。",
            )
        )
    return issues
