"""``check_source_size_hard_limit``: flag source files over 1000 lines not registered in baseline.

This is a lightweight gate that only checks the hard limit (>1000 lines).  It
defaults to checking changed files only so ``scripts/check-engineering-docs``
keeps fast local feedback.  Full scans remain available through the checker
``--full`` flag and the dedicated ``scripts/scan-source-sizes`` tool.

The check only emits issues for files that:

1. Exceed 1000 lines, AND
2. Are not already listed (with a "已拆分" or "🟢" status) in
   ``td-032-source-file-sizes.md``.

Files already tracked in the baseline with a resolution are allowed — the gate
only catches *new* large files that slipped in without being registered.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ._common import Issue, read_lines

from ..scan_source_sizes import (
    HARD_LIMIT,
    SCAN_DIRS,
    SOURCE_EXTENSIONS,
    FileInfo,
    scan_source_files,
)

# Pattern: | `path` | ... | — extracts backtick-quoted file path from table rows
_PATH_IN_TABLE_RE = re.compile(r"^\|\s*`([^`]+)`")

# Patterns indicating the file is already registered / resolved
_RESOLVED_MARKERS = ("🟢", "已拆分", "已合规")
_GIT_TIMEOUT_S = 5


def _registered_large_files(sizes_md: Path) -> set[str]:
    """Parse ``td-032-source-file-sizes.md`` and return file paths that are
    already registered as resolved (contain 🟢 / 已拆分 / 已合规).
    """
    lines = read_lines(sizes_md)
    registered: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        m = _PATH_IN_TABLE_RE.match(stripped)
        if not m:
            continue
        # Only count if the row has a resolution marker
        if any(marker in stripped for marker in _RESOLVED_MARKERS):
            registered.add(m.group(1))
    return registered


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


def _is_source_rel_path(rel_path: str) -> bool:
    path = Path(rel_path)
    if not path.parts:
        return False
    if path.parts[0] not in SCAN_DIRS:
        return False
    if any(part in {"node_modules", "dist", "__pycache__", ".git", ".venv", "uploads"} for part in path.parts):
        return False
    return path.suffix.lower() in SOURCE_EXTENSIONS


def _changed_source_paths(root: Path) -> list[Path] | None:
    """Return changed source files, or ``None`` when git is unavailable.

    The branch diff catches already-committed PR changes.  Staged, unstaged and
    untracked paths catch local pre-commit work.  If the root is not a git repo
    (as in some unit-test temp dirs), callers fall back to a full scan.
    """
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
        _git_lines(root, ["diff", "--name-only", "--diff-filter=ACMRT", "HEAD"]) or []
    )
    rel_paths.update(_git_lines(root, ["ls-files", "--others", "--exclude-standard"]) or [])

    paths: list[Path] = []
    for rel_path in sorted(rel_paths):
        if not _is_source_rel_path(rel_path):
            continue
        path = root / rel_path
        if path.is_file():
            paths.append(path)
    return paths


def _file_info(root: Path, path: Path) -> FileInfo | None:
    try:
        line_count = sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
        rel_path = path.relative_to(root).as_posix()
    except OSError:
        return None
    lang = SOURCE_EXTENSIONS.get(path.suffix.lower())
    if lang is None:
        return None
    return FileInfo(path=rel_path, lines=line_count, language=lang)


def _changed_source_file_infos(root: Path) -> list[FileInfo]:
    changed_paths = _changed_source_paths(root)
    if changed_paths is None:
        return scan_source_files(root)
    entries = [info for path in changed_paths if (info := _file_info(root, path))]
    entries.sort(key=lambda f: (-f.lines, f.path))
    return entries


def check_source_size_hard_limit(root: Path, *, full: bool = False) -> list[Issue]:
    """Check that no source file exceeds 1000 lines without being registered."""
    sizes_md = root / "docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md"
    registered = _registered_large_files(sizes_md) if sizes_md.exists() else set()

    entries = scan_source_files(root) if full else _changed_source_file_infos(root)
    issues: list[Issue] = []
    for f in entries:
        if f.lines <= HARD_LIMIT:
            continue
        if f.path in registered:
            continue
        issues.append(
            Issue(
                path=Path(f.path),
                line=0,
                code="source-size-over-limit",
                message=f"源码文件 {f.path} 有 {f.lines} 行（超过 {HARD_LIMIT} 行硬限制），但未在 td-032-source-file-sizes.md 登记",
                suggestion="在 td-032-source-file-sizes.md 登记例外/拆分计划，或拆分该文件到 500 行以下。",
            )
        )
    return issues
