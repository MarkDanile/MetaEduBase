"""``check_source_size_hard_limit``: flag source files over 1000 lines not registered in baseline.

This is a lightweight gate that only checks the hard limit (>1000 lines).  It
reuses the scanning logic from ``scripts.engineering.scan_source_sizes`` but
only emits issues for files that:

1. Exceed 1000 lines, AND
2. Are not already listed (with a "已拆分" or "🟢" status) in
   ``td-032-source-file-sizes.md``.

Files already tracked in the baseline with a resolution are allowed — the gate
only catches *new* large files that slipped in without being registered.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._common import Issue, read_lines

from ..scan_source_sizes import HARD_LIMIT, scan_source_files

# Pattern: | `path` | ... | — extracts backtick-quoted file path from table rows
_PATH_IN_TABLE_RE = re.compile(r"^\|\s*`([^`]+)`")

# Patterns indicating the file is already registered / resolved
_RESOLVED_MARKERS = ("🟢", "已拆分", "已合规")


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


def check_source_size_hard_limit(root: Path) -> list[Issue]:
    """Check that no source file exceeds 1000 lines without being registered."""
    sizes_md = root / "docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md"
    registered = _registered_large_files(sizes_md) if sizes_md.exists() else set()

    entries = scan_source_files(root)
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
