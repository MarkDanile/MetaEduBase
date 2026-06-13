"""Task pool ordering checks.

These checks intentionally avoid re-sorting historical rows.  They only ensure
the newest stable id for each prefix is not inserted before older rows of the
same prefix.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._common import Issue, read_lines, section, split_table_row, table_rows

TASK_POOL_ID_RE = re.compile(
    r"^(?P<prefix>REQ|TD|DOC|BUG|APP)-(?P<number>\d{3})(?:-\d+)?$"
)


def _collect_task_rows(
    path: Path,
    section_title: str,
) -> list[tuple[int, str, str, int]]:
    lines = read_lines(path)
    _start, body = section(lines, section_title)
    rows: list[tuple[int, str, str, int]] = []
    for line_no, row in table_rows(body):
        cells = split_table_row(row)
        if not cells:
            continue
        match = TASK_POOL_ID_RE.fullmatch(cells[0])
        if not match:
            continue
        rows.append(
            (
                line_no,
                cells[0],
                match.group("prefix"),
                int(match.group("number")),
            )
        )
    return rows


def _check_latest_id_is_last(
    path: Path,
    rows: list[tuple[int, str, str, int]],
    label: str,
) -> list[Issue]:
    issues: list[Issue] = []
    prefixes = sorted({prefix for _line_no, _task_id, prefix, _number in rows})
    for prefix in prefixes:
        prefix_rows = [row for row in rows if row[2] == prefix]
        latest_number = max(number for _line_no, _task_id, _prefix, number in prefix_rows)
        latest_rows = [row for row in prefix_rows if row[3] == latest_number]
        latest_line, latest_task_id, _prefix, _number = latest_rows[-1]
        older_after_latest = [
            (line_no, task_id)
            for line_no, task_id, _prefix, number in prefix_rows
            if number < latest_number and line_no > latest_line
        ]
        if not older_after_latest:
            continue
        older_line, older_task_id = older_after_latest[0]
        issues.append(
            Issue(
                path,
                latest_line,
                "task-pool-order",
                f"{label} 中 {prefix} 最新编号 {latest_task_id} 后面仍有较小编号 {older_task_id}（第 {older_line} 行）。",
                "新增任务必须追加到同前缀主表末尾；不要把新编号插入历史编号中间。",
            )
        )
    return issues


def check_task_pool_order(root: Path) -> list[Issue]:
    checks = (
        (
            root / "docs/01-product-planning/04-backlog.md",
            "Backlog",
            "Backlog 主表",
        ),
        (
            root / "docs/03-engineering-governance/technical-debt.md",
            "任务总览",
            "technical-debt 任务总览",
        ),
    )
    issues: list[Issue] = []
    for path, section_title, label in checks:
        if not path.exists():
            continue
        rows = _collect_task_rows(path, section_title)
        issues.extend(_check_latest_id_is_last(path, rows, label))
    return issues
