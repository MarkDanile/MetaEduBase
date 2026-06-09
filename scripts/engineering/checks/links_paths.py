"""链接 / 路径族：`check_legacy_doc_roots` / `check_markdown_links` / `check_work_log_append_only`."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ._common import (
    Issue,
    iter_doc_files,
    LEGACY_DOC_ROOT_NAMES,
    LINK_RE,
    normalize_link_target,
    read_lines,
    should_skip_link,
)


def check_legacy_doc_roots(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for name in LEGACY_DOC_ROOT_NAMES:
        path = root / "docs" / name
        if not path.exists():
            continue
        issues.append(
            Issue(
                path,
                1,
                "legacy-doc-root",
                f"旧顶层文档目录仍存在：`docs/{name}`。",
                "迁移或镜像到编号目录；历史 superpower 输出只能保留在 90-compat-legacy 下。",
            )
        )
    return issues


def check_markdown_links(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path in iter_doc_files(root):
        for line_no, line in enumerate(read_lines(path), start=1):
            for match in LINK_RE.finditer(line):
                target = normalize_link_target(match.group(1))
                if should_skip_link(target):
                    continue
                target_path = (
                    root / target.lstrip("/")
                    if target.startswith("/")
                    else path.parent / target
                ).resolve()
                if not target_path.exists():
                    issues.append(
                        Issue(
                            path,
                            line_no,
                            "markdown-link",
                            f"Markdown 链接目标不存在：{target}",
                            "修正相对路径，或将历史兼容链接迁入明确白名单。",
                        )
                    )
    return issues


def git_diff_work_log(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "diff", "--unified=0", "--", "docs/03-engineering-governance/work-log.md"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return ""
    if result.returncode not in (0, 1):
        return ""
    return result.stdout


def check_work_log_append_only(root: Path) -> list[Issue]:
    path = root / "docs/03-engineering-governance/work-log.md"
    diff = git_diff_work_log(root)
    issues: list[Issue] = []
    added_task_ids: set[str] = set()
    for diff_line in diff.splitlines():
        if not diff_line.startswith("+|"):
            continue
        if "任务" in diff_line and "类型" in diff_line:
            continue
        added_task_ids.update(re.findall(r"\b(?:TD|DOC|BUG)-\d{3}\b", diff_line))

    for diff_line in diff.splitlines():
        if not diff_line.startswith("-|"):
            continue
        if "任务" in diff_line and "类型" in diff_line:
            continue
        removed_task_ids = set(re.findall(r"\b(?:TD|DOC|BUG)-\d{3}\b", diff_line))
        if removed_task_ids and removed_task_ids.isdisjoint(added_task_ids):
            issues.append(
                Issue(
                    path,
                    1,
                    "work-log-append-only",
                    "work-log.md 默认只新增索引，不应无说明删除或替换已有任务行。",
                    "恢复被删除的索引；若必须删除，在任务文档或提交说明中写清原因。",
                )
            )
    return issues
