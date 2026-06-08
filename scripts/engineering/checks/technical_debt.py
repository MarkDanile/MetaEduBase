"""Technical-debt 一致性族：`check_technical_debt` / `check_completed_plans`."""

from __future__ import annotations

import re
from pathlib import Path

from ._common import (
    DebtDetail,
    Issue,
    read_lines,
    section,
    split_table_row,
    table_rows,
)


DETAIL_HEADING_RE = re.compile(r"^### (TD-\d{3}):")
STATUS_LINE_RE = re.compile(r"^状态：(.+)$")


def parse_debt_overview(lines: list[str]) -> dict[str, tuple[int, str]]:
    _start, body = section(lines, "任务总览")
    overview: dict[str, tuple[int, str]] = {}
    for line_no, row in table_rows(body):
        cells = split_table_row(row)
        if len(cells) < 3 or not re.fullmatch(r"TD-\d{3}", cells[0]):
            continue
        overview[cells[0]] = (line_no, cells[2])
    return overview


def parse_debt_details(lines: list[str]) -> dict[str, DebtDetail]:
    details: dict[str, DebtDetail] = {}
    headings: list[tuple[str, int]] = []
    for line_no, line in enumerate(lines, start=1):
        match = DETAIL_HEADING_RE.match(line)
        if match:
            headings.append((match.group(1), line_no))

    for index, (task_id, heading_line) in enumerate(headings):
        next_line = headings[index + 1][1] if index + 1 < len(headings) else len(lines) + 1
        body = [
            (line_no, lines[line_no - 1])
            for line_no in range(heading_line + 1, next_line)
        ]
        status: str | None = None
        for _line_no, line in body:
            status_match = STATUS_LINE_RE.match(line.strip())
            if status_match:
                status = status_match.group(1).strip()
                break
        details[task_id] = DebtDetail(heading_line, status, body)
    return details


def delivery_record_lines(detail: DebtDetail) -> list[tuple[int, str]]:
    record: list[tuple[int, str]] = []
    in_record = False
    for line_no, line in detail.body:
        stripped = line.strip()
        if stripped == "**交付记录**":
            in_record = True
            continue
        if in_record and stripped.startswith("**") and stripped.endswith("**"):
            break
        if in_record:
            record.append((line_no, line))
    return record


def check_technical_debt(root: Path) -> list[Issue]:
    path = root / "docs/03-engineering-governance/technical-debt.md"
    lines = read_lines(path)
    issues: list[Issue] = []
    overview = parse_debt_overview(lines)
    details = parse_debt_details(lines)

    for task_id, (line_no, overview_status) in overview.items():
        detail = details.get(task_id)
        if detail is None or detail.status is None:
            continue
        if detail.status != overview_status:
            issues.append(
                Issue(
                    path,
                    line_no,
                    "technical-debt-status",
                    f"技术债总览和详情状态不一致：{task_id} 总览为 {overview_status}，详情为 {detail.status}。",
                    "同步任务总览表和对应任务详情的 `状态：` 字段。",
                )
            )

    for task_id, detail in details.items():
        if detail.status != "🟢 完成":
            continue
        record = delivery_record_lines(detail)
        if not record:
            issues.append(
                Issue(
                    path,
                    detail.line,
                    "technical-debt-delivery",
                    f"{task_id} 已完成但缺少交付记录。",
                    "补充完成日期、PR / commit 或验证摘要。",
                )
            )
            continue
        for line_no, line in record:
            if "未完成" in line:
                issues.append(
                    Issue(
                        path,
                        line_no,
                        "technical-debt-delivery",
                        f"{task_id} 完成任务的交付记录仍写未完成。",
                        "将交付记录回填为完成日期、PR / commit 和验证摘要。",
                    )
                )

    return issues


def is_completed_plan(text: str) -> bool:
    return "状态：🟢 完成" in text or "交付历史" in text and "合并到 `main`" in text


def allowed_active_checkbox(line: str) -> bool:
    lowered = line.lower()
    return "out of scope" in lowered or "td-" in lowered or "后续" in line


def check_completed_plans(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in sorted((root / "docs/02-delivery-plans/02-plans").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not is_completed_plan(text):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if re.match(r"^\s*-\s\[\s\]", line) and not allowed_active_checkbox(line):
                issues.append(
                    Issue(
                        path,
                        line_no,
                        "completed-plan-checkbox",
                        "已完成 plan 不得残留活动式 `- [ ]`。",
                        "改为历史记录 / `- [x]`，或绑定后续任务编号并标明 out of scope。",
                    )
                )
    return issues
