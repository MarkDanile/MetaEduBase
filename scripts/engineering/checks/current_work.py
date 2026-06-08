"""`check_current_work` / `check_recent_completed_work_log` family.

校验 `docs/03-engineering-governance/current-work.md` 三个区域（当前进行中 /
下一批候选任务 / 最近完成）的一致性。
"""

from __future__ import annotations

from pathlib import Path

from ._common import (
    CURRENT_WORK_RECENT_SUMMARY_LIMIT,
    Issue,
    read_lines,
    section,
    split_table_row,
    table_rows,
)


def parse_current_work_completed_ids(root: Path) -> list[tuple[str, int]]:
    path = root / "docs/03-engineering-governance/current-work.md"
    lines = read_lines(path)
    _recent_start, recent_body = section(lines, "最近完成")
    completed: list[tuple[str, int]] = []
    from ._common import TASK_ID_RE

    for line_no, row in table_rows(recent_body):
        cells = split_table_row(row)
        if len(cells) < 3 or "完成" not in cells[2]:
            continue
        task_match = TASK_ID_RE.search(cells[1])
        if task_match:
            completed.append((task_match.group(0), line_no))
    return completed


def check_current_work(root: Path) -> list[Issue]:
    path = root / "docs/03-engineering-governance/current-work.md"
    lines = read_lines(path)
    issues: list[Issue] = []

    for title in ("当前进行中", "下一批候选任务", "最近完成"):
        count = sum(1 for line in lines if line.strip() == f"## {title}")
        if count > 1:
            issues.append(
                Issue(
                    path,
                    1,
                    "current-work",
                    f"“{title}”区域不得重复。",
                    "合并重复区域，current-work.md 只保留一个对应标题。",
                )
            )

    candidate_start, candidate_body = section(lines, "下一批候选任务")
    if candidate_start == -1:
        issues.append(
            Issue(
                path,
                1,
                "current-work",
                "缺少“下一批候选任务”区域。",
                "恢复 current-work.md 的近期候选任务区域。",
            )
        )
    else:
        candidates = table_rows(candidate_body)
        if len(candidates) > 3:
            issues.append(
                Issue(
                    path,
                    candidates[3][0],
                    "current-work",
                    "下一批候选任务最多 3 行。",
                    "只保留 1 到 3 个近期未完成候选，完整 backlog 回到事实源。",
                )
            )
        for line_no, row in candidates:
            if "🟢 完成" in row:
                issues.append(
                    Issue(
                        path,
                        line_no,
                        "current-work",
                        "候选区不得出现完成任务。",
                        "已完成任务应进入“最近完成”或 work-log，不留在候选区。",
                    )
                )

    recent_start, recent_body = section(lines, "最近完成")
    if recent_start == -1:
        issues.append(
            Issue(
                path,
                1,
                "current-work",
                "缺少“最近完成”区域。",
                "恢复 current-work.md 的最近完成摘要区域。",
            )
        )
    else:
        recent = table_rows(recent_body)
        if len(recent) > 5:
            issues.append(
                Issue(
                    path,
                    recent[5][0],
                    "current-work",
                    "最近完成最多 5 行。",
                    "最旧完成项应归档到 work-log 或对应事实源。",
                )
            )
        for line_no, row in recent:
            cells = split_table_row(row)
            if len(cells) < 5:
                continue
            summary = cells[3]
            if len(summary) > CURRENT_WORK_RECENT_SUMMARY_LIMIT:
                issues.append(
                    Issue(
                        path,
                        line_no,
                        "current-work",
                        "最近完成摘要过长。",
                        "current-work.md 只保留短摘要；详细交付事实归档到 work-log、技术债总账或 PR。",
                    )
                )

    return issues


def check_recent_completed_work_log(root: Path) -> list[Issue]:
    current_path = root / "docs/03-engineering-governance/current-work.md"
    work_log_path = root / "docs/03-engineering-governance/work-log.md"
    work_log_text = work_log_path.read_text(encoding="utf-8") if work_log_path.exists() else ""
    issues: list[Issue] = []

    for task_id, line_no in parse_current_work_completed_ids(root):
        if task_id in work_log_text:
            continue
        issues.append(
            Issue(
                current_path,
                line_no,
                "current-work-work-log",
                f"最近完成任务 {task_id} 缺少 work-log 索引。",
                "在 docs/03-engineering-governance/work-log.md 增加一行索引，或从最近完成移出。",
            )
        )

    return issues
