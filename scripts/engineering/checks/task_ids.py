"""Task ID 卫生族：`check_followup_ids` / `check_backlog_done_index`."""

from __future__ import annotations

from pathlib import Path

from ._common import (
    BACKLOG_DONE_TYPES,
    FOLLOWUP_ID_RE,
    Issue,
    LEGACY_FOLLOWUP_REFS,
    TASK_ID_RE,
    iter_doc_files,
    read_lines,
    rel,
    section,
    split_table_row,
    table_rows,
)
from .product_planning import normalize_status


def check_followup_ids(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in iter_doc_files(root):
        for line_no, line in enumerate(read_lines(path), start=1):
            for match in FOLLOWUP_ID_RE.finditer(line):
                task_id = match.group(0)
                if (rel(path, root), task_id) in LEGACY_FOLLOWUP_REFS:
                    continue
                issues.append(
                    Issue(
                        path,
                        line_no,
                        "stable-task-id",
                        f"发现临时 follow-up 编号：{task_id}。",
                        "需要长期执行的 follow-up 应改为新的稳定编号，例如 REQ-007、TD-031 或 DOC-039。",
                    )
                )
    return issues


def collect_backlog_done_tasks(root: Path) -> list[tuple[Path, int, str, str, str]]:
    path = root / "docs/01-product-planning/04-backlog.md"
    lines = read_lines(path)
    _start, body = section(lines, "Backlog")
    tasks: list[tuple[Path, int, str, str, str]] = []
    for line_no, row in table_rows(body):
        cells = split_table_row(row)
        if len(cells) < 8:
            continue
        task_id, task_type, status = cells[0], cells[1], cells[2]
        if not TASK_ID_RE.fullmatch(task_id):
            continue
        if task_type not in BACKLOG_DONE_TYPES:
            continue
        if normalize_status(status) != "Done":
            continue
        tasks.append((path, line_no, task_id, task_type, cells[7]))
    return tasks


def has_fact_source(external: str) -> bool:
    return bool(external.strip()) and (
        "[" in external or "PR" in external or "http://" in external or "https://" in external
    )


def check_backlog_done_index(root: Path) -> list[Issue]:
    work_log_path = root / "docs/03-engineering-governance/work-log.md"
    work_log_text = work_log_path.read_text(encoding="utf-8") if work_log_path.exists() else ""
    issues: list[Issue] = []
    for path, line_no, task_id, _task_type, external in collect_backlog_done_tasks(root):
        if task_id in work_log_text or has_fact_source(external):
            continue
        issues.append(
            Issue(
                path,
                line_no,
                "backlog-done-index",
                f"Backlog 中已完成任务 {task_id} 缺少 work-log 或明确事实源。",
                "补充 docs/03-engineering-governance/work-log.md 索引，或在 Backlog External 列链接 PR/spec/plan/事实源。",
            )
        )
    return issues
