"""Gate file scope guard.

DOC-073: prevent ordinary product / feature tasks from modifying the
engineering gate implementation to make the current task pass.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ._common import Issue, read_lines, section, split_table_row, table_rows

_GIT_TIMEOUT_S = 5
_GATE_PATH_PREFIXES = (
    "scripts/engineering/check_engineering_docs.py",
    "scripts/engineering/checks/",
    "scripts/check-engineering-docs",
)
_ALLOWED_TASK_PREFIXES = ("DOC-",)
_ALLOWED_TASK_HINTS = (
    "门禁",
    "质量",
    "脚本",
    "治理",
    "规则",
    "check-engineering-docs",
    "quality",
    "gate",
    "known_issues",
    "ci",
)


def _git_lines(root: Path, args: list[str]) -> list[str] | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _changed_paths(root: Path) -> set[str] | None:
    if _git_lines(root, ["rev-parse", "--is-inside-work-tree"]) is None:
        return None

    rel_paths: set[str] = set()
    for upstream in ("origin/main", "main"):
        base_lines = _git_lines(root, ["merge-base", "HEAD", upstream])
        if not base_lines:
            continue
        rel_paths.update(
            _git_lines(
                root,
                [
                    "diff",
                    "--name-only",
                    "--diff-filter=ACMRT",
                    f"{base_lines[0]}...HEAD",
                ],
            )
            or []
        )
        break

    rel_paths.update(
        _git_lines(root, ["diff", "--name-only", "--cached", "--diff-filter=ACMRT", "HEAD"])
        or []
    )
    rel_paths.update(
        _git_lines(root, ["diff", "--name-only", "--diff-filter=ACMRT", "HEAD"])
        or []
    )
    rel_paths.update(_git_lines(root, ["ls-files", "--others", "--exclude-standard"]) or [])
    return rel_paths


def _is_gate_path(rel_path: str) -> bool:
    return any(
        rel_path == prefix.rstrip("/") or rel_path.startswith(prefix)
        for prefix in _GATE_PATH_PREFIXES
    )


def _active_task_row(root: Path) -> tuple[int, str] | None:
    path = root / "docs/03-engineering-governance/current-work.md"
    lines = read_lines(path)
    _start, body = section(lines, "当前进行中")
    for line_no, row in table_rows(body):
        cells = split_table_row(row)
        if not cells or cells[0] == "暂无":
            continue
        return line_no, row
    return None


def _task_allows_gate_changes(row: str) -> bool:
    lowered = row.lower()
    return any(row.startswith(f"| {prefix}") for prefix in _ALLOWED_TASK_PREFIXES) and any(
        hint in lowered for hint in _ALLOWED_TASK_HINTS
    )


def check_gate_file_scope(root: Path) -> list[Issue]:
    """Fail when gate files changed outside an explicit gate/governance task."""
    changed = _changed_paths(root)
    if changed is None:
        return []

    gate_paths = sorted(path for path in changed if _is_gate_path(path))
    if not gate_paths:
        return []

    current_path = root / "docs/03-engineering-governance/current-work.md"
    active = _active_task_row(root)
    if active is not None and _task_allows_gate_changes(active[1]):
        return []

    line_no = active[0] if active is not None else 1
    preview = ", ".join(gate_paths[:3])
    if len(gate_paths) > 3:
        preview += f", ... (+{len(gate_paths) - 3})"
    return [
        Issue(
            current_path,
            line_no,
            "gate-file-scope",
            f"本次变更修改了门禁脚本文件，但当前任务不是明确的门禁 / 治理脚本任务：{preview}",
            "停止当前任务并单独立项 DOC 门禁治理任务；不得在业务 / 修复任务中修改门禁脚本、KNOWN_ISSUES、忽略列表或阈值来绕过失败。",
        )
    ]
